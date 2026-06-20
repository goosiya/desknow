"""notifications 도메인 ORM 모델: ``Notification`` (Story 5.1).

인앱 배너의 영속 데이터 계층이다. **통합 단일 테이블 + ``type`` 판별자**로 두 종류의 통지를
한 테이블에서 다룬다(KTH 확정 #1):

- ``status_change``: 거절(FR-24)/임의취소(FR-32) **시점에 행 생성**(reason='rejected'|'cancelled').
  표시·'확인'은 5.3, 생성 배선은 6.2/8.3.
- ``reservation_reminder``: 평소 행 없음(24h 이내 확정 예약에서 **도출** — 5.2). '다시 보지 않기'
  시 억제행을 생성해 재노출을 막는다(5.2).

두 종류 모두 **단일 dismiss 메커니즘**(``dismissed_at`` 설정)으로 소멸한다 — '다시 보지 않기'·
'확인'이 같은 ``POST /notifications/{id}/dismiss``를 소비한다(KTH 확정 #3).

**규약(아키텍처 §Naming Patterns L228-241 / §Data-Architecture L141-153):**

- **테이블 복수 snake_case**(``notifications``). 컬럼 snake_case. 단일 제약(PK/FK/INDEX)은 1.4
  ``NAMING_CONVENTION``(``app/core/db.py:28``)이 자동 부여한다. 복합 UNIQUE·CHECK는
  ``favorites``/``reservations`` 선례대로 **명시 단축명**을 부여한다(회고 P1 — 63바이트 절단 회귀
  방지). [Source: deferred-work.md L97]
- **FK ondelete:** ``user_id``=**RESTRICT(미지정)** — 사용자는 하드삭제하지 않는다(운영중단=
  is_active 비활성 E8, favorites 선례). ``reservation_id``=**CASCADE** — 통지는 예약 종속이라
  예약 행이 사라지면 통지도 무의미(단 현 앱은 예약 하드삭제 경로 없음[취소=status flip]이라
  실발현은 E8). ``reservation_slots.reservation_id`` CASCADE 선례.
- ``created_at``/``dismissed_at`` = ``*_at`` 규약상 UTC ``timestamptz``(``core/time`` 단일 출처).
  ``dismissed_at`` nullable — NULL=미확인(표시), 설정=소멸.
- **``type`` 자유 문자열 저장 + DB CHECK + Pydantic 이중 방어**(``status``[4.1]/``role``[1.7]
  선례). ``NotificationType`` enum은 코드 측 참조값이고 최종 검증은 ``ck_notifications_type``.

스키마는 Alembic이 단독 소유한다(``SQLModel.metadata.create_all`` 금지 — 1.4 규약).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Uuid,
)
from sqlmodel import Field, SQLModel

from app.core.time import now_utc


class NotificationType(StrEnum):
    """통지 종류(코드 측 참조값). ``type`` 컬럼은 자유 문자열로 저장하고, 값 검증은 DB
    CHECK(``ck_notifications_type``) + 스키마/Pydantic ``Literal``이 담당한다(defense-in-depth).

    - ``RESERVATION_REMINDER``: 예약 도래 리마인드(FR-18 — 도출/억제행은 5.2). reason=NULL.
    - ``STATUS_CHANGE``: 예약 상태변경 통지(FR-18a — 거절/취소 시점 행 생성). reason=
      'rejected'|'cancelled'(생성 배선은 6.2/8.3).
    """

    RESERVATION_REMINDER = "reservation_reminder"  # 예약 도래 리마인드(5.2)
    STATUS_CHANGE = "status_change"  # 예약 상태변경 통지(거절/취소 — 6.2/8.3)


class Notification(SQLModel, table=True):
    """사용자에게 표시할 인앱 통지 한 건(사용자×예약×종류 1행).

    제약명은 1.4 규약 자동: PK ``pk_notifications``, FK ``fk_notifications_user_id_users``·
    ``fk_notifications_reservation_id_reservations``(44자 ≤63 ✓), INDEX
    ``idx_notifications_user_id``·``idx_notifications_reservation_id``. 복합 UNIQUE·CHECK만
    명시 단축명(``uq_notifications_user_reservation_type``·``ck_notifications_type``).
    """

    __tablename__ = "notifications"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # users는 폐기 종속 데이터가 아님 → CASCADE 아님(ondelete 미지정 = RESTRICT).
            ForeignKey("users.id"),
            nullable=False,
            index=True,  # idx_notifications_user_id — 사용자별 미확인 통지 조회(list_pending)
        ),
    )
    reservation_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # 통지는 예약 종속 데이터 → 예약 행 삭제 시 함께 삭제(CASCADE). 현 앱은 예약 하드삭제
            # 경로 없음(취소=status flip)이라 실발현은 E8 — 의미상 종속을 스키마로 명시한다.
            ForeignKey("reservations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,  # idx_notifications_reservation_id — 룸 이름 합성·예약별 조회
        ),
    )
    # NotificationType 값(자유 문자열 저장 — 검증은 DB CHECK + 스키마 Literal). 기본값 없음
    # (생성 시 호출처가 종류를 명시 — reservation_reminder=5.2·status_change=6.2/8.3).
    type: str = Field(nullable=False)
    # status_change 전용 부가 사유('rejected'|'cancelled' — 배너 카피 분기). reminder=NULL.
    reason: str | None = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=now_utc,  # core/time 단일 출처(datetime.now() 직접 호출 금지)
        sa_column=Column(DateTime(timezone=True), nullable=False),  # *_at = UTC timestamptz
    )
    # NULL=미확인(GET 노출·배너 표시), 설정=소멸('다시 보지 않기'·'확인' 공통, 영속). naive 방지
    # 위해 명시 sa_column으로 timezone=True 강제(created_at 패턴).
    dismissed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    __table_args__ = (
        # 복합 UNIQUE(3컬럼) — 명시 단축명(회고 P1, 38자 ≤63). 사용자·예약·종류당 통지 1행:
        # 같은 예약·같은 종류 통지는 1건(멱등 근거 — status_change 재생성·reminder 억제 중복 합침).
        UniqueConstraint(
            "user_id",
            "reservation_id",
            "type",
            name="uq_notifications_user_reservation_type",
        ),
        # type 허용값 CHECK — 명시 단축명(회고 P1). ck 규약 ck_%(table)s_%(name)s가 접두하므로
        # name엔 **접미사만** 준다(2.1 이중접두 함정 — reservations ck_reservations_status 선례).
        # 전체명을 주면 ck_notifications_ck_notifications_type 이중접두가 된다. → 최종명:
        # ck_notifications_type.
        CheckConstraint(
            "type IN ('reservation_reminder', 'status_change')", name="type"
        ),
    )
