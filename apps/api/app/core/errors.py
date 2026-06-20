"""표준 에러 스키마·에러코드 상수·전역 예외 핸들러 (Story 1.5).

**규약(아키텍처 §Format/Process/Enforcement L256-296):**

- **와이어 스키마는 ``{"detail": {"code": "<ErrorCode>", "message": "..."}}``** 로 단일화한다.
  프론트(``packages/api-client``)는 ``detail.code``로 분기하고 ``message``는 표시·로깅한다.
- **에러코드는 상수(``ErrorCode`` StrEnum)로만 사용한다** — 문자열 하드코딩 금지
  (architecture.md L288). StrEnum이라 멤버가 ``str`` 인스턴스이며 JSON 직렬화 시 값이
  곧 코드 문자열이다. 후속 스토리는 자기 도메인 코드를 이 enum에 **추가**한다.
- **상태 매핑은 ``DEFAULT_STATUS`` 레지스트리가 단일 출처**다(AC3): 409=동시성/상태충돌,
  403=권한, 401=미인증, 422=검증. ``DomainError`` 생성 시 호출처가 override 가능하나 기본을 신뢰.
- **도메인 에러는 ``DomainError``만 사용한다** — raw ``HTTPException(409, detail="문자열")``로
  도메인 에러를 표현하면 표준 스키마가 깨진다(금지).
- **검증 422 단일화:** FastAPI 기본 ``RequestValidationError``는 ``detail``이 배열이라 본
  스키마와 충돌한다. ``validation_exception_handler``가 표준 스키마로 변환한다.
- **범위 경계:** 라우팅 레벨 404/405(Starlette ``HTTPException``)는 표준화하지 않는다
  (프레임워크 기본 유지). 본 모듈은 도메인 에러 + 검증 에러만 표준화한다.

소비처(구현은 각 스토리): EMAIL_TAKEN→1.7, UNAUTHENTICATED/FORBIDDEN_ROLE→1.8,
SLOT_CONFLICT→E4, CANCEL_WINDOW_PASSED→4.7, RESERVATION_NOT_FOUND→4.7.
본 스토리는 계약·핸들러만 고정한다.
"""
from __future__ import annotations

from enum import StrEnum
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorCode(StrEnum):
    """도메인 에러코드 상수(단일 출처). 라우터/서비스는 ``ErrorCode.X``만 사용한다."""

    SLOT_CONFLICT = "SLOT_CONFLICT"  # 409 동시 예약 충돌(FR-15, E4)
    EMAIL_TAKEN = "EMAIL_TAKEN"  # 409 이메일 중복가입(FR-1, 1.7)
    ROOM_LIMIT_REACHED = "ROOM_LIMIT_REACHED"  # 409 제공자당 1개 제약 초과(FR-22, 2.2)
    ROOM_NOT_FOUND = "ROOM_NOT_FOUND"  # 404 미존재 또는 비-소유 공간(소유권 백엔드 최종, 2.3)
    RESERVATION_NOT_FOUND = "RESERVATION_NOT_FOUND"  # 404 미존재/비-소유 예약(소유권 최종, 4.7)
    NOTIFICATION_NOT_FOUND = "NOTIFICATION_NOT_FOUND"  # 404 미존재/비-소유 통지(소유권 최종, 5.1)
    ACCOUNT_NOT_FOUND = "ACCOUNT_NOT_FOUND"  # 404 미존재/admin 대상 계정(비활성 대상 가드, 8.2)
    CANCEL_WINDOW_PASSED = "CANCEL_WINDOW_PASSED"  # 409 취소 가능 시간 경과(FR-16, 4.7)
    REJECT_WINDOW_PASSED = "REJECT_WINDOW_PASSED"  # 409 예약 시작 후 거절 시도(FR-24, 6.2)
    RESERVATION_NOT_COMPLETED = "RESERVATION_NOT_COMPLETED"  # 409 이용완료 전 후기(FR-20, 5.5)
    REVIEW_ALREADY_EXISTS = "REVIEW_ALREADY_EXISTS"  # 409 예약당 후기 1회 초과(FR-20, 5.5)
    REVIEW_NOT_FOUND = "REVIEW_NOT_FOUND"  # 404 미존재 후기(답글 대상, FR-21, 5.6)
    REVIEW_REPLY_FORBIDDEN = "REVIEW_REPLY_FORBIDDEN"  # 403 비-소유 룸 답글(소유권, 5.6)
    REVIEW_REPLY_ALREADY_EXISTS = "REVIEW_REPLY_ALREADY_EXISTS"  # 409 후기당 답글 1회 초과(5.6)
    FORBIDDEN_ROLE = "FORBIDDEN_ROLE"  # 403 역할 권한 없음(RBAC, 1.8)
    UNAUTHENTICATED = "UNAUTHENTICATED"  # 401 미인증(1.8)
    VALIDATION_ERROR = "VALIDATION_ERROR"  # 422 요청 검증 실패(RequestValidationError 변환)
    GEOCODING_UNAVAILABLE = "GEOCODING_UNAVAILABLE"  # 502 카카오 지오코딩 업스트림 실패(NFR-6, 2.2)
    # 502 LLM 업스트림 실패(레이트리밋/타임아웃/인증/API 에러 단일화, FR-29, 7.1)
    LLM_PROVIDER_UNAVAILABLE = "LLM_PROVIDER_UNAVAILABLE"


