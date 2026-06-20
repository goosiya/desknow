"""notifications 도래 리마인드 도출 헬퍼 테스트 (Story 5.2 — AC1·AC5).

**경계 테스트 필수(deferred-work.md L103 의무 회수):** ``is_within_reminder_window``를 24h 정수
경계(``timedelta`` 비교)로 못박는다 — 부동소수 ``hours_until`` 미사용. 정확히 24h(포함)·
24h+1초(제외)·지금(delta 0 포함)·이미 시작(음수 제외)·1초 전(포함)·naive 거부.

``due_reminder_reservations``는 ``reservations.service.list_booker_reservations``와
``notifications.service.dismissed_reminder_reservation_ids``를 조합하는 라우터 계층 헬퍼이므로,
그 두 의존성을 monkeypatch로 주입해 **도출 필터링 로직만** 결정적으로 검증한다(시각도 ``now``
파라미터로 주입). 4.7 ``_CANCEL_WINDOW`` timedelta 경계 테스트 선례를 미러한다.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.time import isoformat_utc
from app.notifications import reminders
from app.reservations.models import Reservation, ReservationStatus

# 결정성 기준 시각(UTC aware). 모든 경계·도출 테스트가 이 now를 주입한다.
_NOW = datetime(2026, 6, 17, 0, 0, tzinfo=UTC)


# ── is_within_reminder_window (AC1·AC5 — 24h timedelta 경계·L103 회수) ────────────────
def test_within_window_exactly_24h_is_true() -> None:
    """정확히 24시간 남음 → 포함(상한 경계 inclusive — timedelta 정수 비교)."""
    earliest = _NOW + timedelta(hours=24)
    assert reminders.is_within_reminder_window(earliest, _NOW) is True


def test_within_window_24h_plus_one_second_is_false() -> None:
    """24시간 + 1초 남음 → 제외(상한 초과)."""
    earliest = _NOW + timedelta(hours=24, seconds=1)
    assert reminders.is_within_reminder_window(earliest, _NOW) is False


def test_within_window_now_is_true() -> None:
    """delta 0(지금 시작) → 포함(하한 경계 inclusive)."""
    assert reminders.is_within_reminder_window(_NOW, _NOW) is True


def test_within_window_already_started_is_false() -> None:
    """이미 시작(음수 delta) → 제외(과거 슬롯 비도출)."""
    earliest = _NOW - timedelta(seconds=1)
    assert reminders.is_within_reminder_window(earliest, _NOW) is False


def test_within_window_just_inside_upper_bound_is_true() -> None:
    """24시간 - 1초 남음 → 포함(상한 직전)."""
    earliest = _NOW + timedelta(hours=24) - timedelta(seconds=1)
    assert reminders.is_within_reminder_window(earliest, _NOW) is True


def test_within_window_rejects_naive_earliest() -> None:
    """naive earliest → ValueError(차감/매칭 실패 방지 fail-fast)."""
    with pytest.raises(ValueError):
        reminders.is_within_reminder_window(datetime(2026, 6, 17, 10, 0), _NOW)


def test_within_window_rejects_naive_now() -> None:
    """naive now → ValueError."""
    with pytest.raises(ValueError):
        reminders.is_within_reminder_window(_NOW + timedelta(hours=1), datetime(2026, 6, 17))


# ── due_reminder_reservations (AC1 — confirmed·억제·24h 조합 필터) ────────────────────
def _reservation(
    *,
    hours_ahead: float,
    status: ReservationStatus = ReservationStatus.CONFIRMED,
    extra_hours: list[float] | None = None,
) -> Reservation:
    """``hours_ahead`` 시간 뒤 시작하는 슬롯을 가진 예약(slot_starts 오름차순 ISO ...Z 스냅샷)."""
    starts = [_NOW + timedelta(hours=hours_ahead)]
    for h in extra_hours or []:
        starts.append(_NOW + timedelta(hours=h))
    return Reservation(
        booker_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        status=status,
        slot_starts=sorted(isoformat_utc(s) for s in starts),
    )


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reservations: list[Reservation],
    suppressed: set[uuid.UUID] | None = None,
) -> None:
    """list_booker_reservations·dismissed_reminder_reservation_ids를 결정적으로 주입한다."""
    monkeypatch.setattr(
        reminders.reservations_service,
        "list_booker_reservations",
        lambda session, user_id: reservations,
    )
    monkeypatch.setattr(
        reminders.service,
        "dismissed_reminder_reservation_ids",
        lambda session, user_id: suppressed or set(),
    )


def test_due_includes_confirmed_within_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """confirmed·24h 이내·미억제 예약 → 도출 포함."""
    reservation = _reservation(hours_ahead=10)
    _patch(monkeypatch, reservations=[reservation])

    result = reminders.due_reminder_reservations(object(), uuid.uuid4(), _NOW)

    assert result == [reservation]


def test_due_excludes_outside_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """24h 밖(48h 뒤) confirmed → 제외."""
    _patch(monkeypatch, reservations=[_reservation(hours_ahead=48)])
    assert reminders.due_reminder_reservations(object(), uuid.uuid4(), _NOW) == []


def test_due_excludes_terminal_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """cancelled/rejected(종료 상태)는 24h 이내여도 제외."""
    _patch(
        monkeypatch,
        reservations=[
            _reservation(hours_ahead=10, status=ReservationStatus.CANCELLED),
            _reservation(hours_ahead=10, status=ReservationStatus.REJECTED),
        ],
    )
    assert reminders.due_reminder_reservations(object(), uuid.uuid4(), _NOW) == []


def test_due_excludes_suppressed(monkeypatch: pytest.MonkeyPatch) -> None:
    """'다시 보지 않기' 억제건(reservation_id ∈ suppressed) → 제외."""
    reservation = _reservation(hours_ahead=10)
    _patch(monkeypatch, reservations=[reservation], suppressed={reservation.id})
    assert reminders.due_reminder_reservations(object(), uuid.uuid4(), _NOW) == []


def test_due_uses_earliest_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """가장 이른 슬롯[0] 기준 판정 — earliest가 24h 이내면 후속 슬롯이 밖이어도 포함."""
    reservation = _reservation(hours_ahead=10, extra_hours=[30])  # [0]=10h(이내)
    _patch(monkeypatch, reservations=[reservation])
    assert reminders.due_reminder_reservations(object(), uuid.uuid4(), _NOW) == [reservation]


def test_due_skips_empty_slot_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    """slot_starts 빈 예약(방어) → skip(confirmed는 ≥1 보장이나 fail-safe)."""
    empty = Reservation(booker_id=uuid.uuid4(), room_id=uuid.uuid4(), slot_starts=[])
    _patch(monkeypatch, reservations=[empty])
    assert reminders.due_reminder_reservations(object(), uuid.uuid4(), _NOW) == []


def test_due_skips_corrupt_slot_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    """손상 비-ISO slot_starts[0] 예약(L7) → 예외 없이 skip(ValueError→GET 500 회피)."""
    corrupt = Reservation(
        booker_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        status=ReservationStatus.CONFIRMED,
        slot_starts=["not-a-date"],
    )
    valid = _reservation(hours_ahead=10)
    _patch(monkeypatch, reservations=[corrupt, valid])
    # 손상은 skip, 정상은 도출 — 손상 한 건이 전체를 죽이지 않음.
    assert reminders.due_reminder_reservations(object(), uuid.uuid4(), _NOW) == [valid]


# ── earliest_slot_start (AC1·AC4 — 안전 파서·L7 회수·공유 헬퍼) ───────────────────────
def test_earliest_slot_start_parses_valid_iso() -> None:
    """정상 ISO ...Z → aware datetime 파싱."""
    reservation = _reservation(hours_ahead=10)
    assert reminders.earliest_slot_start(reservation) == _NOW + timedelta(hours=10)


def test_earliest_slot_start_empty_returns_none() -> None:
    """빈 slot_starts → None(추가 파싱 없음)."""
    empty = Reservation(booker_id=uuid.uuid4(), room_id=uuid.uuid4(), slot_starts=[])
    assert reminders.earliest_slot_start(empty) is None


def test_earliest_slot_start_corrupt_returns_none_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """손상 비-ISO 문자열 → None + logger.warning(전파 금지·L7 회수)."""
    corrupt = Reservation(
        booker_id=uuid.uuid4(), room_id=uuid.uuid4(), slot_starts=["20260617-broken"]
    )
    with caplog.at_level("WARNING"):
        assert reminders.earliest_slot_start(corrupt) is None
    assert "slot_starts[0]" in caplog.text


def test_earliest_slot_start_uses_first_of_sorted() -> None:
    """다중 슬롯(오름차순 스냅샷) → [0]=earliest 반환."""
    reservation = _reservation(hours_ahead=10, extra_hours=[30])  # sorted → [0]=10h
    assert reminders.earliest_slot_start(reservation) == _NOW + timedelta(hours=10)


def test_earliest_slot_start_naive_returns_none_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """naive(무-Z·tz 없음) ISO → None + logger.warning(비-ISO와 동일 손상 처리·코드리뷰 2026-06-17).

    ``fromisoformat``은 tz 없는 유효 ISO를 성공 파싱하나 naive면 윈도 _require_aware /
    직렬화 isoformat_utc가 ValueError→GET 500이 되므로 헬퍼가 None으로 차단(200 유지).
    """
    naive = Reservation(
        booker_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        slot_starts=["2026-06-17T10:00:00"],  # 유효 ISO지만 tz 지정자 없음(naive)
    )
    with caplog.at_level("WARNING"):
        assert reminders.earliest_slot_start(naive) is None
    assert "naive" in caplog.text


def test_due_skips_naive_slot_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    """naive slot_starts[0] 예약 → 예외 없이 skip(GET 500 회피·정상은 도출)."""
    naive = Reservation(
        booker_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2026-06-17T10:00:00"],  # tz 없는 naive
    )
    valid = _reservation(hours_ahead=10)
    _patch(monkeypatch, reservations=[naive, valid])
    assert reminders.due_reminder_reservations(object(), uuid.uuid4(), _NOW) == [valid]
