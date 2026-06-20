"""favorites 도메인 ORM 모델: ``Favorite`` (Story 3.7).

로그인 사용자가 마음에 든 룸을 즐겨찾기로 보관한다(FR-10). 사용자×룸 1행만 허용해
(``uq_favorites_user_id_room_id``) **토글 멱등성**(중복 add=기존 행·없는 행 delete=무에러)의
DB 근거로 삼는다.

**규약(아키텍처 §Naming Patterns L228-241 / §Data-Architecture L141-153):**

- **테이블 복수 snake_case**(``favorites``). 단일 제약(PK/FK/INDEX)은 1.4 ``NAMING_CONVENTION``
  (``app/core/db.py:28``)이 자동 부여한다. 복합(2컬럼) UNIQUE는 ``rooms``/``business_hours``
  선례대로 **명시 단축명**을 부여한다(회고 P1 — 63바이트 절단 회귀 방지).
- **FK ondelete = RESTRICT(미지정)** — rooms/users는 하드삭제하지 않는다(운영중단=is_active 비활성
  E8). ``Room.provider_id``(``rooms/models.py:91-99``) 패턴 그대로 ``Column(Uuid(), ForeignKey,
  nullable=False, index=True)``로 정의한다.
- ``created_at`` = ``*_at`` 규약상 UTC ``timestamptz``(``core/time.now_utc`` 단일 출처). 응답에서는
  도메인 의미를 명확히 하려 ``favorited_at`` 별칭으로 노출한다(컬럼명은 ``created_at`` 유지).

스키마는 Alembic이 단독 소유한다(``SQLModel.metadata.create_all`` 금지 — 1.4 규약).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint, Uuid
from sqlmodel import Field, SQLModel

from app.core.time import now_utc


class Favorite(SQLModel, table=True):
    """사용자가 즐겨찾기한 룸 한 건(사용자×룸 1행).

    제약명은 1.4 규약 자동: PK ``pk_favorites``, FK ``fk_favorites_user_id_users``·
    ``fk_favorites_room_id_rooms``, INDEX ``idx_favorites_user_id``·``idx_favorites_room_id``.
    복합 UNIQUE만 명시 단축명 ``uq_favorites_user_id_room_id``(회고 P1).
    """

    __tablename__ = "favorites"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # users는 폐기 종속 데이터가 아님 → CASCADE 아님(ondelete 미지정 = RESTRICT).
            ForeignKey("users.id"),
            nullable=False,
            index=True,  # idx_favorites_user_id — 사용자별 즐겨찾기 조회
        ),
    )
    room_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # rooms도 하드삭제 안 함(운영중단=is_active 비활성 E8) → ondelete 미지정.
            ForeignKey("rooms.id"),
            nullable=False,
            index=True,  # idx_favorites_room_id
        ),
    )
    created_at: datetime = Field(
        default_factory=now_utc,  # core/time 단일 출처(datetime.now() 직접 호출 금지)
        sa_column=Column(DateTime(timezone=True), nullable=False),  # *_at = UTC timestamptz
    )

    __table_args__ = (
        # 복합 UNIQUE(2컬럼) — 명시 단축명(회고 P1). 사용자·룸당 즐겨찾기 1행(토글 멱등성 근거).
        UniqueConstraint("user_id", "room_id", name="uq_favorites_user_id_room_id"),
    )
