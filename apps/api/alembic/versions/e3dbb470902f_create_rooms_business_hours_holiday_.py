"""create rooms business_hours holiday_exceptions tables

Revision ID: e3dbb470902f
Revises: ac9b81f7d058
Create Date: 2026-06-15 14:09:15.589175

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # autogenerate가 sqlmodel.sql.sqltypes.* 타입을 렌더할 때 NameError 방지
from sqlalchemy.dialects import postgresql  # amenities = JSONB 배열(2.1)


# revision identifiers, used by Alembic.
revision: str = 'e3dbb470902f'
down_revision: Union[str, Sequence[str], None] = 'ac9b81f7d058'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """rooms 도메인 3테이블 생성(Story 2.1).

    제약명은 SQLModel.metadata 네이밍 규약(1.4) + 복합 제약 명시 단축명(회고 P1)을 따른다.
    모든 제약명은 ≤63자(PostgreSQL 식별자 한계)임이 tests/rooms/test_models.py로 회귀 검증된다.

    - rooms: PK pk_rooms, FK fk_rooms_provider_id_users(→users.id, ondelete 미지정 = 룸은
      폐기 종속 데이터 아님), INDEX idx_rooms_provider_id. amenities=JSONB 배열,
      created_at=timestamptz(UTC 규약).
    - business_hours: 룸별 요일 영업시간(open/close=벽시계 sa.Time). FK→rooms CASCADE.
      복합 UNIQUE uq_business_hours_room_id_weekday + CHECK 2종(weekday 0~6, close>open
      = 같은 날 내·자정 넘김 없음을 DB에서 강제).
    - holiday_exceptions: 룸별 휴무 날짜(holiday_date=sa.Date, ROOM_TZ 기준). FK→rooms CASCADE.
      복합 UNIQUE uq_holiday_exceptions_room_id_holiday_date.
    """
    op.create_table(
        "rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("price_per_hour", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("room_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("amenities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("admin_dong_code", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rooms"),
        # 룸은 폐기 종속 데이터가 아니므로 ondelete 미지정(NO ACTION/RESTRICT).
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["users.id"],
            name="fk_rooms_provider_id_users",
        ),
    )
    op.create_index("idx_rooms_provider_id", "rooms", ["provider_id"])

    op.create_table(
        "business_hours",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("open_time", sa.Time(), nullable=False),
        sa.Column("close_time", sa.Time(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_business_hours"),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name="fk_business_hours_room_id_rooms",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("room_id", "weekday", name="uq_business_hours_room_id_weekday"),
        # CHECK name엔 접미사만 — op.create_table도 target_metadata의 ck 규약
        # (ck_%(table_name)s_%(constraint_name)s)을 적용하므로 전체명을 주면 이중접두된다.
        # 모델 메타데이터 해석명(ck_business_hours_weekday)과 일치시켜 autogenerate drift 방지.
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="weekday"),
        sa.CheckConstraint("close_time > open_time", name="hours_order"),
    )
    op.create_index("idx_business_hours_room_id", "business_hours", ["room_id"])

    op.create_table(
        "holiday_exceptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_holiday_exceptions"),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name="fk_holiday_exceptions_room_id_rooms",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "room_id", "holiday_date", name="uq_holiday_exceptions_room_id_holiday_date"
        ),
    )
    op.create_index("idx_holiday_exceptions_room_id", "holiday_exceptions", ["room_id"])


def downgrade() -> None:
    """rooms 도메인 3테이블 제거(왕복 가능 — 생성 역순, FK 의존성 역순).

    holiday_exceptions·business_hours(→rooms FK CASCADE) 먼저, rooms 마지막.
    각 인덱스는 테이블 drop 전에 명시 drop.
    """
    op.drop_index("idx_holiday_exceptions_room_id", table_name="holiday_exceptions")
    op.drop_table("holiday_exceptions")

    op.drop_index("idx_business_hours_room_id", table_name="business_hours")
    op.drop_table("business_hours")

    op.drop_index("idx_rooms_provider_id", table_name="rooms")
    op.drop_table("rooms")
