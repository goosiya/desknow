"""커서 페이징 코어 단위 테스트 (F — 목록 무한스크롤).

``app.core.pagination``의 keyset/offset 커서 인코딩·디코딩·페이지 절단을 라이브 DB 없이 검증한다.
손상/위변조 커서가 조용한 1페이지 폴백이 아니라 ``DomainError(VALIDATION_ERROR)``(=라우터에서 422)로
막히는지, keyset 라운드트립이 tz-aware를 보존하는지, ``keyset_page``/``offset_next_cursor``가 다음
페이지 존재를 정확히 판정하는지를 단언한다.
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.errors import DomainError, ErrorCode
from app.core.pagination import (
    decode_keyset,
    decode_offset,
    encode_keyset,
    keyset_page,
    offset_next_cursor,
)


# ── keyset 라운드트립(인코딩 ↔ 디코딩 정확성·tz 보존) ─────────────────────────────
def test_encode_decode_keyset_roundtrip() -> None:
    """``(created_at, id)`` → 커서 → ``(created_at, id)`` 왕복이 값을 정확히 보존한다."""
    created_at = datetime(2026, 6, 17, 5, 30, 0, tzinfo=UTC)
    row_id = uuid.uuid4()
    cursor = encode_keyset(created_at, row_id)
    decoded_ts, decoded_id = decode_keyset(cursor)
    assert decoded_ts == created_at
    assert decoded_id == row_id
    assert decoded_ts.tzinfo is not None  # tz-aware 보존(naive 환원 금지)


def test_decode_keyset_preserves_non_utc_offset_as_instant() -> None:
    """비-UTC tz-aware 입력도 동일 **순간**으로 왕복한다(isoformat_utc가 UTC ...Z로 정규화)."""
    kst = timezone(timedelta(hours=9))
    created_at = datetime(2026, 6, 17, 14, 30, 0, tzinfo=kst)  # 05:30 UTC와 동일 순간
    cursor = encode_keyset(created_at, uuid.uuid4())
    decoded_ts, _ = decode_keyset(cursor)
    assert decoded_ts.tzinfo is not None
    assert decoded_ts == created_at  # 동일 순간(tz 표현만 다름)


# ── 손상 keyset 커서 → DomainError(VALIDATION_ERROR) ─────────────────────────────
def test_decode_keyset_corrupt_base64_raises_validation_error() -> None:
    """base64 디코딩 불가 문자열 → DomainError(VALIDATION_ERROR)(조용한 폴백 금지)."""
    with pytest.raises(DomainError) as exc_info:
        decode_keyset("!!!not-base64!!!")
    assert exc_info.value.code is ErrorCode.VALIDATION_ERROR


def test_decode_keyset_valid_base64_wrong_shape_raises() -> None:
    """base64이지만 keyset 페이로드가 아니면(키 부재) VALIDATION_ERROR."""
    cursor = base64.urlsafe_b64encode(json.dumps({"foo": "bar"}).encode()).decode()
    with pytest.raises(DomainError) as exc_info:
        decode_keyset(cursor)
    assert exc_info.value.code is ErrorCode.VALIDATION_ERROR


def test_decode_keyset_non_dict_payload_raises() -> None:
    """base64 디코딩 결과가 dict가 아니면(예: 리스트) VALIDATION_ERROR."""
    cursor = base64.urlsafe_b64encode(json.dumps([1, 2, 3]).encode()).decode()
    with pytest.raises(DomainError) as exc_info:
        decode_keyset(cursor)
    assert exc_info.value.code is ErrorCode.VALIDATION_ERROR


def test_decode_keyset_bad_timestamp_raises() -> None:
    """ts가 ISO datetime이 아니면 VALIDATION_ERROR."""
    cursor = base64.urlsafe_b64encode(
        json.dumps({"ts": "notadate", "id": str(uuid.uuid4())}).encode()
    ).decode()
    with pytest.raises(DomainError) as exc_info:
        decode_keyset(cursor)
    assert exc_info.value.code is ErrorCode.VALIDATION_ERROR


def test_decode_keyset_naive_timestamp_raises() -> None:
    """ts가 naive(tz 없음)면 VALIDATION_ERROR(시각 비교 오류 방지)."""
    cursor = base64.urlsafe_b64encode(
        json.dumps({"ts": "2026-06-17T05:30:00", "id": str(uuid.uuid4())}).encode()
    ).decode()
    with pytest.raises(DomainError) as exc_info:
        decode_keyset(cursor)
    assert exc_info.value.code is ErrorCode.VALIDATION_ERROR


def test_decode_keyset_bad_uuid_raises() -> None:
    """id가 UUID가 아니면 VALIDATION_ERROR."""
    cursor = base64.urlsafe_b64encode(
        json.dumps({"ts": "2026-06-17T05:30:00Z", "id": "not-a-uuid"}).encode()
    ).decode()
    with pytest.raises(DomainError) as exc_info:
        decode_keyset(cursor)
    assert exc_info.value.code is ErrorCode.VALIDATION_ERROR


# ── offset 커서 디코딩(없음·정상·손상·음수) ──────────────────────────────────────
def test_decode_offset_none_is_zero() -> None:
    """커서 None(첫 페이지) → offset 0."""
    assert decode_offset(None) == 0


def test_decode_offset_corrupt_base64_raises_validation_error() -> None:
    """base64 디코딩 불가 → DomainError(VALIDATION_ERROR)."""
    with pytest.raises(DomainError) as exc_info:
        decode_offset("!!!invalid!!!")
    assert exc_info.value.code is ErrorCode.VALIDATION_ERROR


def test_decode_offset_missing_key_raises() -> None:
    """``off`` 키 부재 → VALIDATION_ERROR."""
    cursor = base64.urlsafe_b64encode(json.dumps({"x": 1}).encode()).decode()
    with pytest.raises(DomainError) as exc_info:
        decode_offset(cursor)
    assert exc_info.value.code is ErrorCode.VALIDATION_ERROR


def test_decode_offset_negative_raises() -> None:
    """음수 offset → VALIDATION_ERROR(위변조 방어)."""
    cursor = base64.urlsafe_b64encode(json.dumps({"off": -5}).encode()).decode()
    with pytest.raises(DomainError) as exc_info:
        decode_offset(cursor)
    assert exc_info.value.code is ErrorCode.VALIDATION_ERROR


def test_decode_offset_non_int_raises() -> None:
    """off가 정수로 변환 불가(예: 문자열) → VALIDATION_ERROR."""
    cursor = base64.urlsafe_b64encode(json.dumps({"off": "abc"}).encode()).decode()
    with pytest.raises(DomainError) as exc_info:
        decode_offset(cursor)
    assert exc_info.value.code is ErrorCode.VALIDATION_ERROR


# ── keyset_page: limit+1이면 다음 토큰, limit 이하면 None ─────────────────────────
class _Row:
    """keyset_page용 최소 행 — created_at·id만 갖는다."""

    def __init__(self, created_at: datetime, row_id: uuid.UUID) -> None:
        self.created_at = created_at
        self.id = row_id


def _rows(n: int) -> list[_Row]:
    """created_at 내림차순으로 정렬된 n개 행(서비스 쿼리 출력 형태)."""
    base = datetime(2026, 6, 17, tzinfo=UTC)
    return [_Row(base - timedelta(hours=i), uuid.uuid4()) for i in range(n)]


def test_keyset_page_more_than_limit_yields_cursor() -> None:
    """``limit+1``개 조회면 앞 limit개를 페이지로 자르고 next_cursor를 만든다."""
    rows = _rows(4)  # limit=3 → 4개면 더 있음
    page, next_cursor = keyset_page(
        rows, 3, created=lambda r: r.created_at, ident=lambda r: r.id
    )
    assert len(page) == 3
    assert next_cursor is not None
    # next_cursor는 페이지 마지막 행의 (created_at, id)를 가리킨다.
    last = page[-1]
    decoded_ts, decoded_id = decode_keyset(next_cursor)
    assert decoded_ts == last.created_at
    assert decoded_id == last.id


def test_keyset_page_exactly_limit_yields_none() -> None:
    """정확히 limit개면(=더 없음) next_cursor None."""
    rows = _rows(3)
    page, next_cursor = keyset_page(
        rows, 3, created=lambda r: r.created_at, ident=lambda r: r.id
    )
    assert len(page) == 3
    assert next_cursor is None


def test_keyset_page_fewer_than_limit_yields_none() -> None:
    """limit보다 적으면 next_cursor None."""
    rows = _rows(2)
    page, next_cursor = keyset_page(
        rows, 3, created=lambda r: r.created_at, ident=lambda r: r.id
    )
    assert len(page) == 2
    assert next_cursor is None


def test_keyset_page_empty_yields_none() -> None:
    """빈 입력 → 빈 페이지·next_cursor None."""
    page, next_cursor = keyset_page(
        [], 3, created=lambda r: r.created_at, ident=lambda r: r.id
    )
    assert page == []
    assert next_cursor is None


# ── offset_next_cursor: 다음 페이지 있으면 토큰·끝이면 None ───────────────────────
def test_offset_next_cursor_has_more() -> None:
    """offset+limit < total → 다음 offset 토큰(디코딩하면 offset+limit)."""
    cursor = offset_next_cursor(0, 2, 5)  # [0,2) 봤고 총 5개 → 다음 offset 2
    assert cursor is not None
    assert decode_offset(cursor) == 2


def test_offset_next_cursor_exact_end_is_none() -> None:
    """offset+limit == total(끝 도달) → None."""
    assert offset_next_cursor(3, 2, 5) is None  # [3,5) = 끝


def test_offset_next_cursor_past_end_is_none() -> None:
    """offset+limit > total → None."""
    assert offset_next_cursor(4, 2, 5) is None
