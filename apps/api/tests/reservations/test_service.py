"""reservations 서비스 단위 테스트 (Story 4.1 — AC2 멱등성 + 입력 계약).

DB 불필요 — **Fake 세션**으로 상태머신의 멱등성과 ``create_reservation``의 fail-fast
입력 계약을 실증한다(1.7 ``FakeSession`` 패턴 참고). 라이브 DB 왕복(UNIQUE·all-or-nothing·
재활성·CHECK)은 ``tests/integration/test_reservations_migration.py``(skipif 가드)가 담당한다.

**Fake 한계 인지:** Fake는 ``exec``의 쿼리를 해석하지 않는다(쓰기 호출 여부만 기록). 따라서
종료 상태 멱등 no-op의 **"DB 쓰기 0"**(commit/exec 미호출)을 단언하는 데 쓰고, 실제 슬롯
DELETE·재점유 성공은 통합 테스트가 검증한다.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core.errors import DomainError, ErrorCode
from app.core.time import now_utc
from app.notifications.models import Notification, NotificationType
from app.reservations.models import Reservation, ReservationStatus
from app.reservations.schemas import booker_display_label
from app.reservations.service import (
    admin_force_cancel_reservation,
    cancel_reservation,
    cancel_reservation_for_booker,
    confirmed_slot_starts_by_room,
    create_reservation,
    earliest_slot_start,
    list_booker_reservations,
    list_reservations_for_rooms,
    reject_reservation,
    reject_reservation_for_provider,
)


def _staged_notifications(session: Any) -> list[Notification]:
    """Fake 세션 ``added``에서 staged된 status_change 통지만 골라낸다(통지 원자화 단언용)."""
    return [obj for obj in session.added if isinstance(obj, Notification)]

# 6h 취소 윈도우 거부 시 노출되는 고정 한국어 카피(UX-DR10 — 정확 문자열 단언, UTF-8).
_CANCEL_COPY = "이제 6시간이 안 남아서 취소가 어려워요."
# 거절 시작-후 게이트 거부 시 노출되는 고정 한국어 카피(Story 6.2 — 정확 문자열 단언, UTF-8).
_REJECT_COPY = "이미 시작된 예약은 거절할 수 없어요."


# ── ★조건부 종료 전이 UPDATE Fake 모사(Story 6.2 — _transition_to_terminal 결정화) ──
#
# _transition_to_terminal이 read-then-flip 대신 조건부 원자 UPDATE(WHERE status='confirmed')를
# 쓰면서 ``session.exec(update(...))``가 ``CursorResult.rowcount``를 돌려준다. Fake 세션들이 이
# 와이어를 모사하도록 공유 헬퍼를 둔다(test_router·test_concurrency도 import). 실 DB 행 락 중재를
# in-memory로 재현: id 일치 + 현재 status가 WHERE(confirmed)와 같은 예약만 target으로 flip
# (rowcount=1=승자), 아니면 변경 0(rowcount=0=멱등 패자). 승자 flip은 commit+refresh의 net 효과를
# 여기서 반영한다(Fake refresh는 no-op). 진짜 rowcount 정확성(SQLite/PG)은 통합 테스트가 핀한다.


class _UpdateResult:
    """``session.exec(update(...))`` 결과 흉내 — 조건부 UPDATE의 ``rowcount``만 노출한다."""

    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


def _is_update(statement: Any) -> bool:
    """SQLAlchemy ``Update`` 구문인지 클래스명으로 판별한다(delete/select와 분기)."""
    return statement.__class__.__name__ == "Update"


def _apply_conditional_terminal_update(
    statement: Any, reservations: list[Reservation]
) -> _UpdateResult:
    """조건부 종료 전이 UPDATE를 in-memory 예약들에 적용한다(실 DB 행 락 중재 모사).

    파라미터 이름 순서(``id_1``/``status_1``)에 의존하지 않도록 값 타입으로 식별한다: SET 값은
    접미사 없는 ``status`` 키(target), WHERE는 접미사 키 중 UUID(=id)·ReservationStatus(=confirmed).
    매칭 행만 flip(승자=rowcount 1), 없으면 no-op(패자=rowcount 0).
    """
    params = statement.compile().params
    target = params["status"]  # SET 값(접미사 없음)
    where_id = next(
        v for k, v in params.items() if k != "status" and isinstance(v, uuid.UUID)
    )
    where_status = next(
        v
        for k, v in params.items()
        if k != "status" and isinstance(v, ReservationStatus)
    )
    for reservation in reservations:
        if reservation.id == where_id and reservation.status == where_status:
            reservation.status = target  # 승자 flip(commit+refresh net 효과)
            return _UpdateResult(1)
    return _UpdateResult(0)  # 동시 전이가 선점(또는 stale 종료) — 멱등 패자


class FakeSession:
    """Session 인터페이스(exec/add/commit/refresh/rollback)를 흉내내고 쓰기 호출을 기록한다.

    종료 상태 멱등 no-op은 어떤 세션 메서드도 호출하지 않아야 하므로, 호출 카운터로
    "DB 쓰기 0"을 단언한다. ``exec``는 쿼리를 해석하지 않는다(_release_slots의 DELETE는
    호출 사실만 기록 — 실제 삭제 효과는 통합 테스트가 검증).
    """

    def __init__(self, reservations: list[Reservation] | None = None) -> None:
        # 조건부 종료 전이 UPDATE가 flip할 대상 예약(없으면 self.added의 Reservation도 함께 스캔).
        self.reservations = reservations or []
        self.added: list[Any] = []
        self.exec_calls: list[Any] = []
        self.commit_count = 0
        self.refresh_count = 0
        self.rolled_back = False

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        self.exec_calls.append(statement)
        if _is_update(statement):
            # create_reservation 경로(self.added에 Reservation 적재)·직접 주입 모두 커버.
            candidates = self.reservations + [
                a for a in self.added if isinstance(a, Reservation)
            ]
            return _apply_conditional_terminal_update(statement, candidates)
        return None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, obj: Any) -> None:
        self.refresh_count += 1

    def rollback(self) -> None:
        self.rolled_back = True


def _reservation(status: ReservationStatus) -> Reservation:
    return Reservation(
        id=uuid.uuid4(),
        booker_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        status=status,
    )


# ── AC2 종료 상태 멱등 no-op(쓰기 0) ──────────────────────────────────────────
@pytest.mark.parametrize(
    "transition",
    [cancel_reservation, reject_reservation],
)
@pytest.mark.parametrize(
    "terminal_status",
    [ReservationStatus.CANCELLED, ReservationStatus.REJECTED],
)
def test_terminal_transition_is_idempotent_noop(
    transition: Any, terminal_status: ReservationStatus
) -> None:
    """이미 종료 상태인 예약에 취소/거절 재호출 → 현재 상태 그대로·DB 쓰기 0(AC2 멱등)."""
    reservation = _reservation(terminal_status)
    session = FakeSession()

    result = transition(session, reservation)

    assert result is reservation
    assert result.status == terminal_status  # 상태 불변(전이 무시)
    # 멱등 no-op = 세션에 아무 쓰기도 하지 않는다.
    assert session.commit_count == 0
    assert session.exec_calls == []  # _release_slots(DELETE) 미호출
    assert session.added == []
    assert session.refresh_count == 0


@pytest.mark.parametrize(
    "transition, expected_status",
    [
        (cancel_reservation, ReservationStatus.CANCELLED),
        (reject_reservation, ReservationStatus.REJECTED),
    ],
)
def test_transition_from_confirmed_writes_once(
    transition: Any, expected_status: ReservationStatus
) -> None:
    """confirmed → 종료 전이는 조건부 UPDATE(승자) + 슬롯 DELETE를 단일 commit으로 수행(AC3·AC4).

    Story 6.2: read-then-flip → 조건부 UPDATE(WHERE status='confirmed')로 결정화. 승자(rowcount=1)는
    UPDATE + ``_release_slots`` DELETE = exec 2회를 단일 트랜잭션으로 묶고 commit·refresh한다.
    in-memory flip(``session.add``) 대신 Core UPDATE라 ``session.added``엔 예약이 들지 않는다.
    """
    reservation = _reservation(ReservationStatus.CONFIRMED)
    session = FakeSession(reservations=[reservation])

    result = transition(session, reservation)

    assert result.status == expected_status  # 전이 적용(조건부 UPDATE 승자 → refresh net 효과)
    assert session.commit_count == 1  # 단일 트랜잭션 commit(원자)
    assert len(session.exec_calls) == 2  # 조건부 UPDATE 1 + _release_slots DELETE 1(동일 트랜잭션)
    assert session.rolled_back is False  # 승자 경로 — rollback 없음
    assert reservation not in session.added  # Core UPDATE라 in-memory add(read-then-flip) 없음


# ── 8.3 통지 원자화 + admin force-cancel(_transition_to_terminal notify_reason) ──
#
# 거절/임의취소 통지가 status flip + 슬롯 DELETE와 **동일 트랜잭션**(단일 commit)에 staged되는지를
# 단언한다. Fake는 add(Notification)을 기록하므로 staging 여부·필드·"winner만 통지"를 검증한다.
# 진짜 원자성(통지 실패 시 UPDATE/DELETE 롤백)은 단일 commit 구조 + 통지 실패가 commit 도달을
# 막는다는 사실로 보장되며, 아래 atomicity 테스트가 "commit 미도달"을 단언해 이를 핀한다.


def test_admin_force_cancel_confirmed_cancels_and_notifies_atomically() -> None:
    """ⓐ admin force-cancel(confirmed) → cancelled + 슬롯 DELETE + cancelled 통지 단일 commit."""
    reservation = _reservation(ReservationStatus.CONFIRMED)
    session = FakeSession(reservations=[reservation])

    result = admin_force_cancel_reservation(session, reservation)

    assert result.status == ReservationStatus.CANCELLED  # 전이 적용(조건부 UPDATE 승자)
    assert session.commit_count == 1  # 단일 트랜잭션(status flip + 슬롯 DELETE + 통지 INSERT 원자)
    assert len(session.exec_calls) == 2  # UPDATE 1 + _release_slots DELETE 1
    notes = _staged_notifications(session)
    assert len(notes) == 1  # 예약자에게 status_change 통지 1건 staged
    note = notes[0]
    assert note.user_id == reservation.booker_id  # 예약자에게(admin 아님)
    assert note.reservation_id == reservation.id
    assert note.type == str(NotificationType.STATUS_CHANGE)
    assert note.reason == "cancelled"  # 정확히 'cancelled'(FE 하드코딩 분기 키 — 오타 금지)


@pytest.mark.parametrize(
    "terminal_status",
    [ReservationStatus.CANCELLED, ReservationStatus.REJECTED],
)
def test_admin_force_cancel_terminal_is_idempotent_noop(
    terminal_status: ReservationStatus,
) -> None:
    """ⓑ 이미 종료 상태 force-cancel → status 불변·슬롯 변화 0·통지 0(winner 아님 — AC3)."""
    reservation = _reservation(terminal_status)
    session = FakeSession()

    result = admin_force_cancel_reservation(session, reservation)

    assert result is reservation
    assert result.status == terminal_status  # 상태 불변(멱등 no-op)
    assert session.commit_count == 0
    assert session.exec_calls == []  # 슬롯 DELETE 미호출
    assert _staged_notifications(session) == []  # 통지 0(전이 winner 아님)


class _RaiseOnNotificationSession(FakeSession):
    """통지 staging이 실패하는 Fake — ``add(Notification)``에서 raise해 commit 도달 전 중단을 모사.

    **원자성 단언의 핵심:** 통지 staging이 ``session.commit()`` *전*에 위치하므로, staging이
    실패하면 commit에 도달하지 못한다(``commit_count==0``). 실 DB에선 미commit UPDATE/DELETE가
    롤백되어 예약이 ``confirmed``로 남고 재시도가 전부 재수행된다 → 통지 영구 손실 불가(deferred L42
    회수). Fake는 ``exec(update)``를 즉시 in-memory flip하므로(통합 테스트가 실 rowcount 핀) 여기선
    **status가 아니라 commit 미도달**을 단언해 원자 구조를 검증한다(Fake 한계 — 상단 docstring).
    """

    def add(self, obj: Any) -> None:
        if isinstance(obj, Notification):
            raise RuntimeError("통지 staging 실패(주입) — 단일 commit 원자성 검증용")
        super().add(obj)


def test_force_cancel_notification_failure_aborts_commit() -> None:
    """ⓒ 통지 staging 실패 → commit 미도달(부분 영속 0 — retry-safe·deferred L42 회수)."""
    reservation = _reservation(ReservationStatus.CONFIRMED)
    session = _RaiseOnNotificationSession(reservations=[reservation])

    with pytest.raises(RuntimeError):
        admin_force_cancel_reservation(session, reservation)

    # 통지 staging이 commit 전에 실패 → commit 미도달(전이·슬롯 DELETE가 실 DB에서 롤백 = 원자).
    assert session.commit_count == 0


def test_booker_cancel_stays_notification_free() -> None:
    """ⓓ booker cancel(4.7)은 여전히 통지 0(notify_reason 미전달) + 전이·commit 보존(무회귀)."""
    reservation = _reservation(ReservationStatus.CONFIRMED)
    session = FakeSession(reservations=[reservation])

    result = cancel_reservation(session, reservation)

    assert result.status == ReservationStatus.CANCELLED
    assert session.commit_count == 1
    assert _staged_notifications(session) == []  # 본인 취소는 자기 통지 불요(통지 0 유지)


def test_provider_reject_notifies_atomically() -> None:
    """ⓔ reject(6.2)는 rejected + reason='rejected' 통지가 동일 트랜잭션에 staged(원자화 무회귀)."""
    reservation = _reservation(ReservationStatus.CONFIRMED)
    session = FakeSession(reservations=[reservation])

    result = reject_reservation(session, reservation)

    assert result.status == ReservationStatus.REJECTED
    assert session.commit_count == 1  # status flip + 슬롯 DELETE + 통지 INSERT 단일 commit
    notes = _staged_notifications(session)
    assert len(notes) == 1
    assert notes[0].type == str(NotificationType.STATUS_CHANGE)
    assert notes[0].reason == "rejected"  # 거절 통지 생성 보존(배선만 service로 이동·원자화)


def test_force_cancel_after_reject_is_idempotent_no_extra_notification() -> None:
    """ⓕ race 결정화 보존: 먼저 거절(winner·통지 1) → force-cancel은 멱등 no-op(추가 통지 0)."""
    reservation = _reservation(ReservationStatus.CONFIRMED)
    session = FakeSession(reservations=[reservation])

    reject_reservation(session, reservation)  # 첫 전이 승자 → rejected + reason='rejected' 통지
    assert len(_staged_notifications(session)) == 1

    # admin force-cancel은 이미 종료(rejected)라 fast-path 멱등 — 상태 불변·추가 통지/commit 0.
    result = admin_force_cancel_reservation(session, reservation)
    assert result.status == ReservationStatus.REJECTED  # 첫-전이-승자 유지(둔갑 안 함)
    assert session.commit_count == 1  # 거절 1회만(force-cancel은 commit 안 함)
    assert len(_staged_notifications(session)) == 1  # 추가 통지 0(winner 아님)


# ── create_reservation 입력 계약 fail-fast(라이브 DB 불필요) ──────────────────
def test_create_reservation_rejects_empty_slots() -> None:
    """빈 slot_starts → ValueError(점유할 슬롯이 최소 1개 필요)."""
    session = FakeSession()
    with pytest.raises(ValueError):
        create_reservation(
            session, booker_id=uuid.uuid4(), room_id=uuid.uuid4(), slot_starts=[]
        )
    assert session.added == []  # 삽입 시도 없음
    assert session.commit_count == 0


def test_create_reservation_rejects_naive_datetime() -> None:
    """naive datetime 슬롯 → ValueError(slot_start는 tz-aware UTC여야 함 — 차감 매칭 실패 방지)."""
    session = FakeSession()
    naive = datetime(2026, 6, 16, 9, 0, 0)  # tz 없음
    with pytest.raises(ValueError):
        create_reservation(
            session, booker_id=uuid.uuid4(), room_id=uuid.uuid4(), slot_starts=[naive]
        )
    assert session.added == []
    assert session.commit_count == 0


def test_create_reservation_rejects_duplicate_slots() -> None:
    """동일 호출 내 중복 slot_start → ValueError(자기충돌이 SLOT_CONFLICT로 오변환되는 것 방지)."""
    session = FakeSession()
    slot = now_utc()
    with pytest.raises(ValueError):
        create_reservation(
            session,
            booker_id=uuid.uuid4(),
            room_id=uuid.uuid4(),
            slot_starts=[slot, slot],  # 같은 슬롯 2개
        )
    assert session.added == []  # 삽입 시도 없음(commit 이전 fail-fast)
    assert session.commit_count == 0


def test_create_reservation_materializes_iterable_slots() -> None:
    """일회성 이터러블(제너레이터)이 와도 materialize 후 검사·INSERT 두 순회가 안전하다."""
    session = FakeSession()
    slots = (now_utc() + timedelta(hours=i) for i in range(2))  # 제너레이터(소진성)
    result = create_reservation(
        session, booker_id=uuid.uuid4(), room_id=uuid.uuid4(), slot_starts=slots
    )
    assert result.status == ReservationStatus.CONFIRMED
    # Reservation 1 + ReservationSlot 2 = 3행 add(제너레이터가 검사 루프에서 소진되지 않음).
    assert len(session.added) == 3
    assert session.commit_count == 1


def test_create_reservation_accepts_aware_then_attempts_commit() -> None:
    """aware UTC 슬롯은 입력 계약을 통과해 add + commit까지 진행한다(Fake는 충돌 없이 성공)."""
    session = FakeSession()
    slot = now_utc()
    result = create_reservation(
        session, booker_id=uuid.uuid4(), room_id=uuid.uuid4(), slot_starts=[slot]
    )
    assert result.status == ReservationStatus.CONFIRMED
    # Reservation 1 + ReservationSlot 1 = 2행 add(단일 트랜잭션 다중행 INSERT).
    assert len(session.added) == 2
    assert session.commit_count == 1


# ── 4.7 취소: earliest_slot_start + 6h 게이트 래퍼 ────────────────────────────


class FakeReadSession(FakeSession):
    """``exec(select).all()``로 점유 슬롯 행을 돌려주는 Fake 세션(4.7 취소 게이트용).

    ``FakeSession``을 확장해 ``exec``가 주입된 ``slot_rows``를 ``.all()``로 노출한다
    (``earliest_slot_start``의 ``select(...).all()`` 경로). ``_release_slots``의 DELETE도 같은
    ``exec``를 타지만 반환값을 무시하므로 무해하다. 쓰기 카운터(commit/exec/added)는 부모가 기록.
    """

    def __init__(
        self, slot_rows: list[Any], *, reservations: list[Reservation] | None = None
    ) -> None:
        super().__init__(reservations=reservations)
        self._slot_rows = slot_rows

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        self.exec_calls.append(statement)
        if _is_update(statement):
            candidates = self.reservations + [
                a for a in self.added if isinstance(a, Reservation)
            ]
            return _apply_conditional_terminal_update(statement, candidates)
        return _SlotRows(self._slot_rows)


class _SlotRows:
    """``session.exec(...)`` 결과 흉내 — ``.all()``로 슬롯 시작시각 리스트를 반환한다."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)


