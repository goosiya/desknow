"""보안 프리미티브 테스트 (Story 1.7 해싱 + 1.8 JWT/RBAC).

DB 불필요. 해싱/검증은 순수 함수, JWT는 ``auth_env``로 시크릿만 주입(라이브 DB 무관),
RBAC 의존성은 미니 FastAPI 앱(test_errors 패턴)으로 실증한다.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import DomainError, ErrorCode, register_exception_handlers
from app.core.security import (
    ACCESS_COOKIE_NAME,
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    AuthPrincipal,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_principal,
    hash_password,
    hash_token,
    require_role,
    verify_password,
)
from app.core.time import now_utc

_PLAIN = "Test1234!"


def _sign(payload: dict[str, object]) -> str:
    """앱과 동일한 시크릿/알고리즘으로 임의 페이로드를 서명한다(손상 클레임 토큰 생성용).

    ``auth_env`` 적용 하에서 ``get_settings()``는 테스트 시크릿을 돌려준다.
    """
    return jwt.encode(payload, get_settings().JWT_SECRET_KEY, algorithm="HS256")


# ── 비밀번호 해싱(1.7) ────────────────────────────────────────────────────────
def test_hash_password_is_not_plaintext_and_argon2() -> None:
    """해시는 평문과 다르고 Argon2 포맷(``$argon2``)이다(NFR-6)."""
    hashed = hash_password(_PLAIN)
    assert hashed != _PLAIN
    assert hashed.startswith("$argon2")


def test_verify_password_roundtrip() -> None:
    """올바른 비밀번호는 True, 틀린 비밀번호는 False(인자 순서 verify(password, hash))."""
    hashed = hash_password(_PLAIN)
    assert verify_password(_PLAIN, hashed) is True
    assert verify_password("WrongPass9!", hashed) is False


def test_hash_password_uses_random_salt() -> None:
    """같은 비밀번호라도 매 해시가 다르다(솔트 무작위성)."""
    assert hash_password(_PLAIN) != hash_password(_PLAIN)


# ── verify_password fail-closed(1.8 — 1.7 deferred 회수) ──────────────────────
@pytest.mark.parametrize("bad_hash", ["not-a-hash", "", "$argon2id$broken"])
def test_verify_password_fail_closed_on_corrupt_hash(bad_hash: str) -> None:
    """손상/빈/파싱불가 해시는 예외 없이 False를 반환한다(fail-open 차단)."""
    assert verify_password("anything", bad_hash) is False


# ── JWT 발급/검증(1.8) ────────────────────────────────────────────────────────
def test_access_token_roundtrip(auth_env: None) -> None:
    """access 토큰 발급→디코드로 sub(user_id)·role·type을 복원한다."""
    uid = uuid.uuid4()
    token = create_access_token(uid, "provider")
    claims = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    assert claims["sub"] == str(uid)
    assert claims["role"] == "provider"
    assert claims["type"] == TOKEN_TYPE_ACCESS


def test_refresh_token_roundtrip_has_jti_no_role(auth_env: None) -> None:
    """refresh 토큰은 jti(고유성)를 가지며 role 클레임을 담지 않는다(회전 시 DB 최신 role)."""
    uid = uuid.uuid4()
    token = create_refresh_token(uid)
    claims = decode_token(token, expected_type=TOKEN_TYPE_REFRESH)
    assert claims["sub"] == str(uid)
    assert claims["type"] == TOKEN_TYPE_REFRESH
    assert "jti" in claims
    assert "role" not in claims


def test_refresh_tokens_are_unique_per_issue(auth_env: None) -> None:
    """jti 랜덤으로 같은 사용자·동시각 발급이라도 토큰(해시)이 고유하다."""
    uid = uuid.uuid4()
    fixed = now_utc()
    t1 = create_refresh_token(uid, now=fixed)
    t2 = create_refresh_token(uid, now=fixed)
    assert t1 != t2
    assert hash_token(t1) != hash_token(t2)


def test_decode_expired_token_raises_401(auth_env: None) -> None:
    """만료된 토큰은 401 UNAUTHENTICATED로 거부된다(now 주입으로 결정적)."""
    past = now_utc() - timedelta(hours=1)  # exp = past + 15분 = 45분 전(만료)
    token = create_access_token(uuid.uuid4(), "booker", now=past)
    with pytest.raises(DomainError) as exc_info:
        decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED
    assert exc_info.value.status_code == 401


def test_decode_wrong_type_raises_401(auth_env: None) -> None:
    """access를 refresh로(또는 반대로) 디코드하면 401(교차 사용 차단)."""
    token = create_access_token(uuid.uuid4(), "booker")
    with pytest.raises(DomainError) as exc_info:
        decode_token(token, expected_type=TOKEN_TYPE_REFRESH)
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED


def test_decode_forged_token_raises_401(auth_env: None) -> None:
    """다른 시크릿으로 서명한(위조) 토큰·임의 문자열은 401로 거부된다.

    (마지막 base64url 글자 변조는 패딩 비트만 바꿔 서명이 동일해질 수 있어 비결정적 →
    명확히 다른 시크릿 서명으로 InvalidSignatureError를 결정적으로 유발한다.)
    """
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "booker", "type": TOKEN_TYPE_ACCESS},
        key="a-completely-different-secret-key-32bytes-xx",
        algorithm="HS256",
    )
    with pytest.raises(DomainError):
        decode_token(forged, expected_type=TOKEN_TYPE_ACCESS)
    with pytest.raises(DomainError):
        decode_token("not.a.real.token", expected_type=TOKEN_TYPE_ACCESS)


def test_decode_alg_none_rejected(auth_env: None) -> None:
    """alg=none(서명 없는) 토큰은 거부된다(algorithms 명시로 alg=none 공격 차단)."""
    unsigned = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "admin", "type": TOKEN_TYPE_ACCESS},
        key="",
        algorithm="none",
    )
    with pytest.raises(DomainError):
        decode_token(unsigned, expected_type=TOKEN_TYPE_ACCESS)


def test_decode_token_missing_exp_raises_401(auth_env: None) -> None:
    """exp 없는(영구) 서명유효 토큰은 401 — require=[exp]로 영구 토큰을 차단한다."""
    token = _sign({"sub": str(uuid.uuid4()), "role": "booker", "type": TOKEN_TYPE_ACCESS})
    with pytest.raises(DomainError) as exc_info:
        decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED


def test_decode_token_missing_sub_raises_401(auth_env: None) -> None:
    """sub 없는 서명유효 토큰은 401 — require=[sub]로 거부한다(소비처 KeyError 방지)."""
    token = _sign(
        {"role": "booker", "type": TOKEN_TYPE_ACCESS, "exp": now_utc() + timedelta(minutes=15)}
    )
    with pytest.raises(DomainError) as exc_info:
        decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED


# ── hash_token(1.8) ───────────────────────────────────────────────────────────
def test_hash_token_is_deterministic_64_hex() -> None:
    """sha256 해시는 결정적이며 정확히 64자 hex다."""
    h1 = hash_token("some-refresh-token")
    h2 = hash_token("some-refresh-token")
    assert h1 == h2
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)
    assert hash_token("other") != h1


# ── get_current_principal / require_role(1.8 — 미니앱 실증) ───────────────────
# require_role(...)를 인자 기본값 안에서 직접 호출하면 ruff B008 → 모듈 변수로 추출한다
# (실 도메인 라우터도 의존성을 한 번 만들어 재사용하는 패턴을 권장).
_require_provider = require_role("provider")


def _make_principal_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/me-test")
    def me_test(principal: AuthPrincipal = Depends(get_current_principal)) -> dict[str, str]:
        return {"user_id": str(principal.user_id), "role": principal.role}

    @app.get("/provider-only")
    def provider_only(
        principal: AuthPrincipal = Depends(_require_provider),
    ) -> dict[str, str]:
        return {"role": principal.role}

    return app


def test_get_current_principal_from_header(auth_env: None) -> None:
    """Authorization Bearer 헤더의 access 토큰으로 주체를 도출한다(AC1)."""
    client = TestClient(_make_principal_app())
    uid = uuid.uuid4()
    token = create_access_token(uid, "booker")
    resp = client.get("/me-test", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"user_id": str(uid), "role": "booker"}


def test_get_current_principal_from_cookie(auth_env: None) -> None:
    """access 쿠키(desknow_access)에서도 주체를 도출한다(헤더 부재 시 폴백 — AC1)."""
    client = TestClient(_make_principal_app())
    uid = uuid.uuid4()
    token = create_access_token(uid, "provider")
    client.cookies.set(ACCESS_COOKIE_NAME, token)  # 클라이언트 인스턴스에 설정(권장)
    resp = client.get("/me-test")
    assert resp.status_code == 200
    assert resp.json()["role"] == "provider"


def test_get_current_principal_without_token_401(auth_env: None) -> None:
    """토큰이 없으면 401 UNAUTHENTICATED."""
    client = TestClient(_make_principal_app())
    resp = client.get("/me-test")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_require_role_allows_matching_role(auth_env: None) -> None:
    """허용 역할(provider)은 보호 엔드포인트를 통과한다(200)."""
    client = TestClient(_make_principal_app())
    token = create_access_token(uuid.uuid4(), "provider")
    resp = client.get("/provider-only", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"role": "provider"}


def test_require_role_forbids_other_role_403(auth_env: None) -> None:
    """권한 없는 역할(booker)은 403 FORBIDDEN_ROLE로 거부된다(백엔드 최종 강제 — AC5)."""
    client = TestClient(_make_principal_app())
    token = create_access_token(uuid.uuid4(), "booker")
    resp = client.get("/provider-only", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_require_role_without_token_401(auth_env: None) -> None:
    """토큰 없이 보호 엔드포인트 접근 시 401 UNAUTHENTICATED(인증이 인가보다 먼저)."""
    client = TestClient(_make_principal_app())
    resp = client.get("/provider-only")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── 손상 클레임 토큰 → 401(미처리 500 방지, 코드리뷰 2026-06-15) ──────────────────
def test_principal_missing_role_returns_401_not_500(auth_env: None) -> None:
    """서명·exp·type 유효하나 role 클레임이 없으면 500이 아니라 401(계약 유지)."""
    client = TestClient(_make_principal_app())
    token = _sign(
        {
            "sub": str(uuid.uuid4()),
            "type": TOKEN_TYPE_ACCESS,
            "exp": now_utc() + timedelta(minutes=15),
        }
    )
    resp = client.get("/me-test", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_principal_non_uuid_sub_returns_401_not_500(auth_env: None) -> None:
    """sub가 UUID 형식이 아니면 500이 아니라 401(uuid.UUID ValueError 가드)."""
    client = TestClient(_make_principal_app())
    token = _sign(
        {
            "sub": "not-a-uuid",
            "role": "booker",
            "type": TOKEN_TYPE_ACCESS,
            "exp": now_utc() + timedelta(minutes=15),
        }
    )
    resp = client.get("/me-test", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── _extract_access_token 분기 실증(코드리뷰 2026-06-15) ──────────────────────────
def test_extract_token_lowercase_bearer_scheme(auth_env: None) -> None:
    """스킴이 소문자 'bearer'여도 access 토큰을 추출한다(대소문자 무관)."""
    client = TestClient(_make_principal_app())
    uid = uuid.uuid4()
    token = create_access_token(uid, "booker")
    resp = client.get("/me-test", headers={"Authorization": f"bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == str(uid)


def test_extract_token_empty_bearer_falls_back_to_cookie(auth_env: None) -> None:
    """빈 'Bearer ' 헤더(토큰 없음)는 무시하고 쿠키로 폴백한다."""
    client = TestClient(_make_principal_app())
    uid = uuid.uuid4()
    token = create_access_token(uid, "provider")
    client.cookies.set(ACCESS_COOKIE_NAME, token)
    resp = client.get("/me-test", headers={"Authorization": "Bearer "})
    assert resp.status_code == 200
    assert resp.json()["role"] == "provider"


def test_extract_token_header_precedes_cookie(auth_env: None) -> None:
    """헤더와 쿠키가 모두 있으면 헤더가 우선한다(헤더 우선·쿠키 폴백)."""
    client = TestClient(_make_principal_app())
    header_uid = uuid.uuid4()
    cookie_uid = uuid.uuid4()
    client.cookies.set(ACCESS_COOKIE_NAME, create_access_token(cookie_uid, "provider"))
    resp = client.get(
        "/me-test",
        headers={"Authorization": f"Bearer {create_access_token(header_uid, 'booker')}"},
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == str(header_uid)  # 쿠키가 아니라 헤더 주체
