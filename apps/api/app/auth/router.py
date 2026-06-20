"""auth 라우터: 회원가입(1.7) + 로그인/세션/RBAC(1.8).

``main.py``가 ``api_router``(``/api/v1``) 아래에 포함하므로 최종 경로는
``/api/v1/auth/{register,login,refresh,logout,me}``가 된다(``main.py`` 변경 불필요 —
auth_router는 이미 배선됨).

**규약:**

- **``response_model=UserPublic``** 으로 ``password_hash``가 새지 않게 한다(AC1).
- **상태코드:** register=201(생성), login=200·refresh=200(생성 아님), logout=204, me=200.
- **토큰 보관 이원화(AC1):** 로그인/회전은 쿠키 set(웹: httpOnly+Secure+SameSite) **및**
  본문 반환(RN: SecureStore→Bearer). 백엔드 추출은 헤더 우선·쿠키 폴백(``get_current_principal``).
- **``responses={401: ErrorResponse}``** 로 OpenAPI에 에러 계약을 노출한다(1.9 SDK가
  ``detail.code`` 타입을 생성하도록). 검증 실패는 Pydantic→1.5 핸들러가 422로 자동 변환.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlmodel import Session

from app.auth import service
from app.auth.models import User
from app.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserPublic,
)
from app.core.db import get_session
from app.core.errors import DomainError, ErrorCode, ErrorResponse
from app.core.security import (
    ACCESS_COOKIE_NAME,
    ACCESS_TOKEN_TTL,
    REFRESH_COOKIE_NAME,
    REFRESH_TOKEN_TTL,
    AuthPrincipal,
    get_current_principal,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, tokens: TokenResponse) -> None:
    """access/refresh 토큰을 httpOnly+Secure+SameSite 쿠키로 설정한다(웹 보관, AC1).

    refresh 쿠키 path는 ``/api/v1/auth``로 한정해 노출을 최소화한다(refresh/logout만 전송).
    access는 모든 보호 엔드포인트가 읽도록 ``path="/"``.
    """
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        tokens.access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        max_age=int(ACCESS_TOKEN_TTL.total_seconds()),
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        tokens.refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/api/v1/auth",
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
    )


def _clear_auth_cookies(response: Response) -> None:
    """인증 쿠키를 제거한다(만료 Set-Cookie 발행 — path가 set과 일치해야 한다)."""
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def register(data: RegisterRequest, session: Session = Depends(get_session)) -> User:
    """이메일·비밀번호·역할로 가입한다 → 201 + UserPublic(해시 비노출)."""
    return service.register_user(session, data)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse}},
)
def login(
    data: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> TokenResponse:
    """이메일·비밀번호로 로그인한다 → 200 + 토큰 쌍(본문) + 인증 쿠키 set(AC1·AC2).

    잘못된 자격(미존재·틀린 비번·비활성)은 서비스가 401 ``UNAUTHENTICATED``로 단일화한다.
    """
    user = service.authenticate_user(session, data.email, data.password)
    tokens = service.issue_token_pair(session, user)
    _set_auth_cookies(response, tokens)  # 주입 Response에 set → FastAPI가 최종 응답에 병합
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse}},
)
def refresh(
    data: RefreshRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> TokenResponse:
    """refresh 토큰으로 새 토큰 쌍을 회전 발급한다 → 200(AC3).

    토큰은 본문(RN) 또는 쿠키(웹)에서 추출한다. 만료/위조/회전·로그아웃됨은 401.
    """
    raw = data.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)
    if raw is None:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "리프레시 토큰이 필요합니다.")
    tokens = service.rotate_token_pair(session, raw)
    _set_auth_cookies(response, tokens)
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    data: LogoutRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    """로그아웃한다 → 204(AC4 — 멱등). refresh 해시 행을 삭제하고 인증 쿠키를 제거한다.

    토큰이 본문/쿠키 모두 없거나 이미 무효여도 204로 정상 종료한다(멱등).
    """
    raw = data.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)
    service.revoke_refresh_token(session, raw)
    # ⚠️ 별도 Response를 반환하므로 쿠키 삭제는 *반환 객체*에 한다(주입 response 병합 안 됨).
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(resp)
    return resp


@router.get(
    "/me",
    response_model=UserPublic,
    responses={401: {"model": ErrorResponse}},
)
def me(
    principal: AuthPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> User:
    """현재 인증된 사용자를 반환한다 → 200 + UserPublic(인증 필요, AC1·AC5 실증).

    프론트 세션 복원에 사용 + ``get_current_principal``(헤더/쿠키 추출)을 실증한다.
    """
    return service.get_user_by_id(session, principal.user_id)