# 코드 → HTTP 상태 단일 출처(AC3). CANCEL_WINDOW_PASSED는 상태 전이 위반=409 Conflict.
# ROOM_LIMIT_REACHED=409(제공자당 1개 충돌). GEOCODING_UNAVAILABLE=502(업스트림 Bad Gateway).
DEFAULT_STATUS: dict[ErrorCode, int] = {
    ErrorCode.SLOT_CONFLICT: 409,
    ErrorCode.EMAIL_TAKEN: 409,
    ErrorCode.ROOM_LIMIT_REACHED: 409,
    # 도메인 404(리소스 not-found를 DomainError로 명시 발생 → 표준 스키마로 응답). 모듈
    # docstring의 "라우팅 404/405 미표준화"는 프레임워크 404(미존재 경로)를 가리키며 상충하지
    # 않는다 — 이쪽은 도메인 리소스 not-found다(2.3 소유권/존재 합침, 향후 reservation 등 동일).
    ErrorCode.ROOM_NOT_FOUND: 404,
    # 예약 도메인 404(미존재 + 비-소유 합침 — 타인 예약 존재 누설 금지, ROOM_NOT_FOUND 미러, 4.7).
    ErrorCode.RESERVATION_NOT_FOUND: 404,
    # 통지 도메인 404(미존재 + 비-소유 합침 — 타인 통지 존재 누설 금지, 4.7 미러, 5.1).
    ErrorCode.NOTIFICATION_NOT_FOUND: 404,
    # 계정 도메인 404(미존재 + admin 대상 합침 — admin 존재 누설/자기·타admin 비활성 금지, 8.2).
    ErrorCode.ACCOUNT_NOT_FOUND: 404,
    ErrorCode.CANCEL_WINDOW_PASSED: 409,
    # 거절 게이트("시작 전까지")는 6h 윈도우(취소)와 달리 고정 윈도우 없음 — earliest <= now(시작·
    # 경과)면 거절 차단. 상태 전이 위반=409 Conflict(CANCEL_WINDOW_PASSED 동형, FR-24, 6.2).
    ErrorCode.REJECT_WINDOW_PASSED: 409,
    # 후기 도메인 409(상태/중복 충돌 — 5.5). 이용 완료 안 된 예약 후기 시도 = 상태 위반(취소/거절/
    # 미완료), 예약당 1회 초과 = uq_reviews_reservation 중복 충돌. 둘 다 409 Conflict.
    ErrorCode.RESERVATION_NOT_COMPLETED: 409,
    ErrorCode.REVIEW_ALREADY_EXISTS: 409,
    # 답글 도메인(5.6). 답글 대상 후기 미존재=404. 비-소유 룸 후기 답글 시도=403 소유권 차단(epic AC
    # 명시 — booker 404 비노설과 의도적 분기, 후기·룸은 공개 데이터). 후기당 답글 1회 초과=409 중복.
    ErrorCode.REVIEW_NOT_FOUND: 404,
    ErrorCode.REVIEW_REPLY_FORBIDDEN: 403,
    ErrorCode.REVIEW_REPLY_ALREADY_EXISTS: 409,
    ErrorCode.FORBIDDEN_ROLE: 403,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.GEOCODING_UNAVAILABLE: 502,
    # LLM 업스트림(레이트리밋/타임아웃/인증/API 에러)을 단일 502로 정규화(GEOCODING 선례 미러, 7.1).
    ErrorCode.LLM_PROVIDER_UNAVAILABLE: 502,
}