def test_earliest_slot_start_returns_minimum_of_multiple_slots() -> None:
    """다중 점유 슬롯에서 가장 이른 ``slot_start``(UTC aware)를 반환한다."""
    base = now_utc()
    rows = [base + timedelta(hours=2), base, base + timedelta(hours=1)]  # 무순서
    session = FakeReadSession(rows)
    assert earliest_slot_start(session, uuid.uuid4()) == base  # 최소값


def test_earliest_slot_start_returns_none_when_no_slots() -> None:
    """점유 슬롯이 0건(종료 상태 = 슬롯 DELETE됨)이면 ``None``을 반환한다."""
    session = FakeReadSession([])
    assert earliest_slot_start(session, uuid.uuid4()) is None


def _confirmed_with_now() -> tuple[Reservation, datetime]:
    return _reservation(ReservationStatus.CONFIRMED), datetime(2026, 7, 1, 0, tzinfo=UTC)


def test_cancel_at_exactly_6h_is_allowed() -> None:
    """경계: 정확히 6h 남은 시점(``earliest - now == 6h``)은 취소 **가능**(>= 경계 포함, AC1)."""
    reservation, now = _confirmed_with_now()
    session = FakeReadSession([now + timedelta(hours=6)], reservations=[reservation])
    result = cancel_reservation_for_booker(session, reservation, now=now)
    assert result.status == ReservationStatus.CANCELLED  # 전이 적용
    assert session.commit_count == 1  # 단일 트랜잭션 취소


