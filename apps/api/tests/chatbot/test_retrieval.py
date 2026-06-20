"""문서 벡터 검색 단위 테스트 (Story 7.5 — Task 1, 네트워크/실키/DB 불필요).

검증 항목(단위 가능 범위):
  - 쿼리 1건을 ``Embedder.embed_documents([query])[0]``로 임베딩(7.2 재사용 — 페이크 주입)
  - 임계값(``max_distance``) 초과 후보는 버린다 → 채택 0이면 빈 리스트(분기 b 토대)
  - 반환은 ``(청크, 코사인 거리)`` 튜플 — 거리를 함께 반환(분기 판정용)
  - ``top_k``/``max_distance``가 SQL 식·필터에 반영된다

★실제 코사인 정렬·임계값(실 pgvector)은 SQLite가 ``Vector``를 모르므로(7.2 §함정 #6) 라이브
통합/골든셋(test_golden_set.py)에서 검증한다. 여기선 페이크 ``Session``으로 임계값 필터·반환
형태만 결정적으로 실증한다(검색 SQL은 빌드되지만 실행되지 않는다).
"""
from __future__ import annotations

from typing import Any

from app.chatbot.models import DocumentChunk
from app.chatbot.retrieval import DEFAULT_MAX_DISTANCE, search_documents


class _FakeEmbedder:
    """``embed_documents``만 구현하는 페이크(쿼리 임베딩 호출만 기록)."""

    def __init__(self) -> None:
        self.queries: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.queries.append(list(texts))
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FakeResult:
    def __init__(self, rows: list[tuple[DocumentChunk, float]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[DocumentChunk, float]]:
        return self._rows


class _FakeSession:
    """``exec(stmt).all()``로 미리 정한 (청크, 거리) 행을 돌려주는 페이크.

    검색 식(``cosine_distance`` ORDER BY/LIMIT)은 정상적으로 빌드되지만, 페이크는 statement를
    무시하고 캔드 행을 반환한다 — 임계값 필터·반환 형태를 DB 없이 실증한다.
    """

    def __init__(self, rows: list[tuple[DocumentChunk, float]]) -> None:
        self._rows = rows
        self.exec_called = 0

    def exec(self, statement: Any) -> _FakeResult:
        self.exec_called += 1
        return _FakeResult(self._rows)


def _chunk(source_path: str, content: str) -> DocumentChunk:
    return DocumentChunk(
        source_path=source_path,
        content_hash="h",
        chunk_index=0,
        content=content,
        embedding=[0.0, 0.0, 0.0],
    )


def test_search_embeds_query_once_via_protocol() -> None:
    near = _chunk("faq.md", "환불은 6시간 전까지 가능합니다.")
    embedder = _FakeEmbedder()
    search_documents(_FakeSession([(near, 0.2)]), "환불 어떻게 해요?", embedder)
    # 쿼리 1건을 embed_documents([query])로 임베딩(배치 API 단건 재사용 — 7.2 경계).
    assert embedder.queries == [["환불 어떻게 해요?"]]


def test_search_returns_chunk_and_distance() -> None:
    near = _chunk("faq.md", "환불은 6시간 전까지 가능합니다.")
    results = search_documents(_FakeSession([(near, 0.2)]), "환불", _FakeEmbedder())
    assert len(results) == 1
    chunk, distance = results[0]
    assert chunk.content == "환불은 6시간 전까지 가능합니다."
    assert distance == 0.2  # 거리를 함께 반환(분기 판정용)


def test_search_drops_candidates_beyond_threshold() -> None:
    near = _chunk("faq.md", "관련 근거")
    far = _chunk("other.md", "무관 텍스트")
    # 임계값 0.6 이내(0.3)만 채택, 초과(0.9)는 버린다.
    rows = [(near, 0.3), (far, 0.9)]
    results = search_documents(
        _FakeSession(rows), "질문", _FakeEmbedder(), max_distance=DEFAULT_MAX_DISTANCE
    )
    assert [c.source_path for c, _ in results] == ["faq.md"]


def test_search_returns_empty_when_all_beyond_threshold() -> None:
    far1 = _chunk("a.md", "무관1")
    far2 = _chunk("b.md", "무관2")
    # 모든 후보가 임계값 초과 → 빈 리스트(툴이 "관련 근거 없음" 신호 → 분기 b).
    results = search_documents(
        _FakeSession([(far1, 0.8), (far2, 1.1)]), "전혀 무관한 질문", _FakeEmbedder()
    )
    assert results == []