class ErrorDetail(BaseModel):
    """표준 에러 본문의 ``detail`` 객체(OpenAPI 계약 노출용)."""

    code: ErrorCode
    message: str


class ErrorResponse(BaseModel):
    """표준 에러 응답. 후속 라우터가 ``responses={409: {"model": ErrorResponse}}``로 참조."""

    detail: ErrorDetail


class DomainError(Exception):
    """도메인 오류 신호(전역 핸들러가 표준 스키마로 변환).

    ``code``→``message``→``status_code``를 보유한다. ``status_code`` 미지정 시
    ``DEFAULT_STATUS`` 레지스트리에서 도출하고, 필요하면 호출처가 override한다.
    raw ``HTTPException``이 아니라 이 예외를 던져야 표준 스키마가 보장된다.
    """

    def __init__(self, code: ErrorCode, message: str, status_code: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code if status_code is not None else DEFAULT_STATUS[code]
        super().__init__(message)


# 핸들러는 Starlette ExceptionHandler 시그니처(Request, Exception)에 맞춰 exc를 Exception으로
# 받는다(좁은 타입은 contravariance로 add_exception_handler에 할당 불가). 등록 시 해당 예외
# 타입으로만 라우팅되므로 내부에서 cast로 좁힌다.
def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """``DomainError``를 표준 스키마(``{"detail":{"code","message"}}``)로 응답한다."""
    err = cast(DomainError, exc)
    return JSONResponse(
        status_code=err.status_code,
        content={"detail": {"code": err.code.value, "message": err.message}},
    )


def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """``RequestValidationError``(기본 배열 detail)를 표준 스키마(422)로 단일화한다.

    검증 정보는 비밀이 아니므로 첫 오류의 위치·메시지를 요약해 ``message``에 담는다.
    """
    err = cast(RequestValidationError, exc)
    errors = err.errors()
    if errors:
        first = errors[0]
        # 사용자-facing 메시지에는 기술적 prefix 를 빼고 validator 가 쓴 안내문만 노출한다(KTH
        # 2026-06-19). Pydantic 은 커스텀 validator 의 ValueError 를 "Value error, {원문}" 으로
        # 감싸고 FastAPI 는 위치를 loc(예 body.password)로 준다 — 둘 다 제거한다.
        raw_msg = str(first.get("msg", "")).removeprefix("Value error, ").strip()
        message = f"요청 검증 실패: {raw_msg}" if raw_msg else "요청 검증에 실패했습니다."
    else:
        message = "요청 검증에 실패했습니다."
    return JSONResponse(
        status_code=DEFAULT_STATUS[ErrorCode.VALIDATION_ERROR],
        content={"detail": {"code": ErrorCode.VALIDATION_ERROR.value, "message": message}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """전역 예외 핸들러를 앱에 배선한다(``main.py``가 한 줄로 호출).

    도메인 에러와 검증 에러만 표준화한다. Starlette ``HTTPException``(404/405)은
    오버라이드하지 않는다(프레임워크 기본 유지 — 범위 경계).
    """
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
