"""가입 스키마 검증 테스트 (Story 1.7, AC2·AC4).

DB 불필요. 이메일 형식·비밀번호 정책(FR-3)·역할 Literal 검증과 응답 직렬화
(해시 비노출 + ``...Z``)를 실증한다.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.auth.models import User
from app.auth.schemas import RegisterRequest, UserPublic

_VALID_PW = "Test1234!"


def test_register_request_accepts_valid_input() -> None:
    """유효한 이메일·정책 충족 비번·허용 역할은 통과한다."""
    req = RegisterRequest(email="user@example.com", password=_VALID_PW, role="booker")
    assert req.email == "user@example.com"
    assert req.role == "booker"


@pytest.mark.parametrize("role", ["booker", "provider"])
def test_register_request_accepts_both_signup_roles(role: str) -> None:
    """가입 허용 역할(booker·provider)은 모두 통과한다."""
    req = RegisterRequest(email="user@example.com", password=_VALID_PW, role=role)
    assert req.role == role


@pytest.mark.parametrize(
    "bad_password",
    [
        "Aa1!",  # 8자 미만
        "test1234!",  # 대문자 없음
        "Testtest!",  # 숫자 없음
        "Test12345",  # 특수문자 없음
        "Test1234 ",  # 공백은 특수문자 아님(끝 공백 footgun 차단 — 코드리뷰 2026-06-15)
        "Test1234\n",  # 개행은 특수문자 아님
        "Test1234\xa0",  # NBSP(비ASCII 공백)는 특수문자 아님
    ],
)
def test_register_request_rejects_weak_password(bad_password: str) -> None:
    """정책(8자+대문자+숫자+특수문자) 위반 비밀번호는 ValidationError로 거부된다(AC4).

    특수문자는 ASCII 인쇄가능 구두점만 인정한다 — 공백·개행·NBSP 등은 불인정.
    """
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password=bad_password, role="booker")


@pytest.mark.parametrize("bad_email", ["not-an-email", "user@", "@example.com", "user example.com"])
def test_register_request_rejects_invalid_email(bad_email: str) -> None:
    """이메일 형식 위반은 ValidationError로 거부된다(AC2)."""
    with pytest.raises(ValidationError):
        RegisterRequest(email=bad_email, password=_VALID_PW, role="booker")


@pytest.mark.parametrize("bad_role", ["admin", "superuser", ""])
def test_register_request_rejects_disallowed_role(bad_role: str) -> None:
    """admin·미지정·기타값 역할은 가입으로 허용되지 않는다(admin은 시드 전용)."""
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password=_VALID_PW, role=bad_role)


def test_register_request_requires_role() -> None:
    """역할 미지정은 거부된다."""
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password=_VALID_PW)  # type: ignore[call-arg]


def test_user_public_hides_password_hash_and_serializes_z() -> None:
    """응답 스키마는 password_hash를 노출하지 않고 created_at을 ...Z로 직렬화한다(AC1)."""
    user = User(
        id=uuid.uuid4(),
        email="user@example.com",
        password_hash="$argon2id$secret",
        role="provider",
        is_active=True,
        created_at=datetime(2026, 6, 15, 5, 0, 0, tzinfo=UTC),
    )
    dumped = UserPublic.model_validate(user).model_dump(mode="json")
    assert set(dumped) == {"id", "email", "role", "is_active", "created_at"}
    assert "password_hash" not in dumped
    assert dumped["created_at"] == "2026-06-15T05:00:00Z"
    assert dumped["created_at"].endswith("Z")