def test_cancel_at_6h_minus_1s_is_blocked() -> None:
    """경계: 6h−1초(``< 6h``)는 409 ``CANCEL_WINDOW_PASSED``로 차단·상태 불변(AC1)."""
    reservation, now = _confirmed_with_now()
    session = FakeReadSession([now + timedelta(hours=6) - timedelta(seconds=1)])
    with pytest.raises(DomainError) as exc_info:
        cancel_reservation_for_booker(session, reservation, now=now)
    assert exc_info.value.code is ErrorCode.CANCEL_WINDOW_PASSED
    assert exc_info.value.status_code == 409
    assert exc_info.value.message == _CANCEL_COPY  # 고정 카피(UTF-8)
    assert reservation.status == ReservationStatus.CONFIRMED  # 상태 전이 0
    assert session.commit_count == 0  # 슬롯 변경 0


def test_cancel_at_6h_plus_1s_is_allowed() -> None:
    """경계: 6h+1초(``> 6h``)는 취소 **가능**(AC1)."""
    reservation, now = _confirmed_with_now()
    session = FakeReadSession(
        [now + timedelta(hours=6) + timedelta(seconds=1)], reservations=[reservation]
    )
    result = cancel_reservation_for_booker(session, reservation, now=now)
    assert result.status == ReservationStatus.CANCELLED
    assert session.commit_count == 1


