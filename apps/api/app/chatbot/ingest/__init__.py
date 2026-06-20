"""문서 인제스트 파이프라인 (Story 7.2).

``docs_corpus/`` 디렉터리의 텍스트 문서를 청크로 쪼개 OpenAI ``text-embedding-3-small``로
임베딩해 pgvector(``document_chunks``)에 **멱등하게** 적재하는 코어 파이프라인.

핵심 함수 ``ingest_corpus``는 라우터/엔드포인트가 아니라 **호출 가능한 함수**로 제공된다
(AC4). 관리 표면(트리거 UI·상태 조회 API)은 FR-33(Story 8.4)이 소유하며, 본 패키지의
``ingest_corpus``·``IngestReport``를 재사용한다.

후속 문서 RAG(7.5)의 유사도 검색·리트리버는 본 스토리 범위 밖이다 — 여기서는 적재만 한다.
"""
from __future__ import annotations

from app.chatbot.ingest.chunking import (
    SUPPORTED_EXTENSIONS,
    chunk_text,
    compute_content_hash,
    iter_corpus_files,
    load_document_text,
)
from app.chatbot.ingest.embedding import Embedder, build_embedder
from app.chatbot.ingest.service import (
    DEFAULT_CORPUS_DIR,
    IngestReport,
    ingest_corpus,
)
from app.chatbot.ingest.store import DocumentChunkStore, SqlDocumentChunkStore

__all__ = [
    "DEFAULT_CORPUS_DIR",
    "SUPPORTED_EXTENSIONS",
    "DocumentChunkStore",
    "Embedder",
    "IngestReport",
    "SqlDocumentChunkStore",
    "build_embedder",
    "chunk_text",
    "compute_content_hash",
    "ingest_corpus",
    "iter_corpus_files",
    "load_document_text",
]
