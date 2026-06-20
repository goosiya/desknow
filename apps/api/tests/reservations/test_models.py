"""reservations 모델 메타데이터 제약명 검증 (Story 4.1 — AC4 회귀 가드).

DB 불필요 — ``SQLModel.metadata``에서 제약/인덱스 이름을 추출해 검증한다(2.1
``tests/rooms/test_models.py`` 미러):

1. **모든 제약명 ≤63자**(PostgreSQL 식별자 한계 — 절단 시 autogenerate 불일치·충돌).
   특히 deferred L71(1.4 — "63자 한계, 트리거=4.1 복합 UNIQUE")을 본 스토리에서 회수하는
   회귀 가드다(가장 긴 FK 자동명 ``fk_reservation_slots_reservation_id_reservations``=48자 ✓).
2. **복합 제약 명시 단축명이 의도대로 해석**(특히 CHECK ``ck_reservations_status``가 ``ck``
   규약에 의해 이중접두 ``ck_reservations_ck_reservations_status``로 렌더되지 않는지 — 2.1 함정).

``app.core.db`` import로 네이밍 규약을 먼저 등록한 뒤 모델을 import 한다(규약은 모델 정의
이전에 ``SQLModel.metadata``에 설정돼야 자동 적용된다 — conftest도 이미 import하지만 명시).
"""
from __future__ import annotations

from sqlmodel import SQLModel

import app.auth.models  # noqa: F401 — users 테이블(FK 대상) 등록
import app.core.db  # noqa: F401 — 네이밍 규약 등록(import 시점)
import app.rooms.models  # noqa: F401 — rooms 테이블(FK 대상) 등록
from app.reservations import models  # noqa: F401 — 2테이블을 SQLModel.metadata에 등록

_RESERVATIONS_TABLES = ("reservations", "reservation_slots")

# PostgreSQL 식별자 한계(바이트). 모든 이름은 ASCII라 글자수 == 바이트수.
_PG_IDENTIFIER_LIMIT = 63


def _constraint_and_index_names(table_name: str) -> set[str]:
    table = SQLModel.metadata.tables[table_name]
    names = {c.name for c in table.constraints if c.name is not None}
    names |= {idx.name for idx in table.indexes if idx.name is not None}
    return names


def test_all_constraint_names_within_63_chars() -> None:
    """AC4: reservations 도메인의 모든 제약·인덱스 이름이 ≤63자(deferred L71 회수 회귀 가드)."""
    too_long: list[tuple[str, int]] = []
    for tname in _RESERVATIONS_TABLES:
        for name in _constraint_and_index_names(tname):
            if len(name) > _PG_IDENTIFIER_LIMIT:
                too_long.append((name, len(name)))
    assert not too_long, f"63자 초과 제약명: {too_long}"


def test_expected_composite_constraint_names_present() -> None:
    """복합 UNIQUE·CHECK 명시 단축명이 의도대로(이중접두 없이) 존재한다."""
    slot_names = _constraint_and_index_names("reservation_slots")
    assert "uq_reservation_slots_room_slot" in slot_names

    resv_names = _constraint_and_index_names("reservations")
    # CHECK가 이중접두되지 않고 깔끔히 해석됐는지(2.1 함정 회귀 가드).
    assert "ck_reservations_status" in resv_names
    assert "ck_reservations_ck_reservations_status" not in resv_names


def test_expected_pk_fk_index_names_present() -> None:
    """단일 제약(PK/FK/INDEX)이 1.4 네이밍 규약대로 자동 부여됐다."""
    resv = _constraint_and_index_names("reservations")
    assert "pk_reservations" in resv
    assert "fk_reservations_booker_id_users" in resv
    assert "fk_reservations_room_id_rooms" in resv
    assert "idx_reservations_booker_id" in resv
    assert "idx_reservations_room_id" in resv

    slot = _constraint_and_index_names("reservation_slots")
    assert "pk_reservation_slots" in slot
    # FK 자동명 중 가장 긴 이름 — 48자로 ≤63 확인(deferred L71 회수의 핵심 케이스).
    assert "fk_reservation_slots_reservation_id_reservations" in slot
    assert "fk_reservation_slots_room_id_rooms" in slot
    assert "idx_reservation_slots_reservation_id" in slot
