"""커서 페이징 코어 (F — 목록 무한스크롤). 모든 목록 엔드포인트가 공유하는 봉투 + 불투명 커서.

**봉투(envelope):** 목록 응답을 배열이 아니라 ``CursorPage[T] = {items, next_cursor}``
객체로 감싼다.
``next_cursor``는 다음 페이지 시작점을 가리키는 **불투명 base64 토큰**으로,
클라이언트는 의미를 몰라도
다음 요청의 ``?cursor=``에 그대로 echo하면 된다(``null``=마지막 페이지). 6개 목록 표면이 동일한
``useInfiniteQuery`` 패턴으로 통일되는 게 이 방식의 이유다.

**커서 두 종류(불투명하게 흡수 — 프론트는 구분 불필요):**

- **keyset(시간순 목록 — 예약·즐겨찾기·후기·제공자예약):** 마지막 항목의 ``(created_at, id)``를
  담는다. 다음 페이지는 ``(created_at, id) < cursor``로 "그보다 과거 것부터" 가져온다. 스크롤 도중
  새 항목이 추가돼도 페이지 경계가 안 밀려(중복/누락 없음) offset 대비 안전하다.
- **offset(검색):** 거리순 계산 정렬이라 시간 keyset이 부적합 → "몇 개까지 봤는지"(offset)를 담는다.

**디코딩 실패(위변조·형식오류)는 422 ``VALIDATION_ERROR``로 막는다**(조용한 1페이지 폴백 금지 —
잘못된 커서를 정상 첫 페이지로 둔갑시키지 않는다). ``limit``는 기본 20·최대 100.
"""
from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, or_

from app.core.errors import DomainError, ErrorCode
from app.core.time import isoformat_utc

T = TypeVar("T")

#: 한 페이지 기본 크기(무한스크롤 1회 로드 = 20). 프론트는 항상 이 값을 쓴다.
PAGE_SIZE_DEFAULT = 20
#: 한 페이지 상한(악의적 대량 요청 방어 — Query le=).
PAGE_SIZE_MAX = 100


# pydantic 제네릭 모델 — PEP695 type-param 전환은 pydantic/mypy 호환 위해 보류(UP046).
class CursorPage(BaseModel, Generic[T]):  # noqa: UP046
    """커서 페이징 응답 봉투. ``items``=이번 페이지,
    ``next_cursor``=다음 페이지 토큰(없으면 None)."""

    items: list[T]
    next_cursor: str | None = None


def _invalid_cursor() -> DomainError:
    return DomainError(ErrorCode.VALIDATION_ERROR, "잘못된 커서입니다.")


def _encode(payload: dict[str, Any]) -> str:
    """payload dict → URL-safe base64 문자열(불투명 커서)."""
    raw = json.dumps(payload, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(cursor: str) -> dict[str, Any]:
    """불투명 커서 → payload dict. 손상/위변조면 422."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise _invalid_cursor() from exc
    if not isinstance(data, dict):
        raise _invalid_cursor()
    return data


# ── keyset 커서(시간순 목록) ────────────────────────────────────────────────
def encode_keyset(created_at: datetime, row_id: uuid.UUID) -> str:
    """``(created_at, id)`` → 불투명 keyset 커서. created_at은 ``...Z`` ISO로 직렬화."""
    return _encode({"ts": isoformat_utc(created_at), "id": str(row_id)})


def decode_keyset(cursor: str) -> tuple[datetime, uuid.UUID]:
    """keyset 커서 → ``(created_at, id)``. 형식오류면 422."""
    data = _decode(cursor)
    try:
        # isoformat_utc는 ...Z를 내므로 fromisoformat용으로 +00:00로 환원해 tz-aware 파싱.
        ts = datetime.fromisoformat(str(data["ts"]).replace("Z", "+00:00"))
        row_id = uuid.UUID(str(data["id"]))
    except (KeyError, ValueError) as exc:
        raise _invalid_cursor() from exc
    if ts.tzinfo is None:
        raise _invalid_cursor()
    return ts, row_id


def keyset_predicate(
    created_col: Any,
    id_col: Any,
    cursor: str | None,
) -> ColumnElement[bool] | None:
    """커서가 있으면 ``(created_at, id) < cursor`` row-value 조건을 만든다(없으면 None).

    ``tuple_(...) < (...)`` 대신 ``or_(created < ts, and_(created == ts, id < id))``로 전개한다 —
    모든 백엔드에서 동작하고 정렬(``created desc, id desc``)과 정확히 짝이 맞는다(동일 created_at
    타이브레이커=id). 호출처가
    ``select(...).where(pred).order_by(created.desc(), id.desc())``로 쓴다.
    """
    if cursor is None:
        return None
    ts, row_id = decode_keyset(cursor)
    return or_(
        created_col < ts,
        and_(created_col == ts, id_col < row_id),
    )


def keyset_page(
    rows: list[Any],
    limit: int,
    *,
    created: Callable[[Any], Any],
    ident: Callable[[Any], Any],
) -> tuple[list[Any], str | None]:
    """``limit+1`` 개를 조회한 ``rows``에서 앞 ``limit``개를 페이지로 잘라내고 next_cursor를 만든다.

    ``limit+1``번째 행이 있으면(=더 있음) 페이지 마지막 행의 ``(created, ident)``로 next_cursor를
    만든다. ``created``/``ident``는 행에서 정렬 키를 꺼내는 콜러블(예: ``lambda r: r.created_at``).
    """
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor: str | None = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_keyset(created(last), ident(last))
    return page, next_cursor


# ── offset 커서(검색 — 거리순 계산 정렬) ─────────────────────────────────────
def decode_offset(cursor: str | None) -> int:
    """offset 커서 → 시작 인덱스(없으면 0). 음수/형식오류면 422."""
    if cursor is None:
        return 0
    data = _decode(cursor)
    try:
        offset = int(data["off"])
    except (KeyError, ValueError, TypeError) as exc:
        raise _invalid_cursor() from exc
    if offset < 0:
        raise _invalid_cursor()
    return offset


def offset_next_cursor(offset: int, limit: int, total: int) -> str | None:
    """이번 페이지가 ``[offset, offset+limit)``일 때 다음 offset 커서(끝이면 None)."""
    nxt = offset + limit
    return _encode({"off": nxt}) if nxt < total else None
