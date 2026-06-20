"""OpenAI 어댑터 등록 (Story 7.1 — 기준 프로바이더).

LangChain 통합 인터페이스(``langchain-openai``의 ``ChatOpenAI``)를 그대로 쓰므로 이 파일은
**메타데이터 등록만** 하는 얇은 파일이다(이게 정상 — 중복 구현 금지). OpenAI는 ≤2초 SLA
대상 기준 프로바이더이며 ``OPENAI_API_KEY``는 필수 키다(config.py REQUIRED, AC4).
"""
from __future__ import annotations

import openai

from app.chatbot.llm.base import ProviderSpec, register_provider

# openai.OpenAIError가 root — RateLimitError/APITimeoutError/AuthenticationError/APIError 모두 하위.
register_provider(
    ProviderSpec(
        name="openai",
        model_provider="openai",
        settings_key_attr="OPENAI_API_KEY",
        api_key_kwarg="api_key",
        required=True,
        native_exceptions=(openai.OpenAIError,),
    )
)