def test_cancel_past_start_is_blocked() -> None:
    """이미 시작이 지난(``earliest < now``) 예약은 409로 차단된다(AC1)."""
    reservation, now = _confirmed_with_now()
    session = FakeReadSession([now - timedelta(hours=1)])  # 과거
    with pytest.raises(DomainError) as exc_info:
        cancel_reservation_for_booker(session, reservation, now=now)
    assert exc_info.value.code is ErrorCode.CANCEL_WINDOW_PASSED
    assert reservation.status == ReservationStatus.CONFIRMED


@pytest.mark.parametrize(
    "terminal_status",
    [ReservationStatus.CANCELLED, ReservationStatus.REJECTED],
)
def test_cancel_terminal_is_idempotent_noop_before_6h_check(
    terminal_status: ReservationStatus,
) -> None:
    """종료 상태(cancelled/rejected) 재취소 → 6h 검사 전 즉시 멱등 반환·DB 쓰기 0(AC3)."""
    reservation = _reservation(terminal_status)
    session = FakeReadSession([])  # 슬롯 0 — 호출되면 None이지만 호출 자체가 없어야 함
    now = datetime(2026, 7, 1, 0, tzinfo=UTC)

    result = cancel_reservation_for_booker(session, reservation, now=now)

    assert result is reservation
    assert result.status == terminal_status  # 상태 불변
    assert session.commit_count == 0
    assert session.exec_calls == []  # earliest 조회·6h 검사 진입 전 즉시 반환(분기 순서)
    assert session.added == []


