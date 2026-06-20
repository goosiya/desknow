"""users 마이그레이션 + 가입 왕복 통합 테스트 (Story 1.7 — 라이브 DB 필요, 기본 skip).

``TEST_DATABASE_URL``(PostgreSQL+pgvector 가능 DB)이 설정된 경우에만 실행한다.
CI에 라이브 DB가 없으면 자동 skip → 회귀 0(1.4 패턴).

검증: ``alembic upgrade head`` 후 ⓐ ``users`` 테이블 + ``uq_users_email`` 제약 존재,
ⓑ 실제 가입 왕복(소문자 정규화·Argon2 해시 저장), ⓒ 동일 이메일 재삽입 시 UNIQUE
위반(``IntegrityError``)을 확인하고, ``downgrade base``로 정리한다.
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
    reason=(
        "TEST_DATABASE_URL 미설정, 또는 Supabase 등 데이터 보유 DB"
        "(downgrade base=전 테이블 DROP 방지) — 일회용 DB에서만 실행."
    ),
)


def test_users_migration_and_register_roundtrip(monkeypatch):
    from alembic.config import Config
    from sqlalchemy import inspect
    from sqlalchemy.exc import IntegrityError
    from sqlmodel import Session, select

    from alembic import command
    from app.auth.models import User
    from app.auth.schemas import RegisterRequest
    from app.auth.service import register_user
    from app.core.config import get_settings
    from app.core.db import get_engine
    from app.core.errors import DomainError

    # env.py가 settings에서 URL을 읽으므로 필수 키 + 테스트 DB를 환경에 주입한다.
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test")
    monkeypatch.setenv("KAKAO_JS_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    # JWT_SECRET_KEY는 Story 1.8부터 필수(env.py가 settings 로드) — ≥32자.
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-bytes-long-xx")
    get_settings.cache_clear()
    get_engine.cache_clear()

    cfg = Config(str(ALEMBIC_INI))
    try:
        command.upgrade(cfg, "head")

        engine = get_engine()
        inspector = inspect(engine)
        assert "users" in inspector.get_table_names(), "마이그레이션 후 users 테이블 존재 필요"
        uniques = {uc["name"] for uc in inspector.get_unique_constraints("users")}
        assert "uq_users_email" in uniques, "uq_users_email UNIQUE 제약이 존재해야 한다"

        # ⓑ 실제 가입 왕복: 소문자 정규화 + Argon2 해시 저장.
        with Session(engine) as session:
            req = RegisterRequest(email="RT@Example.com", password="Test1234!", role="booker")
            created = register_user(session, req)
            assert created.email == "rt@example.com"
            assert created.password_hash.startswith("$argon2")

        # 저장 확인.
        with Session(engine) as session:
            fetched = session.exec(select(User).where(User.email == "rt@example.com")).first()
            assert fetched is not None
            assert fetched.is_active is True

        # ⓒ 동일 이메일 재가입: 서비스 선검사로 EMAIL_TAKEN.
        with Session(engine) as session:
            with pytest.raises(DomainError):
                register_user(
                    session,
                    RegisterRequest(email="rt@example.com", password="Test1234!", role="provider"),
                )

        # UNIQUE 제약 자체(진실의 원천)도 직접 확인: 선검사 우회 raw 삽입 → IntegrityError.
        with Session(engine) as session:
            session.add(
                User(email="rt@example.com", password_hash="$argon2id$x", role="booker")
            )
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        command.downgrade(cfg, "base")
        get_settings.cache_clear()
        get_engine.cache_clear()
