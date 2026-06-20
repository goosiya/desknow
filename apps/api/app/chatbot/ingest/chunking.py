"""결정적 청킹 · 내용 해시 · 문서 로딩 (Story 7.2, Task 3).

★설계 의도(Dev Notes §청킹): **자체 결정적 청커**(문자 길이 기반 + overlap, 표준 라이브러리만)
를 쓴다 — 신규 의존성 0이고 테스트가 결정적이다. ``langchain-text-splitters``는 현재 미설치이며
MVP 텍스트 문서엔 단순 청커로 충분하므로 도입하지 않는다(범위 최소).

- **결정성:** 같은 입력 → 같은 청크 경계·overlap. 비결정 요소(난수·시간·로캘) 없음.
- **멱등 기준:** ``compute_content_hash`` = 문서 전체 내용의 sha256(문서 단위 멱등 — 7.2 핵심).
- **문서 로딩:** ``.md``/``.txt`` 텍스트 파일만(바이너리 파서는 범위 밖 — MVP). 디코드 실패·빈
  문서는 ``DocumentLoadError``로 올려 호출처(파이프라인)가 **문서 단위 부분 실패**로 흡수한다(AC3).
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

# 인제스트 대상 텍스트 확장자(소문자). PDF/docx 등 바이너리 파서는 범위 밖(MVP는 텍스트 문서).
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".md", ".txt"})

# 기본 청크 크기/overlap(문자 단위). 호출처가 덮어쓸 수 있다. overlap은 청크 경계에서 문맥이
# 잘려 검색 품질이 떨어지는 것을 완화한다(인접 청크가 일부를 공유).
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 200


class DocumentLoadError(Exception):
    """문서 로딩 실패(디코드 불가·빈 문서). 파이프라인이 부분 실패로 흡수한다(AC3)."""


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """텍스트를 ``chunk_size`` 문자 단위로 ``overlap`` 만큼 겹치게 분할한다(결정적).

    같은 입력은 항상 같은 청크 리스트를 낸다. 빈 문자열은 빈 리스트를 낸다.

    Args:
        text: 분할 대상 원문.
        chunk_size: 청크당 최대 문자 수(>0).
        overlap: 인접 청크가 공유하는 문자 수(``0 <= overlap < chunk_size``).

    Raises:
        ValueError: ``chunk_size <= 0`` 또는 overlap이 범위를 벗어난 경우(무의미한 파라미터가
            무한 루프·빈 결과로 조용히 강등되는 것을 막는다 — fail-fast).
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size는 1 이상이어야 합니다 (받은 값: {chunk_size}).")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            f"overlap은 0 이상 chunk_size 미만이어야 합니다 "
            f"(overlap={overlap}, chunk_size={chunk_size})."
        )
    if not text:
        return []

    step = chunk_size - overlap
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        chunks.append(text[start : start + chunk_size])
        # 마지막 청크가 끝에 도달했으면 종료(step만큼 더 나아가면 빈/중복 꼬리 청크가 생김).
        if start + chunk_size >= length:
            break
        start += step
    return chunks


def compute_content_hash(content: str) -> str:
    """문서 전체 내용의 sha256 hexdigest를 반환한다(문서 단위 멱등 기준).

    같은 내용 → 같은 해시, 다른 내용 → 다른 해시. UTF-8 인코딩 바이트를 해싱해 플랫폼 무관하게
    안정적이다. ``hashlib`` 표준 라이브러리만 사용(신규 의존성 0).
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_document_text(path: Path) -> str:
    """텍스트 문서를 UTF-8로 읽어 **정규화된** 내용을 반환한다.

    멱등 기준(``content_hash``)과 청크 텍스트가 OS·에디터 차이에 흔들리지 않도록 두 가지를
    정규화한다(AC2 멱등 보호 — 같은 문서가 환경 경계에서 불필요 재임베딩되는 것을 막는다):

    - **BOM 제거:** ``utf-8-sig``로 읽어 선두 BOM(``\\ufeff``)을 제거한다(``utf-8``은 BOM을 내용에
      그대로 남겨 해시를 바꾸고 첫 청크에 섞인다).
    - **줄바꿈 정규화:** CRLF(``\\r\\n``)·CR(``\\r``)을 LF(``\\n``)로 통일한다(Windows 체크아웃 vs
      Linux 체크아웃이 같은 문서를 다른 해시로 만드는 것을 막는다).

    디코드 실패(바이너리·잘못된 인코딩)나 빈/공백뿐인 문서는 ``DocumentLoadError``로 올린다 →
    파이프라인이 문서 단위 부분 실패로 흡수한다(AC3 — 한 문서 실패가 배치를 중단시키지 않음).
    """
    try:
        # utf-8-sig: BOM이 있으면 제거하고, 없으면 일반 UTF-8과 동일하게 동작한다.
        content = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError) as exc:
        raise DocumentLoadError(f"문서를 읽을 수 없습니다: {exc}") from exc
    # 줄바꿈을 LF로 통일(CRLF·CR → LF). 멱등 해시·청크가 OS 경계에서 안정적이게 한다.
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if not content.strip():
        raise DocumentLoadError("빈 문서입니다(내용 없음).")
    return content


def iter_corpus_files(corpus_dir: Path) -> Iterator[Path]:
    """``corpus_dir`` 하위에서 지원 확장자 텍스트 파일을 **정렬된 순서**로 순회한다(결정적).

    재귀적으로 스캔하되 지원 확장자(``SUPPORTED_EXTENSIONS``)만 낸다. 정렬은 인제스트 순서를
    결정적으로 만들어(테스트·재현) OS별 디렉터리 순서 차이를 제거한다.
    """
    if not corpus_dir.is_dir():
        return
    for path in sorted(corpus_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path
