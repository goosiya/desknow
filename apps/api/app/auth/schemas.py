"""auth 요청/응답 스키마: ``RegisterRequest`` · ``UserPublic`` (Story 1.7).

요청 검증(이메일 형식·비번 정책·역할)과 응답 직렬화(해시 비노출 + ``...Z`` 시각)를
분리한다.

**규약(아키텍처 §Format/Process/Enforcement L256-296):**

- **검증은 백엔드가 신뢰 경계**(L277). 이메일 형식·비번 정책·역할 위반은 모두 Pydantic
  검증으로 ``RequestValidationError``가 되며, Story 1.5의 ``validation_exception_handler``가
  자동으로 **422 + ``{detail:{code:"VALIDATION_ERROR", message}}``** 로 단일화한다(AC2·AC4).
  → 422용 별도 핸들러/에러코드를 작성하지 않는다.
- **응답에 ``password_hash`` 노출 금지**(AC1, NFR-6). ``UserPublic``에 해당 필드를 두지 않고
  라우터가 ``response_model=UserPublic``으로 강제한다.
- **와이어는 snake_case 유지**(L286, camelCase 변환 레이어 금지). ``created_at``은
  ``isoformat_utc``로 ``...Z`` 직렬화한다(L263).
"""
from __future__ import annotations

import re
import string
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, field_serializer, field_validator

from app.core.time import isoformat_utc

# "특수문자" = ASCII 인쇄가능 구두점(``!"#$…~`` 32자). 공백·제어문자·비ASCII는 특수문자로
# 인정하지 않는다 — 끝/앞 공백만으로 정책을 만족하는 비밀번호 footgun을 차단한다
# (코드리뷰 2026-06-15: `[^A-Za-z0-9]`가 공백·개행·NBSP를 특수문자로 통과시키던 문제 수정).
_SPECIAL_CHARS = frozenset(string.punctuation)


class RegisterRequest(BaseModel):
    """회원가입 요청. 형식·정책·역할 위반은 Pydantic 검증 → 1.5 핸들러가 422로 단일화."""

    email: EmailStr  # 형식 위반 시 RequestValidationError → 422
    password: str
    role: Literal["booker", "provider"]  # admin은 시드 전용 — 가입 거부(위반 시 422)

    @field_validator("password")
    @classmethod
    def _enforce_password_policy(cls, v: str) -> str:
        """FR-3: 최소 8자 + 대문자1 + 숫자1 + 특수문자1(백엔드 신뢰 경계)."""
        if (
            len(v) < 8
            or re.search(r"[A-Z]", v) is None
            or re.search(r"[0-9]", v) is None
            or not any(c in _SPECIAL_CHARS for c in v)
        ):
            raise ValueError(
                "비밀번호는 8자 이상이며 대문자·숫자·특수문자(공백 제외 구두점)를 "
                "각각 1개 이상 포함해야 합니다."
            )
        return v


class UserPublic(BaseModel):
    """가입 성공 응답(사용자 리소스). ``password_hash`` 필드 없음 — 해시 비노출(AC1)."""

    model_config = ConfigDict(from_attributes=True)  # User ORM 객체 → 응답 직렬화

    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    created_at: datetime

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)


class LoginRequest(BaseModel):
    """로그인 요청(Story 1.8).

    ``email``은 의도적으로 ``str``(EmailStr 아님)이다 — 로그인은 *검증*이 아니라 *대조*이므로,
    이메일 형식 위반까지 422가 아니라 401로 단일화한다(enumeration·형식 누출 차단, AC2).
    정규화(``.strip().lower()``)는 서비스가 수행한다. ``password``도 정책 validator 없음.
    """

    email: str
    password: str


class TokenResponse(BaseModel):
    """토큰 발급 응답(로그인·회전 공용, AC1·AC3). 와이어는 snake_case 유지(L286).

    ``refresh_token``은 **원문**만 반환한다(해시는 DB 내부 — 절대 응답에 노출 금지).
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # RFC 6750 소문자


class RefreshRequest(BaseModel):
    """재발급 요청(AC3). RN=본문 / 웹=쿠키(미전송 시 라우터가 쿠키 폴백)."""

    refresh_token: str | None = None


class LogoutRequest(BaseModel):
    """로그아웃 요청(AC4 — 멱등). RN=본문 / 웹=쿠키(미전송 시 라우터가 쿠키 폴백)."""

    refresh_token: str | None = None
