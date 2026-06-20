"""add rooms provider-unique + value-range checks and users role check

Revision ID: b2c4f1a9d3e7
Revises: e3dbb470902f
Create Date: 2026-06-15 16:30:00.000000

Story 2.2 — 쓰기 경로 도입과 함께 제약을 회수/추가한다:

- **rooms**: ``uq_rooms_provider_id``(제공자당 1개 — AC4) + 값 범위 CHECK 5종
  (``room_type`` enum[P3] · ``price_per_hour>=0`` · ``capacity>=1`` ·
  ``lat`` ∈ [-90,90] · ``lng`` ∈ [-180,180] — 2.1 code-review defer 회수).
- **users**: ``ck_users_role``(role enum DB CHECK — P3 회수, 시드 admin 포함 3종 허용).

**제약명 일치(프리플라이트 ④b — 2.1 이중접두 함정의 ALTER 판):** ``op.f(...)``로 **이미
해석된 최종명**을 그대로 전달한다. 바 문자열을 주면 ck 네이밍 규약(``ck_%(table)s_
%(constraint_name)s``)이 한 번 더 접두해 ``ck_rooms_ck_rooms_room_type`` 식 이중접두가 된다.
``op.f()``가 그 재적용을 차단하므로 최종 DB 제약명이 모델 ``__table_args__`` 해석명과
정확히 일치한다(``tests/rooms/test_models.py`` + 오프라인 ``--sql``로 회귀 검증).

**운영 DB 미변조:** 라이브 연결 없이 ``alembic upgrade head --sql``(오프라인)로 DDL을
실증했다(1.4/1.7/2.1 패턴). rooms는 빈 테이블, users 기존 행은 유효 role이라 CHECK와 충돌 없음.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c4f1a9d3e7'
down_revision: Union[str, Sequence[str], None] = 'e3dbb470902f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """rooms UNIQUE + 값범위 CHECK + users role CHECK 추가(제약명은 op.f로 최종명 고정)."""
    # rooms: 제공자당 1개(AC4).
    op.create_unique_constraint(op.f("uq_rooms_provider_id"), "rooms", ["provider_id"])
    # rooms: 값 범위 CHECK(P3 enum + 2.1 defer 회수).
    op.create_check_constraint(
        op.f("ck_rooms_room_type"), "rooms", "room_type IN ('open', 'private')"
    )
    op.create_check_constraint(
        op.f("ck_rooms_price_per_hour_nonneg"), "rooms", "price_per_hour >= 0"
    )
    op.create_check_constraint(
        op.f("ck_rooms_capacity_positive"), "rooms", "capacity >= 1"
    )
    op.create_check_constraint(
        op.f("ck_rooms_lat_range"), "rooms", "lat >= -90 AND lat <= 90"
    )
    op.create_check_constraint(
        op.f("ck_rooms_lng_range"), "rooms", "lng >= -180 AND lng <= 180"
    )
    # users: role enum DB CHECK(P3 회수 — 시드 admin 포함 3종).
    op.create_check_constraint(
        op.f("ck_users_role"), "users", "role IN ('booker', 'provider', 'admin')"
    )


def downgrade() -> None:
    """제약 제거(생성 역순)."""
    op.drop_constraint(op.f("ck_users_role"), "users", type_="check")
    op.drop_constraint(op.f("ck_rooms_lng_range"), "rooms", type_="check")
    op.drop_constraint(op.f("ck_rooms_lat_range"), "rooms", type_="check")
    op.drop_constraint(op.f("ck_rooms_capacity_positive"), "rooms", type_="check")
    op.drop_constraint(op.f("ck_rooms_price_per_hour_nonneg"), "rooms", type_="check")
    op.drop_constraint(op.f("ck_rooms_room_type"), "rooms", type_="check")
    op.drop_constraint(op.f("uq_rooms_provider_id"), "rooms", type_="unique")
