"""FastAPI 앱 셸 테스트 (Story 1.2).

- ``GET /api/v1/health`` → 200 ``{"status": "ok"}`` (AC2 기동·liveness).
- ``/api/v1`` 프리픽스가 적용되어 프리픽스 없는 경로는 404 (AC3 버저닝).
- CORS 미들웨어가 등록되어 허용 origin에 ACAO 헤더가 응답된다 (AC3 CORS).
- preflight(``OPTIONS``)와 비허용 origin 처리까지 검증한다 (AC3 CORS 견고화).

참고: ``get_settings()``의 fail-fast는 앱 ``lifespan``(startup)에서 트리거되므로,
``app.main`` import 자체는 ``.env`` 없이도 안전하다(``TestClient(app)``를 ``with`` 없이
모듈 레벨로 생성하면 lifespan이 실행되지 않아 환경 검증이 수집을 막지 않는다).
"""
from __future__ import annotations

from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.errors import DomainError
from app.main import API_V1_PREFIX, app

client = TestClient(app)


def test_health_returns_ok() -> None:
    """헬스 엔드포인트는 200과 {"status": "ok"}를 반환한다."""
    response = client.get(f"{API_V1_PREFIX}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_requires_v1_prefix() -> None:
    """프리픽스 없는 /health는 등록되지 않아 404 (버저닝 보장)."""
    response = client.get("/health")
    assert response.status_code == 404


def test_cors_allows_web_origin() -> None:
    """CORS 미들웨어가 허용 웹 origin에 ACAO 헤더를 응답한다(simple request)."""
    response = client.get(
        f"{API_V1_PREFIX}/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_preflight_allows_web_origin() -> None:
    """preflight(OPTIONS)에 허용 origin·메서드면 ACAO와 credentials 헤더를 응답한다."""
    response = client.options(
        f"{API_V1_PREFIX}/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejects_unknown_origin() -> None:
    """비허용 origin에는 ACAO 헤더를 붙이지 않는다(요청은 통과하나 브라우저가 차단)."""
    response = client.get(
        f"{API_V1_PREFIX}/health",
        headers={"Origin": "http://evil.example.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_exception_handlers_registered() -> None:
    """실 app에 도메인·검증 예외 핸들러가 배선되어 있다(Story 1.5 register_exception_handlers).

    test_errors는 미니앱으로 핸들러 동작을 검증하므로, 실 ``app``이 실제로 배선됐는지
    (main.py의 register 호출)를 여기서 회귀로 가드한다. import만 트리거하므로 DB 무관.
    """
    assert DomainError in app.exception_handlers
    assert RequestValidationError in app.exception_handlers
