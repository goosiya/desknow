"""rooms 모델 메타데이터 제약명 검증 (Story 2.1 — AC4 회귀 가드).

DB 불필요 — ``SQLModel.metadata``에서 제약/인덱스 이름을 추출해 검증한다:

1. **모든 제약명 ≤63자**(PostgreSQL 식별자 한계 — 절단 시 autogenerate 불일치·충돌).
2. **복합 제약 명시 단축명이 의도대로 해석**(특히 CHECK가 ``ck`` 규약에 의해 이중접두
   ``ck_business_hours_ck_business_hours_weekday``로 렌더되지 않는지 — 이 프로젝트 첫 CHECK라
   처음 드러난 함정. 마이그레이션도 동일 이름이어야 drift가 없다).

``app.core.db`` import로 네이밍 규약을 먼저 등록한 뒤 모델을 import 한다(규약은 모델 정의
이전에 ``SQLModel.metadata``에 설정돼야 자동 적용된다 — conftest도 이미 import하지만 명시).
"""
from __future__ import annotations

from sqlmodel import SQLModel

import app.auth.models  # noqa: F401 — users 테이블(ck_users_role) 등록(2.2 P3)
import app.core.db  # noqa: F401 — 네이밍 규약 등록(import 시점)
from app.rooms import models  # noqa: F401 — 3테이블을 SQLModel.metadata에 등록

_ROOMS_TABLES = ("rooms", "business_hours", "holiday_exceptions")

# PostgreSQL 식별자 한계(바이트). 모든 이름은 ASCII라 글자수 == 바이트수.
_PG_IDENTIFIER_LIMIT = 63


def _constraint_and_index_names(table_name: str) -> set[str]:
    table = SQLModel.metadata.tables[table_name]
    names = {c.name for c in table.constraints if c.name is not None}
    names |= {idx.name for idx in table.indexes if idx.name is not None}
    return names


def test_all_constraint_names_within_63_chars() -> None:
    """AC4: rooms 도메인의 모든 제약·인덱스 이름이 ≤63자."""
    too_long: list[tuple[str, int]] = []
    for tname in _ROOMS_TABLES:
        for name in _constraint_and_index_names(tname):
            if len(name) > _PG_IDENTIFIER_LIMIT:
                too_long.append((name, len(name)))
    assert not too_long, f"63자 초과 제약명: {too_long}"


def test_expected_composite_constraint_names_present() -> None:
    """복합 UNIQUE·CHECK 명시 단축명이 의도대로(이중접두 없이) 존재한다."""
    bh_names = _constraint_and_index_names("business_hours")
    assert "uq_business_hours_room_id_weekday" in bh_names
    # CHECK가 이중접두되지 않고 깔끔히 해석됐는지(함정 회귀 가드).
    assert "ck_business_hours_weekday" in bh_names
    assert "ck_business_hours_hours_order" in bh_names
    assert "ck_business_hours_ck_business_hours_weekday" not in bh_names

    hx_names = _constraint_and_index_names("holiday_exceptions")
    assert "uq_holiday_exceptions_room_id_holiday_date" in hx_names


def test_expected_pk_fk_index_names_present() -> None:
    """단일 제약(PK/FK/INDEX)이 1.4 네이밍 규약대로 자동 부여됐다."""
    assert "pk_rooms" in _constraint_and_index_names("rooms")
    assert "fk_rooms_provider_id_users" in _constraint_and_index_names("rooms")
    assert "idx_rooms_provider_id" in _constraint_and_index_names("rooms")
    assert "fk_business_hours_room_id_rooms" in _constraint_and_index_names("business_hours")
    assert "idx_business_hours_room_id" in _constraint_and_index_names("business_hours")
    assert (
        "fk_holiday_exceptions_room_id_rooms"
        in _constraint_and_index_names("holiday_exceptions")
    )


def test_story_2_2_write_path_constraint_names_present() -> None:
    """Story 2.2가 추가한 UNIQUE/CHECK 제약명이 이중접두 없이 의도대로 존재한다(AC4·AC6).

    마이그레이션 b2c4f1a9d3e7의 오프라인 --sql 산출명과 정확히 일치해야 한다(drift 방지).
    """
    rooms = _constraint_and_index_names("rooms")
    assert "uq_rooms_provider_id" in rooms  # 제공자당 1개(AC4)
    assert "ck_rooms_room_type" in rooms  # P3 enum
    assert "ck_rooms_price_per_hour_nonneg" in rooms  # 2.1 defer 회수
    assert "ck_rooms_capacity_positive" in rooms
    assert "ck_rooms_lat_range" in rooms
    assert "ck_rooms_lng_range" in rooms
    # 이중접두 회귀 가드(2.1 함정).
    assert "ck_rooms_ck_rooms_room_type" not in rooms

    users = _constraint_and_index_names("users")
    assert "ck_users_role" in users  # P3 role CHECK
    assert "ck_users_ck_users_role" not in users


def test_story_2_2_constraint_names_within_63_chars() -> None:
    """rooms + users 신규 제약명도 ≤63자(PostgreSQL 식별자 한계)."""
    for tname in ("rooms", "users"):
        for name in _constraint_and_index_names(tname):
            assert len(name) <= _PG_IDENTIFIER_LIMIT, f"63자 초과: {name}"