def test_cancel_confirmed_with_zero_slots_is_defensively_blocked() -> None:
    """데이터 이상(confirmed인데 점유 슬롯 0) → 방어적 차단(조용히 취소하지 않음, fail-safe)."""
    reservation = _reservation(ReservationStatus.CONFIRMED)
    session = FakeReadSession([])  # earliest_slot_start → None
    now = datetime(2026, 7, 1, 0, tzinfo=UTC)
    with pytest.raises(DomainError) as exc_info:
        cancel_reservation_for_booker(session, reservation, now=now)
    assert exc_info.value.code is ErrorCode.CANCEL_WINDOW_PASSED
    assert reservation.status == ReservationStatus.CONFIRMED  # 상태 불변
    assert session.commit_count == 0


def test_cancel_rejects_naive_now() -> None:
    """주입된 ``now``가 naive면 ``ValueError``(시각 비교 오류 방지 — _require_aware)."""
    reservation = _reservation(ReservationStatus.CONFIRMED)
    session = FakeReadSession([now_utc() + timedelta(days=1)])
    with pytest.raises(ValueError):
        cancel_reservation_for_booker(
            session, reservation, now=datetime(2026, 7, 1, 0)  # tz 없음
        )


# ── 6.2 거절 게이팅 래퍼(reject_reservation_for_provider) ─────────────────────
def test_reject_before_start_succeeds() -> None:
    """시작 전(now < earliest) confirmed 예약 거절 → rejected 전이·단일 트랜잭션 commit(AC1)."""
    reservation, now = _confirmed_with_now()
    session = FakeReadSession([now + timedelta(hours=1)], reservations=[reservation])
    result = reject_reservation_for_provider(session, reservation, now=now)
    assert result.status == ReservationStatus.REJECTED  # 전이 적용(조건부 UPDATE 승자)
    assert session.commit_count == 1  # 단일 트랜잭션 거절(status flip + 슬롯 DELETE)


