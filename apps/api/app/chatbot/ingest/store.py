"""인제스트 영속 계층 (Story 7.2, Task 5).

파이프라인(``service.ingest_corpus``)을 raw SQL/세션에서 분리하는 얇은 데이터 접근 표면이다.
파이프라인은 ``DocumentChunkStore`` Protocol에만 의존하므로:

- 프로덕션은 ``SqlDocumentChunkStore``(실 ``Session``)를 주입한다.
- 단위 테스트는 인메모리 페이크를 주입한다 — **SQLite는 pgvector 타입을 모르므로**(Dev Notes
  §함정 #6) 실 DB 없이 멱등 결정 로직·해시 대조·DELETE/INSERT 동작을 검증할 수 있다.

**문서 단위 원자성(AC3):** ``replace_document_chunks``의 DELETE+INSERT는 단일 트랜잭션이다 —
한 문서의 적재가 절반만 커밋되는 일이 없고(commit 또는 rollback), 한 문서 실패가 이미 커밋된
다른 문서를 롤백하지 않는다(문서별 commit 경계).
"""
from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Protocol

from sqlmodel import Session, col, delete, func, select

from app.chatbot.models import DocumentChunk


class DocumentChunkStore(Protocol):
    """파이프라인이 의존하는 최소 영속 표면(멱등 대조 + 원자 교체 + stale 정리)."""

    def get_content_hash(self, source_path: str) -> str | None:
        """``source_path`` 기존 적재분의 ``content_hash``를 반환한다(없으면 ``None``).

        한 문서의 청크들은 동일 ``content_hash``를 denormalize 공유하므로 1행만 읽으면 된다.
        """
        ...

    def replace_document_chunks(
        self, source_path: str, chunks: Sequence[DocumentChunk]
    ) -> None:
        """``source_path`` 기존 청크를 모두 삭제하고 새 청크를 적재한다(단일 트랜잭션 — 원자).

        stale 벡터 잔존 0(기존 전량 삭제). 실패 시 롤백하고 예외를 올린다(부분 적재 0).
        """
        ...

    def rollback(self) -> None:
        """진행 중인 트랜잭션을 되돌려 세션을 깨끗한 상태로 만든다(문서 단위 격리 방어).

        파이프라인은 한 문서 실패를 흡수한 뒤 **다음 문서로 넘어가기 전** 이 메서드를 호출한다.
        공유 세션에서 한 문서의 DB 오류가 트랜잭션을 aborted 상태로 남기면, 이후 문서의 SELECT가
        ``InFailedSqlTransaction``으로 연쇄 실패한다(AC3 격리 구멍). 실패 직후 롤백해 전파를 끊는다.
        """
        ...

    def delete_orphans(self, present_source_paths: Collection[str]) -> list[str]:
        """현 corpus에 없는(``present_source_paths`` 밖) ``source_path``의 청크를 DELETE한다(8.4).

        corpus에서 삭제/리네임된 문서의 옛 청크(orphan)가 DB에 영구 잔존하면 문서검색(7.5)이
        삭제된 안내를 근거로 회수해 환각할 수 있다(deferred-work L344). DB에 적재된 distinct
        ``source_path`` 중 ``present_source_paths``에 없는 것을 정리하고 삭제 경로 목록을 반환한다.
        """
        ...


class SqlDocumentChunkStore:
    """``Session`` 기반 ``DocumentChunkStore`` 구현(프로덕션)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_content_hash(self, source_path: str) -> str | None:
        return self._session.exec(
            select(DocumentChunk.content_hash)
            .where(col(DocumentChunk.source_path) == source_path)
            .limit(1)
        ).first()

    def replace_document_chunks(
        self, source_path: str, chunks: Sequence[DocumentChunk]
    ) -> None:
        chunk_list = list(chunks)
        # 빈 청크로 호출되면 no-op(기존 적재를 DELETE만 하고 0행 INSERT하는 데이터 소실 방지 —
        # 방어). 현 파이프라인은 빈 청크를 service에서 이미 거르지만, 8.4 관리 표면이 store를
        # 재사용할 때를 대비한 가드다.
        if not chunk_list:
            return
        # DELETE + INSERT를 단일 트랜잭션으로 커밋한다(문서 단위 원자성 — AC3). 멱등 DELETE가
        # 기존 행을 비우므로 (source_path, chunk_index) UNIQUE 위반 없이 재적재된다.
        try:
            self._session.exec(
                delete(DocumentChunk).where(
                    col(DocumentChunk.source_path) == source_path
                )
            )
            self._session.add_all(chunk_list)
            self._session.commit()
        except Exception:
            # 한 문서의 쓰기 실패가 절반만 적재되지 않도록 롤백 후 올린다(파이프라인이 부분
            # 실패로 흡수 — 이미 커밋된 다른 문서에는 영향 없음).
            self._session.rollback()
            raise

    def rollback(self) -> None:
        self._session.rollback()

    def delete_orphans(self, present_source_paths: Collection[str]) -> list[str]:
        # ★빈 present 집합 가드(방어 이중화 — 호출처 가드와 독립). present가 비면 "DB의 모든 청크가
        # orphan"으로 간주돼 전체 wipe되는 footgun이라, store를 직접 재사용(8.4 관리 표면 등)하는
        # 호출처가 빈 집합을 넘겨도 안전하게 no-op한다(ingest_corpus도 동일 가드를 두지만 footgun
        # 방어를 store 자체에 내려 단일 호출처 가드에 의존하지 않는다).
        if not present_source_paths:
            return []
        # ① DB에 적재된 distinct source_path 집합을 조회한다(현 적재 경로 전체).
        loaded_paths = set(
            self._session.exec(select(DocumentChunk.source_path).distinct()).all()
        )
        # ② 차집합(현 적재 − 현 corpus) = orphan. 빈 집합이면 DELETE를 발행하지 않는다(no-op).
        orphans = sorted(loaded_paths - set(present_source_paths))
        if not orphans:
            return []
        # ③ orphan 청크를 단일 트랜잭션으로 DELETE한다(replace_document_chunks 미러 — 실패 시 롤백).
        try:
            self._session.exec(
                delete(DocumentChunk).where(col(DocumentChunk.source_path).in_(orphans))
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return orphans

    def summarize_loaded_documents(self) -> dict[str, tuple[int, str]]:
        """적재된 ``source_path``별 ``(청크 수, content_hash)``를 한 번의 집계 쿼리로 반환한다.

        운영 문서 목록(admin) 전용 읽기 표면이다. corpus 디스크 목록·디스크 파일의 현재 해시와
        병합해 ingested(해시 동일)/stale(해시 상이)/pending/orphan 상태를 산출한다. 한 문서의
        청크는 동일 ``content_hash``를 denormalize 공유하므로(원자 교체) GROUP BY +
        ``max(content_hash)``로 대표 해시 1개만 읽는다(문서별 N+1 금지). 미적재면 빈 dict.
        """
        rows = self._session.exec(
            select(
                DocumentChunk.source_path,
                func.count(),
                func.max(col(DocumentChunk.content_hash)),
            ).group_by(col(DocumentChunk.source_path))
        ).all()
        return {source_path: (count, content_hash) for source_path, count, content_hash in rows}
