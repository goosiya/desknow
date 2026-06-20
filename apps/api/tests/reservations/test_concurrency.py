"""reservations 동시성 불변식 — 결정적 직렬 단위 테스트 (Story 4.6 — AC1·AC2·AC5).

**always-on(매 게이트 실행·라이브 DB 불요)** 결정적 테스트로, ``create_reservation``의
**충돌 변환 메커니즘**을 증명한다: 슬롯 UNIQUE(``uq_reservation_slots_room_slot``) 위반으로
``IntegrityError``가 나면 ⓐ **전체 ROLLBACK**(부분 점유 0 — all-or-nothing)을 하고 ⓑ
``violated_constraint``로 그 제약을 식별해 **``DomainError(SLOT_CONFLICT)``(409)**로 선별
변환하며 ⓒ **무관한 제약 위반은 오변환하지 않고 그대로 re-raise**(P2 과대캐치 금지)한다.

**왜 SQLite가 아니라 가짜 ``IntegrityError`` 주입인가 (KTH FINAL 2026-06-17):**
스토리 범위결정 #2의 "SQLite·always-on"은 현 코드베이스에서 세 벽으로 불가하다 — ①
``reservations``가 ``users``·``rooms``로 FK를 가져 그 테이블 없이 ``create_all`` 불가, ②
FK 타깃 ``rooms.amenities``가 ``postgresql.JSONB``라 SQLite 스키마 생성 실패(게다가
``create_all``은 1.4 규약상 금지 — Alembic 단독 소유), ③ ``violated_constraint``가
psycopg3 ``exc.orig.diag.constraint_name`` 전용이라 SQLite ``IntegrityError``엔 ``diag``가
없어 변환이 일어나지 않는다. 그래서 **세션 ``commit``에 실제 와이어와 동형인 가짜
``IntegrityError``(``orig.diag.constraint_name`` 보유)를 주입**해 변환 경로를 결정적으로
탄다. **행 수준** all-or-nothing(부분 점유 0건 잔존)·겹치는 연속 구간·진짜 멀티스레드 동시성은
``tests/integration/test_reservations_concurrency.py``(Postgres skipif)가 실DB로 증명한다.

**등가성(범위결정 #1):** 4.1의 'plain 다중행 INSERT + UNIQUE 위반 → 전체 ROLLBACK(0건)'은
에픽 AC1의 ``ON CONFLICT 후 affected=N 검증, 아니면 ROLLBACK``을 **등가로(부분 커밋을
구조적으로 불가능하게 해 더 강하게)** 충족한다. 따라서 BE 프로덕션 코드 변경 0 — 테스트만 추가.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import DomainError, ErrorCode
from app.reservations.models import Reservation, ReservationStatus
from app.reservations.service import (
    cancel_reservation_for_booker,
    create_reservation,
    reject_reservation_for_provider,
)
from tests.reservations.test_service import _UpdateResult


class _FakeDiag:
    """psycopg3 진단 객체(``exc.orig.diag``) 흉내 — 위반 제약명만 보유한다."""

    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _FakeOrig(Exception):
    """psycopg ``IntegrityError``(``exc.orig``) 흉내 — ``diag.constraint_name`` 제공.

    ``violated_constraint``는 ``getattr(getattr(exc, "orig", None), "diag", None)`` →
    ``getattr(diag, "constraint_name", None)`` 체인으로 제약명을 읽으므로, 그 형태만 맞춘다.
    """

    def __init__(self, constraint_name: str | None) -> None:
        self.diag = _FakeDiag(constraint_name)
        super().__init__("fake psycopg IntegrityError")


def _integrity_error(constraint_name: str | None) -> IntegrityError:
    """주어진 제약명으로 위반된 SQLAlchemy ``IntegrityError``를 합성한다(실 와이어 동형)."""
    return IntegrityError(
        statement="INSERT INTO reservation_slots ...",
        params={},
        orig=_FakeOrig(constraint_name),
    )


class ConflictingSession:
    """``commit`` 시 지정 제약 위반 ``IntegrityError``를 던지는 Fake 세션.

    ``create_reservation``의 충돌 경로(rollback → ``violated_constraint`` → 선별 변환)를
    DB 없이 결정적으로 탄다. ``rollback`` 호출 여부를 기록해 **전체 ROLLBACK(0건)**을 단언한다.
    """

    def __init__(self, constraint_name: str | None) -> None:
        self._constraint_name = constraint_name
        self.added: list[Any] = []
        self.commit_count = 0
        self.refresh_count = 0
        self.rolled_back = False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.commit_count += 1
        raise _integrity_error(self._constraint_name)

    def rollback(self) -> None:
        self.rolled_back = True

    def refresh(self, obj: Any) -> None:  # pragma: no cover - 충돌 시 도달하지 않음
        self.refresh_count += 1


def _slot(hour: int) -> datetime:
    return datetime(2026, 7, 1, hour, tzinfo=UTC)


# ── AC1·AC5: 동일 슬롯 충돌 → SLOT_CONFLICT 변환 + 전체 ROLLBACK ──────────────
def test_slot_unique_violation_converts_to_slot_conflict_and_rolls_back() -> None:
    """슬롯 UNIQUE 위반 ``IntegrityError`` → ``DomainError(SLOT_CONFLICT)``(409) + 전체 ROLLBACK.

    "동일 슬롯에 다른 예약이 이미 점유" 상황을 commit 충돌로 결정적으로 재현한다(AC1). 변환된
    코드는 409이고, rollback이 호출돼 부분 점유가 0(전체 0건)임을 단언한다(all-or-nothing).
    """
    session = ConflictingSession("uq_reservation_slots_room_slot")

    with pytest.raises(DomainError) as exc_info:
        create_reservation(
            session,  # type: ignore[arg-type]
            booker_id=uuid.uuid4(),
            room_id=uuid.uuid4(),
            slot_starts=[_slot(9)],
        )

    assert exc_info.value.code is ErrorCode.SLOT_CONFLICT
    assert exc_info.value.status_code == 409
    assert session.rolled_back is True  # 전체 ROLLBACK(0건) — 부분 점유 없음
    assert session.refresh_count == 0  # 실패 경로 — refresh 도달 안 함


# ── AC2·AC5: 겹치는 연속 구간(다중 슬롯) 충돌도 동일하게 전체 ROLLBACK·SLOT_CONFLICT ──
def test_multi_slot_overlap_conflict_is_all_or_nothing_slot_conflict() -> None:
    """겹치는 연속 구간(다중 슬롯) 중 하나라도 충돌하면 전체 ROLLBACK → ``SLOT_CONFLICT``(AC2).

    예: A가 14·15·16을 점유한 상태에서 B가 16·17·18을 확정 시도 → 16 겹침으로 UNIQUE 위반 →
    **전체 ROLLBACK(B는 18시 빈 슬롯조차 점유 0건)**. 본 단위 테스트는 다중 슬롯 입력에서도
    변환·rollback이 동일함을 결정적으로 증명한다. **행 수준 '부분 점유 0건 잔존'**(A의 3행만)은
    ``tests/integration/test_reservations_concurrency.py``(Postgres)가 실DB로 단언한다.
    """
    session = ConflictingSession("uq_reservation_slots_room_slot")

    with pytest.raises(DomainError) as exc_info:
        create_reservation(
            session,  # type: ignore[arg-type]
            booker_id=uuid.uuid4(),
            room_id=uuid.uuid4(),
            slot_starts=[_slot(16), _slot(17), _slot(18)],
        )

    assert exc_info.value.code is ErrorCode.SLOT_CONFLICT
    assert session.rolled_back is True  # 전체 ROLLBACK = all-or-nothing(부분 커밋 구조적 불가)
    # 다중 슬롯 전부 add 시도됐으나(단일 트랜잭션 다중행 INSERT) commit 충돌로 전부 무효.
    # Reservation 1 + ReservationSlot 3 = 4행 add 후 commit 1회 시도 → IntegrityError.
    assert len(session.added) == 4
    assert session.commit_count == 1


# ── P2: 무관한 제약 위반은 오변환 금지(그대로 re-raise) ────────────────────────
@pytest.mark.parametrize(
    "constraint_name",
    [
        "fk_reservation_slots_room_id_rooms",  # FK 위반(미존재 룸) — SLOT_CONFLICT 아님
        None,  # 비-psycopg 드라이버/진단 부재 — 제약명을 못 얻음
    ],
)
def test_unrelated_integrity_error_is_reraised_not_slot_conflict(
    constraint_name: str | None,
) -> None:
    """슬롯 UNIQUE가 **아닌** 제약 위반은 ``SLOT_CONFLICT``로 둔갑시키지 않고 그대로 전파한다.

    ``violated_constraint``가 ``uq_reservation_slots_room_slot``을 식별하지 못하면(다른 제약명 또는
    ``None``) ``create_reservation``은 ``IntegrityError``를 re-raise한다 — 포괄 except로 무관 위반을
    409로 오변환하는 과대캐치(회고 P2)를 방지한다. rollback은 어느 경우든 수행한다(상태 누수 방지).
    """
    session = ConflictingSession(constraint_name)

    with pytest.raises(IntegrityError):
        create_reservation(
            session,  # type: ignore[arg-type]
            booker_id=uuid.uuid4(),
            room_id=uuid.uuid4(),
            slot_starts=[_slot(9), _slot(10)],
        )

    assert session.rolled_back is True  # 무관 위반도 전체 ROLLBACK(부분 점유 없음)


def test_slot_starts_span_is_preserved_in_insert_order() -> None:
    """입력 슬롯 전부가 단일 트랜잭션에 INSERT 시도된다(다중행 INSERT — 누락 없음).

    겹치는 구간이든 비연속이든, ``create_reservation``은 받은 슬롯 전부에 점유 행을 add한 뒤
    한 번에 commit한다(부분 커밋 경로 자체가 없음 — all-or-nothing의 전제).
    """
    # commit 충돌 없이 통과시키기 위해 제약명을 식별 불가로 두되, 충돌 자체를 안 내는 세션이
    # 필요하므로 별도 통과 세션을 쓴다.
    span = [datetime(2026, 7, 1, 9, tzinfo=UTC) + timedelta(hours=i) for i in range(3)]

    class _OkSession(ConflictingSession):
        def commit(self) -> None:  # 충돌 없이 성공
            self.commit_count += 1

    session = _OkSession(None)
    result = create_reservation(
        session,  # type: ignore[arg-type]
        booker_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        slot_starts=span,
    )

    assert result.status.value == "confirmed"
    # Reservation 1 + ReservationSlot 3 = 4행(슬롯 누락 0).
    assert len(session.added) == 4
    assert session.commit_count == 1
    assert session.rolled_back is False


# ── AC4·AC5: cancel↔reject 교차 race 결정화(조건부 원자 UPDATE — 회고 2c 회수) ──
#
# **설계가 결정적인 이유(범위 결정 #2·Dev Notes):** Story 6.2 전엔 ``_transition_to_terminal``이
# Python에서 read-then-flip해 booker 취소(4.7)·provider 거절(6.2)이 동시 진입하면 둘 다 stale
# ``confirmed``를 읽고 통과 → last-write-wins(통지·히스토리 비결정)였다. 6.2가 통지를 *생성*하면서
# 이 비결정성이 사용자-가시 결함이 되므로, **조건부 원자 UPDATE**(``WHERE status='confirmed'``)로
# DB 행 락이 단일 승자를 중재하게 했다: 첫 전이만 rowcount=1(승자=슬롯 DELETE+commit), 둘째는
# rowcount=0(패자=슬롯·통지 0·현재 상태 수렴). 아래는 그 결정성을 always-on으로 증명한다 — 실 SQL
# rowcount·진짜 멀티스레드는 tests/integration/test_reservations_concurrency.py(Postgres skipif)가.


class _SlotStore:
    """예약별 점유 슬롯 + 행 status를 보유하는 공유 가짜 DB(``exec``를 update/select/delete로 해석).

    조건부 UPDATE 중재를 행 수준으로 모사한다: ``status``가 행의 canonical 상태(조건부 UPDATE의
    ``WHERE status='confirmed'`` 판정 기준)이고, ``earliest_slot_start``의 SELECT는 점유 슬롯을,
    ``_release_slots``의 DELETE는 그 예약의 슬롯을 비운다. 두 '세션'이 같은 store를 공유해 실DB 한
    행을 두 트랜잭션이 경합하는 상황을 흉내낸다(첫 UPDATE가 status를 flip하면 둘째 UPDATE는 0행).
    """

    def __init__(self, reservation_id: uuid.UUID, slots: list[datetime]) -> None:
        self.slots: dict[uuid.UUID, list[datetime]] = {reservation_id: list(slots)}
        self.status: dict[uuid.UUID, ReservationStatus] = {
            reservation_id: ReservationStatus.CONFIRMED
        }
        self.delete_calls = 0


class _SharedCancelSession:
    """``_SlotStore`` 공유 + SELECT는 **자기 스냅샷**으로 읽는 가짜 세션(조건부 UPDATE race 모사).

    race의 핵심은 두 트랜잭션이 **각자 commit 전에 슬롯을 읽는다**는 점이다 — SELECT는 생성 시점에
    받은 ``read_snapshot``(둘 다 슬롯이 보임)으로 답한다. **조건부 UPDATE**는 공유 store.status를
    원자적으로 중재한다: 행이 아직 ``confirmed``면 target으로 flip(rowcount=1=승자), 아니면 변경 0
    (rowcount=0=패자). DELETE도 공유 store에 반영한다(패자는 DELETE에 도달하지 않음). ``refresh``는
    store의 canonical status를 ORM 객체에 동기화한다(승자 flip·패자 수렴 모두 반영).
    """

    def __init__(
        self,
        store: _SlotStore,
        reservation_id: uuid.UUID,
        read_snapshot: list[datetime],
    ) -> None:
        self._store = store
        self._rid = reservation_id
        self._read = list(read_snapshot)  # 이 트랜잭션이 commit 전에 본 점유 슬롯
        self.commit_count = 0
        self.rolled_back = False
        self.added: list[Any] = []

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        name = statement.__class__.__name__.lower()
        if name == "update":
            # 조건부 원자 UPDATE(WHERE status='confirmed') — 공유 store.status로 단일 승자 중재.
            params = statement.compile().params
            target = params["status"]
            where_id = next(
                v for k, v in params.items() if k != "status" and isinstance(v, uuid.UUID)
            )
            where_status = next(
                v
                for k, v in params.items()
                if k != "status" and isinstance(v, ReservationStatus)
            )
            if self._store.status.get(where_id) == where_status:
                self._store.status[where_id] = target  # 승자 — DB 행 flip
                return _UpdateResult(1)
            return _UpdateResult(0)  # 동시 전이가 선점 — 멱등 패자
        if name.startswith("delete"):
            self._store.delete_calls += 1
            self._store.slots[self._rid] = []
            return None
        return _SlotRowsResult(self._read)  # select(earliest_slot_start)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rolled_back = True

    def refresh(self, obj: Any) -> None:
        # Core UPDATE는 ORM 객체를 자동 동기화 안 함 → store canonical status를 객체에 반영
        # (승자 flip·패자 수렴 모두 — _transition_to_terminal이 양 경로에서 refresh 호출).
        rid = getattr(obj, "id", None)
        if rid in self._store.status:
            obj.status = self._store.status[rid]


class _SlotRowsResult:
    def __init__(self, rows: list[datetime]) -> None:
        self._rows = rows

    def all(self) -> list[datetime]:
        return list(self._rows)


def test_concurrent_cancel_reject_is_deterministic_first_wins() -> None:
    """동일 confirmed 예약에 취소·거절이 동시 진입하면 조건부 UPDATE가 단일 승자를 중재한다(AC4).

    cancel↔reject 교차 race(둘 다 commit 전 confirmed로 읽음)를 모사한다: 두 Reservation 인스턴스가
    같은 행을 보고(둘 다 confirmed), 같은 store를 공유한다. ① **첫 전이(취소)가 승자**(rowcount 1·
    슬롯 DELETE·commit·cancelled) ② **둘째(거절)는 패자**(rowcount 0·DELETE 0·rollback·refresh로
    cancelled 수렴) ③ 최종 상태는 **결정적**(첫-전이-승자 — last-write-wins 제거). 통지 결정은
    라우터가 ``updated.status``로 하므로 패자=cancelled면 "거절" 통지를 안 만든다(router 테스트).
    """
    rid = uuid.uuid4()
    booker_id = uuid.uuid4()
    room_id = uuid.uuid4()
    far_future = datetime(2099, 1, 5, 5, tzinfo=UTC)  # 시작 전 — 양쪽 게이트 통과
    store = _SlotStore(rid, [far_future])
    now = datetime(2026, 7, 1, 0, tzinfo=UTC)

    # 같은 행을 보는 두 인스턴스(둘 다 confirmed — race 전제: 둘 다 게이트 통과).
    instance_cancel = Reservation(
        id=rid, booker_id=booker_id, room_id=room_id, status=ReservationStatus.CONFIRMED
    )
    instance_reject = Reservation(
        id=rid, booker_id=booker_id, room_id=room_id, status=ReservationStatus.CONFIRMED
    )

    snapshot = [far_future]  # 둘 다 commit 전 같은 슬롯을 읽음(race 전제)
    cancel_session = _SharedCancelSession(store, rid, snapshot)
    reject_session = _SharedCancelSession(store, rid, snapshot)

    # 취소가 먼저 진입 → 승자.
    result_cancel = cancel_reservation_for_booker(
        cancel_session, instance_cancel, now=now  # type: ignore[arg-type]
    )
    # 거절이 이어 진입 → 패자(이미 cancelled로 flip된 행 — rowcount 0).
    result_reject = reject_reservation_for_provider(
        reject_session, instance_reject, now=now  # type: ignore[arg-type]
    )

    # ① 첫 전이(취소)가 승자 — cancelled·슬롯 DELETE·commit.
    assert result_cancel.status == ReservationStatus.CANCELLED
    assert cancel_session.commit_count == 1
    assert cancel_session.rolled_back is False
    # ② 둘째(거절)는 패자 — rowcount 0이라 슬롯·commit 0, rollback + refresh로 cancelled 수렴.
    assert result_reject.status == ReservationStatus.CANCELLED  # 결정적(첫-전이-승자)
    assert reject_session.commit_count == 0
    assert reject_session.rolled_back is True
    # ③ 슬롯은 승자만 비움(둘째는 DELETE 미도달) → store에 단 1회 DELETE.
    assert store.slots[rid] == []
    assert store.delete_calls == 1  # 승자만 DELETE — read-then-flip의 '둘째도 DELETE'와 대비


def test_sequential_cancel_second_is_strict_noop() -> None:
    """첫 취소가 commit된 뒤 도착한 둘째 취소는 종료상태 멱등 분기로 **쓰기 0**이다(AC3·AC5).

    동시 진입이 아닌 순차(둘째가 첫 commit 이후 도착) 경우, 둘째는 이미 cancelled를 읽어 시간
    검사·UPDATE·DELETE·commit 없이 즉시 반환한다(무해 no-op의 가장 강한 형태 — 쓰기 자체가 없음).
    """
    rid = uuid.uuid4()
    reservation = Reservation(
        id=rid,
        booker_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        status=ReservationStatus.CONFIRMED,
    )
    future = datetime(2099, 1, 5, 5, tzinfo=UTC)
    store = _SlotStore(rid, [future])
    now = datetime(2026, 7, 1, 0, tzinfo=UTC)

    session = _SharedCancelSession(store, rid, [future])
    cancel_reservation_for_booker(session, reservation, now=now)  # type: ignore[arg-type]
    assert reservation.status == ReservationStatus.CANCELLED
    assert session.commit_count == 1

    # 둘째 취소(같은 인스턴스, 이미 cancelled) → 즉시 멱등 반환(추가 쓰기 0).
    session2 = _SharedCancelSession(store, rid, [future])
    cancel_reservation_for_booker(session2, reservation, now=now)  # type: ignore[arg-type]
    assert session2.commit_count == 0
    assert store.delete_calls == 1  # 둘째는 DELETE조차 안 함(종료상태 즉시 반환)