def test_reject_exactly_at_start_is_blocked() -> None:
    """경계: 정확히 시작 시각(earliest == now)은 거절 **불가**(시작 포함 — earliest <= now, AC3)."""
    reservation, now = _confirmed_with_now()
    session = FakeReadSession([now], reservations=[reservation])  # earliest == now
    with pytest.raises(DomainError) as exc_info:
        reject_reservation_for_provider(session, reservation, now=now)
    assert exc_info.value.code is ErrorCode.REJECT_WINDOW_PASSED
    assert exc_info.value.status_code == 409
    assert exc_info.value.message == _REJECT_COPY  # 고정 카피(UTF-8)
    assert reservation.status == ReservationStatus.CONFIRMED  # 상태 전이 0
    assert session.commit_count == 0  # 슬롯 변경 0


def test_reject_after_start_is_blocked() -> None:
    """이미 시작이 지난(earliest < now) 예약은 409 REJECT_WINDOW_PASSED로 차단된다(AC3)."""
    reservation, now = _confirmed_with_now()
    session = FakeReadSession([now - timedelta(hours=1)], reservations=[reservation])
    with pytest.raises(DomainError) as exc_info:
        reject_reservation_for_provider(session, reservation, now=now)
    assert exc_info.value.code is ErrorCode.REJECT_WINDOW_PASSED
    assert reservation.status == ReservationStatus.CONFIRMED
    assert session.commit_count == 0


@pytest.mark.parametrize(
    "terminal_status",
    [ReservationStatus.CANCELLED, ReservationStatus.REJECTED],
)
def test_reject_terminal_is_idempotent_noop_before_time_check(
    terminal_status: ReservationStatus,
) -> None:
    """종료 상태(cancelled/rejected) 재거절 → 시간 검사 전 즉시 멱등 반환·DB 쓰기 0(AC2·AC3).

    예: booker가 먼저 취소(cancelled)했으면 거절은 멱등 no-op으로 현재 상태를 돌려준다(통지 0).
    """
    reservation = _reservation(terminal_status)
    session = FakeReadSession([])  # 슬롯 0 — 호출되면 안 됨(즉시 반환)
    now = datetime(2026, 7, 1, 0, tzinfo=UTC)

    result = reject_reservation_for_provider(session, reservation, now=now)

    assert result is reservation
    assert result.status == terminal_status  # 상태 불변
    assert session.commit_count == 0
    assert session.exec_calls == []  # earliest 조회·시간 검사 진입 전 즉시 반환(분기 순서)


def test_reject_confirmed_with_zero_slots_is_defensively_blocked() -> None:
    """데이터 이상(confirmed인데 점유 슬롯 0) → 방어적 차단(조용히 거절 안 함, fail-safe)."""
    reservation = _reservation(ReservationStatus.CONFIRMED)
    session = FakeReadSession([], reservations=[reservation])  # earliest → None
    now = datetime(2026, 7, 1, 0, tzinfo=UTC)
    with pytest.raises(DomainError) as exc_info:
        reject_reservation_for_provider(session, reservation, now=now)
    assert exc_info.value.code is ErrorCode.REJECT_WINDOW_PASSED
    assert reservation.status == ReservationStatus.CONFIRMED  # 상태 불변
    assert session.commit_count == 0


def test_reject_rejects_naive_now() -> None:
    """주입된 now가 naive면 ValueError(시각 비교 오류 방지 — _require_aware)."""
    reservation = _reservation(ReservationStatus.CONFIRMED)
    session = FakeReadSession([now_utc() + timedelta(days=1)], reservations=[reservation])
    with pytest.raises(ValueError):
        reject_reservation_for_provider(
            session, reservation, now=datetime(2026, 7, 1, 0)  # tz 없음
        )


# ── 6.2 ★cancel↔reject 교차 race 결정화(조건부 원자 UPDATE — 회고 2c 회수) ──────
@pytest.mark.parametrize(
    "first, second, expected_status",
    [
        # 거절이 먼저 승자 → 이후 취소는 rowcount 0 멱등(상태 rejected 유지).
        (reject_reservation, cancel_reservation, ReservationStatus.REJECTED),
        # 취소가 먼저 승자 → 이후 거절은 rowcount 0 멱등(상태 cancelled 유지).
        (cancel_reservation, reject_reservation, ReservationStatus.CANCELLED),
    ],
)
def test_cross_transition_second_is_idempotent_noop(
    first: Any, second: Any, expected_status: ReservationStatus
) -> None:
    """동일 confirmed 예약에 거절·취소를 순차 호출하면 첫 전이가 승자, 둘째는 멱등 no-op(AC4).

    조건부 원자 UPDATE(WHERE status='confirmed') 결정화: 첫 전이만 status flip(rowcount 1·슬롯
    DELETE·commit), 둘째는 이미 종료 상태라 fast-path 멱등 반환(쓰기 0). 최종 상태는 첫-전이-승자로
    결정적이다(last-write-wins 비결정성 제거). 실 SQL rowcount는 통합 테스트가 핀한다.
    """
    reservation = _reservation(ReservationStatus.CONFIRMED)
    session = FakeSession(reservations=[reservation])

    first_result = first(session, reservation)
    assert first_result.status == expected_status  # 첫 전이가 승자(결정)
    assert session.commit_count == 1  # 첫 전이만 commit
    exec_after_first = len(session.exec_calls)  # UPDATE 1 + DELETE 1 = 2

    # 둘째 전이 — 이미 종료 상태라 fast-path 멱등(추가 쓰기·exec 0).
    second_result = second(session, reservation)
    assert second_result.status == expected_status  # 상태 불변(첫-전이-승자 유지)
    assert session.commit_count == 1  # 둘째는 commit 안 함
    assert len(session.exec_calls) == exec_after_first  # 둘째는 exec(UPDATE) 진입 0(fast-path)


