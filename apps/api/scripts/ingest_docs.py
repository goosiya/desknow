"""``docs_corpus/`` 문서 인제스트 수동/개발 실행 진입점 (Story 7.2, AC4).

코어 파이프라인(``app.chatbot.ingest.ingest_corpus``)을 실 의존성(세션·settings·OpenAI 임베딩)과
배선해 구동하고, 결과 리포트를 사람이 읽게 출력한다. **라우터·FastAPI 엔드포인트가 아니다** —
관리 표면(트리거 UI·상태 조회 API)은 FR-33(Story 8.4)이 소유하며 본 파이프라인을 재사용한다.

사용:
    uv run python scripts/ingest_docs.py [corpus_dir]
기본 corpus_dir: ``apps/api/docs_corpus``

실 OpenAI 임베딩·실 DB 적재가 일어나므로 ``OPENAI_API_KEY``·``DATABASE_URL``이 필요하다
(누락 시 settings fail-fast). 종료 코드: 실패 문서가 하나라도 있으면 1, 전부 성공/스킵이면 0.
"""
from __future__ import annotations

import sys
from pathlib import Path

# ``python scripts/ingest_docs.py`` 실행 시 sys.path[0]는 scripts/라 app 패키지를 못 찾는다.
# apps/api(=parents[1])를 경로에 추가해 cwd 무관하게 import가 안정적이게 한다(export_openapi 선례).
_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from sqlmodel import Session  # noqa: E402  (sys.path 부트스트랩 후 import)

from app.chatbot.ingest import (  # noqa: E402
    DEFAULT_CORPUS_DIR,
    IngestReport,
    SqlDocumentChunkStore,
    build_embedder,
    ingest_corpus,
)
from app.core.config import _ensure_utf8_streams  # noqa: E402 — cp949 콘솔 한글/유니코드 출력 보호
from app.core.db import get_engine  # noqa: E402

# corpus 경로는 ingest 패키지의 단일 출처(DEFAULT_CORPUS_DIR)를 재사용한다(DRY — 8.4 admin과 공유).
# 값은 동일하게 apps/api/docs_corpus로 해석된다.


def _print_report(report: IngestReport, corpus_dir: Path) -> None:
    """리포트를 사람이 읽기 좋은 요약으로 출력한다(성공 N·스킵 N·실패 N + 실패 경로·사유).

    출력은 ASCII 마커만 쓴다 — Windows cp949 콘솔에서 이모지가 UnicodeEncodeError를 내는 것을
    피한다(config.py가 스트림을 UTF-8로 재설정하는 것과 같은 동기 — 여기선 의존 없이 ASCII로).
    """
    print(f"[인제스트 완료] {corpus_dir}")
    print(
        f"  문서 {report.total}개 — "
        f"성공 {len(report.succeeded)} / 스킵 {len(report.skipped)} / 실패 {len(report.failed)}"
        f" / 정리 {len(report.removed)}"
    )
    for path in report.succeeded:
        print(f"  [OK]   {path}")
    for path in report.skipped:
        print(f"  [SKIP] {path}  (내용 동일)")
    for path, reason in report.failed:
        print(f"  [FAIL] {path} — {reason}")
    for path in report.removed:
        print(f"  [GONE] {path}  (corpus에 없어 정리됨)")


def main(argv: list[str]) -> int:
    # Windows cp949/리다이렉트 환경에서 한글·기호 출력 UnicodeEncodeError 방지(config.py 선례).
    _ensure_utf8_streams()
    corpus_dir = Path(argv[1]) if len(argv) > 1 else DEFAULT_CORPUS_DIR
    if not corpus_dir.is_dir():
        print(f"❌ corpus 디렉터리가 없습니다: {corpus_dir}", file=sys.stderr)
        return 1

    embeddings = build_embedder()
    with Session(get_engine()) as session:
        store = SqlDocumentChunkStore(session)
        report = ingest_corpus(store, corpus_dir, embeddings)

    _print_report(report, corpus_dir)
    # 실패 문서가 하나라도 있으면 비정상 종료(CI/수동 점검에서 식별 가능 — AC3).
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
