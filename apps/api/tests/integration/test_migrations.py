"""Alembic 마이그레이션 왕복 통합 테스트 (Story 1.4 — 라이브 DB 필요, 기본 skip).

``TEST_DATABASE_URL``(PostgreSQL+pgvector 가능 DB)이 설정된 경우에만 실행한다.
CI에 라이브 DB가 없으면 자동 skip → 회귀 0.

검증: ``alembic upgrade head`` 후 pgvector 확장이 존재하고, ``downgrade base``로
왕복이 가능하다(베이스라인이 빈 스키마 + 확장만이라는 AC2 불변식 확인).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# alembic.ini는 apps/api 루트에 있다. cwd가 아니라 이 파일 기준으로 앵커링해
# (tests/integration/ → parents[2] = apps/api) 어느 cwd에서 pytest를 돌려도 안정적으로 찾는다.
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL or "supabase" in TEST_DATABASE_URL,
    # ★ downgrade base가 전 테이블 DROP → Supabase 등 데이터 보유 DB 금지(일회용 DB만).
    reason="TEST_DATABASE_URL 미설정, 또는 Supabase 등 데이터 보유 DB(downgrade base=전 테이블 DROP 방지) — 일회용 DB에서만 실행.",
)


def test_migration_upgrade_downgrade_roundtrip(monkeypatch):
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from alembic import command
    from app.core.config import get_settings

    # env.py가 settings에서 URL을 읽으므로, 필수 키 + 테스트 DB를 환경에 주입한다.
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test")
    monkeypatch.setenv("KAKAO_JS_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    get_settings.cache_clear()

    cfg = Config(str(ALEMBIC_INI))
    try:
        command.upgrade(cfg, "head")

        engine = create_engine(get_settings().DATABASE_URL)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).first()
        assert row is not None, "upgrade 후 pgvector 확장이 존재해야 한다"
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
