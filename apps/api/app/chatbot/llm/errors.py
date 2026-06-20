"""LLM 어댑터 에러 정규화 (Story 7.1).

리서치/런타임 확인: ``langchain_core.exceptions``는 파싱·트레이싱 등 LangChain 자체 에러만
다루고, **프로바이더 API/네트워크/레이트리밋 예외는 wrapping 없이 네이티브로 그대로 전파**된다
(공통 베이스 예외 없음). 따라서 에러 스키마 차이 흡수(AC3)는 어댑터가 직접 매핑해야 한다.

- 각 프로바이더의 네이티브 예외 root(``openai.OpenAIError`` / ``anthropic.AnthropicError`` /
  ``google.genai.errors.APIError``)는 각 ``ProviderSpec.native_exceptions``가 들고 있다(base.py).
- 업스트림 호출부(후속 7.3/7.4)는 ``except spec.native_exceptions``로 잡아
  ``normalize_llm_error``로 단일 ``DomainError(LLM_PROVIDER_UNAVAILABLE)``(502)로 변환한다.

**비밀 누출 주의:** 네이티브 예외 메시지에는 API 키·요청 본문이 섞일 수 있다. 사용자에게는
안전한 고정 문구만 노출하고, 원문은 ``logger``로만 남긴다(config.py ``mask_secret`` 정신).
"""
from __future__ import annotations

import logging

from app.core.errors import DomainError, ErrorCode

logger = logging.getLogger(__name__)


class LLMConfigurationError(Exception):
    """LLM 어댑터 **설정** 오류(미등록 프로바이더 문자열·선택 프로바이더 키 미설정).

    이건 업스트림 런타임 실패가 아니라 개발/배포 설정 문제다 → 업스트림 502를 뜻하는
    ``DomainError(LLM_PROVIDER_UNAVAILABLE)``와 의도적으로 구분한다(잘못된 설정을 502 업스트림
    장애로 위장하지 않는다). 기준 프로바이더는 정상 동작하고 이 선택만 실패한다(AC4).
    """


def normalize_llm_error(exc: BaseException, provider: str) -> DomainError:
    """프로바이더 네이티브 예외(레이트리밋/타임아웃/인증/일반 API 에러)를 단일 도메인 예외로 변환.

    호출 측은 ``ProviderSpec.native_exceptions``로 좁혀 catch한 뒤 이 함수로 변환한다.
    원문 메시지(키·요청이 섞일 수 있음)는 **로깅만** 하고, 반환 ``DomainError.message``에는
    절대 싣지 않는다(비밀 비노출 — config.py 규약). 프로바이더 이름은 비밀이 아니므로 노출 OK.
    """
    # 원문은 진단용으로만 — 예외 타입명까지만 남기고 str(exc)는 메시지에 싣지 않는다.
    logger.warning(
        "LLM 업스트림 실패: provider=%s exc_type=%s", provider, type(exc).__name__
    )
    return DomainError(
        ErrorCode.LLM_PROVIDER_UNAVAILABLE,
        f"LLM 제공자({provider}) 요청에 실패했습니다. 잠시 후 다시 시도해 주세요.",
    )
