"""reservations 도메인 서비스: 예약 생성·취소·거절 + 점유 재활성 + 차감 seam (Story 4.1).

이 모듈은 예약 핵심의 **데이터 계층 프리미티브 전부**를 소유한다(라우터/엔드포인트/UI는
범위 밖 — 4.5 즉시예약·4.7 취소·4.8 현황이 소비). Story 2.1의 ``rooms.service``와 동형으로,
도메인 로직(원자 삽입·제약명 선별 변환·멱등 상태 전이·동일 트랜잭션 재활성)만 진다.

**상태머신(단일 출처 — architecture.md "상태 전이는 서버 단일 연산"):**

- 시작 상태 = ``confirmed``(즉시예약 = 결제 없음, 생성 즉시 확정 — FR-15).
- 허용 전이: ``confirmed → cancelled``(예약자 취소, 4.7) · ``confirmed → rejected``(제공자 거절,
  E6/6.2). 그 외 전이는 정의하지 않는다.
- **종료 상태**(``cancelled``·``rejected`` = ``models._TERMINAL_STATUSES``)에서의 추가 전이는
  **멱등하게 무시**한다 — DB 쓰기 0, 현재 상태 그대로 반환(에러 아님, AC2).

**동시성·점유 불변식(FR-15·NFR-7):**

- 점유는 ``reservation_slots`` 행으로 표현되고, 진실의 원천은 ``uq_reservation_slots_room_slot``
  (한 룸·한 슬롯에 활성 점유 최대 1행). 생성은 ``Reservation`` + N개 ``ReservationSlot``을
  **단일 트랜잭션 다중행 INSERT**로 넣어, 어느 슬롯이라도 충돌하면 **전체 ROLLBACK → 0건**
  (부분 점유 없음 — all-or-nothing). 충돌은 ``SLOT_CONFLICT``(409)로 변환한다.
- 취소/거절은 ``reservations.status`` flip(히스토리 잔존) + ``reservation_slots`` 행 DELETE
  (슬롯 재활성)를 **동일 트랜잭션**에서 수행한다(AC3). 슬롯이 비워져 같은 슬롯이 재점유 가능해진다.

본 스토리(4.1)는 **순차 UNIQUE 왕복**(중복 INSERT→``IntegrityError``)으로 불변식의 메커니즘을
증명한다. 진정한 멀티스레드 동시 검증(SM-4)·409 마이크로카피는 **Story 4.6** 소유다.
6h 취소 윈도우(``is_within_hours``)는 **4.7**, ``confirmed_slot_starts`` → ``derive_slots`` 차감
배선은 **4.9**가 소유한다(본 스토리는 함수 정의·테스트까지).

**도메인 경계(architecture.md L354-355):** 이 모듈은 ``reservations``·``reservation_slots``만
만진다. ``rooms``를 import하지 않는다(4.9가 역방향으로 ``rooms.service``에서
``confirmed_slot_starts``를 호출해 차감을 연결한다 — 챗봇 예약검색 E7도 이 service 경유).
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, delete, select, update

from app.core.db import violated_constraint
from app.core.errors import DomainError, ErrorCode
from app.core.pagination import keyset_page, keyset_predicate
from app.core.time import isoformat_utc, now_utc
from app.notifications import service as notifications_service
from app.reservations.models import (
    _TERMINAL_STATUSES,
    Reservation,
    ReservationSlot,
    ReservationStatus,
)

# 생성 시 충돌하면 SLOT_CONFLICT로 변환할 제약명(다른 위반은 re-raise — P2 과대캐치 금지).
_SLOT_UNIQUE_CONSTRAINT = "uq_reservation_slots_room_slot"

# 취소 가능 윈도우(FR-16, Story 4.7). 취소 가능 = ``earliest_slot_start - now >= 6시간``
# (정확히 6h 남은 시점 포함), 차단 = ``< 6시간``. 부동소수 ``hours_until`` 대신 ``timedelta``
# 정수 비교를 써 6.0h 경계의 1µs 모호성(deferred L91)을 제거한다.
_CANCEL_WINDOW = timedelta(hours=6)


def _require_aware(dt: datetime, label: str) -> None:
    """tz-aware datetime인지 검증한다(naive 거부 — core/time ``_require_aware`` 철학).

    예약 ``slot_start``는 UTC로 저장·전달되며, naive datetime을 받으면 ``derive_slots``가 내는
    aware UTC 슬롯과 결코 같지 않아(차감/매칭 실패) 이미 점유된 슬롯이 "가용"으로 새거나
    잘못된 슬롯을 점유한다 → 경계에서 즉시 차단한다(조용한 실패 방지). ``derive_slots``의
    ``reserved_starts`` naive 거부와 동일 철학(private ``core.time._require_aware`` 미import =
    derive_slots 선례 따라 인라인 검사).
    """
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(
            f"{label}은(는) tz-aware여야 합니다 (naive datetime 금지) — "
            "예약 slot_start는 UTC로 저장·전달됩니다."
        )


def create_reservation(
    session: Session,
    *,
    booker_id: uuid.UUID,
    room_id: uuid.UUID,
    slot_starts: Iterable[datetime],
) -> Reservation:
    """확정 예약 1건 + 그 슬롯 점유 행들을 **단일 트랜잭션 all-or-nothing**으로 생성한다(AC2·AC3).

    Args:
        session: DB 세션.
        booker_id: 예약자(``users.id``).
        room_id: 예약 대상 룸(``rooms.id``). 모든 슬롯 점유 행이 이 룸에 귀속된다.
        slot_starts: 점유할 슬롯 시작시각들(UTC aware). 연속/비연속 무관(연속 선택 규칙은 4.4 UI).

    Returns:
        생성된 ``Reservation``(``status='confirmed'``, ``refresh`` 완료).

    Raises:
        ValueError: ``slot_starts``가 비었거나 항목이 naive datetime일 때(입력 계약 fail-fast —
            라이브 DB 불필요 경로). ``derive_slots``의 fail-fast 철학과 일관.
        DomainError: 어느 슬롯이라도 이미 점유돼 ``uq_reservation_slots_room_slot``이 위반되면
            409 ``SLOT_CONFLICT``. **이때 전체 ROLLBACK으로 0건**(부분 점유 없음 — AC3).
            무관한 제약 위반(FK 등)은 오변환하지 않고 그대로 re-raise한다(P2 과대캐치 금지).
    """
    # ⓐ 입력 계약 fail-fast(조용한 무시 금지 — derive_slots 선례).
    # 일회성 이터러블(제너레이터)이 와도 검사·INSERT 두 순회가 안전하도록 먼저 materialize한다
    # (검사 루프가 소진시켜 슬롯 0개짜리 예약이 조용히 commit되는 footgun 차단).
    slot_starts = tuple(slot_starts)
    if not slot_starts:
        raise ValueError("slot_starts는 비어 있을 수 없습니다 (점유할 슬롯이 최소 1개 필요).")
    for slot_start in slot_starts:
        _require_aware(slot_start, "slot_start")
    # 동일 호출 내 중복 슬롯은 입력 계약 위반으로 거부한다. 그대로 두면 같은 (room_id, slot_start)
    # 두 행이 uq_reservation_slots_room_slot을 위반해 신규 예약인데도 SLOT_CONFLICT(409 "이미
    # 예약됨")로 오변환된다 — SLOT_CONFLICT는 **타 예약과의 충돌** 전용 신호이므로, "내 입력이
    # 중복"은 빈 입력·naive datetime과 동일하게 ValueError로 분리해 fail-fast 한다.
    if len(set(slot_starts)) != len(slot_starts):
        raise ValueError("slot_starts에 중복된 슬롯이 있습니다 (각 슬롯은 한 번만 점유 가능).")

    # ⓑ 예약 단위 + 슬롯 점유 행을 단일 트랜잭션에 add(다중행 INSERT).
    # 슬롯 시작시각 스냅샷(표시 전용 immutable 히스토리, 4.8 — models.Reservation.slot_starts
    # 주석)을 **생성 시 1회만** 오름차순 ISO ...Z로 기록한다. 취소/거절 전이는 이 컬럼을 건드리지
    # 않아(슬롯 점유 행은 DELETE돼도) 종료 상태 예약의 날짜·시간이 잔존한다(히스토리 보존).
    # UTC ...Z는 사전식=시간순이라 정렬된 리스트의 [0]이 곧 earliest(FE 6h 취소 계산 기준).
    reservation = Reservation(
        booker_id=booker_id,
        room_id=room_id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=sorted(isoformat_utc(slot_start) for slot_start in slot_starts),
    )
    session.add(reservation)
    # reservation.id는 default_factory=uuid4라 commit 전 이미 존재 → FK 연결 가능(단일 트랜잭션).
    for slot_start in slot_starts:
        session.add(
            ReservationSlot(
                reservation_id=reservation.id, room_id=room_id, slot_start=slot_start
            )
        )

    # ⓒ all-or-nothing: 한 슬롯이라도 충돌하면 전체 ROLLBACK(0건) 후 선별 변환.
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()  # 전체 0건 — 부분 점유 없음(AC3)
        if violated_constraint(exc) == _SLOT_UNIQUE_CONSTRAINT:
            raise DomainError(
                ErrorCode.SLOT_CONFLICT,
                "선택한 시간 중 이미 예약된 슬롯이 있습니다.",
            ) from exc  # 409
        raise  # 무관한 제약 위반은 오변환 금지 — 그대로 전파(P2)
    session.refresh(reservation)
    return reservation


def _release_slots(session: Session, reservation_id: uuid.UUID) -> None:
    """예약의 점유 행을 모두 제거한다(재활성 = 슬롯이 다시 빔). **commit은 호출처가** 한다.

    상태 전이(취소/거절)와 **동일 트랜잭션**에서 슬롯을 비우기 위해 commit을 호출처에 위임한다
    (``update_room``의 영업시간 교체 선례 — 원자성 유지). DELETE 후 ``reservation_slots``엔 그
    예약의 점유 행이 0개가 되고, 같은 ``(room_id, slot_start)``를 다른 예약이 재점유할 수 있다.
    """
    session.exec(
        delete(ReservationSlot).where(
            col(ReservationSlot.reservation_id) == reservation_id
        )
    )


def _transition_to_terminal(
    session: Session,
    reservation: Reservation,
    target: ReservationStatus,
    *,
    notify_reason: str | None = None,
) -> Reservation:
    """예약을 종료 상태(``cancelled``/``rejected``)로 전이한다(멱등·결정적·동일 트랜잭션 재활성).

    **★cancel↔reject 교차 race 결정화(epic-5 회고 2c 의무 회수 — Story 6.2):** 과거엔
    Python에서 ``reservation.status``를 읽고 flip(read-then-flip)했는데, booker 취소(4.7)와
    provider 거절(6.2)이 같은 ``confirmed`` 예약에 동시 진입하면 둘 다 stale ``confirmed``를 읽고
    통과해 **last-write-wins**(최종 status·통지가 비결정)가 됐다. 6.2가 통지를 *생성*하면서 이
    비결정성이 "거절 안 했는데 거절 통지" 같은 사용자-가시 결함이 되므로, **조건부 원자 UPDATE**
    (``UPDATE ... WHERE status='confirmed'``)로 바꿔 **DB 행 락이 단일 승자를 중재**하게 한다:

    - **종료 상태 fast-path**(``status in _TERMINAL_STATUSES``) → **멱등 no-op**(DB 왕복 0, 현재
      상태 그대로 반환 — 불변). 종료 상태는 시간 판정 불가(슬롯 0건)이므로 게이트 *전*에 분기한다.
    - **조건부 UPDATE**: ``rowcount == 1``이면 **이 전이가 승자** → ``_release_slots``(동일 트랜잭션
      DELETE=슬롯 재활성) + commit + ``refresh``(Core UPDATE는 identity-map 객체를 자동 동기화하지
      않으므로 refresh 필수). ``rowcount == 0``이면 **동시 전이가 선점**(또는 stale 종료 상태) →
      슬롯·통지 없이 ``rollback``(no-op UPDATE 정리) + ``refresh``로 현재 DB 상태에 수렴(멱등 패자).

    이로써 cancel↔reject는 **상호 배타·첫-전이-승자**로 결정화된다. cancel/reject **공유**
    프리미티브라 cancel(4.7)도 함께 결정화되나 동작 불변(무회귀): cancel-vs-cancel(첫째 승자·
    둘째 rowcount 0 멱등)·단일 cancel(rowcount 1=기존과 동일)·종료 fast-path(불변) 전부 보존한다.

    ``rowcount``는 ``_release_slots``의 ``session.exec(delete(...))``와 동형으로
    ``CursorResult.rowcount``를 읽는다(``synchronize_session`` 기본 동작의 SQLite/PG rowcount
    정확성은 통합 테스트가 핀한다).

    **★통지 원자 편입(Story 8.3 — deferred L42 회수):** ``notify_reason``이 주어지면(거절=
    ``'rejected'``·임의취소=``'cancelled'``) **winner 경로에서만** ``_release_slots`` 직후·
    ``commit`` 전에 예약자(``booker_id``) status_change 통지를 staged한다 → status flip + 슬롯
    DELETE + 통지 INSERT가 **단일 commit**으로 원자화된다(통지 실패 시 전이도 롤백 → 재시도가 전부
    재수행 → 영구 손실 불가). fast-path(이미 종료)·loser(``rowcount==0``)는 winner가 아니므로 통지를
    staged하지 **않는다**(멱등 no-op 효과 0 — AC3). ``notify_reason=None``이면 통지 없음(booker
    본인 취소 4.7 — 자기 통지 불요).
    """
    if reservation.status in _TERMINAL_STATUSES:
        return reservation  # 멱등 no-op(쓰기 0 — AC2)

    # 조건부 원자 UPDATE — WHERE status='confirmed'가 DB 행 락으로 단일 승자를 중재(race 결정화).
    result = session.exec(
        update(Reservation)
        .where(
            col(Reservation.id) == reservation.id,
            col(Reservation.status) == ReservationStatus.CONFIRMED,
        )
        .values(status=target)
    )
    if result.rowcount == 0:
        # 동시 전이가 선점(또는 stale 종료 상태) → 슬롯·통지 없이 현재 DB 상태로 수렴(멱등 패자).
        # 보류 중인 실제 변경이 없으므로 no-op UPDATE를 rollback으로 정리하고, stale in-memory
        # status(confirmed)를 refresh로 실제 종료 상태에 동기화한다(통지 결정이 이 값을 본다).
        session.rollback()
        session.refresh(reservation)
        return reservation

    # rowcount == 1 (이 전이가 승자) → 슬롯 재활성 + (통지 staging) + commit(동일 트랜잭션).
    _release_slots(session, reservation.id)
    # ★통지 원자 편입(deferred L42 회수) — winner일 때만, commit 전에 staged한다. add-only
    # 프리미티브라 commit은 아래 단일 commit이 한다(status flip + 슬롯 DELETE + 통지 INSERT 원자).
    if notify_reason is not None:
        notifications_service.stage_status_change_notification(
            session,
            user_id=reservation.booker_id,
            reservation_id=reservation.id,
            reason=notify_reason,
        )
    session.commit()
    # Core UPDATE는 ORM 객체를 자동 동기화하지 않으므로 refresh로 status를 동기화한다(필수).
    session.refresh(reservation)
    return reservation


def cancel_reservation(session: Session, reservation: Reservation) -> Reservation:
    """예약을 예약자 취소(``cancelled``)로 전이한다(멱등·동일 트랜잭션 슬롯 재활성, AC2·AC3).

    6h 취소 윈도우(``is_within_hours`` — FR-16)는 **Story 4.7**이 이 함수 호출 *전에* 게이팅한다.
    본 함수는 시간 경계를 판정하지 않는다(상태 전이·재활성만).
    """
    return _transition_to_terminal(session, reservation, ReservationStatus.CANCELLED)


def reject_reservation(session: Session, reservation: Reservation) -> Reservation:
    """예약을 제공자 거절(``rejected``)로 전이한다 + 예약자 status_change 통지 원자 생성(E6/6.2).

    **통지 원자화(Story 8.3 — deferred L42 회수):** ``notify_reason="rejected"``를 전달해 거절
    전이가 winner일 때 status flip + 슬롯 DELETE + ``reason="rejected"`` 통지를 **단일 commit**으로
    묶는다(이전엔 라우터가 거절 commit *후* 별도 트랜잭션으로 통지를 만들어 통지 실패 시 영구 손실
    위험이 있었다 — 이제 원자라 retry-safe). 멱등 no-op·race loser는 통지 0(winner만). 거절 통지가
    **생성되는 사실은 6.2와 불변**(배선이 router→service로 이동·원자화).
    """
    return _transition_to_terminal(
        session, reservation, ReservationStatus.REJECTED, notify_reason="rejected"
    )


def admin_force_cancel_reservation(
    session: Session, reservation: Reservation
) -> Reservation:
    """시드 관리자가 예약을 임의 취소(``cancelled``)한다 + 예약자 통지 원자 생성(Story 8.3, AC1~3).

    **시간 게이트 없음(admin 권한):** booker 6h(``cancel_reservation_for_booker``)·provider
    시작전(``reject_reservation_for_provider``) **게이팅 래퍼를 호출하지 않는다** — 관리자는
    시작된/지난 예약도 임의 취소할 수 있는 예외 운영 도구이므로 프리미티브
    (``_transition_to_terminal``)를 직접 호출한다.

    **동작(``_transition_to_terminal`` 재사용 — 재구현 0):**

    - **confirmed면 winner:** status flip(``cancelled``) + ``_release_slots``(슬롯 DELETE=재활성) +
      예약자 ``status_change``/``reason="cancelled"`` 통지가 **단일 commit으로 원자**(통지 실패 시
      전체 롤백·재시도 전부 재수행 → 영구 손실 불가, deferred L42 회수).
    - **이미 종료(``cancelled``/``rejected``)면 멱등 no-op:** status·슬롯·통지 변경 0, 현재 상태
      그대로 반환(전이 winner 아님 — AC3).

    ``reason``은 정확히 ``"cancelled"``다(FE ``NotificationBanner``가 5.3에서 ``reason==
    "cancelled"``로 하드코딩 분기 — 오타 금지). 슬롯 재활성은 ``_release_slots``(DELETE) 경로라
    가용성 reader의 DELETE-on-cancel 불변식을 보존한다(bare status UPDATE 금지 — deferred L78).
    """
    return _transition_to_terminal(
        session, reservation, ReservationStatus.CANCELLED, notify_reason="cancelled"
    )


def earliest_slot_start(
    session: Session, reservation_id: uuid.UUID
) -> datetime | None:
    """예약이 점유한 슬롯 중 **가장 이른 시작시각**(UTC aware)을 반환한다(읽기 전용, 4.7).

    6h 취소 윈도우 판정의 기준 시각(예약 시작 = 점유 슬롯 중 최소 ``slot_start``)을 구한다.
    점유 슬롯이 0건이면(종료 상태 = 취소/거절로 슬롯 DELETE됨) ``None``을 반환한다 —
    종료 상태는 시간 판정이 무의미하므로 호출처(``cancel_reservation_for_booker``)가 6h 게이트
    *전*에 멱등 분기한다. ``confirmed_slot_starts``의 읽기 패턴(``col()``·UTC aware)을 미러한다.

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).
        reservation_id: 조회 대상 예약(``reservations.id``).

    Returns:
        가장 이른 점유 슬롯 시작시각(UTC aware). 점유 0건이면 ``None``.
    """
    statement = select(ReservationSlot.slot_start).where(
        col(ReservationSlot.reservation_id) == reservation_id
    )
    starts = session.exec(statement).all()
    return min(starts) if starts else None


def cancel_reservation_for_booker(
    session: Session, reservation: Reservation, *, now: datetime | None = None
) -> Reservation:
    """예약자 취소 게이팅 래퍼: 종료 상태 멱등 → 6h 윈도우 게이트 → 4.1 취소 호출(4.7).

    4.1 ``cancel_reservation``은 시간 경계를 판정하지 않는다(상태 전이·재활성만). 6h 취소
    윈도우(FR-16)는 **이 함수가 4.1 호출 *전*에** 강제한다. 분기 순서가 중요하다(AC3):

    1. **종료 상태면 즉시 멱등 반환**(``status in _TERMINAL_STATUSES`` → ``return``, DB 쓰기 0).
       6h 검사보다 **먼저** 한다 — 종료 상태는 점유 슬롯이 0건이라 ``earliest_slot_start``가
       ``None``이 되어 시간 판정 자체가 불가하기 때문이다(순서를 어기면 오판/방어차단).
    2. **confirmed면 6h 게이트:** 가장 이른 점유 슬롯까지 ``< 6시간`` 남았거나 이미 지났으면
       409 ``CANCEL_WINDOW_PASSED``로 거부한다(상태 전이·슬롯 변경 0 — 예약은 confirmed 유지).
       경계 정책(deferred L91 회수): 취소 **가능** = ``earliest - now >= 6시간``(정확히 6h 포함),
       **차단** = ``< 6시간``. float ``hours_until`` 대신 ``timedelta`` 정수 비교로 6.0h 경계의
       1µs 모호성을 제거한다.
    3. **게이트 통과** → 4.1 ``cancel_reservation``을 **그대로 호출**(status flip + 슬롯 DELETE
       단일 트랜잭션 — 재구현 금지, AC2).

    Args:
        session: DB 세션.
        reservation: 취소 대상 예약(소유권·존재 검증은 라우터가 선차단).
        now: 현재시각(테스트 결정성 — ``core/time`` now 주입 철학). 미지정 시 ``now_utc()``.
            tz-aware여야 한다(naive면 ``ValueError`` — 시각 비교 오류 방지).

    Returns:
        취소된 예약(``status='cancelled'``) 또는 이미 종료 상태인 예약(멱등 no-op).

    Raises:
        DomainError: 6h 윈도우가 지났으면 409 ``CANCEL_WINDOW_PASSED``.
    """
    # ⓐ 종료 상태(cancelled/rejected)면 6h 검사 전 즉시 멱등 반환(슬롯 0 — earliest 계산 불가).
    if reservation.status in _TERMINAL_STATUSES:
        return reservation

    # ⓑ confirmed → 6h 게이트. earliest는 점유 슬롯 중 최소 slot_start(UTC aware).
    current = now if now is not None else now_utc()
    _require_aware(current, "now")
    earliest = earliest_slot_start(session, reservation.id)
    if earliest is None:
        # confirmed인데 점유 슬롯 0건 = 데이터 이상(정상 경로에선 불가). 시간 윈도우를 검증할 수
        # 없으므로 조용히 취소하지 않고 방어적으로 차단한다(fail-safe — 불변식 위반을 숨기지 않음).
        raise DomainError(
            ErrorCode.CANCEL_WINDOW_PASSED, "이제 6시간이 안 남아서 취소가 어려워요."
        )
    if (earliest - current) < _CANCEL_WINDOW:
        # < 6시간(경계 미만·과거 포함) → 취소 불가(서버 권위 최종 강제, AC1). timedelta 정수 비교.
        raise DomainError(
            ErrorCode.CANCEL_WINDOW_PASSED, "이제 6시간이 안 남아서 취소가 어려워요."
        )

    # ⓒ 게이트 통과 → 4.1 프리미티브 그대로 호출(상태 전이·재활성·멱등은 이미 보장 — 재구현 금지).
    return cancel_reservation(session, reservation)


def reject_reservation_for_provider(
    session: Session, reservation: Reservation, *, now: datetime | None = None
) -> Reservation:
    """제공자 거절 게이팅 래퍼: 종료 상태 멱등 → 시작 전 게이트 → 4.1 거절 호출(Story 6.2).

    ``cancel_reservation_for_booker``(4.7)의 **거울상**이다 — 게이트만 다르다. 4.1
    ``reject_reservation``은 시간 경계를 판정하지 않으므로(상태 전이·재활성만), 거절 윈도우
    (FR-24 "예약 시작 전까지")는 **이 함수가 4.1 호출 *전*에** 강제한다. 분기 순서가 중요하다(AC3):

    1. **종료 상태면 즉시 멱등 반환**(``status in _TERMINAL_STATUSES`` → ``return``, DB 쓰기 0).
       시간 검사보다 **먼저** 한다 — 종료 상태는 점유 슬롯이 0건이라 ``earliest_slot_start``가
       ``None``이 되어 시간 판정 자체가 불가하기 때문이다(``cancel_reservation_for_booker`` 선례).
       예: booker가 먼저 취소(``cancelled``)했으면 거절은 멱등 no-op으로 현재 상태를 돌려준다.
    2. **confirmed면 시작 전 게이트:** 가장 이른 점유 슬롯 시작시각(``earliest``)보다 현재가
       이전(``now < earliest``)일 때만 거절 가능하고, **시작했거나 지났으면**(``earliest <= now``)
       409 ``REJECT_WINDOW_PASSED``로 차단한다(상태 전이·슬롯 변경 0 — 예약은 confirmed 유지).
       취소의 6h 윈도우(``< 6시간`` 차단)와 달리 거절은 **고정 윈도우 없이 시작 직전까지** 가능하다
       (제공자 운영 권한). ``earliest is None``(confirmed인데 슬롯 0건 = 데이터 이상, 정상 경로
       불가)이면 시간을 검증할 수 없으므로 조용히 거절하지 않고 방어적으로 차단한다(fail-safe —
       ``cancel_reservation_for_booker``의 ``earliest is None`` 분기 미러).
    3. **게이트 통과** → 4.1 ``reject_reservation``을 **그대로 호출**(status flip + 슬롯 DELETE
       단일 트랜잭션·조건부 원자 UPDATE 강화분 자동 적용 — 재구현 금지, AC1).

    Args:
        session: DB 세션.
        reservation: 거절 대상 예약(소유권·존재 검증은 라우터가 선차단 — 본인 소유 룸 예약만).
        now: 현재시각(테스트 결정성 — ``core/time`` now 주입 철학). 미지정 시 ``now_utc()``.
            tz-aware여야 한다(naive면 ``ValueError`` — 시각 비교 오류 방지).

    Returns:
        거절된 예약(``status='rejected'``) 또는 이미 종료 상태인 예약(멱등 no-op).

    Raises:
        DomainError: 예약이 시작했거나 지났으면(``earliest <= now``) 409 ``REJECT_WINDOW_PASSED``.
    """
    # ⓐ 종료 상태(cancelled/rejected)면 시간 검사 전 즉시 멱등 반환(슬롯 0 — earliest 계산 불가).
    if reservation.status in _TERMINAL_STATUSES:
        return reservation

    # ⓑ confirmed → 시작 전 게이트. earliest는 점유 슬롯 중 최소 slot_start(UTC aware).
    current = now if now is not None else now_utc()
    _require_aware(current, "now")
    earliest = earliest_slot_start(session, reservation.id)
    if earliest is None:
        # confirmed인데 점유 슬롯 0건 = 데이터 이상(정상 경로에선 불가). 시작 시각을 알 수 없으므로
        # 조용히 거절하지 않고 방어적으로 차단한다(fail-safe — 불변식 위반을 숨기지 않음).
        raise DomainError(
            ErrorCode.REJECT_WINDOW_PASSED, "이미 시작된 예약은 거절할 수 없어요."
        )
    if earliest <= current:
        # 시작했거나 지남(시작 시각 자체가 경계 — 취소 6h 윈도우와 달리 고정 윈도우 없음) → 거절
        # 불가(서버 권위 최종 강제, AC3). aware UTC 직접 비교(earliest·current 모두 aware 보장).
        raise DomainError(
            ErrorCode.REJECT_WINDOW_PASSED, "이미 시작된 예약은 거절할 수 없어요."
        )

    # ⓒ 게이트 통과 → 4.1 프리미티브 호출(상태 전이·재활성·멱등·race 결정화 보장 — 재구현 금지).
    return reject_reservation(session, reservation)


def list_booker_reservations(
    session: Session, booker_id: uuid.UUID
) -> list[Reservation]:
    """예약자 본인의 모든 예약을 최근 생성순으로 반환한다(읽기 전용, 4.8 AC4).

    상태 무관(confirmed/cancelled/rejected 전부 — 예약현황 히스토리는 종료 상태도 표시)으로
    ``booker_id`` 소유 예약을 ``created_at`` 내림차순 flat 목록으로 낸다. 다가오는/지난 분류·정렬은
    **FE가 ``now`` 기준**으로 한다(서버 시계 의존·캐시 신선도 문제 회피 — favorites
    ``list_favorites`` 선례: 서버는 단순 flat, 분류는 소비처). ``idx_reservations_booker_id`` 백킹.

    **rooms import 금지(도메인 경계 — service docstring·4.9 순환):** 이 함수는 ``reservations``
    테이블만 만진다. 룸 이름·``is_active`` 합성은 **라우터(조합 계층)**가 ``session.get(Room, …)``로
    한다(reservations.service가 rooms를 import하면 4.9 ``rooms.service → reservations.service``
    역방향과 순환 import). 따라서 여기선 ``Reservation`` 행만 반환한다.

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).
        booker_id: 조회 대상 예약자(``users.id`` = 인증 principal).

    Returns:
        본인 예약 리스트(``created_at`` desc). 예약이 없으면 ``[]``(정상 빈 목록).
    """
    statement = (
        select(Reservation)
        .where(col(Reservation.booker_id) == booker_id)
        .order_by(col(Reservation.created_at).desc())  # 최근 생성 먼저
    )
    return list(session.exec(statement).all())


def list_reservations_for_rooms(
    session: Session, room_ids: Iterable[uuid.UUID]
) -> list[Reservation]:
    """주어진 룸들의 모든 예약을 최근 생성순으로 반환한다(읽기 전용, Story 6.1 — 제공자 예약현황).

    ``list_booker_reservations``의 **거울상**(소유권 축이 ``booker_id``(본인) → ``room_id IN``(소유
    룸들))이다. ``room_ids``에 속한 예약을 **상태 무관**(confirmed/cancelled/rejected 전부 —
    예약현황 히스토리는 종료 상태도 표시)으로 ``created_at`` 내림차순 flat 목록으로 낸다. 다가오는/
    지난 분류·정렬은 **소비처가 ``slot_starts``·``now`` 기준**으로 한다(서버 시계 의존·캐시 신선도
    회피 — 4.8 선례). ``idx_reservations_room_id``(models.py — 주석 "룸별 예약 현황 조회(제공자
    6.1)") 백킹.

    **빈 입력 가드:** ``room_ids``를 먼저 materialize(``list(...)``)하고 **비면 ``[]`` 반환(쿼리
    미발행)** — ``confirmed_slot_starts_by_room``의 빈 입력 ``{}`` 가드와 동형(불필요한 ``IN ()``
    회피). 제공자가 소유 룸 0개일 때 안전하다.

    **rooms import 금지(도메인 경계 — service docstring·4.9 순환):** 이 함수는 ``reservations``
    테이블만 만지고 ``room_ids``(UUID)만 받는다. 룸 이름 합성은 **라우터(조합 계층)**가
    한다(``list_booker_reservations`` 선례와 동일 — service는 ``reservations``만, 룸 메타는 라우터).
    ``from app.rooms…`` import를 추가하지 않는다.

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).
        room_ids: 조회 대상 룸들(``rooms.id`` — 제공자 소유 룸). **빈 입력이면 ``[]``**(쿼리
            미발행 — IN () 회피).

    Returns:
        해당 룸들의 예약 리스트(``created_at`` desc). 예약이 없으면 ``[]``(정상 빈 목록).
    """
    # 일회성 이터러블(제너레이터)이 와도 안전하도록 먼저 materialize한다(빈 입력 판정·IN 절 재사용).
    room_ids = list(room_ids)
    if not room_ids:
        return []  # 빈 입력 → 쿼리 미발행(불필요한 IN () 회피 — 제공자 룸 0개 안전)

    statement = (
        select(Reservation)
        .where(col(Reservation.room_id).in_(room_ids))
        .order_by(col(Reservation.created_at).desc())  # 최근 생성 먼저(4.8 동형)
    )
    return list(session.exec(statement).all())


def list_booker_reservations_page(
    session: Session,
    booker_id: uuid.UUID,
    *,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[Reservation], str | None]:
    """``list_booker_reservations``의 **커서 페이징판**(F — 목록 무한스크롤).

    동일한 본인 예약 flat 목록을 ``(created_at, id)`` keyset 커서로 한 페이지씩 낸다. 정렬은
    ``created_at desc, id desc``(전체판은 ``created_at`` desc만 — 페이징은 동일 created_at 타이를
    ``id``로 깬다, [[pagination]] keyset_predicate와 짝). ``limit+1``을 조회해 다음 페이지 존재를
    판정하고(``keyset_page``), 다음 토큰(없으면 ``None``)을 함께 반환한다. 전체판은 reminders가
    여전히 전량 소비하므로(``notifications.reminders``) 시그니처를 깨지 않고 **별도 함수**로 둔다.

    Args:
        session: DB 세션(**읽기 전용**).
        booker_id: 조회 대상 예약자(``users.id`` = 인증 principal).
        limit: 한 페이지 크기(라우터가 ``PAGE_SIZE_DEFAULT``~``MAX``로 검증).
        cursor: 이전 페이지의 ``next_cursor``(없으면 첫 페이지). 손상 커서는 422(``decode_keyset``).

    Returns:
        ``(이번 페이지 예약 리스트, next_cursor)`` — 마지막 페이지면 next_cursor=``None``.
    """
    predicate = keyset_predicate(
        col(Reservation.created_at), col(Reservation.id), cursor
    )
    statement = select(Reservation).where(col(Reservation.booker_id) == booker_id)
    if predicate is not None:
        statement = statement.where(predicate)
    statement = statement.order_by(
        col(Reservation.created_at).desc(), col(Reservation.id).desc()
    ).limit(limit + 1)
    rows = list(session.exec(statement).all())
    return keyset_page(
        rows, limit, created=lambda r: r.created_at, ident=lambda r: r.id
    )


def list_reservations_for_rooms_page(
    session: Session,
    room_ids: Iterable[uuid.UUID],
    *,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[Reservation], str | None]:
    """``list_reservations_for_rooms``의 **커서 페이징판**(F — 제공자 예약현황 무한스크롤).

    ``list_booker_reservations_page``의 거울상(소유권 축이 ``booker_id`` → ``room_id IN``). 빈
    ``room_ids``면 쿼리 미발행으로 ``([], None)``(전체판의 빈 입력 가드 동형). 정렬·keyset·
    ``limit+1`` 판정은 booker판과 동일하다.

    Args:
        session: DB 세션(**읽기 전용**).
        room_ids: 조회 대상 룸들(제공자 소유 룸). 빈 입력이면 ``([], None)``.
        limit: 한 페이지 크기.
        cursor: 이전 페이지의 ``next_cursor``(없으면 첫 페이지). 손상 커서는 422.

    Returns:
        ``(이번 페이지 예약 리스트, next_cursor)`` — 마지막 페이지면 next_cursor=``None``.
    """
    room_ids = list(room_ids)
    if not room_ids:
        return [], None  # 빈 입력 → 쿼리 미발행(불필요한 IN () 회피 — 제공자 룸 0개 안전)
    predicate = keyset_predicate(
        col(Reservation.created_at), col(Reservation.id), cursor
    )
    statement = select(Reservation).where(col(Reservation.room_id).in_(room_ids))
    if predicate is not None:
        statement = statement.where(predicate)
    statement = statement.order_by(
        col(Reservation.created_at).desc(), col(Reservation.id).desc()
    ).limit(limit + 1)
    rows = list(session.exec(statement).all())
    return keyset_page(
        rows, limit, created=lambda r: r.created_at, ident=lambda r: r.id
    )


def confirmed_slot_starts(
    session: Session, room_id: uuid.UUID, *, on_or_after: datetime | None = None
) -> set[datetime]:
    """한 룸의 **활성(confirmed) 점유 슬롯 시작시각**(UTC aware) 집합을 반환한다(읽기 전용).

    **Story 4.9 예약 차감 seam:** 4.9의 ``rooms.service``가 ``reservation_slots`` SQL을 직접
    만지지 않고 이 함수를 경유해 ``derive_slots(..., reserved_starts=confirmed_slot_starts(...))``
    에 주입한다(도메인 경계 준수 — architecture.md L354). 취소/거절 시 점유 행을 DELETE하므로
    ``reservation_slots``엔 활성 점유만 남는다 → 이 조회가 곧 "현재 점유된 슬롯"이다(status 조인
    불요). 본 스토리는 함수를 **정의·테스트**만 하고, 실제 ``derive_slots`` 배선은 4.9다.

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).
        room_id: 조회 대상 룸(``rooms.id``).
        on_or_after: 주어지면 이 시각 이후(``>=``)의 점유만 반환한다(UTC aware — 과거 슬롯 차감
            제외 등 호출처 최적화용). naive면 ``ValueError``(차감 매칭 실패 방지).

    Returns:
        활성 점유 ``slot_start``(UTC aware) 집합. 점유 0건이면 빈 집합.
    """
    statement = select(ReservationSlot.slot_start).where(
        col(ReservationSlot.room_id) == room_id
    )
    if on_or_after is not None:
        _require_aware(on_or_after, "on_or_after")
        statement = statement.where(col(ReservationSlot.slot_start) >= on_or_after)
    # DB 반환값도 aware 보장 — 드라이버가 naive를 돌려주면 derive_slots aware 슬롯과 instant
    # 미매칭으로 차감이 조용히 no-op된다(점유 슬롯 누출). 경계에서 fail-fast(naive 거부 표준).
    slot_starts = session.exec(statement).all()
    for slot_start in slot_starts:
        _require_aware(slot_start, "slot_start")
    return set(slot_starts)


def confirmed_slot_starts_by_room(
    session: Session,
    room_ids: Iterable[uuid.UUID],
    *,
    on_or_after: datetime | None = None,
) -> dict[uuid.UUID, set[datetime]]:
    """여러 룸의 활성 점유 슬롯 시작시각을 **룸별 집합**으로 한 번에 반환한다(벌크 — N+1 회피).

    ``confirmed_slot_starts``의 벌크판(**Story 4.9 차감 seam**). ``rooms.service``의 다중 룸 집계
    (``aggregate_availability``·``search_rooms``)가 룸마다 단건 reader를 호출하면 N+1이 되므로,
    ``reservation_slots``를 ``room_id IN (...)``로 **1회 조회**한 뒤 Python에서 ``room_id``별
    ``set[datetime]``으로 그룹핑한다(영업시간/휴무 벌크 그룹핑 패턴과 동형). 단건
    ``confirmed_slot_starts``는 단일 룸 소비처(``get_room_summary``·``room_remaining_slots``·
    ``get_room_slots``)가 그대로 쓴다 — 둘 다 ``reservation_slots``만 만진다(도메인 경계 —
    rooms import 금지 유지).

    취소/거절 시 점유 행을 DELETE하므로 ``reservation_slots``엔 활성 점유만 남는다 → status 조인
    불요(단건 reader와 동일 — docstring 참조).

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).
        room_ids: 조회 대상 룸들(``rooms.id``). **빈 입력이면 ``{}``**(쿼리 미발행).
        on_or_after: 주어지면 이 시각 이후(``>=``)의 점유만 반환한다(UTC aware — 과거 슬롯 차감
            제외 등 호출처 최적화용). naive면 ``ValueError``(차감 매칭 실패 방지 — 단건 동일).

    Returns:
        ``{room_id: {slot_start, ...}}`` — 활성 점유가 있는 룸만 키로 갖는다(점유 0건 룸은 키 부재).
        ``room_ids``가 비면 ``{}``. 호출처는 ``.get(room_id, frozenset())``로 부재 룸을 안전 처리.
    """
    # 일회성 이터러블(제너레이터)이 와도 안전하도록 먼저 materialize한다(빈 입력 판정·IN 절 재사용).
    room_ids = list(room_ids)
    if not room_ids:
        return {}  # 빈 입력 → 쿼리 미발행(불필요한 IN () 회피)

    statement = select(ReservationSlot.room_id, ReservationSlot.slot_start).where(
        col(ReservationSlot.room_id).in_(room_ids)
    )
    if on_or_after is not None:
        _require_aware(on_or_after, "on_or_after")
        statement = statement.where(col(ReservationSlot.slot_start) >= on_or_after)

    by_room: dict[uuid.UUID, set[datetime]] = defaultdict(set)
    for room_id, slot_start in session.exec(statement).all():
        # 단건 reader 동일 — DB 반환 slot_start naive면 차감 조용히 no-op → fail-fast.
        _require_aware(slot_start, "slot_start")
        by_room[room_id].add(slot_start)
    return dict(by_room)  # defaultdict 누수 방지 — 부재 룸은 KeyError 아닌 .get 폴백으로
