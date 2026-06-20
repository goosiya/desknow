"""auth 도메인 서비스: ``register_user`` (Story 1.7).

도메인 로직(이메일 정규화·중복 검사·해싱·삽입)을 라우터에서 분리한다
(아키텍처 §Boundaries L349 — service 계층).

**규약:**

- **에러는 ``DomainError(ErrorCode.EMAIL_TAKEN, ...)``만** 사용한다(Story 1.5). raw
  ``HTTPException``/문자열 코드 하드코딩 금지. ``EMAIL_TAKEN``은 이미 ``ErrorCode``(409)에
  시드되어 있다.
- **이메일 소문자 정규화** 저장으로 대소문자만 다른 중복가입을 차단한다.
- **이중 방어(defense-in-depth):** 서비스 선검사(친절한 메시지) + ``users.email`` UNIQUE
  제약(경합 안전망). 선검사 통과 후 동시 삽입이 일어나도 ``IntegrityError``를 잡아
  동일한 ``EMAIL_TAKEN``으로 변환한다.
"""
from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.models import RefreshToken, User
from app.auth.schemas import RegisterRequest, TokenResponse
from app.core.db import violated_constraint
from app.core.errors import DomainError, ErrorCode
from app.core.security import (
    REFRESH_TOKEN_TTL,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.core.time import now_utc

# 인증 실패(미존재·틀린 비번·비활성)와 토큰 무효(만료·위조·회전/로그아웃됨)는 모두 동일한
# 401 메시지로 단일화한다 — 계정 존재 여부 노출(enumeration)을 막는다(AC2).
_INVALID_CREDENTIALS_MSG = "이메일 또는 비밀번호가 올바르지 않습니다."
_INVALID_TOKEN_MSG = "유효하지 않은 토큰입니다."


def register_user(session: Session, data: RegisterRequest) -> User:
    """검증된 가입 요청으로 ``users`` 계정을 생성한다(Argon2 해싱 저장).

    이메일은 ``.strip().lower()``로 정규화해 대소문자만 다른 중복을 차단한다. 중복은
    선검사(409 ``EMAIL_TAKEN``) + UNIQUE 제약 경합 변환으로 이중 방어한다.
    """
    email = data.email.strip().lower()  # 대소문자 무관 중복 차단 → 소문자 정규화 저장
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing is not None:
        raise DomainError(ErrorCode.EMAIL_TAKEN, "이미 가입된 이메일입니다.")  # 409
    user = User(email=email, password_hash=hash_password(data.password), role=data.role)
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:  # 경합: 선검사 통과 후 동시 삽입 → UNIQUE 위반
        session.rollback()
        # P2 정합화(Story 2.2): 포괄 캐치 → 제약명 선별 변환. uq_users_email만 EMAIL_TAKEN으로
        # 바꾸고 무관한 위반은 오변환 금지(re-raise). create_room과 동일 패턴(회고 P2 회수).
        if violated_constraint(exc) == "uq_users_email":
            raise DomainError(ErrorCode.EMAIL_TAKEN, "이미 가입된 이메일입니다.") from exc
        raise
    session.refresh(user)
    return user


def authenticate_user(session: Session, email: str, password: str) -> User:
    """이메일·비밀번호로 사용자를 인증한다(Story 1.8, AC2).

    미존재·틀린 비밀번호·비활성 계정 **세 실패 모드를 동일한 401 ``UNAUTHENTICATED``**로
    응답해 계정 존재 여부 노출(enumeration)을 차단한다. 이메일은 ``.strip().lower()``로
    정규화해 가입 시 저장한 소문자 이메일과 대조한다(``verify_password``는 fail-closed라
    손상 해시도 안전히 False→401).
    """
    normalized = email.strip().lower()
    user = session.exec(select(User).where(User.email == normalized)).first()
    if (
        user is None
        or not verify_password(password, user.password_hash)
        or not user.is_active
    ):
        raise DomainError(ErrorCode.UNAUTHENTICATED, _INVALID_CREDENTIALS_MSG)
    return user


def issue_token_pair(session: Session, user: User) -> TokenResponse:
    """새 access+refresh 토큰 쌍을 발급한다(Story 1.8, AC1).

    refresh는 **해시만** ``refresh_tokens``에 저장하고(원문 미저장) 원문은 응답으로만 반환한다.
    ``jti``(랜덤)로 토큰 해시가 고유하므로 ``token_hash`` 충돌은 천문학적 → IntegrityError
    과대캐치(register의 EMAIL_TAKEN 변환)를 **복사하지 않는다**(만약의 충돌은 그대로 전파).
    """
    access = create_access_token(user.id, user.role)
    raw_refresh = create_refresh_token(user.id)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=now_utc() + REFRESH_TOKEN_TTL,
        )
    )
    session.commit()
    return TokenResponse(access_token=access, refresh_token=raw_refresh)


def rotate_token_pair(session: Session, raw_refresh: str) -> TokenResponse:
    """유효한 refresh로 새 토큰 쌍을 회전 발급한다(Story 1.8, AC3).

    JWT 디코드(만료/위조/타입오류 → 401) + DB 해시 조회(로그아웃·이미 회전·위조 = 행 부재
    → 401)의 이중 검증을 통과해야 한다. 기존 행을 삭제하고 새 쌍을 같은 트랜잭션에서 발급해
    refresh를 1회용화한다(재사용 공격 차단). 비활성 사용자에게는 발급하지 않는다.
    """
    claims = decode_token(raw_refresh, expected_type=TOKEN_TYPE_REFRESH)
    row = session.exec(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
    ).first()
    if row is None:  # 로그아웃·이미 회전·위조 → DB에 해시 없음
        raise DomainError(ErrorCode.UNAUTHENTICATED, _INVALID_TOKEN_MSG)
    # decode_token이 sub 존재는 보장하나 UUID 형태는 미보장 → 가드(미처리 500 방지).
    sub = claims.get("sub")
    if not isinstance(sub, str):
        raise DomainError(ErrorCode.UNAUTHENTICATED, _INVALID_TOKEN_MSG)
    try:
        user_id = uuid.UUID(sub)
    except ValueError as exc:
        raise DomainError(ErrorCode.UNAUTHENTICATED, _INVALID_TOKEN_MSG) from exc
    user = get_user_by_id(session, user_id)
    if not user.is_active:
        raise DomainError(ErrorCode.UNAUTHENTICATED, _INVALID_TOKEN_MSG)
    session.delete(row)  # 회전 — 기존 refresh 즉시 무효화
    return issue_token_pair(session, user)  # delete+add를 한 commit으로 원자 처리


def revoke_refresh_token(session: Session, raw_refresh: str | None) -> None:
    """제시한 refresh 토큰의 해시 행을 삭제(무효화)한다(Story 1.8, AC4 — 멱등).

    **decode 하지 않고** 해시로만 조회·삭제한다 → 만료/위조/손상 토큰에도 절대 예외/401 없이
    로그아웃이 성공한다(멱등). 토큰이 None이거나 행이 없어도 no-op으로 정상 종료한다.
    """
    if raw_refresh is None:
        return
    row = session.exec(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
    ).first()
    if row is not None:
        session.delete(row)
        session.commit()


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User:
    """user_id로 사용자를 조회한다(``/me``·회전 공용, Story 1.8).

    미존재 시 401 ``UNAUTHENTICATED``(토큰은 유효하나 사용자가 사라진 경우 = 신뢰 불가).
    """
    user = session.get(User, user_id)
    if user is None:
        raise DomainError(ErrorCode.UNAUTHENTICATED, _INVALID_TOKEN_MSG)
    return user
