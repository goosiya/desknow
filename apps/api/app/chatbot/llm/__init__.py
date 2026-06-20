"""멀티 LLM 어댑터 레이어 (Story 7.1).

설정(``LLM_PROVIDER``/``LLM_MODEL``)만 바꿔 OpenAI/Anthropic/Google을 전환해도 챗봇 공통 5종
기능(채팅·시스템프롬프트·툴콜·스트리밍·범위밖거절)이 if 분기 없이 동일하게 동작하도록, 세
프로바이더의 요청/응답/스트리밍/에러 차이를 단일 공통 표면으로 흡수한다(FR-29, NFR-2·6).

하위 chatbot 코드는 LangChain 프로바이더 클래스에 직접 의존하지 말고 이 패키지의
``create_chat_model``만 사용한다.
"""
from __future__ import annotations

from app.chatbot.llm.base import (
    ProviderSpec,
    create_chat_model,
    get_provider_spec,
    list_providers,
    register_provider,
    with_transient_retry,
)
from app.chatbot.llm.errors import LLMConfigurationError, normalize_llm_error

__all__ = [
    "LLMConfigurationError",
    "ProviderSpec",
    "create_chat_model",
    "get_provider_spec",
    "list_providers",
    "normalize_llm_error",
    "register_provider",
    "with_transient_retry",
]
