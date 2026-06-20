"""보안 프리미티브: 비밀번호 해싱(1.7) + JWT 발급/검증·RBAC 의존성(1.8).

**규약(아키텍처 §Authentication & Security L155-166 / §Boundaries L347-360):**

- **해싱 = pwdlib + Argon2.** ``PasswordHash.recommended()``가 Argon2(기본 파라미터)를
  쓴다(``pwdlib[argon2]`` 설치 — pyproject). **bcrypt/passlib/직접 hashlib 사용 금지.**
- **pwdlib 시그니처 함정:** ``hash(password)`` / **``verify(password, hash)``**. pwdlib
  ``__init__`` docstring 예제가 ``verify(hash, "password")``로 적혀 있으나 실제 시그니처는
  ``verify(self, password, hash)``(소스 ``_hash.py:59``)다 — 순서를 뒤집으면 항상 False가
  되어 로그인이 조용히 깨진다.
- **``verify_password`` fail-closed(1.8):** pwdlib ``verify``는 손상/빈/파싱불가 해시에
  **예외**(``UnknownHashError`` 등)를 던진다(False 아님 — 실측). 부분 마이그레이션·손상
  ``password_hash`` 행을 만나면 로그인이 500이 되고, 더 위험하게는 검증 불가가 인증 통과로
  새는 fail-open이 될 수 있다. ``try/except → False``로 감싸 **검증 불가 = 인증 실패**로 만든다.
- **단일 백엔드 발급 JWT(HS256, PyJWT 2.13):** access 단기(15분) + refresh 장기(14일).
  HS256은 HMAC이라 ``cryptography`` extra 불필요. ``jwt.decode``에 ``algorithms``를 반드시
  명시한다(생략 시 alg=none 공격 노출). ``type`` 클레임으로 access↔refresh 교차 사용을 막고,
  refresh의 ``jti``(랜덤)로 발급 토큰마다 해시가 고유해진다.
- **refresh = 해시 저장(원문 미저장):** ``hash_token``(sha256 hex 64자)만 DB에 저장/조회한다
  (DB 유출 시에도 토큰 사용 불가). 검증은 JWT 디코드(stateless: sig+exp+type) + DB 해시 조회
  (stateful: 무효화 여부) 이중이다.
- **RBAC = JWT role 클레임 + ``require_role`` 의존성(백엔드 최종 강제, §Boundaries L351):**
  권한 없는 역할은 403 ``FORBIDDEN_ROLE``, 미인증은 401 ``UNAUTHENTICATED``. 역할은 가입 시
  확정·전환 불가(역할 변경 엔드포인트 없음). 프론트 라우트 보호는 보조일 뿐 최종 강제 아님.
- **시크릿 지연 로드:** JWT 함수는 함수 내부에서 ``get_settings().JWT_SECRET_KEY``를 읽는다
  (모듈 import 시점 호출 금지 — ``test_main`` 모듈레벨 TestClient/도구 import가 ``.env`` 없이도
  안전해야 함, 1.4 지연 패턴과 동일).
- **평문 저장 절대 금지(NFR-6):** 컬럼명은 ``password_hash``이며, 해싱 결과만 저장한다.
"""
from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, Request
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.errors import DomainError, ErrorCode
from app.core.time import now_utc

# ── JWT/토큰 상수(단일 출처) ──────────────────────────────────────────────────
JWT_ALGORITHM = "HS256"  # HMAC → cryptography extra 불필요(실측)
ACCESS_TOKEN_TTL = timedelta(minutes=15)  # access = 단기 토큰
REFRESH_TOKEN_TTL = timedelta(days=14)  # refresh = 장기 토큰(회전으로 1회용화)
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# 쿠키명(웹 토큰 보관). RN은 응답 본문→SecureStore→Bearer 헤더로 보관(쿠키 미사용).
ACCESS_COOKIE_NAME = "desknow_access"
REFRESH_COOKIE_NAME = "desknow_refresh"

# Argon2(기본 파라미터) 해셔 단일 인스턴스. recommended()가 현재 권장 알고리즘을 고른다
# (현재 Argon2id). 향후 파라미터 상향 시 verify_and_update로 재해싱 가능(MVP 미사용).
_password_hasher = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    """평문 비밀번호를 Argon2 해시 문자열(``$argon2...``)로 반환한다(NFR-6).

    동일 비밀번호라도 매 호출 솔트가 달라 해시가 서로 다르다. 결과만 ``password_hash``
    컬럼에 저장하고 평문은 절대 저장하지 않는다.
    """
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """평문 비밀번호가 저장된 해시와 일치하는지 검증한다(Story 1.8 로그인이 소비).

    ⚠️ pwdlib 시그니처는 ``verify(password, hash)`` 순서다(docstring 예제 ``verify(hash, ...)``는
    오기). 순서를 뒤집으면 항상 False가 되어 로그인이 조용히 깨진다.

    **fail-closed(1.8):** pwdlib ``verify``는 손상/빈/파싱불가 해시에 예외를 던지므로,
    예외를 잡아 **False**(인증 실패)로 만든다. 검증 불가가 인증 통과(fail-open)가 되면 안 된다.
    """
    try:
        return _password_hasher.verify(plain_password, password_hash)
    except Exception:  # 손상/빈/파싱불가 해시 → 인증 실패(fail-closed, fail-open 차단)
        return False


@dataclass(frozen=True)
class AuthPrincipal:
    """토큰 클레임에서 디코드한 인증 주체(DB 객체 아님).

    access 토큰의 ``sub``(user_id)·``role``만 담는다. DB 미접근(access는 단명 토큰이라
    클레임을 신뢰 — is_active 즉시 취소는 E8 영역).
    """

    user_id: uuid.UUID
    role: str


