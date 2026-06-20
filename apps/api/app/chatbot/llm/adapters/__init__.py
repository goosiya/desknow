"""LLM 프로바이더 어댑터 (Story 7.1).

각 모듈 import의 **부작용으로 ProviderSpec이 base 레지스트리에 등록**된다. base가 첫 조회
시점에 이 패키지를 1회 import해 레지스트리를 채운다(``base._ensure_providers_loaded``).
"""
from __future__ import annotations

from app.chatbot.llm.adapters import anthropic, google, openai  # noqa: F401  등록 부작용
