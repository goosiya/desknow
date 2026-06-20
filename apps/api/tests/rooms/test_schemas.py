"""rooms 요청 스키마 검증 테스트 (Story 2.2 — AC1·AC3·P3 1차 차단).

DB 불필요 — Pydantic 검증을 직접 단언한다. 백엔드 신뢰 경계(range·enum·자정 넘김)가
요청 단계에서 ``ValidationError``로 거부됨을 실증한다(1.5 핸들러가 라우터에서 422로 단일화).
"""
from __future__ import annotations

from datetime import time

import pytest
from pydantic import ValidationError

from app.rooms.schemas import BusinessHoursInput, RoomCreateRequest

_VALID_BH = {"weekday": 0, "open_time": "09:00:00", "close_time": "22:00:00"}


def _room_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "테스트룸",
        "price_per_hour": 10000,
        "capacity": 4,
        "room_type": "open",
        "amenities": ["wifi", "parking"],
        "lat": 37.5,
        "lng": 127.0,
        "admin_dong_code": "1168010100",
        "business_hours": [dict(_VALID_BH)],
    }
    base.update(overrides)
    return base


# ── BusinessHoursInput (AC3 — 같은 날 내, 자정 넘김 거부) ──────────────────────
def test_business_hours_valid() -> None:
    bh = BusinessHoursInput(**_VALID_BH)
    assert bh.open_time == time(9, 0)
    assert bh.close_time == time(22, 0)


def test_business_hours_close_equals_open_rejected() -> None:
    """close == open → 거부(슬롯 0, 무의미)."""
    with pytest.raises(ValidationError):
        BusinessHoursInput(weekday=0, open_time="09:00:00", close_time="09:00:00")


def test_business_hours_midnight_crossing_rejected() -> None:
    """자정 넘김(22:00~02:00 = close < open) → 거부(AC3)."""
    with pytest.raises(ValidationError):
        BusinessHoursInput(weekday=0, open_time="22:00:00", close_time="02:00:00")


@pytest.mark.parametrize("weekday", [-1, 7, 99])
def test_business_hours_weekday_out_of_range_rejected(weekday: int) -> None:
    """weekday는 0~6만 허용."""
    with pytest.raises(ValidationError):
        BusinessHoursInput(weekday=weekday, open_time="09:00:00", close_time="18:00:00")


# ── RoomCreateRequest (AC1 · P3 · 2.1 defer 회수) ─────────────────────────────
def test_room_create_request_valid() -> None:
    req = RoomCreateRequest(**_room_payload())
    assert req.room_type == "open"
    assert req.amenities == ["wifi", "parking"]


def test_room_type_invalid_rejected() -> None:
    """room_type은 open/private만(P3 Literal 1차 차단)."""
    with pytest.raises(ValidationError):
        RoomCreateRequest(**_room_payload(room_type="shared"))


def test_amenity_unknown_code_rejected() -> None:
    """미지정 부대시설 코드는 거부."""
    with pytest.raises(ValidationError):
        RoomCreateRequest(**_room_payload(amenities=["wifi", "sauna"]))


def test_amenities_deduplicated() -> None:
    """중복 부대시설은 순서 보존 제거된다."""
    req = RoomCreateRequest(**_room_payload(amenities=["wifi", "wifi", "parking", "wifi"]))
    assert req.amenities == ["wifi", "parking"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"price_per_hour": -1},  # 음수 금액(2.1 defer 회수)
        {"capacity": 0},  # 0명
        {"lat": 91.0},  # 위도 범위 밖
        {"lat": -91.0},
        {"lng": 181.0},  # 경도 범위 밖
        {"lng": -181.0},
        {"name": ""},  # 빈 이름
        {"business_hours": []},  # 영업시간 없음(min_length=1)
    ],
)
def test_room_create_request_range_violations_rejected(overrides: dict[str, object]) -> None:
    """금액·인원·좌표·이름·영업시간 범위 위반은 거부(2.1 defer + P3 회수)."""
    with pytest.raises(ValidationError):
        RoomCreateRequest(**_room_payload(**overrides))


def test_business_hours_duplicate_weekday_rejected() -> None:
    """동일 weekday 중복 영업시간은 422로 거부된다(code-review patch).

    이 검증이 없으면 중복 weekday가 Pydantic을 통과해 create_room commit에서
    uq_business_hours_room_id_weekday 위반 IntegrityError → 미처리 500이 된다.
    """
    with pytest.raises(ValidationError):
        RoomCreateRequest(
            **_room_payload(
                business_hours=[
                    {"weekday": 0, "open_time": "09:00:00", "close_time": "18:00:00"},
                    {"weekday": 0, "open_time": "10:00:00", "close_time": "20:00:00"},
                ]
            )
        )


def test_business_hours_distinct_weekdays_allowed() -> None:
    """서로 다른 weekday 다중 행은 정상 허용된다(중복 거부가 과잉 차단하지 않음)."""
    req = RoomCreateRequest(
        **_room_payload(
            business_hours=[
                {"weekday": 0, "open_time": "09:00:00", "close_time": "18:00:00"},
                {"weekday": 1, "open_time": "10:00:00", "close_time": "20:00:00"},
            ]
        )
    )
    assert [bh.weekday for bh in req.business_hours] == [0, 1]
