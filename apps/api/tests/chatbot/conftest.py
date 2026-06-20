"""chatbot 테스트 공유 픽스처.

chatbot 툴(``search_available_rooms``·``search_service_docs``)은 자체 단명 세션
``Session(get_engine())``을 열며, get_engine→get_settings가 필수 env(5키)를 읽는다. DB·검색을
monkeypatch해 실 DB 없이 도는 단위 테스트라도 env가 없으면 get_settings가 ValidationError를 낸다.
로컬은 ``.env``가 채우지만 CI엔 ``.env``가 없어 실패했다(2026-06-20). → 이 디렉터리 전체에 부모
conftest의 ``auth_env``(필수 env 주입)를 autouse로 끌어와 적용한다.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _chatbot_env(auth_env: None) -> None:
    """부모 ``auth_env``를 chatbot 디렉터리 전체에 autouse로 적용해 필수 env를 주입한다."""
