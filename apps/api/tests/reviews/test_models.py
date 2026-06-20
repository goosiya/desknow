"""reviews 모델 메타데이터 제약명 검증 (Story 5.5 — AC7① 회귀 가드).

DB 불필요 — ``SQLModel.metadata``에서 제약/인덱스 이름을 추출해 검증한다(4.1
``tests/reservations/test_models.py`` 미러):

1. **모든 제약명 ≤63자**(PostgreSQL 식별자 한계 — 절단 시 autogenerate 불일치·충돌).
   가장 긴 FK 자동명 ``fk_reviews_reservation_id_reservations``=38자 ≤63 ✓.
2. **단일컬럼 UNIQUE·CHECK 명시 단축명이 의도대로 해석**(특히 CHECK ``ck_reviews_rating``가 ``ck``
   규약에 의해 이중접두 ``ck_reviews_ck_reviews_rating``로 렌더되지 않는지 — 2.1 함정).

``app.core.db`` import로 네이밍 규약을 먼저 등록한 뒤 모델을 import 한다(규약은 모델 정의
이전에 ``SQLModel.metadata``에 설정돼야 자동 적용된다 — conftest도 이미 import하지만 명시).
"""
from __future__ import annotations

from sqlmodel import SQLModel

import app.auth.models  # noqa: F401 — users 테이블(FK 대상) 등록
import app.core.db  # noqa: F401 — 네이밍 규약 등록(import 시점)
import app.reservations.models  # noqa: F401 — reservations 테이블(FK 대상) 등록
import app.rooms.models  # noqa: F401 — rooms 테이블(FK 대상) 등록
from app.reviews import models  # noqa: F401 — reviews 테이블을 SQLModel.metadata에 등록

_REVIEWS_TABLES = ("reviews", "review_replies")

# PostgreSQL 식별자 한계(바이트). 모든 이름은 ASCII라 글자수 == 바이트수.
_PG_IDENTIFIER_LIMIT = 63


def _constraint_and_index_names(table_name: str) -> set[str]:
    table = SQLModel.metadata.tables[table_name]
    names = {c.name for c in table.constraints if c.name is not None}
    names |= {idx.name for idx in table.indexes if idx.name is not None}
    return names


def test_all_constraint_names_within_63_chars() -> None:
    """AC7①: reviews 도메인의 모든 제약·인덱스 이름이 ≤63자(63바이트 절단 회귀 가드)."""
    too_long: list[tuple[str, int]] = []
    for tname in _REVIEWS_TABLES:
        for name in _constraint_and_index_names(tname):
            if len(name) > _PG_IDENTIFIER_LIMIT:
                too_long.append((name, len(name)))
    assert not too_long, f"63자 초과 제약명: {too_long}"


def test_expected_named_constraints_present() -> None:
    """단일컬럼 UNIQUE·CHECK 명시 단축명이 의도대로(이중접두 없이) 존재한다."""
    names = _constraint_and_index_names("reviews")
    # 예약당 1회 UNIQUE(중복 후기 차단의 진실의 원천).
    assert "uq_reviews_reservation" in names
    # CHECK가 이중접두되지 않고 깔끔히 해석됐는지(2.1 함정 회귀 가드).
    assert "ck_reviews_rating" in names
    assert "ck_reviews_ck_reviews_rating" not in names


def test_expected_pk_fk_index_names_present() -> None:
    """단일 제약(PK/FK/INDEX)이 1.4 네이밍 규약대로 자동 부여됐다."""
    names = _constraint_and_index_names("reviews")
    assert "pk_reviews" in names
    # FK 자동명 중 가장 긴 이름 — 38자로 ≤63 확인.
    assert "fk_reviews_reservation_id_reservations" in names
    assert "fk_reviews_room_id_rooms" in names
    assert "fk_reviews_booker_id_users" in names
    assert "idx_reviews_room_id" in names


def test_review_replies_named_constraints_present() -> None:
    """답글 테이블(5.6): 후기당 1회 UNIQUE 명시 단축명 + PK/FK 자동명이 의도대로 존재한다."""
    names = _constraint_and_index_names("review_replies")
    # 후기당 1회 UNIQUE(중복 답글 차단의 진실의 원천 — uq 규약상 bare 명시명 그대로).
    assert "uq_review_replies_review" in names
    assert "pk_review_replies" in names
    # FK 자동명(가장 긴 ``fk_review_replies_provider_id_users``=39자 ≤63 확인).
    assert "fk_review_replies_review_id_reviews" in names
    assert "fk_review_replies_provider_id_users" in names
    # 답글엔 별점이 없어 CHECK가 없다(op.f() 이중접두 함정 비해당).
    assert not any(n.startswith("ck_review_replies") for n in names)
