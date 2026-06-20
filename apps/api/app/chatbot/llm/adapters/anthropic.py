"""Anthropic 어댑터 등록 (Story 7.1 — best-effort 프로바이더).

``langchain-anthropic``의 ``ChatAnthropic``을 그대로 쓰는 얇은 등록 파일. Anthropic은
best-effort라 ``ANTHROPIC_API_KEY``는 선택 키다(미설정 시 이 프로바이더 선택만 실패, AC4).
"""
from __future__ import annotations

import anthropic

from app.chatbot.llm.base import ProviderSpec, register_provider

# anthropic.AnthropicError가 root — RateLimitError/APITimeoutError/AuthenticationError 등 하위.
register_provider(
    ProviderSpec(
        name="anthropic",
        model_provider="anthropic",
        settings_key_attr="ANTHROPIC_API_KEY",
        api_key_kwarg="api_key",
        required=False,
        native_exceptions=(anthropic.AnthropicError,),
    )
)
