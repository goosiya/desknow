"""가입 라우터 통합 테스트 (Story 1.7, AC1·AC2·AC3·AC4).

**DB 불필요** — ``app.dependency_overrides[get_session]``로 세션을 Fake로 교체하고,
``TestClient(app)``(모듈 레벨, lifespan 미실행 — 1.4 불변식 유지)로 엔드포인트를 검증한다.
오버라이드는 매 테스트 ``finally``에서 정리해 누수를 막는다.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.auth.models import RefreshToken, User
from app.core.db import get_session
from app.core.security import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
)
from app.core.time import now_utc
from app.main import app
from tests.auth.test_service import FakeSession

client = TestClient(app)

_VALID_BODY = {"email": "User@Example.com", "password": "Test1234!", "role": "booker"}


def _active_user(email: str = "user@example.com", role: str = "booker") -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("Test1234!"),
        role=role,
        is_active=True,
        created_at=datetime(2026, 6, 15, tzinfo=UTC),
    )


def _set_cookie_header(resp: Any, name: str) -> str | None:
    """응답의 Set-Cookie 헤더 중 ``name``에 해당하는 것을 찾아 반환한다(없으면 None)."""
    for header in resp.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header
    return None


@contextmanager
def _override_session(session: FakeSession) -> Iterator[None]:
    """get_session 의존성을 Fake 세션으로 교체하고, 종료 시 반드시 정리한다."""

    def _fake_get_session() -> Iterator[Any]:
        yield session

    app.dependency_overrides[get_session] = _fake_get_session
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def test_register_success_returns_201_user_resource() -> None:
    """유효 입력 → 201 + 사용자 리소스(해시 비노출, created_at ...Z)."""
    with _override_session(FakeSession(existing=None)):
        resp = client.post("/api/v1/auth/register", json=_VALID_BODY)

    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {"id", "email", "role", "is_active", "created_at"}
    assert "password_hash" not in body
    assert body["email"] == "user@example.com"  # 소문자 정규화
    assert body["role"] == "booker"
    assert body["is_active"] is True
    assert body["created_at"].endswith("Z")


def test_register_invalid_email_returns_422() -> None:
    """이메일 형식 위반 → 422 표준 스키마(VALIDATION_ERROR)."""
    with _override_session(FakeSession(existing=None)):
        resp = client.post(
            "/api/v1/auth/register",
            json={**_VALID_BODY, "email": "not-an-email"},
        )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_register_weak_password_returns_422() -> None:
    """약한 비밀번호 → 422 표준 스키마(VALIDATION_ERROR)."""
    with _override_session(FakeSession(existing=None)):
        resp = client.post(
            "/api/v1/auth/register",
            json={**_VALID_BODY, "password": "weak"},
        )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_register_admin_role_returns_422() -> None:
    """role=admin은 가입 거부 → 422(admin은 시드 전용)."""
    with _override_session(FakeSession(existing=None)):
        resp = client.post(
            "/api/v1/auth/register",
            json={**_VALID_BODY, "role": "admin"},
        )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_register_duplicate_email_returns_409() -> None:
    """이미 가입된 이메일 → 409 EMAIL_TAKEN 표준 스키마(AC3)."""
    existing = User(
        id=uuid.uuid4(),
        email="user@example.com",
        password_hash="$argon2id$x",
        role="booker",
        is_active=True,
        created_at=datetime(2026, 6, 15, tzinfo=UTC),
    )
    with _override_session(FakeSession(existing=existing)):
        resp = client.post("/api/v1/auth/register", json=_VALID_BODY)

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "EMAIL_TAKEN"


# ── 로그인(1.8, AC1·AC2) ──────────────────────────────────────────────────────
def test_login_success_returns_tokens_and_sets_cookies(auth_env: None) -> None:
    """로그인 성공 → 200 + 토큰 쌍(본문) + HttpOnly·Secure·SameSite 인증 쿠키(AC1)."""
    user = _active_user(role="provider")
    with _override_session(FakeSession(existing=user)):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "User@Example.com", "password": "Test1234!"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"access_token", "refresh_token", "token_type"}
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]

    access_cookie = _set_cookie_header(resp, ACCESS_COOKIE_NAME)
    refresh_cookie = _set_cookie_header(resp, REFRESH_COOKIE_NAME)
    assert access_cookie is not None and refresh_cookie is not None
    for cookie in (access_cookie, refresh_cookie):
        lowered = cookie.lower()
        assert "httponly" in lowered
        assert "secure" in lowered
        assert "samesite=lax" in lowered
    # refresh 쿠키 path는 /api/v1/auth로 한정(노출 최소화)
    assert "path=/api/v1/auth" in refresh_cookie.lower()


def test_login_invalid_credentials_returns_401(auth_env: None) -> None:
    """미존재/틀린 자격 → 401 UNAUTHENTICATED(enumeration 차단)."""
    with _override_session(FakeSession(existing=None)):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "missing@example.com", "password": "Test1234!"},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── 리프레시(1.8, AC3) ────────────────────────────────────────────────────────
def test_refresh_rotates_and_returns_new_tokens(auth_env: None) -> None:
    """유효 refresh(본문) → 200 + 새 토큰 쌍(회전) + 쿠키 갱신."""
    user = _active_user()
    raw = create_refresh_token(user.id)
    old_row = RefreshToken(
        user_id=user.id, token_hash=hash_token(raw), expires_at=now_utc() + timedelta(days=14)
    )
    session = FakeSession(
        users_by_id={user.id: user}, tokens_by_hash={hash_token(raw): old_row}
    )
    with _override_session(session):
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": raw})

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]
    assert old_row in session.deleted  # 회전 — 기존 무효화
    assert _set_cookie_header(resp, ACCESS_COOKIE_NAME) is not None


def test_refresh_invalid_token_returns_401(auth_env: None) -> None:
    """무효 refresh(DB 해시 부재) → 401."""
    user = _active_user()
    raw = create_refresh_token(user.id)
    session = FakeSession(users_by_id={user.id: user}, tokens_by_hash={})  # 행 부재
    with _override_session(session):
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": raw})

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_refresh_missing_token_returns_401(auth_env: None) -> None:
    """본문·쿠키 모두 토큰이 없으면 401."""
    with _override_session(FakeSession()):
        resp = client.post("/api/v1/auth/refresh", json={})

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── 로그아웃(1.8, AC4 — 멱등) ─────────────────────────────────────────────────
def test_logout_revokes_and_clears_cookies(auth_env: None) -> None:
    """로그아웃 → 204 + 인증 쿠키 만료(삭제) + refresh 해시 행 삭제."""
    raw = "raw-refresh-token"
    row = RefreshToken(
        user_id=uuid.uuid4(), token_hash=hash_token(raw), expires_at=now_utc()
    )
    session = FakeSession(tokens_by_hash={hash_token(raw): row})
    with _override_session(session):
        resp = client.post("/api/v1/auth/logout", json={"refresh_token": raw})

    assert resp.status_code == 204
    assert row in session.deleted
    # 쿠키 삭제는 Max-Age=0 만료 Set-Cookie로 표현된다.
    access_cookie = _set_cookie_header(resp, ACCESS_COOKIE_NAME)
    assert access_cookie is not None and "max-age=0" in access_cookie.lower()


def test_logout_is_idempotent_without_token(auth_env: None) -> None:
    """토큰 없이 호출해도 204(멱등)."""
    with _override_session(FakeSession()):
        resp = client.post("/api/v1/auth/logout", json={})

    assert resp.status_code == 204


# ── /me(1.8, AC1·AC5) ─────────────────────────────────────────────────────────
def test_me_with_valid_access_returns_user(auth_env: None) -> None:
    """유효 access(헤더 Bearer) → 200 + UserPublic(해시 비노출·created_at ...Z)."""
    user = _active_user(role="provider")
    token = create_access_token(user.id, user.role)
    with _override_session(FakeSession(users_by_id={user.id: user})):
        resp = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"id", "email", "role", "is_active", "created_at"}
    assert "password_hash" not in body
    assert body["role"] == "provider"
    assert body["created_at"].endswith("Z")


def test_me_without_token_returns_401(auth_env: None) -> None:
    """토큰 없이 /me 접근 → 401 UNAUTHENTICATED."""
    with _override_session(FakeSession()):
        resp = client.get("/api/v1/auth/me")

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"
