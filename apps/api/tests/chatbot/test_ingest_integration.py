"""인제스트 실 연동 통합 테스트 (Story 7.2 — AC5, 라이브 DB+키 필요, 기본 skip).

``TEST_DATABASE_URL``(PostgreSQL+pgvector)이 설정된 경우에만 실행한다. CI에 라이브 DB가 없으면
자동 skip → 회귀 0(test_migrations.py 게이트 패턴 재사용). 실 OpenAI 임베딩 호출이 일어나므로
``OPENAI_API_KEY``도 실키여야 한다(미설정 시 본 테스트 내부에서 skip).

검증(스파이크 verify.sql 정신): 실 DB에 마이그레이션 적용 → 작은 문서를 실 임베딩으로 적재 →
코사인 유사도 검색이 그 청크를 1위로 반환 → 재인제스트가 멱등(행 증가 0). 종료 시 정리한다.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL 미설정 — 라이브 DB 통합 테스트를 skip 합니다.",
)


def test_real_ingest_then_similarity_search(tmp_path: Path, monkeypatch) -> None:
    """실 임베딩으로 적재 후 코사인 유사도 검색이 적재 청크를 반환하고, 재인제스트가 멱등이다."""
    from alembic.config import Config
    from sqlalchemy import text
    from sqlmodel import Session

    from alembic import command
    from app.chatbot.ingest import (
        SqlDocumentChunkStore,
        build_embedder,
        ingest_corpus,
    )
    from app.core.config import get_settings
    from app.core.db import get_engine

    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY 미설정 — 실 임베딩 통합 테스트를 skip 합니다.")

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test")
    monkeypatch.setenv("KAKAO_JS_KEY", "test")
    get_settings.cache_clear()
    get_engine.cache_clear()

    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")

    (tmp_path / "guide.txt").write_text(
        "데스크나우 예약 취소는 이용 시작 6시간 전까지 가능합니다.", encoding="utf-8"
    )
    embedder = build_embedder()
    try:
        engine = get_engine()
        with Session(engine) as session:
            store = SqlDocumentChunkStore(session)
            report = ingest_corpus(store, tmp_path, embedder)
            assert report.succeeded == ["guide.txt"]

        # 코사인 유사도 검색(<=>): 질의 임베딩으로 가장 가까운 청크가 적재한 문서여야 한다.
        # 바인드 파라미터는 문자열 리터럴이므로 (:q)::vector로 명시 캐스트해야 한다 —
        # 캐스트 없으면 psycopg가 VARCHAR로 바인딩해 `vector <=> character varying`
        # 연산자 부재로 실패.
        query_vector = embedder.embed_documents(["예약을 취소하고 싶어요"])[0]
        literal = "[" + ",".join(str(x) for x in query_vector) + "]"
        with Session(engine) as session:
            row = session.execute(
                text(
                    "SELECT source_path FROM document_chunks "
                    "ORDER BY embedding <=> (:q)::vector LIMIT 1"
                ).bindparams(q=literal)
            ).first()
            assert row is not None and row[0] == "guide.txt"

        # 멱등: 동일 내용 재인제스트는 스킵(행 증가 0).
        with Session(engine) as session:
            store = SqlDocumentChunkStore(session)
            again = ingest_corpus(store, tmp_path, embedder)
            assert again.skipped == ["guide.txt"]
    finally:
        # 적재 행 정리(다른 통합 테스트·실 데이터 오염 방지). 테이블/확장은 보존한다.
        with Session(get_engine()) as session:
            session.execute(text("DELETE FROM document_chunks"))
            session.commit()
        get_settings.cache_clear()
        get_engine.cache_clear()