def create_access_token(
    user_id: uuid.UUID, role: str, *, now: datetime | None = None
) -> str:
    """access 토큰(단기)을 발급한다. role 클레임을 포함해 RBAC가 DB 없이 강제 가능하다.

    ``now``는 테스트 결정성을 위해 주입 가능하다(미지정 시 ``now_utc()`` — 1.5 단일 출처).
    """
    issued_at = now if now is not None else now_utc()
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": TOKEN_TYPE_ACCESS,
        "iat": issued_at,
        "exp": issued_at + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, get_settings().JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: uuid.UUID, *, now: datetime | None = None) -> str:
    """refresh 토큰(장기)을 발급한다.

    ``jti``(랜덤)로 매 발급 토큰이 달라 해시가 고유해진다(동일 사용자·동초 발급 충돌 방지).
    role 클레임은 넣지 않는다 — 회전 시 DB의 최신 role을 사용한다.
    """
    issued_at = now if now is not None else now_utc()
    payload = {
        "sub": str(user_id),
        "type": TOKEN_TYPE_REFRESH,
        "jti": uuid.uuid4().hex,
        "iat": issued_at,
        "exp": issued_at + REFRESH_TOKEN_TTL,
    }
    return jwt.encode(payload, get_settings().JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str, *, expected_type: str) -> dict[str, Any]:
    """토큰을 검증·디코드한다. 만료/위조/타입오류는 401 ``UNAUTHENTICATED``로 통일한다.

    ``algorithms``를 명시해 alg=none 공격을 차단한다. ``ExpiredSignatureError``(만료)·
    ``InvalidSignatureError``(위조)는 모두 ``InvalidTokenError`` 하위클래스라 단일 except로
    포괄한다(실측). 디코드 후 ``type`` 클레임이 ``expected_type``과 다르면 access↔refresh
    교차 사용으로 보고 동일하게 거부한다.
    """
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            get_settings().JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            # 필수 클레임 부재(특히 exp 없는 영구 토큰·sub 누락)도 거부한다 — PyJWT가
            # MissingRequiredClaimError(InvalidTokenError 하위)를 던져 아래 except로 401화한다.
            # role은 access 전용이라 전역 require에 빼고 소비처(get_current_principal)가 검증.
            options={"require": ["exp", "type", "sub"]},
        )
    except jwt.InvalidTokenError as exc:  # 만료·위조·형식오류·필수클레임부재 전부 포괄
        raise DomainError(ErrorCode.UNAUTHENTICATED, "유효하지 않은 토큰입니다.") from exc
    if claims.get("type") != expected_type:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "유효하지 않은 토큰입니다.")
    return claims


def hash_token(raw: str) -> str:
    """refresh 토큰 원문을 sha256 hex(64자)로 해시한다(DB 저장/조회 키).

    원문 대신 해시를 저장하므로 DB가 유출돼도 토큰을 사용할 수 없다.
    """
    return hashlib.sha256(raw.encode()).hexdigest()


def _extract_access_token(request: Request) -> str | None:
    """access 토큰을 헤더 우선·쿠키 폴백으로 추출한다(토큰 보관 이원화 — AC1).

    ``Authorization: Bearer <t>``(스킴 대소문자 무관)를 우선 보고, 없으면 access 쿠키를 본다.
    """
    auth = request.headers.get("Authorization")
    if auth:
        scheme, _, param = auth.partition(" ")
        if scheme.lower() == "bearer" and param.strip():
            return param.strip()
    return request.cookies.get(ACCESS_COOKIE_NAME)


def get_current_principal(request: Request) -> AuthPrincipal:
    """FastAPI 의존성: access 토큰에서 인증 주체를 도출한다(헤더/쿠키 양쪽 — AC1).

    토큰 부재·만료·위조·타입오류는 모두 401 ``UNAUTHENTICATED``. DB 미접근(access는 단명
    토큰이라 클레임 신뢰 — is_active 즉시 취소는 E8).
    """
    token = _extract_access_token(request)
    if token is None:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "인증이 필요합니다.")
    claims = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    # 서명·exp·type은 유효하나 sub/role 형태가 손상된 토큰을 미처리 500이 아니라 401로 막는다
    # (모듈 계약 "모든 토큰 문제 → 401" 유지 — decode_token은 sub 존재만 보장, 형태는 미보장).
    role = claims.get("role")
    sub = claims.get("sub")
    if not isinstance(role, str) or not isinstance(sub, str):
        raise DomainError(ErrorCode.UNAUTHENTICATED, "유효하지 않은 토큰입니다.")
    try:
        user_id = uuid.UUID(sub)
    except ValueError as exc:  # sub가 UUID 형식이 아님 → 신뢰 불가
        raise DomainError(ErrorCode.UNAUTHENTICATED, "유효하지 않은 토큰입니다.") from exc
    return AuthPrincipal(user_id=user_id, role=role)


def require_role(*allowed_roles: str) -> Callable[..., AuthPrincipal]:
    """RBAC 의존성 팩토리: 허용 역할만 통과시킨다(백엔드 최종 강제 — AC5).

    향후 도메인 라우터가 ``Depends(require_role("provider"))``(E2 rooms)·
    ``Depends(require_role("admin"))``(E8)로 소비한다. 권한 없는 역할은 403 ``FORBIDDEN_ROLE``,
    미인증은 ``get_current_principal``이 먼저 401로 거부한다.
    """

    def checker(
        principal: AuthPrincipal = Depends(get_current_principal),
    ) -> AuthPrincipal:
        if principal.role not in allowed_roles:
            raise DomainError(ErrorCode.FORBIDDEN_ROLE, "이 작업을 수행할 권한이 없습니다.")
        return principal

    return checker
