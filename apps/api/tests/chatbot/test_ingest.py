"""인제스트 파이프라인 단위 테스트 (Story 7.2 — AC2·AC3·AC5).

**네트워크·실 DB 없이**(임베딩 페이크 + 인메모리 페이크 store) 멱등·부분실패·청크·해시 로직을
실증한다. SQLite는 pgvector 타입을 모르므로(Dev Notes §함정 #6) 실 DB 대신 페이크 store로
멱등 DELETE/INSERT·해시 대조를 검증한다. 실 OpenAI·실 DB 적재는 별도 @integration(키/DB 게이트).
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from app.chatbot.ingest import (
    IngestReport,
    chunk_text,
    compute_content_hash,
    ingest_corpus,
    iter_corpus_files,
    load_document_text,
)
from app.chatbot.ingest.chunking import DocumentLoadError
from app.chatbot.models import EMBEDDING_DIM, DocumentChunk

# ── 페이크 (네트워크·실 DB 0) ──────────────────────────────────────────────


class FakeEmbedder:
    """결정적 더미 벡터를 내는 임베딩 페이크. 호출 횟수·누적 텍스트를 기록(멱등 검증용)."""

    def __init__(self) -> None:
        self.calls = 0
        self.embedded_texts: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        self.embedded_texts.extend(texts)
        # 차원은 EMBEDDING_DIM 고정(파이프라인 차원 불변식 검증을 통과하도록). 값은 결정적 더미.
        return [[float(len(t) % 7)] * EMBEDDING_DIM for t in texts]


class FailingEmbedder(FakeEmbedder):
    """특정 마커 텍스트가 포함된 배치에서 예외를 던지는 임베딩 페이크(부분 실패 검증)."""

    def __init__(self, fail_marker: str) -> None:
        super().__init__()
        self._fail_marker = fail_marker

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if any(self._fail_marker in t for t in texts):
            raise RuntimeError("임베딩 업스트림 오류(페이크)")
        return super().embed_documents(texts)


class FakeStore:
    """인메모리 ``DocumentChunkStore`` — source_path → 청크 리스트. 멱등/원자 교체를 모사."""

    def __init__(self) -> None:
        self.data: dict[str, list[DocumentChunk]] = {}
        self.rollback_calls = 0  # 실패 시 파이프라인이 rollback을 부르는지 검증용

    def get_content_hash(self, source_path: str) -> str | None:
        chunks = self.data.get(source_path)
        return chunks[0].content_hash if chunks else None

    def replace_document_chunks(
        self, source_path: str, chunks: Sequence[DocumentChunk]
    ) -> None:
        chunk_list = list(chunks)
        if not chunk_list:  # 실 store와 동일하게 빈 청크는 no-op(데이터 소실 방지 방어)
            return
        # 기존 전량 교체(stale 0). 실 store의 DELETE+INSERT 단일 트랜잭션을 모사.
        self.data[source_path] = chunk_list

    def rollback(self) -> None:
        # 실 store는 session.rollback()으로 aborted txn을 청소한다. 페이크는 호출만 센다.
        self.rollback_calls += 1

    def delete_orphans(self, present_source_paths: Sequence[str]) -> list[str]:
        # 실 store의 "DB distinct source_path − present = orphan DELETE"를 인메모리로 모사한다.
        orphans = sorted(set(self.data) - set(present_source_paths))
        for path in orphans:
            del self.data[path]
        return orphans


class FailingDeleteStore(FakeStore):
    """delete_orphans가 예외를 던지는 페이크(reconcile best-effort 검증 — 적재는 보존돼야 함)."""

    def delete_orphans(self, present_source_paths: Sequence[str]) -> list[str]:
        raise RuntimeError("reconcile DB 오류(페이크)")


def _orphan_chunk(source_path: str) -> DocumentChunk:
    """corpus에 없지만 DB에 잔존하는 stale 청크를 미리 적재하기 위한 최소 청크(orphan 픽스처)."""
    return DocumentChunk(
        source_path=source_path,
        content_hash="stale",
        chunk_index=0,
        content="옛 내용",
        embedding=[0.0] * EMBEDDING_DIM,
    )


def _write(corpus: Path, name: str, content: str) -> None:
    path = corpus / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── 청커 결정성 (AC1) ──────────────────────────────────────────────────────


def test_chunk_text_is_deterministic() -> None:
    """같은 입력 → 같은 청크(경계·overlap 동일). 비결정 요소 없음."""
    text = "가" * 2500
    first = chunk_text(text, chunk_size=1000, overlap=200)
    second = chunk_text(text, chunk_size=1000, overlap=200)
    assert first == second


def test_chunk_text_overlap_and_coverage() -> None:
    """overlap만큼 인접 청크가 겹치고, step=chunk_size-overlap으로 전진한다."""
    text = "".join(str(i % 10) for i in range(2500))  # 길이 2500
    chunks = chunk_text(text, chunk_size=1000, overlap=200)
    # step=800 → 시작 0,800,1600. start=1600에서 1600+1000=2600≥2500이라 break → 3청크.
    assert len(chunks) == 3
    assert chunks[0] == text[0:1000]
    assert chunks[1] == text[800:1800]
    assert chunks[2] == text[1600:2500]
    # 인접 청크가 overlap(200자)을 공유한다.
    assert chunks[0][-200:] == chunks[1][:200]
    # 마지막 청크는 끝까지 포함(꼬리 손실 0).
    assert chunks[-1].endswith(text[-1])


def test_chunk_text_empty_returns_empty() -> None:
    assert chunk_text("") == []


def test_chunk_text_rejects_bad_params() -> None:
    """무의미한 파라미터는 ValueError(조용한 무한루프/빈결과 강등 방지 — fail-fast)."""
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=0)
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=100, overlap=100)  # overlap >= chunk_size


# ── 내용 해시 (AC2) ─────────────────────────────────────────────────────────


def test_content_hash_stability() -> None:
    """같은 내용 → 같은 해시, 다른 내용 → 다른 해시."""
    assert compute_content_hash("hello") == compute_content_hash("hello")
    assert compute_content_hash("hello") != compute_content_hash("hello!")


# ── 문서 로딩 (AC3 — 빈/디코드 실패) ────────────────────────────────────────


def test_load_document_text_rejects_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("   \n  ", encoding="utf-8")
    with pytest.raises(DocumentLoadError):
        load_document_text(path)


def test_iter_corpus_files_filters_and_sorts(tmp_path: Path) -> None:
    """지원 확장자(.md/.txt)만, 정렬된 결정적 순서로 순회한다(바이너리·기타 제외)."""
    _write(tmp_path, "b.txt", "b")
    _write(tmp_path, "a.md", "a")
    _write(tmp_path, "ignore.pdf", "x")
    _write(tmp_path, "nested/c.txt", "c")
    rels = [p.relative_to(tmp_path).as_posix() for p in iter_corpus_files(tmp_path)]
    assert rels == ["a.md", "b.txt", "nested/c.txt"]


# ── 멱등 (AC2) ──────────────────────────────────────────────────────────────


def test_reingest_same_content_skips(tmp_path: Path) -> None:
    """동일 문서 2회 인제스트 → 2회차는 임베딩 호출 0·DB 행 증가 0(skip)."""
    _write(tmp_path, "doc.md", "내용 " * 500)
    store = FakeStore()
    embedder = FakeEmbedder()

    first = ingest_corpus(store, tmp_path, embedder)
    assert first.succeeded == ["doc.md"]
    assert first.skipped == []
    calls_after_first = embedder.calls
    chunks_after_first = list(store.data["doc.md"])

    second = ingest_corpus(store, tmp_path, embedder)
    assert second.skipped == ["doc.md"]
    assert second.succeeded == []
    # 2회차는 임베딩을 호출하지 않는다(OpenAI 비용 0 — AC2 핵심).
    assert embedder.calls == calls_after_first
    # DB(페이크 store) 청크가 그대로(행 증가 0).
    assert store.data["doc.md"] == chunks_after_first


def test_reingest_changed_content_replaces(tmp_path: Path) -> None:
    """내용 변경 시 기존 청크를 모두 삭제 후 신규만 남는다(stale 벡터 0)."""
    _write(tmp_path, "doc.md", "원본 내용")
    store = FakeStore()
    embedder = FakeEmbedder()
    ingest_corpus(store, tmp_path, embedder)
    original_hash = store.data["doc.md"][0].content_hash

    # 내용을 길게 바꿔 청크 수도 달라지게 한다.
    _write(tmp_path, "doc.md", "완전히 다른 내용 " * 300)
    report = ingest_corpus(store, tmp_path, embedder)

    assert report.succeeded == ["doc.md"]
    new_chunks = store.data["doc.md"]
    new_hash = new_chunks[0].content_hash
    assert new_hash != original_hash
    # 모든 청크가 새 해시를 denormalize 공유한다(stale 잔존 0).
    assert all(c.content_hash == new_hash for c in new_chunks)
    # chunk_index가 0부터 연속(재적재 정합).
    assert [c.chunk_index for c in new_chunks] == list(range(len(new_chunks)))


# ── 부분 실패 (AC3) ─────────────────────────────────────────────────────────


def test_partial_failure_isolates_documents(tmp_path: Path) -> None:
    """한 문서 임베딩이 예외를 던져도 다른 문서는 성공하고, 리포트 failed에 사유가 잡힌다."""
    _write(tmp_path, "good.md", "정상 문서 내용")
    _write(tmp_path, "bad.md", "BOOM 실패 유발 문서")
    store = FakeStore()
    embedder = FailingEmbedder(fail_marker="BOOM")

    report = ingest_corpus(store, tmp_path, embedder)

    assert report.succeeded == ["good.md"]
    assert "good.md" in store.data
    assert "bad.md" not in store.data  # 실패 문서는 적재되지 않음(부분 적재 0)
    assert len(report.failed) == 1
    failed_path, reason = report.failed[0]
    assert failed_path == "bad.md"
    assert "RuntimeError" in reason  # 어떤 사유로 실패했는지 식별(AC3)


def test_failure_triggers_store_rollback(tmp_path: Path) -> None:
    """문서 실패 시 파이프라인이 store.rollback()을 호출해 세션을 청소한다(공유 세션 격리 — AC3).

    실 DB에서 공유 세션의 aborted 트랜잭션이 다음 문서로 전파(InFailedSqlTransaction)되는 것을
    막는 방어. 페이크 store의 rollback 호출 횟수로 실패당 1회 호출을 단언한다.
    """
    _write(tmp_path, "good.md", "정상 문서 내용")
    _write(tmp_path, "bad.md", "BOOM 실패 유발 문서")
    store = FakeStore()
    embedder = FailingEmbedder(fail_marker="BOOM")

    report = ingest_corpus(store, tmp_path, embedder)

    assert len(report.failed) == 1  # bad.md만 실패
    assert store.rollback_calls == 1  # 실패한 문서에 대해서만 정확히 1회 롤백


def test_reingest_is_stable_across_newline_and_bom(tmp_path: Path) -> None:
    """같은 논리 문서가 CRLF·BOM 차이만 있을 때 재인제스트가 멱등(skip)이다(AC2 — OS 경계 보호).

    LF로 먼저 적재한 뒤, 동일 내용을 CRLF + BOM으로 다시 써도 정규화 후 해시가 같아 skip 돼야
    한다(불필요 재임베딩·재적재 0).
    """
    body = "첫 줄입니다.\n둘째 줄입니다.\n"
    # write_bytes로 정확한 바이트를 제어한다(write_text는 Windows에서 \n을 \r\n으로 번역해
    # 픽스처를 오염시킨다). 먼저 LF + BOM 없는 UTF-8로 적재.
    doc = tmp_path / "doc.md"
    doc.write_bytes(body.encode("utf-8"))
    store = FakeStore()
    embedder = FakeEmbedder()
    first = ingest_corpus(store, tmp_path, embedder)
    assert first.succeeded == ["doc.md"]
    calls_after_first = embedder.calls

    # 같은 내용을 BOM + CRLF로 다시 쓴다(Windows 에디터/체크아웃 모사). ﻿ = UTF-8 BOM.
    crlf_with_bom = "﻿" + body.replace("\n", "\r\n")
    doc.write_bytes(crlf_with_bom.encode("utf-8"))
    second = ingest_corpus(store, tmp_path, embedder)

    assert second.skipped == ["doc.md"]  # 정규화 후 해시 동일 → skip
    assert embedder.calls == calls_after_first  # 재임베딩 0(OpenAI 비용 0)


def test_whitespace_only_chunks_are_dropped(tmp_path: Path) -> None:
    """공백뿐인 후속 청크는 임베딩·적재에서 제외되고 chunk_index는 연속 유지된다(검색 노이즈 0)."""
    # 첫 청크는 실내용, chunk_size를 넘긴 꼬리는 공백만 → 공백 청크가 생성되는 입력.
    _write(tmp_path, "doc.txt", "유효한 첫 청크 내용" + " " * 60)
    store = FakeStore()
    ingest_corpus(store, tmp_path, FakeEmbedder(), chunk_size=20, overlap=5)
    chunks = store.data["doc.txt"]
    # 적재된 모든 청크는 비공백 내용을 가진다(공백-only 청크 적재 0).
    assert all(c.content.strip() for c in chunks)
    # chunk_index가 0..n 연속(필터 후에도 정합).
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_decode_failure_recorded_as_failed(tmp_path: Path) -> None:
    """디코드 불가(바이너리) 문서는 부분 실패로 기록되고 배치를 중단시키지 않는다."""
    _write(tmp_path, "ok.txt", "정상")
    # 잘못된 UTF-8 바이트를 .txt로 저장(디코드 실패 유발).
    (tmp_path / "binary.txt").write_bytes(b"\xff\xfe\x00\x01invalid")
    store = FakeStore()
    embedder = FakeEmbedder()

    report = ingest_corpus(store, tmp_path, embedder)

    assert "ok.txt" in report.succeeded
    assert [p for p, _ in report.failed] == ["binary.txt"]


def test_empty_report_for_empty_corpus(tmp_path: Path) -> None:
    """문서가 없으면 빈 리포트(total 0). 빈 디렉터리도 안전."""
    report = ingest_corpus(FakeStore(), tmp_path, FakeEmbedder())
    assert isinstance(report, IngestReport)
    assert report.total == 0


def test_chunks_carry_embedding_and_metadata(tmp_path: Path) -> None:
    """적재된 청크가 source_path·embedding(1536)·content를 올바로 담는다."""
    _write(tmp_path, "doc.txt", "한 청크 분량 내용")
    store = FakeStore()
    ingest_corpus(store, tmp_path, FakeEmbedder())
    chunk = store.data["doc.txt"][0]
    assert chunk.source_path == "doc.txt"
    assert len(chunk.embedding) == EMBEDDING_DIM
    assert chunk.content


# ── stale 청크 reconcile (AC3 — deferred-work L344 회수) ───────────────────────


def test_reconcile_removes_orphan_chunks(tmp_path: Path) -> None:
    """ⓐ corpus에 없는(삭제/리네임된) 문서의 stale 청크가 정리되고 removed에 보고된다."""
    _write(tmp_path, "keep.md", "유지되는 문서 내용")
    store = FakeStore()
    # corpus엔 없지만 DB에 잔존하는 orphan(옛 경로의 청크)을 미리 적재한다.
    store.data["gone.md"] = [_orphan_chunk("gone.md")]

    report = ingest_corpus(store, tmp_path, FakeEmbedder())

    assert "keep.md" in report.succeeded
    assert report.removed == ["gone.md"]  # corpus에 없는 문서만 정리
    assert "gone.md" not in store.data  # orphan 청크 DELETE됨
    assert "keep.md" in store.data  # 존재 문서는 영향 0
    # removed는 처리 문서 총수에 포함되지 않는다(정리분 — total 의미 보존).
    assert report.total == 1


def test_reconcile_skips_on_empty_corpus(tmp_path: Path) -> None:
    """ⓑ ★footgun 가드: corpus 파일 0(빈 디렉터리) → reconcile 미실행(기존 청크 wipe 방지)."""
    store = FakeStore()
    store.data["existing.md"] = [_orphan_chunk("existing.md")]

    report = ingest_corpus(store, tmp_path, FakeEmbedder())  # 빈 디렉터리

    assert report.removed == []  # present_paths 공집합 → reconcile 스킵
    assert "existing.md" in store.data  # 데이터 보존(wipe 0)


def test_reconcile_disabled_keeps_orphans(tmp_path: Path) -> None:
    """ⓒ reconcile=False 명시 off 시 orphan을 삭제하지 않는다."""
    _write(tmp_path, "keep.md", "유지되는 문서 내용")
    store = FakeStore()
    store.data["gone.md"] = [_orphan_chunk("gone.md")]

    report = ingest_corpus(store, tmp_path, FakeEmbedder(), reconcile=False)

    assert report.removed == []
    assert "gone.md" in store.data  # 명시 off → orphan 미삭제


def test_reconcile_failure_is_best_effort(tmp_path: Path) -> None:
    """ⓓ reconcile(delete_orphans) 실패 시 best-effort — 적재 성공은 보존되고 리포트는 미사망."""
    _write(tmp_path, "keep.md", "유지되는 문서 내용")
    store = FailingDeleteStore()
    store.data["gone.md"] = [_orphan_chunk("gone.md")]

    report = ingest_corpus(store, tmp_path, FakeEmbedder())

    assert "keep.md" in report.succeeded  # 적재 성공은 롤백되지 않음(best-effort)
    assert report.removed == []  # reconcile 실패 → removed 빈 채로 진행
    # 실패 시 store.rollback() 호출(per-doc 실패 0이므로 정확히 1회).
    assert store.rollback_calls == 1
