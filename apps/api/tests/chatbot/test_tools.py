"""문서검색 툴 단위 테스트 (Story 7.5 — Task 2, 네트워크/실키/DB 불필요).

검증 항목:
  - 채택 청크가 있으면 ``content``(+출처)를 그라운딩 컨텍스트로 직렬화
  - 채택 청크가 없으면(임계값 초과) **명시 "관련 근거를 찾지 못했어요." 신호** 반환(환각 유도 금지)
  - 검색 로직은 ``retrieval.search_documents``에 위임(툴은 얇다) — monkeypatch로 DB/키 없이 검증

툴은 자체 단명 세션(``Session(get_engine())``)을 열지만, ``search_documents``를 monkeypatch하면
세션은 쿼리를 실행하지 않으므로(엔진은 lazy·연결 0) 실 DB 없이 돈다. ``_get_embedder``도
패치해 OpenAI 클라 생성을 피한다.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.chatbot import tools as tools_mod
from app.chatbot.models import DocumentChunk
from app.chatbot.tools import NO_RELEVANT_DOCS, search_service_docs


def _chunk(source_path: str, content: str) -> DocumentChunk:
    return DocumentChunk(
        source_path=source_path,
        content_hash="h",
        chunk_index=0,
        content=content,
        embedding=[0.0],
    )


@pytest.fixture(autouse=True)
def _patch_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI 임베더 생성을 피한다(툴은 _get_embedder를 호출 — 더미로 대체)."""
    monkeypatch.setattr(tools_mod, "_get_embedder", lambda: object())


def _invoke(query: str) -> str:
    # LangChain @tool은 .invoke({"query": ...})로 호출(스키마 검증 포함).
    return search_service_docs.invoke({"query": query})


def test_tool_serializes_adopted_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_search(session: Any, query: str, embedder: Any, **kw: Any) -> list[Any]:
        return [
            (_chunk("faq/refund.md", "환불은 이용 6시간 전까지 가능합니다."), 0.2),
            (_chunk("faq/usage.md", "이용은 예약한 시간에 입실하세요."), 0.4),
        ]

    monkeypatch.setattr(tools_mod, "search_documents", fake_search)
    result = _invoke("환불 어떻게 해요?")

    # 근거 텍스트와 출처가 그라운딩 컨텍스트에 포함된다.
    assert "환불은 이용 6시간 전까지 가능합니다." in result
    assert "이용은 예약한 시간에 입실하세요." in result
    assert "faq/refund.md" in result
    assert "faq/usage.md" in result


def test_tool_returns_no_relevant_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    # 채택 청크가 없으면(임계값 초과) 명시 신호를 반환 → 모델이 분기 b(모름)로 간다.
    monkeypatch.setattr(
        tools_mod, "search_documents", lambda *a, **k: []
    )
    result = _invoke("전혀 무관한 질문")
    assert result == NO_RELEVANT_DOCS