# ── 4.8 슬롯 시간 스냅샷(표시 전용 히스토리) ──────────────────────────────────
def test_create_reservation_records_slot_starts_snapshot() -> None:
    """create_reservation이 점유 슬롯 시작시각을 오름차순 ISO ...Z 스냅샷으로 기록한다(AC1)."""
    session = FakeSession()
    base = datetime(2026, 6, 20, 5, 0, tzinfo=UTC)
    # 무순서 입력(15시, 14시) — 스냅샷은 오름차순 정렬되어야 한다.
    slots = [base + timedelta(hours=1), base]
    result = create_reservation(
        session, booker_id=uuid.uuid4(), room_id=uuid.uuid4(), slot_starts=slots
    )
    # 오름차순 ...Z 문자열(사전식=시간순) — [0]이 곧 earliest(FE 6h 취소 계산 기준).
    assert result.slot_starts == [
        "2026-06-20T05:00:00Z",
        "2026-06-20T06:00:00Z",
    ]
    assert all(s.endswith("Z") for s in result.slot_starts)


def test_snapshot_survives_cancel_transition() -> None:
    """취소 전이는 slot_starts 스냅샷을 건드리지 않는다(immutable 히스토리 — 점유 행은 DELETE)."""
    session = FakeSession()
    slot = datetime(2026, 6, 20, 5, 0, tzinfo=UTC)
    reservation = create_reservation(
        session, booker_id=uuid.uuid4(), room_id=uuid.uuid4(), slot_starts=[slot]
    )
    snapshot_before = list(reservation.slot_starts)
    assert snapshot_before == ["2026-06-20T05:00:00Z"]

    # 취소(status flip + 슬롯 DELETE) 후에도 스냅샷은 잔존(예약현황 히스토리 표시용).
    cancelled = cancel_reservation(session, reservation)
    assert cancelled.status == ReservationStatus.CANCELLED
    assert cancelled.slot_starts == snapshot_before  # 스냅샷 불변


# ── 4.8 본인 예약 목록 서비스(읽기 전용) ──────────────────────────────────────
def test_list_booker_reservations_is_read_only() -> None:
    """list_booker_reservations는 exec 결과를 그대로 반환하고 쓰기를 하지 않는다(읽기 전용, AC4)."""
    booker_id = uuid.uuid4()
    stored = [
        _reservation(ReservationStatus.CONFIRMED),
        _reservation(ReservationStatus.CANCELLED),
    ]
    session = FakeReadSession(stored)  # exec(select).all() → stored

    result = list_booker_reservations(session, booker_id)

    assert result == stored  # flat 목록 그대로(WHERE/ORDER BY는 SQL — 통합 테스트가 검증)
    # 읽기 전용 — 쓰기 메서드 호출 0(commit/add/refresh/rollback).
    assert session.commit_count == 0
    assert session.added == []
    assert session.refresh_count == 0
    assert len(session.exec_calls) == 1  # select 1회


# ── 4.9 벌크 차감 reader(confirmed_slot_starts_by_room) ────────────────────────
def test_confirmed_slot_starts_by_room_groups_by_room() -> None:
    """벌크 reader가 (room_id, slot_start) 행을 룸별 집합으로 정확히 분리한다(룸 격리, AC1)."""
    room_a, room_b = uuid.uuid4(), uuid.uuid4()
    base = datetime(2026, 6, 20, 5, 0, tzinfo=UTC)
    slot_a1 = base
    slot_a2 = base + timedelta(hours=1)
    slot_b1 = base + timedelta(hours=2)
    # exec(...).all()은 (room_id, slot_start) 튜플 행을 낸다(select 2-컬럼). 무순서·룸 혼재.
    rows = [(room_a, slot_a1), (room_b, slot_b1), (room_a, slot_a2)]
    session = FakeReadSession(rows)

    result = confirmed_slot_starts_by_room(session, [room_a, room_b])

    # 각 룸이 자기 슬롯만 갖는다(타 룸 슬롯이 안 섞임 — 그룹핑 정확).
    assert result == {room_a: {slot_a1, slot_a2}, room_b: {slot_b1}}
    assert len(session.exec_calls) == 1  # IN (...) 1회 — N+1 회피
    # 읽기 전용 — 쓰기 0.
    assert session.commit_count == 0
    assert session.added == []


