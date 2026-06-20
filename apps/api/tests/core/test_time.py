"""core.time 단위 테스트 (Story 1.5 — 라이브 DB 불필요, 벽시계 비의존).

검증 항목(AC1 — UTC 저장 / KST 판정):
  (a) now_utc()가 tz-aware UTC(오프셋 0)를 반환
  (b) 날짜 경계 결정성 — UTC 2026-06-14T15:30:00Z 주입 시 today_in_tz가
      KST 기준 2026-06-15를 반환(= UTC 날짜와 다름, NFR-1 핵심 실증)
  (c) hours_until / is_within_hours 경계 규칙(부호·경계 포함)
  (d) isoformat_utc가 '...Z'로 끝나고 '+00:00'을 포함하지 않음
  (e) naive datetime 입력 거부(ValueError) — 로컬 tz 해석 원천 차단

모든 시각은 now를 명시 주입하여 결정적으로 검증한다(벽시계 의존 금지).
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core import time as t


# (a) now_utc() — tz-aware UTC ---------------------------------------------------
def test_now_utc_is_tz_aware_utc():
    now = t.now_utc()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


# (b) 날짜 경계 결정성(KST = UTC+9) ---------------------------------------------
def test_today_in_tz_crosses_date_boundary():
    # UTC 2026-06-14 15:30 → KST 2026-06-15 00:30 → "오늘"은 6/15 (UTC 날짜와 다름)
    injected = datetime(2026, 6, 14, 15, 30, tzinfo=UTC)
    assert t.today_in_tz(now=injected) == date(2026, 6, 15)
    # 같은 순간의 UTC 날짜는 6/14 — 로컬 tz 의존이면 틀린 답이 나오는 지점
    assert injected.date() == date(2026, 6, 14)


def test_today_in_tz_before_boundary_same_date():
    # UTC 2026-06-14 14:59 → KST 2026-06-14 23:59 → "오늘"은 6/14
    injected = datetime(2026, 6, 14, 14, 59, tzinfo=UTC)
    assert t.today_in_tz(now=injected) == date(2026, 6, 14)


# (c) hours_until / is_within_hours 경계 ---------------------------------------
def test_hours_until_signed():
    now = datetime(2026, 6, 14, 0, 0, tzinfo=UTC)
    assert t.hours_until(now + timedelta(hours=5), now=now) == pytest.approx(5.0)
    assert t.hours_until(now - timedelta(hours=2), now=now) == pytest.approx(-2.0)


def test_is_within_hours_boundaries():
    now = datetime(2026, 6, 14, 0, 0, tzinfo=UTC)
    # 5h 남음, 6h 이내 → True
    assert t.is_within_hours(now + timedelta(hours=5), 6, now=now) is True
    # 7h 남음, 6h 이내 → False
    assert t.is_within_hours(now + timedelta(hours=7), 6, now=now) is False
    # 정확히 6.0h 남음 → 상한 경계 포함(True)
    assert t.is_within_hours(now + timedelta(hours=6), 6, now=now) is True
    # 하한 경계: target == now (0h 남음) → 경계 포함(True)
    assert t.is_within_hours(now, 6, now=now) is True
    # 이미 지남(음수) → False
    assert t.is_within_hours(now - timedelta(hours=1), 6, now=now) is False


def test_is_within_hours_rejects_invalid_hours():
    # 음수·NaN hours는 조용한 False가 아니라 ValueError로 거부(판정 누락 방지)
    now = datetime(2026, 6, 14, 0, 0, tzinfo=UTC)
    target = now + timedelta(hours=1)
    with pytest.raises(ValueError):
        t.is_within_hours(target, -1, now=now)
    with pytest.raises(ValueError):
        t.is_within_hours(target, float("nan"), now=now)


# (d) isoformat_utc — '...Z' 직렬화 --------------------------------------------
def test_isoformat_utc_uses_z_suffix():
    dt = datetime(2026, 6, 14, 5, 0, 0, tzinfo=UTC)
    s = t.isoformat_utc(dt)
    assert s.endswith("Z")
    assert "+00:00" not in s
    assert s == "2026-06-14T05:00:00Z"


def test_isoformat_utc_normalizes_non_utc_to_utc():
    # KST 14:00 → UTC 05:00Z (다른 tz 입력도 UTC로 정규화)
    kst = t.to_tz(datetime(2026, 6, 14, 5, 0, 0, tzinfo=UTC))
    assert t.isoformat_utc(kst) == "2026-06-14T05:00:00Z"


# (e) naive datetime 거부(ValueError) ------------------------------------------
def test_naive_datetime_rejected():
    naive = datetime(2026, 6, 14, 5, 0, 0)  # tzinfo 없음
    with pytest.raises(ValueError):
        t.to_tz(naive)
    with pytest.raises(ValueError):
        t.hours_until(naive)
    with pytest.raises(ValueError):
        t.isoformat_utc(naive)
