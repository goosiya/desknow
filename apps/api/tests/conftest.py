"""공유 테스트 픽스처 (Story 1.8).

JWT 발급/검증 함수는 ``get_settings()``(5개 필수 키 전부)를 소비하므로, JWT를 건드리는
테스트는 필수 env를 주입해야 한다. ``auth_env``는 **non-autouse** 픽스처라 요청한 테스트만
적용된다 → test_config(자체 env 조작)·test_main(import 안전)과 무간섭.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.config import get_settings
from app.core.db import get_engine

# 필수 키 전부(JWT_SECRET_KEY는 ≥32자 — InsecureKeyLengthWarning 회피).
_AUTH_ENV = {
    "KAKAO_REST_API_KEY": "test-kakao-rest",
    "KAKAO_JS_KEY": "test-kakao-js",
    "OPENAI_API_KEY": "test-openai",
    "DATABASE_URL": "postgresql://u:p@localhost:5432/desknow",
    "JWT_SECRET_KEY": "test-jwt-secret-key-at-least-32-bytes-long-xx",
}


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """필수 env(특히 JWT_SECRET_KEY)를 주입하고 settings/engine 캐시를 비운다.

    JWT를 발급/검증하는 단위·라우터 테스트만 명시적으로 요청한다(라이브 DB 무관).
    """
    for k, v in _AUTH_ENV.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
