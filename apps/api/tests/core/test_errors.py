"""core.errors 단위 + 경량 통합 테스트 (Story 1.5 — 라이브 DB 불필요).

검증 항목:
  (AC2) ErrorCode가 StrEnum(str 인스턴스, 값=코드 문자열) — 상수 단일 출처
  (AC3) DomainError.status_code가 코드→상태 레지스트리 기본과 일치(409/403/401/422)
  (AC2) ErrorResponse/ErrorDetail가 {"detail":{"code","message"}}로 직렬화
  (AC2/AC3) 핸들러 와이어 — 미니 FastAPI 앱에 register_exception_handlers 적용 후
            DomainError(409/403/401)·RequestValidationError(422) 모두 표준 스키마로 응답

핸들러 와이어는 실 app을 오염시키지 않도록 테스트 내부 미니 앱으로 검증한다
(TestClient(mini_app) — 실 앱 lifespan/DB 무관).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import (
    DEFAULT_STATUS,
    DomainError,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    register_exception_handlers,
)


# (a) ErrorCode = StrEnum -------------------------------------------------------
def test_error_code_is_str_enum():
    assert isinstance(ErrorCode.SLOT_CONFLICT, str)
    assert ErrorCode.SLOT_CONFLICT == "SLOT_CONFLICT"
    assert ErrorCode.SLOT_CONFLICT.value == "SLOT_CONFLICT"


def test_default_status_covers_all_error_codes():
    # 후속 스토리가 ErrorCode에 멤버를 추가하면서 DEFAULT_STATUS 등록을 누락하면,
    # DomainError(code) 생성이 KeyError로 500을 내 표준 스키마를 우회한다(이 모듈의 존재
    # 이유와 정반대). 레지스트리↔enum 완전성을 회귀로 가드한다.
    assert set(DEFAULT_STATUS) == set(ErrorCode)


# (b) DomainError 상태 매핑 -----------------------------------------------------
@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        (ErrorCode.SLOT_CONFLICT, 409),
        (ErrorCode.EMAIL_TAKEN, 409),
        (ErrorCode.CANCEL_WINDOW_PASSED, 409),
        (ErrorCode.REJECT_WINDOW_PASSED, 409),  # 거절 시작 후 차단(FR-24, 6.2)
        (ErrorCode.FORBIDDEN_ROLE, 403),
        (ErrorCode.UNAUTHENTICATED, 401),
        (ErrorCode.VALIDATION_ERROR, 422),
    ],
)
def test_domain_error_default_status(code: ErrorCode, expected_status: int):
    err = DomainError(code, "메시지")
    assert err.status_code == expected_status
    assert err.status_code == DEFAULT_STATUS[code]
    assert err.code is code
    assert err.message == "메시지"


def test_domain_error_status_override():
    err = DomainError(ErrorCode.SLOT_CONFLICT, "x", status_code=400)
    assert err.status_code == 400


# (c) 응답 스키마 직렬화 --------------------------------------------------------
def test_error_response_serialization():
    resp = ErrorResponse(detail=ErrorDetail(code=ErrorCode.SLOT_CONFLICT, message="충돌"))
    assert resp.model_dump(mode="json") == {
        "detail": {"code": "SLOT_CONFLICT", "message": "충돌"}
    }


# 핸들러 와이어용 미니 앱 -------------------------------------------------------
def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/conflict")
    def conflict() -> dict[str, str]:
        raise DomainError(ErrorCode.SLOT_CONFLICT, "이미 예약된 슬롯입니다.")

    @app.get("/forbidden")
    def forbidden() -> dict[str, str]:
        raise DomainError(ErrorCode.FORBIDDEN_ROLE, "권한이 없습니다.")

    @app.get("/unauth")
    def unauth() -> dict[str, str]:
        raise DomainError(ErrorCode.UNAUTHENTICATED, "로그인이 필요합니다.")

    @app.get("/needs-q")
    def needs_q(value: int) -> dict[str, int]:  # 필수 쿼리 파라미터
        return {"value": value}

    return app


# (AC3) DomainError 핸들러 — 409 -----------------------------------------------
def test_domain_error_handler_conflict_409():
    client = TestClient(_make_app())
    resp = client.get("/conflict")
    assert resp.status_code == 409
    assert resp.json() == {
        "detail": {"code": "SLOT_CONFLICT", "message": "이미 예약된 슬롯입니다."}
    }


# (AC3) DomainError 핸들러 — 403 -----------------------------------------------
def test_domain_error_handler_forbidden_403():
    client = TestClient(_make_app())
    resp = client.get("/forbidden")
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


# (AC3) DomainError 핸들러 — 401 -----------------------------------------------
def test_domain_error_handler_unauthenticated_401():
    client = TestClient(_make_app())
    resp = client.get("/unauth")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# (AC3) RequestValidationError 핸들러 — 422 표준화 ------------------------------
def test_validation_error_handler_422_standardized():
    client = TestClient(_make_app())
    resp = client.get("/needs-q")  # 필수 value 누락 → RequestValidationError
    assert resp.status_code == 422
    body = resp.json()
    # FastAPI 기본 배열 형태가 아니라 표준 스키마로 단일화되어야 한다
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["detail"]["message"], str)
