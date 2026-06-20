"""문서 벡터 검색 (Story 7.5, Task 1).

7.2가 적재한 ``document_chunks``(pgvector)에서 **질의와 가장 가까운 청크**를 코사인 거리로
회수하는 **순수·주입식** 함수다. 7.5 RAG의 "검색" 단계 — 라우터/툴이 아니라 호출 가능한 함수로
제공해, 단위 테스트가 페이크 ``Session``/``Embedder``로 네트워크·실키 없이 검증 가능하게 한다
(7.2 store 주입 정신과 동일).

★경계(반드시 재사용 — 재발명 금지):
- 쿼리 임베딩은 7.2 ``Embedder`` Protocol(``embed_documents``)을 그대로 쓴다(쿼리 1건은
  ``embed_documents([query])[0]``). 신규 임베더를 만들지 않는다 — chat 어댑터(7.1)와도 무관한
  별도 임베딩 경로다(``ingest/embedding.py`` §경계).
- 검색 대상 테이블·차원은 7.2 ``DocumentChunk``/``EMBEDDING_DIM``. HNSW 인덱스가
  ``vector_cosine_ops``(``models.py`` L27)이므로 **코사인 거리**가 인덱스와 정합한다.

★함정(SQLite·pgvector): 단위 테스트의 SQLite는 ``Vector``/코사인 연산자를 모른다(7.2 §함정 #6).
실제 코사인 정렬·임계값 동작은 **실 Postgres 통합/골든셋 테스트**에서 검증한다. 단위 테스트는
페이크 ``Session``으로 임계값 필터·반환 형태만 실증한다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import col, select

from app.chatbot.models import DocumentChunk

if TYPE_CHECKING:
    from sqlmodel import Session

    from app.chatbot.ingest.embedding import Embedder

# 회수 상위 청크 수. 4~5면 근거 그라운딩에 충분하고 프롬프트 토큰도 절제된다.
DEFAULT_TOP_K = 5

# 근거 채택 코사인 거리 상한(0=동일, 2=정반대). 이 값을 넘는 청크는 질의와 무관하다고 보고
# 버린다 → 채택 청크가 0이면 툴이 "관련 근거를 찾지 못함"을 반환해 모델이 분기 b(모름)로 간다.
# 근거 채택 코사인 거리 상한(0=동일, 2=정반대). 이 값을 넘는 청크는 질의와 무관하다고 보고
# 버린다 → 채택 청크가 0이면 툴이 "관련 근거를 찾지 못함"을 반환해 모델이 분기 b(모름)로 간다.
# 근거 채택의 **엄격 거리 바닥**(0=동일, 2=정반대). tools.search_service_docs는 더 넓게 회수한 뒤
# (느슨한 _RETRIEVE_MAX_DISTANCE) 회색지대 후보를 LLM grade로 판정한다 — 거리는 "주제 관련"만
# 알려줘 "답 포함"을 못 가르기 때문(임베딩 교체·청킹 실험으로 거리론 못 가름이 확인됨, 2026-06-18).
# 이 상수는 ① grade를 생략하는 확신 채택의 바닥, ② grade 실패 시 강등 임계값으로 쓰인다.
DEFAULT_MAX_DISTANCE = 0.6


def search_by_vector(
    session: Session,
    query_vec: list[float],
    *,
    top_k: int = DEFAULT_TOP_K,
    max_distance: float = DEFAULT_MAX_DISTANCE,
) -> list[tuple[DocumentChunk, float]]:
    """**미리 임베딩된** 쿼리 벡터로 코사인 거리 상위 청크를 회수한다(채택 임계값 적용).

    다중쿼리에서 여러 쿼리를 **한 번에 배치 임베딩**한 뒤 벡터별로 호출해 임베딩 round-trip을
    모으려고 분리했다(지연↓). ``search_documents``는 단건을 임베딩해 이 함수에 위임하는 래퍼다.

    Returns:
        ``(청크, 코사인 거리)`` 튜플 리스트(거리 오름차순, ``max_distance`` 이내만). 거리를 함께
        반환해야 호출처가 채택/모름 분기를 판정할 수 있다.
    """
    # pgvector 코사인 거리 식. HNSW vector_cosine_ops 인덱스와 정합해 ORDER BY ... ASC가
    # 인덱스 스캔으로 풀린다. ``cosine_distance``는 pgvector comparator라 mypy 스텁에 없다 →
    # attr-defined만 좁혀 무시한다(런타임은 정상 — 통합/골든셋에서 실증).
    distance = col(DocumentChunk.embedding).cosine_distance(query_vec)  # type: ignore[attr-defined]
    rows = session.exec(
        select(DocumentChunk, distance.label("distance"))
        .order_by(distance.asc())
        .limit(top_k)
    ).all()
    # 임계값 초과(=무관) 후보는 버린다. 결과가 비면 호출처가 분기 b(모름)로 간다.
    return [
        (chunk, float(dist))
        for chunk, dist in rows
        if dist is not None and float(dist) <= max_distance
    ]


def search_documents(
    session: Session,
    query: str,
    embedder: Embedder,
    *,
    top_k: int = DEFAULT_TOP_K,
    max_distance: float = DEFAULT_MAX_DISTANCE,
) -> list[tuple[DocumentChunk, float]]:
    """``query`` 1건을 임베딩해 ``search_by_vector``에 위임한다(단건 편의 래퍼).

    Args:
        session: DB 세션(프로덕션=실 ``Session``, 테스트=페이크). 호출처(툴)가 세션 수명을 제어.
        query: 사용자 질의 문자열.
        embedder: 배치 임베딩 클라이언트(``Embedder`` Protocol, 페이크 주입 가능).
        top_k: 코사인 거리 오름차순 상위 몇 개를 후보로 볼지(>0).
        max_distance: 근거로 채택할 코사인 거리 상한(초과는 무관으로 버림).
    """
    # 쿼리 1건 임베딩(7.2 Embedder 재사용 — 배치 API에 단건을 넣고 0번째를 꺼낸다).
    query_vec = embedder.embed_documents([query])[0]
    return search_by_vector(
        session, query_vec, top_k=top_k, max_distance=max_distance
    )
