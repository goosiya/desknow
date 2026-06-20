"""refresh_tokens 마이그레이션 + 로그인/세션 왕복 통합 테스트 (Story 1.8 — 라이브 DB, 기본 skip).

``TEST_DATABASE_URL``(PostgreSQL+pgvector 가능 DB)이 설정된 경우에만 실행한다.
CI에 라이브 DB가 없으면 자동 skip → 회귀 0(1.4/1.7 패턴).

검증: ``alembic upgrade head`` 후 ⓐ ``refresh_tokens`` 테이블 + ``uq_refresh_tokens_token_hash``
UNIQUE + ``fk_refresh_tokens_user_id_users`` FK 존재, ⓑ 가입→로그인(refresh 해시 1행 생성)→
회전(옛 행 삭제·새 행 생성)→로그아웃(행 삭제) 왕복, ⓒ 회전된 refresh 재사용 → 401.
``downgrade base``로 정리한다.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# alembic.ini는 apps/api 루트에 있다(tests/integration/ → parents[2] = apps/api).
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL or "supabase" in TEST_DATABASE_URL,
    # downgrade base = 전 테이블 DROP -> Supabase 등 데이터 보유 DB 금지(일회용 DB만).
    reason="TEST_DATABASE_URL 미설정, 또는 Supabase 등 데이터 보유 DB(downgrade base=전 테이블 DROP 방지) — 일회용 DB에서만 실행.",
)


def test_refresh_tokens_migration_and_session_roundtrip(monkeypatch):
    from alembic.config import Config
    from sqlalchemy import inspect
    from sqlmodel import Session, select

    from alembic import command
    from app.auth.models import RefreshToken
    from app.auth.schemas import RegisterRequest
    from app.auth.service import (
        authenticate_user,
        issue_token_pair,
        register_user,
        revoke_refresh_token,
        rotate_token_pair,
    )
    from app.core.config import get_settings
    from app.core.db import get_engine
    from app.core.errors import DomainError
    from app.core.security import hash_token

    # env.py가 settings에서 URL을 읽으므로 필수 키 + 테스트 DB를 환경에 주입한다.
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test")
    monkeypatch.setenv("KAKAO_JS_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-bytes-long-xx")
    get_settings.cache_clear()
    get_engine.cache_clear()

    cfg = Config(str(ALEMBIC_INI))
    try:
        command.upgrade(cfg, "head")
        engine = get_engine()

        # ⓐ refresh_tokens 테이블 + UNIQUE + FK 존재(규약명).
        inspector = inspect(engine)
        assert "refresh_tokens" in inspector.get_table_names()
        uniques = {uc["name"] for uc in inspector.get_unique_constraints("refresh_tokens")}
        assert "uq_refresh_tokens_token_hash" in uniques
        fks = {fk["name"] for fk in inspector.get_foreign_keys("refresh_tokens")}
        assert "fk_refresh_tokens_user_id_users" in fks

        # ⓑ 가입 → 로그인(refresh 해시 1행 생성, 원문 아님).
        with Session(engine) as session:
            register_user(
                session,
                RegisterRequest(email="sess@example.com", password="Test1234!", role="booker"),
            )
        with Session(engine) as session:
            user = authenticate_user(session, "sess@example.com", "Test1234!")
            tokens = issue_token_pair(session, user)
        raw1 = tokens.refresh_token
        with Session(engine) as session:
            rows = session.exec(
                select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw1))
            ).all()
            assert len(rows) == 1
            assert rows[0].token_hash != raw1  # 원문 미저장(해시만)

        # 회전: 옛 해시 삭제 + 새 해시 생성.
        with Session(engine) as session:
            new_tokens = rotate_token_pair(session, raw1)
        raw2 = new_tokens.refresh_token
        with Session(engine) as session:
            assert (
                session.exec(
                    select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw1))
                ).first()
                is None
            )
            assert (
                session.exec(
                    select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw2))
                ).first()
                is not None
            )

        # ⓒ 회전된(옛) refresh 재사용 → 401(DB에 해시 없음).
        with Session(engine) as session:
            with pytest.raises(DomainError):
                rotate_token_pair(session, raw1)

        # 로그아웃: 새 refresh 행 삭제 + 멱등(재호출 무에러).
        with Session(engine) as session:
            revoke_refresh_token(session, raw2)
        with Session(engine) as session:
            assert (
                session.exec(
                    select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw2))
                ).first()
                is None
            )
        with Session(engine) as session:
            revoke_refresh_token(session, raw2)  # 멱등: 이미 없어도 정상 종료
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
        get_engine.cache_clear()
