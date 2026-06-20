"""notifications 모델 메타데이터 제약명 검증 (Story 5.1 — AC1 회귀 가드).

DB 불필요 — ``SQLModel.metadata``에서 제약/인덱스 이름을 추출해 검증한다(4.1
``tests/reservations/test_models.py`` 미러):

1. **모든 제약명 ≤63자**(PostgreSQL 식별자 한계 — 절단 시 autogenerate 불일치·충돌).
   가장 긴 FK 자동명 ``fk_notifications_reservation_id_reservations``=44자 ✓.
2. **복합 제약 명시 단축명이 의도대로 해석**(특히 CHECK ``ck_notifications_type``가 ``ck`` 규약에
   의해 이중접두 ``ck_notifications_ck_notifications_type``로 렌더되지 않는지 — 2.1 함정).

``app.core.db`` import로 네이밍 규약을 먼저 등록한 뒤 모델을 import 한다(규약은 모델 정의
이전에 ``SQLModel.metadata``에 설정돼야 자동 적용된다 — conftest도 이미 import하지만 명시).
"""
from __future__ import annotations

from sqlmodel import SQLModel

import app.auth.models  # noqa: F401 — users 테이블(FK 대상) 등록
import app.core.db  # noqa: F401 — 네이밍 규약 등록(import 시점)
import app.reservations.models  # noqa: F401 — reservations 테이블(FK 대상) 등록
import app.rooms.models  # noqa: F401 — rooms 테이블(FK 그래프 완성) 등록
from app.notifications import models  # noqa: F401 — notifications를 SQLModel.metadata에 등록

# PostgreSQL 식별자 한계(바이트). 모든 이름은 ASCII라 글자수 == 바이트수.
_PG_IDENTIFIER_LIMIT = 63


def _constraint_and_index_names(table_name: str) -> set[str]:
    table = SQLModel.metadata.tables[table_name]
    names = {c.name for c in table.constraints if c.name is not None}
    names |= {idx.name for idx in table.indexes if idx.name is not None}
    return names


def test_all_constraint_names_within_63_chars() -> None:
    """AC1: notifications 도메인의 모든 제약·인덱스 이름이 ≤63자(절단 회귀 가드)."""
    too_long = [
        (name, len(name))
        for name in _constraint_and_index_names("notifications")
        if len(name) > _PG_IDENTIFIER_LIMIT
    ]
    assert not too_long, f"63자 초과 제약명: {too_long}"


def test_expected_composite_constraint_names_present() -> None:
    """복합 UNIQUE·CHECK 명시 단축명이 의도대로(이중접두 없이) 존재한다."""
    names = _constraint_and_index_names("notifications")
    assert "uq_notifications_user_reservation_type" in names
    # CHECK가 이중접두되지 않고 깔끔히 해석됐는지(2.1 함정 회귀 가드).
    assert "ck_notifications_type" in names
    assert "ck_notifications_ck_notifications_type" not in names


def test_expected_pk_fk_index_names_present() -> None:
    """단일 제약(PK/FK/INDEX)이 1.4 네이밍 규약대로 자동 부여됐다."""
    names = _constraint_and_index_names("notifications")
    assert "pk_notifications" in names
    assert "fk_notifications_user_id_users" in names
    # FK 자동명 중 가장 긴 이름 — 44자로 ≤63 확인.
    assert "fk_notifications_reservation_id_reservations" in names
    assert "idx_notifications_user_id" in names
    assert "idx_notifications_reservation_id" in names


def test_check_constraint_renders_expected_sql() -> None:
    """type CHECK가 두 허용값을 강제한다(DB 방어 — 스키마 Literal과 이중)."""
    table = SQLModel.metadata.tables["notifications"]
    checks = [
        str(c.sqltext)
        for c in table.constraints
        if c.name == "ck_notifications_type"
    ]
    assert checks, "ck_notifications_type CHECK가 존재해야 한다"
    assert "reservation_reminder" in checks[0]
    assert "status_change" in checks[0]
