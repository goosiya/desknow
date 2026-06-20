"""chatbot 모델 메타데이터 제약명·벡터 차원 검증 (Story 7.2 — AC1 회귀 가드).

DB 불필요 — ``SQLModel.metadata``에서 제약/인덱스 이름과 벡터 컬럼 차원을 추출해 검증한다
(notifications ``test_models.py`` 미러). ``document_chunks``는 FK가 없어 타 도메인 import 불필요.

``app.core.db`` import로 네이밍 규약을 먼저 등록한 뒤 모델을 import 한다(규약은 모델 정의 이전에
``SQLModel.metadata``에 설정돼야 자동 적용된다).
"""
from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlmodel import SQLModel

import app.core.db  # noqa: F401 — 네이밍 규약 등록(import 시점)
from app.chatbot import models  # noqa: F401 — document_chunks를 SQLModel.metadata에 등록
from app.chatbot.models import EMBEDDING_DIM

# PostgreSQL 식별자 한계(바이트). 모든 이름은 ASCII라 글자수 == 바이트수.
_PG_IDENTIFIER_LIMIT = 63


def _constraint_and_index_names(table_name: str) -> set[str]:
    table = SQLModel.metadata.tables[table_name]
    names = {c.name for c in table.constraints if c.name is not None}
    names |= {idx.name for idx in table.indexes if idx.name is not None}
    return names


def test_all_constraint_names_within_63_chars() -> None:
    """AC1: document_chunks의 모든 제약·인덱스 이름이 ≤63자(절단 회귀 가드)."""
    too_long = [
        (name, len(name))
        for name in _constraint_and_index_names("document_chunks")
        if len(name) > _PG_IDENTIFIER_LIMIT
    ]
    assert not too_long, f"63자 초과 제약명: {too_long}"


def test_expected_composite_unique_name_present() -> None:
    """복합 UNIQUE 명시 단축명이 의도대로(이중접두 없이) 존재한다(멱등 이중 방어 — AC2)."""
    names = _constraint_and_index_names("document_chunks")
    assert "uq_document_chunks_source_path_chunk_index" in names


def test_expected_pk_and_index_names_present() -> None:
    """단일 제약(PK)·source_path 조회 인덱스가 1.4 네이밍 규약대로 자동 부여됐다."""
    names = _constraint_and_index_names("document_chunks")
    assert "pk_document_chunks" in names
    assert "idx_document_chunks_source_path" in names


def test_embedding_column_is_vector_1536() -> None:
    """AC1: embedding 컬럼이 pgvector ``Vector(1536)`` 타입이고 차원 상수와 일치한다."""
    assert EMBEDDING_DIM == 1536
    table = SQLModel.metadata.tables["document_chunks"]
    embedding_col = table.columns["embedding"]
    assert isinstance(embedding_col.type, Vector)
    assert embedding_col.type.dim == EMBEDDING_DIM
