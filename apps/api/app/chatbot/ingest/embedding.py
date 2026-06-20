"""임베딩 클라이언트 (Story 7.2, Task 4).

★설계 의도(Dev Notes §경계): 임베딩은 **7.1 멀티 LLM 어댑터를 거치지 않는다**. 어댑터는 chat
model 전용(채팅·툴콜·스트리밍)이고, 임베딩은 **단일 고정 모델**(``text-embedding-3-small``)이라
프로바이더 분기가 없다 → ``chatbot/llm/``(채팅 어댑터)과 별개 경로다.

- 클라이언트는 ``langchain_openai.OpenAIEmbeddings``(이미 설치된 ``langchain-openai`` —
  신규 의존성 0). ``openai`` SDK를 직접 import해 HTTP를 손코딩하지 않는다.
- **api_key를 settings에서 명시 전달**한다(7.1 footgun 일관성 — env 자동 픽업 의존 금지,
  키 백엔드 격리 NFR-6). 모델명도 ``settings.EMBEDDING_MODEL``(하드코딩 금지).
- 파이프라인은 ``Embedder`` Protocol에만 의존한다 → 테스트는 네트워크 없이 페이크로 주입한다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.core.config import get_settings

if TYPE_CHECKING:
    from langchain_openai import OpenAIEmbeddings


@runtime_checkable
class Embedder(Protocol):
    """배치 임베딩 인터페이스(파이프라인이 의존하는 최소 표면).

    ``OpenAIEmbeddings``가 이 시그니처를 만족하며, 테스트는 결정적 더미 벡터를 내는 페이크를
    주입한다(네트워크·실키 0).
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """여러 텍스트를 한 번에 임베딩해 각 벡터(``list[float]``) 리스트를 반환한다."""
        ...


def build_embedder() -> OpenAIEmbeddings:
    """settings 기반 OpenAI 임베딩 클라이언트를 생성한다(실행 진입점이 배선).

    ``api_key``/``model``을 settings에서 **명시 전달**한다(env 자동 픽업 의존 금지 — 7.1 footgun).
    import는 함수 내부에서 한다 — 모듈 import만으로 OpenAI 의존을 끌어오지 않게 해, 페이크로
    테스트하는 경로(파이프라인 단위 테스트)가 OpenAI 설치/키와 무관하게 가볍게 돈다.
    """
    from langchain_openai import OpenAIEmbeddings

    settings = get_settings()
    # 필드명 openai_api_key로 명시 전달(footgun 차단). alias는 ``api_key``지만 필드명이 mypy
    # (pydantic 플러그인)·런타임(populate_by_name) 양쪽에서 통한다. 모델명도 명시(하드코딩 금지).
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        openai_api_key=settings.OPENAI_API_KEY,
    )
