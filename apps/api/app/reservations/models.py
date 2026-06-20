"""reservations 도메인 ORM 모델: ``Reservation`` · ``ReservationSlot`` (Story 4.1).

예약 단위(상태머신·히스토리)와 그 **슬롯 점유 행**을 2테이블로 분리해 정의한다. 이
두 테이블이 예약 핵심(Epic 4: 4.5 즉시예약·4.6 동시성·4.7 취소·4.8 현황·4.9 차감)의
데이터 계층 foundation이다 — Story 2.1(``rooms`` 모델 + ``derive_slots``)과 **동형**으로,
모델·마이그레이션·서비스 프리미티브까지만 책임지고 라우터/엔드포인트/UI는 범위 밖이다.

**2-테이블 설계 (KTH 확정 2026-06-16):**

- **``reservations``**(예약 단위, 1행/예약) = 상태머신·히스토리 보유. ``status`` 단일 컬럼이라
  상태 전이가 **원자·멱등**(단일 행 1컬럼 flip)으로 자명하다. 취소/거절해도 행은
  ``status='cancelled'``/``'rejected'``로 **잔존**(4.7·4.8 히스토리).
- **``reservation_slots``**(점유 행, N행/예약) = ``room_id``·``slot_start``. 취소/거절 시
  이 행을 **DELETE**해 슬롯을 재활성(다시 빔)한다. 따라서 테이블엔 **활성(confirmed) 점유만**
  잔존 → **FULL ``UNIQUE(room_id, slot_start)``로 충분**(부분 인덱스 ``WHERE status=...`` 불요).
  status 컬럼을 두지 않는다(상태는 부모 ``reservations``에만 — 단일 출처).

점유의 진실의 원천은 ``uq_reservation_slots_room_slot``(중복·부분 점유 0 — FR-15·NFR-7).
확정 예약 슬롯은 ``reservation_slots.slot_start``(UTC)를 **보유**하므로 영업시간 변경에
독립이다(FR-22 — architecture.md L149-150, ``update_room`` docstring이 이미 전제).

**규약(아키텍처 §Naming Patterns L228-241 / §Data-Architecture L141-153):**

- **테이블 복수 snake_case**(``reservations``·``reservation_slots``). 단일 제약(PK/FK/INDEX)은
  1.4 ``NAMING_CONVENTION``(``app/core/db.py:28``)이 자동 부여한다. 복합(2컬럼) UNIQUE·CHECK는
  ``rooms``/``business_hours`` 선례대로 **명시 단축명**을 부여한다(회고 P1 — 63바이트 절단 회귀
  방지 + deferred L71 회수).
- **FK ondelete:** ``booker_id``·``room_id``(예약·슬롯)는 **RESTRICT(미지정)** — users/rooms는
  하드삭제하지 않는다(운영중단=is_active 비활성 E8). ``ReservationSlot.reservation_id``만
  **CASCADE** — 점유는 예약 종속 자식 데이터다(예약 행이 사라지면 점유 행도 함께).
- ``created_at`` = ``*_at`` 규약상 UTC ``timestamptz``(``core/time.now_utc`` 단일 출처).
- **``status``는 ``role``(1.7)/``room_type``(2.1)과 동일하게 자유 문자열로 저장**한다.
  ``ReservationStatus`` enum은 코드 측 참조값이고, 최종 검증은 DB CHECK(``ck_reservations_status``)
  + 쓰기 경로(4.5)의 Pydantic ``Literal``이 담당한다(defense-in-depth).

스키마는 Alembic이 단독 소유한다(``SQLModel.metadata.create_all`` 금지 — 1.4 규약).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Uuid,
)
from sqlmodel import Field, SQLModel

from app.core.time import now_utc


class ReservationStatus(StrEnum):
    """예약 상태(코드 측 참조값). ``status`` 컬럼은 ``role``(1.7)·``room_type``(2.1)과 동일하게
    자유 문자열로 저장하며, 값 검증은 DB CHECK(``ck_reservations_status``) + 쓰기 경로(4.5)의
    Pydantic ``Literal``이 담당한다(defense-in-depth).

    상태머신(단일 출처):
        - 시작: ``confirmed``(즉시예약 = 결제 없음, 생성 즉시 확정 — FR-15).
        - 허용 전이: ``confirmed → cancelled``(예약자 취소, 4.7) · ``confirmed → rejected``
          (제공자 거절, E6/6.2).
        - 종료 상태(``_TERMINAL_STATUSES``)에서의 추가 전이는 **멱등하게 무시**한다(에러 아님).
    """

    CONFIRMED = "confirmed"  # 확정(즉시예약 시작 상태)
    CANCELLED = "cancelled"  # 예약자 취소(4.7)
    REJECTED = "rejected"  # 제공자 거절(E6/6.2)


# 종료 상태 집합(상태머신 단일 출처). 이 집합에 든 상태에서의 전이는 멱등 no-op이다(AC2).
# service.cancel_reservation/reject_reservation이 이 상수로 멱등성을 판정한다.
_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {ReservationStatus.CANCELLED, ReservationStatus.REJECTED}
)


class Reservation(SQLModel, table=True):
    """예약 한 건(예약 단위 — 상태머신·히스토리, 1행/예약).

    제약명은 1.4 규약 자동: PK ``pk_reservations``, FK ``fk_reservations_booker_id_users``·
    ``fk_reservations_room_id_rooms``, INDEX ``idx_reservations_booker_id``·
    ``idx_reservations_room_id``. CHECK만 명시 단축명 ``ck_reservations_status``(아래).

    ``booker_id``·``room_id``는 **ondelete 미지정(RESTRICT)** — users/rooms는 하드삭제하지
    않는다(운영중단=is_active 비활성 E8). 둘 다 ``index=True``(예약자별·룸별 현황 조회 4.8).
    """

    __tablename__ = "reservations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    booker_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # users는 폐기 종속 데이터가 아님 → CASCADE 아님(ondelete 미지정 = RESTRICT).
            ForeignKey("users.id"),
            nullable=False,
            index=True,  # idx_reservations_booker_id — 예약자별 현황/히스토리 조회(4.8)
        ),
    )
    room_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # rooms도 하드삭제 안 함(운영중단=is_active 비활성 E8) → ondelete 미지정.
            ForeignKey("rooms.id"),
            nullable=False,
            index=True,  # idx_reservations_room_id — 룸별 예약 현황 조회(제공자 6.1)
        ),
    )
    # ReservationStatus 값(자유 문자열 저장 — 검증은 DB CHECK + Pydantic Literal, 4.5).
    # 기본값 confirmed(즉시예약 시작 상태).
    status: str = Field(default=ReservationStatus.CONFIRMED)
    # 점유 슬롯 시작시각의 **표시 전용 immutable 스냅샷**(UTC ISO ...Z 문자열, 오름차순 — 4.8).
    #
    # 점유의 진실의 원천은 ``reservation_slots``(차감·UNIQUE)이고, 이 컬럼은 취소/거절로 슬롯이
    # DELETE된 뒤에도 **시간 표시를 위해 잔존**한다(예약현황 히스토리 — confirmed/cancelled/rejected
    # 모두 날짜·시간 표시). ``create_reservation``이 생성 시 1회 기록하고, 취소/거절 전이
    # (``_transition_to_terminal``)는 이 컬럼을 **건드리지 않는다**(immutable 히스토리 보존).
    # ``derive_slots``/가용성 집계는 이 컬럼을 **절대 읽지 않는다**(4.9 차감 불변식은 활성 점유
    # ``reservation_slots``만 대상 — 스냅샷 ≠ 차감).
    #
    # **왜 ISO 문자열 + ``sa.JSON``:** ``sa.JSON``은 datetime을 직렬화하지 못하므로
    # ``isoformat_utc`` ISO ``...Z`` 문자열로 저장한다. UTC ``...Z`` ISO-8601은 **사전식 정렬 =
    # 시간순 정렬**이라 ``min()``이 곧 earliest(파싱 불요). 크로스-다이얼렉트 ``JSON``이라 SQLite
    # 단위 테스트와 Postgres 양쪽에서 동작한다(``rooms.amenities``의 postgresql ``JSONB``는 SQLite
    # 전용이라 미러 금지).
    slot_starts: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),  # NOT NULL·기본 [](마이그레이션 server_default)
    )
    created_at: datetime = Field(
        default_factory=now_utc,  # core/time 단일 출처(datetime.now() 직접 호출 금지)
        sa_column=Column(DateTime(timezone=True), nullable=False),  # *_at = UTC timestamptz
    )

    __table_args__ = (
        # status 허용값 CHECK — 명시 단축명(회고 P1). ck 규약 ck_%(table)s_%(name)s가
        # 접두하므로 name엔 **접미사만** 준다(2.1 이중접두 함정 — business_hours/rooms 선례).
        # 전체명을 주면 ck_reservations_ck_reservations_status 이중접두가 된다.
        # → 최종명: ck_reservations_status.
        CheckConstraint(
            "status IN ('confirmed', 'cancelled', 'rejected')", name="status"
        ),
    )


class ReservationSlot(SQLModel, table=True):
    """예약이 점유한 슬롯 한 칸(점유 행 — ``room_id``·``slot_start``, N행/예약).

    **재활성 = DELETE 설계(핵심):** 취소/거절(``cancelled``/``rejected``) 시 이 행을 **DELETE**
    하므로 테이블엔 항상 **활성(confirmed) 점유만** 잔존한다 → **FULL ``UNIQUE(room_id,
    slot_start)``로 충분**(부분 유니크 인덱스 ``WHERE status='confirmed'`` 불요). 상태 컬럼을 두지
    않는다(상태는 부모 ``reservations``에만 — 단일 출처). 예약 단위는 ``reservations``에 status로
    히스토리에 남고(4.7 "취소 상태로 잔존" + 4.8 현황), 슬롯은 비워져 재점유 가능해진다.

    제약명은 1.4 규약 자동: PK ``pk_reservation_slots``, FK
    ``fk_reservation_slots_reservation_id_reservations``(48자 ≤63 ✓)·
    ``fk_reservation_slots_room_id_rooms``, INDEX ``idx_reservation_slots_reservation_id``.
    복합 UNIQUE만 명시 단축명 ``uq_reservation_slots_room_slot``(회고 P1 + deferred L71 회수, 30자).

    ``room_id``는 **denormalized**(부모 ``reservations.room_id``와 중복) — UNIQUE 제약과 4.9
    ``confirmed_slot_starts`` 조회를 **조인 없이** 수행하기 위함. ``slot_start``는 **UTC aware**
    ``timestamptz``로 ``derive_slots``가 내는 슬롯 인스턴트와 동형이다(차감 매칭의 전제).
    """

    __tablename__ = "reservation_slots"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    reservation_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # 점유는 예약 종속 자식 데이터 → 예약 행 삭제 시 함께 삭제(CASCADE).
            ForeignKey("reservations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,  # idx_reservation_slots_reservation_id — 재활성 시 예약별 점유 조회
        ),
    )
    room_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # rooms 하드삭제 안 함 → ondelete 미지정(RESTRICT). denormalized(UNIQUE·4.9 조인 회피).
            ForeignKey("rooms.id"),
            nullable=False,
        ),
    )
    # 슬롯 시작시각 — UTC aware timestamptz(derive_slots 출력과 동형). list/복합 컬럼이 아니라
    # 명시 sa_column으로 timezone=True를 강제한다(created_at 패턴 — naive 저장 방지).
    slot_start: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    __table_args__ = (
        # FULL 복합 UNIQUE(2컬럼) — 명시 단축명(회고 P1 + deferred L71 회수, 30자 ≤63).
        # 한 룸·한 슬롯에 활성 점유 최대 1행 = 중복·부분 점유 0의 진실의 원천(FR-15·NFR-7).
        UniqueConstraint(
            "room_id", "slot_start", name="uq_reservation_slots_room_slot"
        ),
    )