def test_confirmed_slot_starts_by_room_empty_input_skips_query() -> None:
    """빈 room_ids → {} 이고 쿼리를 발행하지 않는다(불필요한 IN () 회피)."""
    session = FakeReadSession([])

    assert confirmed_slot_starts_by_room(session, []) == {}
    assert session.exec_calls == []  # exec 미호출


def test_confirmed_slot_starts_by_room_materializes_generator() -> None:
    """제너레이터 room_ids도 안전 — 빈 판정·IN 절 재사용 위해 먼저 materialize한다."""
    room_a = uuid.uuid4()
    slot = datetime(2026, 6, 20, 5, 0, tzinfo=UTC)
    session = FakeReadSession([(room_a, slot)])

    result = confirmed_slot_starts_by_room(session, (rid for rid in [room_a]))

    assert result == {room_a: {slot}}


def test_confirmed_slot_starts_by_room_rejects_naive_on_or_after() -> None:
    """naive on_or_after → ValueError(차감 매칭 실패 방지 — 단건 reader와 동일 fail-fast)."""
    session = FakeReadSession([])
    with pytest.raises(ValueError, match="tz-aware"):
        confirmed_slot_starts_by_room(
            session, [uuid.uuid4()], on_or_after=datetime(2026, 6, 20, 5, 0)  # naive
        )
    assert session.exec_calls == []  # 가드가 쿼리 전에 차단


# ── 6.1 제공자 룸 단위 예약 목록 서비스(읽기 전용·거울상) ──────────────────────
def test_list_reservations_for_rooms_is_read_only() -> None:
    """list_reservations_for_rooms는 exec 결과를 그대로 반환하고 쓰기를 하지 않는다(읽기 전용)."""
    stored = [
        _reservation(ReservationStatus.CONFIRMED),
        _reservation(ReservationStatus.CANCELLED),
        _reservation(ReservationStatus.REJECTED),  # 상태 무관(히스토리) — 전부 반환
    ]
    session = FakeReadSession(stored)  # exec(select).all() → stored

    result = list_reservations_for_rooms(session, [uuid.uuid4(), uuid.uuid4()])

    assert result == stored  # flat 목록 그대로(WHERE IN/ORDER BY는 SQL — 통합 테스트가 검증)
    # 읽기 전용 — 쓰기 메서드 호출 0(commit/add/refresh/rollback).
    assert session.commit_count == 0
    assert session.added == []
    assert session.refresh_count == 0
    assert len(session.exec_calls) == 1  # select 1회(IN 벌크 — N+1 회피)


def test_list_reservations_for_rooms_empty_input_skips_query() -> None:
    """빈 room_ids → [] 이고 쿼리를 발행하지 않는다(제공자 룸 0개 안전 — 불필요한 IN () 회피)."""
    session = FakeReadSession([])

    assert list_reservations_for_rooms(session, []) == []
    assert session.exec_calls == []  # exec 미호출(빈 입력 가드)


def test_list_reservations_for_rooms_materializes_generator() -> None:
    """제너레이터 room_ids도 안전 — 빈 판정·IN 절 재사용 위해 먼저 materialize한다."""
    stored = [_reservation(ReservationStatus.CONFIRMED)]
    session = FakeReadSession(stored)

    result = list_reservations_for_rooms(session, (rid for rid in [uuid.uuid4()]))

    assert result == stored
    assert len(session.exec_calls) == 1


# ── 6.1 예약자 익명 라벨 파생(순수 함수 — 프라이버시) ──────────────────────────
def test_booker_display_label_is_deterministic_and_prefixed() -> None:
    """같은 booker_id → 항상 같은 라벨·"예약자 #" 접두·6자 hex(결정적·집계 가능, AC2)."""
    booker_id = uuid.uuid4()

    label = booker_display_label(booker_id)

    assert label == booker_display_label(booker_id)  # 결정적(같은 id=같은 라벨)
    assert label.startswith("예약자 #")
    suffix = label.removeprefix("예약자 #")
    assert len(suffix) == 6
    assert all(c in "0123456789abcdef" for c in suffix)  # 6자 hex


def test_booker_display_label_differs_by_booker() -> None:
    """다른 booker_id → 다른 라벨(제공자가 예약자 구분 가능 — "표시 이름" 문구 충족)."""
    assert booker_display_label(uuid.uuid4()) != booker_display_label(uuid.uuid4())


def test_booker_display_label_does_not_leak_raw_uuid() -> None:
    """라벨은 raw UUID 어떤 부분도 노출하지 않는다(sha256 파생 — prefix 자르기 아님, AC2).

    고정 UUID로 알고리즘을 핀한다(``sha256(str(id))[:6]``). prefix 자르기였다면 라벨에
    ``"550e84"``(str(id)[:6])가 들어갔겠지만, 해시 파생이라 무관한 hex가 나온다 — 비결정 uuid4
    충돌(1/16M) 없이 누출 부재를 결정적으로 단언한다.
    """
    import hashlib

    booker_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
    expected = "예약자 #" + hashlib.sha256(str(booker_id).encode()).hexdigest()[:6]

    label = booker_display_label(booker_id)

    assert label == expected  # 알고리즘 핀(sha256 파생)
    assert str(booker_id) not in label  # raw UUID 전체 미노출
    assert str(booker_id)[:6] not in label  # prefix 자르기 누출 부재(해시라 무관 hex)
