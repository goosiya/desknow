"""인제스트 파이프라인 + 리포트 (Story 7.2, Task 5).

``ingest_corpus``: ``docs_corpus/`` 문서를 멱등하게 pgvector에 적재하는 코어 파이프라인.
라우터/엔드포인트가 아니라 **호출 가능한 함수**다(AC4) — 8.4(관리 API)가 재사용한다.

흐름(문서별 독립 처리 — AC3 부분 실패 격리):
  1. ``corpus_dir`` 텍스트 문서를 결정적 순서로 스캔.
  2. 문서별로: 내용 로딩 → ``content_hash`` 계산 → 기존 적재분 해시 대조
     - **동일** → 임베딩·DB 쓰기 모두 스킵(OpenAI 호출 0 — AC2 멱등).
     - **다름/신규** → 청크 분할 → 배치 임베딩 → 기존 청크 DELETE 후 신규 INSERT(단일 트랜잭션).
  3. 성공/스킵/실패를 ``IngestReport``로 집계해 반환(어떤 문서가 왜 실패했는지 식별 — AC3).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.chatbot.ingest.chunking import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    chunk_text,
    compute_content_hash,
    iter_corpus_files,
    load_document_text,
)
from app.chatbot.ingest.embedding import Embedder
from app.chatbot.ingest.store import DocumentChunkStore
from app.chatbot.models import EMBEDDING_DIM, DocumentChunk

logger = logging.getLogger(__name__)

# ``docs_corpus/`` 인제스트 기본 디렉터리(단일 출처 — scripts/CLI·8.4 admin이 공유).
# service.py는 ``app/chatbot/ingest/`` 아래라 parents: ingest(0)→chatbot(1)→app(2)→api(3).
# corpus 경로를 settings 신규 필드로 두면 ``_assert_key_lists_match_model``이 REQUIRED/OPTIONAL
# 동기화를 import-time 강제하므로(누락 시 RuntimeError), 모듈 상수로 둔다(Dev Notes §함정 #5).
DEFAULT_CORPUS_DIR = Path(__file__).resolve().parents[3] / "docs_corpus"


@dataclass
class IngestReport:
    """인제스트 결과 집계. 부분 실패 식별 = ``failed`` 목록(AC3).

    Attributes:
        succeeded: 신규/변경되어 (재)적재된 문서 경로(corpus 상대 POSIX).
        skipped: 내용 해시가 같아 적재를 스킵한 문서 경로(임베딩 호출 0).
        failed: ``(경로, 사유)`` 튜플 — 어떤 문서가 왜 실패했는지(AC3 그대로 충족).
        removed: 현 corpus에 없어 정리(DELETE)된 stale 문서 경로(orphan — 삭제/리네임 흔적).
            corpus 처리 문서가 아니라 정리분이므로 ``total``에는 포함하지 않는다(8.4 reconcile).
    """

    succeeded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """처리한 corpus 문서 총수(성공+스킵+실패). ``removed``(정리분)는 포함하지 않는다."""
        return len(self.succeeded) + len(self.skipped) + len(self.failed)


def ingest_corpus(
    store: DocumentChunkStore,
    corpus_dir: Path,
    embeddings: Embedder,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    reconcile: bool = True,
) -> IngestReport:
    """``corpus_dir`` 문서를 멱등하게 임베딩·적재하고 결과 리포트를 반환한다.

    Args:
        store: 영속 표면(``SqlDocumentChunkStore`` 또는 테스트 페이크). raw 세션 대신 store를
            주입해 단위 테스트가 pgvector 없는 실 DB 없이 멱등/부분실패를 실증한다(§함정 #6).
        corpus_dir: 인제스트 대상 디렉터리(``docs_corpus/``).
        embeddings: 배치 임베딩 클라이언트(``Embedder``). 프로덕션=OpenAI, 테스트=페이크.
        chunk_size, overlap: 결정적 청커 파라미터.
        reconcile: True면 적재 후 **현 corpus에 없는 stale 청크(orphan)를 정리**한다(8.4 — corpus
            에서 삭제/리네임된 문서의 옛 청크가 영구 잔존해 문서검색(7.5)을 오염시키는 것을 막음).
            ★빈 corpus(존재 파일 0)면 reconcile를 **스킵**해 전체 청크 wipe footgun을 방지한다.

    각 문서는 독립적으로 try/except 격리된다 — 한 문서 실패가 배치를 중단시키지 않고(AC3),
    문서 단위 트랜잭션이라 이미 성공한 문서를 롤백하지 않는다.
    """
    report = IngestReport()
    # 본 run에 **존재한** corpus 파일의 rel_path(성공/스킵/실패 무관 — 파일이 있으면 orphan 아님).
    # reconcile가 "DB에 있으나 corpus에 없는" 청크를 정리하는 기준 집합이다(stale GC — 8.4).
    present_paths: set[str] = set()
    for path in iter_corpus_files(corpus_dir):
        rel_path = path.relative_to(corpus_dir).as_posix()
        present_paths.add(rel_path)
        try:
            content = load_document_text(path)
            content_hash = compute_content_hash(content)

            # 멱등 대조: 기존 적재분과 해시가 같으면 임베딩·DB 쓰기 모두 스킵(AC2 — OpenAI 호출 0).
            if store.get_content_hash(rel_path) == content_hash:
                report.skipped.append(rel_path)
                continue

            # 공백뿐인 청크는 제거한다(검색 노이즈·임베딩 비용 0). chunk_index는 남은 청크에
            # 대해 enumerate로 0..n 연속 재부여되므로 정합성이 유지된다.
            chunk_contents = [c for c in chunk_text(content, chunk_size, overlap) if c.strip()]
            if not chunk_contents:
                # 유효 청크가 없으면 임베딩·DELETE를 건너뛴다(빈 replace로 기존 적재를 비우는
                # 데이터 소실 방지). load_document_text의 strip 가드 덕에 현 경로에선 드물지만,
                # 공백-only 문서 변형에 대한 방어다. skipped로 보고해 가시성을 남긴다.
                report.skipped.append(rel_path)
                continue
            # 임베딩은 변경/신규 문서에 대해서만 호출한다(스킵 경로는 위에서 이미 continue).
            vectors = embeddings.embed_documents(chunk_contents)
            if len(vectors) != len(chunk_contents):
                # 임베딩 결과 개수가 청크 수와 어긋나면 zip이 조용히 절단하므로 명시 차단한다.
                raise ValueError(
                    f"임베딩 개수 불일치: 청크 {len(chunk_contents)}개 vs 벡터 {len(vectors)}개."
                )

            chunks = [
                DocumentChunk(
                    source_path=rel_path,
                    content_hash=content_hash,
                    chunk_index=index,
                    content=chunk_content,
                    embedding=_validate_vector(vector),
                )
                for index, (chunk_content, vector) in enumerate(
                    zip(chunk_contents, vectors, strict=True)
                )
            ]
            store.replace_document_chunks(rel_path, chunks)
            report.succeeded.append(rel_path)
        except Exception as exc:  # noqa: BLE001 — 문서 단위 부분 실패로 흡수(AC3)
            # 공유 세션이 aborted 상태로 남아 다음 문서의 SELECT가 연쇄 실패(InFailedSqlTransaction)
            # 하지 않도록, 실패를 기록하기 전에 세션을 롤백해 격리를 보장한다(문서 단위 격리 — AC3).
            store.rollback()
            # 어떤 문서가 왜 실패했는지 식별(타입+메시지). 한 문서 실패가 배치를 중단시키지 않는다.
            report.failed.append((rel_path, f"{type(exc).__name__}: {exc}"))

    # stale 청크 정리(reconcile) — corpus에서 삭제/리네임된 문서의 orphan 청크를 DELETE한다(8.4).
    # ★footgun 가드: present_paths가 공집합(corpus 디렉터리 부재·빈 디렉터리·오설정)이면 reconcile를
    # 스킵한다 — 안 그러면 DB의 전체 청크가 orphan으로 간주돼 wipe된다(데이터 소실 사고 방지).
    if reconcile and present_paths:
        try:
            # per-doc 적재는 이미 commit됐으므로 reconcile는 자체 트랜잭션 best-effort다 — 실패가
            # 성공 적재를 롤백하면 안 된다. 실패 시 rollback + 로깅 후 removed는 빈 채로 진행한다.
            report.removed = store.delete_orphans(present_paths)
        except Exception:  # noqa: BLE001 — reconcile 실패는 best-effort(전체 리포트 미사망)
            store.rollback()
            logger.warning(
                "stale 청크 정리(reconcile)에 실패했습니다 — orphan 잔존 가능.", exc_info=True
            )
    return report


def _validate_vector(vector: list[float]) -> list[float]:
    """임베딩 벡터 차원이 ``EMBEDDING_DIM``(1536)인지 검증한다(차원 불변식 — Dev Notes §함정 #7).

    잘못된 차원은 DB 컬럼(``vector(1536)``)이 거부하지만, 그 전에 문서 단위 부분 실패로 명확히
    잡아 어떤 문서가 왜 실패했는지 사유에 남긴다.
    """
    if len(vector) != EMBEDDING_DIM:
        raise ValueError(
            f"임베딩 차원이 {EMBEDDING_DIM}이 아닙니다 (받은 차원: {len(vector)}). "
            "EMBEDDING_MODEL이 text-embedding-3-small인지 확인하세요."
        )
    return vector
