"""예약검색 툴 단위 테스트 (Story 7.6 — Task 2, 네트워크/실키/DB 불필요).

검증 항목(7.5 test_tools.py 패턴 미러 — service reader/지역해석을 monkeypatch 해 DB·키 없이):
  - 상위 3개 + 더보기 직렬화(이름·가격·룸형태·부대시설·상세 `/rooms/{id}` 링크)
  - 자연어 지역명을 `resolve_region`으로 코드 변환해 `search_rooms(region_code=...)`에 전달
  - 미해석 지역 → `REGION_NOT_FOUND` 신호(검색 미수행 — 환각 금지)
  - 후보 0건 → `NO_AVAILABLE_ROOMS` 신호
  - 시간 조건(date/start_hour) → `available_room_ids_at` 벌크 reader로 가용 룸 정합 필터(AC5)
  - 잘못된 시간 인자(범위 밖 시각·파싱 불가 날짜) → `INVALID_TIME` 신호(검색 미수행)
  - 경계: 툴은 service reader만 호출(raw SQL 미접근) — monkeypatch 호출 단언으로 확인

툴은 자체 단명 세션(`Session(get_engine())`)을 열지만, search_rooms/available_room_ids_at를
monkeypatch하면 세션은 쿼리를 실행하지 않으므로(엔진 lazy) 실 DB 없이 돈다.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.chatbot import tools as tools_mod
from app.chatbot.tools import (
    INVALID_TIME,
    LOCATION_UNAVAILABLE,
    NO_AVAILABLE_ROOMS,
    REGION_NOT_FOUND,
    search_available_rooms,
)
from app.rooms.schemas import RoomListItem


def _item(
    name: str,
    *,
    remaining: int = 2,
    room_id: uuid.UUID | None = None,
    price: int = 10000,
    room_type: str = "private",
    amenities: list[str] | None = None,
) -> RoomListItem:
    return RoomListItem(
        room_id=room_id or uuid.uuid4(),
        name=name,
        price_per_hour=price,
        room_type=room_type,
        amenities=amenities if amenities is not None else ["화이트보드"],
        remaining_slots=remaining,
    )


def _invoke(**kwargs: Any) -> str:
    # LangChain @tool은 .invoke({...})로 호출(스키마 검증 포함).
    return search_available_rooms.invoke(kwargs)


def test_reservation_tool_serializes_top_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 5곳 매칭(모두 잔여 ≥1) → 상위 3곳 표시 + 더보기 안내.
    items = [_item(f"룸{i}", remaining=5 - i) for i in range(5)]
    monkeypatch.setattr(tools_mod, "search_rooms", lambda *a, **k: items)
    result = _invoke()

    # 상위 3곳(잔여 내림차순)의 이름·상세 링크·가격이 직렬화된다.
    assert "룸0" in result and "룸1" in result and "룸2" in result
    assert f"/rooms/{items[0].room_id}" in result
    assert "10,000원/시간" in result
    assert "화이트보드" in result
    # 3곳 초과 → 더보기(/) 안내가 포함된다(하위 2곳은 본문 미표시).
    assert "더보기" in result and "/" in result
    assert "룸4" not in result


def test_reservation_tool_resolves_region(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_search(session: Any, region_code: str | None = None, **kw: Any) -> list[Any]:
        captured["region_code"] = region_code
        return [_item("강남룸")]

    monkeypatch.setattr(tools_mod, "resolve_region", lambda name: "1168000000")
    monkeypatch.setattr(tools_mod, "search_rooms", fake_search)
    result = _invoke(region="강남")

    # 자연어 지역명이 코드로 변환돼 search_rooms에 전달된다(경계: 서비스 reader 경유).
    assert captured["region_code"] == "1168000000"
    assert "강남룸" in result


def test_reservation_tool_region_not_found_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {"search": False}

    def fake_search(*a: Any, **k: Any) -> list[Any]:
        called["search"] = True
        return []

    monkeypatch.setattr(tools_mod, "resolve_region", lambda name: None)
    monkeypatch.setattr(tools_mod, "search_rooms", fake_search)
    result = _invoke(region="없는동네")

    # 미해석 지역 → 명시 신호. 검색은 수행하지 않는다(조용한 빈 결과 오인·환각 금지).
    assert result == REGION_NOT_FOUND
    assert called["search"] is False


def test_reservation_tool_no_available_rooms_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 후보 0건(또는 전부 잔여 0) → 명시 신호.
    monkeypatch.setattr(tools_mod, "search_rooms", lambda *a, **k: [])
    assert _invoke() == NO_AVAILABLE_ROOMS

    monkeypatch.setattr(
        tools_mod, "search_rooms", lambda *a, **k: [_item("만석룸", remaining=0)]
    )
    assert _invoke() == NO_AVAILABLE_ROOMS


def test_reservation_tool_time_filters_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    # 시각 조건 → available_room_ids_at 벌크 reader가 가용 룸 id 집합을 돌려주고, 그 집합의
    # 룸만 후보로 남는다(AC5 — 룸별 get_room_slots N+1 회피, 리뷰 patch).
    open_room = _item("열린룸")
    full_room = _item("막힌룸")
    monkeypatch.setattr(
        tools_mod, "search_rooms", lambda *a, **k: [open_room, full_room]
    )
    monkeypatch.setattr(
        tools_mod, "available_room_ids_at", lambda *a, **k: {open_room.room_id}
    )
    result = _invoke(date="2026-06-20", start_hour=15)

    assert "열린룸" in result
    assert "막힌룸" not in result


def test_reservation_tool_time_filter_no_match_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 시각 조건에 맞는 가용 룸이 한 곳도 없으면(빈 집합) 신호.
    room = _item("룸")
    monkeypatch.setattr(tools_mod, "search_rooms", lambda *a, **k: [room])
    monkeypatch.setattr(tools_mod, "available_room_ids_at", lambda *a, **k: set())
    assert _invoke(date="2026-06-20", start_hour=15) == NO_AVAILABLE_ROOMS


def test_reservation_tool_invalid_time_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    # 범위 밖 시각(25·-1)·파싱 불가 날짜는 무필터로 강등하지 않고 명시 신호 — 검색도 미수행
    # (조건이 사라진 무필터 결과를 "요청 시각에 맞는 것처럼" 내지 않기, 리뷰 patch).
    called = {"search": False}

    def fake_search(*a: Any, **k: Any) -> list[Any]:
        called["search"] = True
        return [_item("룸")]

    monkeypatch.setattr(tools_mod, "search_rooms", fake_search)
    assert _invoke(start_hour=25) == INVALID_TIME
    assert _invoke(start_hour=-1) == INVALID_TIME
    assert _invoke(date="내일") == INVALID_TIME
    assert called["search"] is False


def test_reservation_tool_delegates_to_service_readers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 경계 단언: 시간 조건이 오면 search_rooms·available_room_ids_at 두 service reader를 호출한다
    # (툴은 raw SQL/ORM 미접근 — service 계층 위임). 호출 플래그로 확인.
    calls = {"search": 0, "avail": 0}
    room = _item("룸")

    def fake_search(*a: Any, **k: Any) -> list[Any]:
        calls["search"] += 1
        return [room]

    def fake_avail(*a: Any, **k: Any) -> set[uuid.UUID]:
        calls["avail"] += 1
        return {room.room_id}

    monkeypatch.setattr(tools_mod, "search_rooms", fake_search)
    monkeypatch.setattr(tools_mod, "available_room_ids_at", fake_avail)
    _invoke(date="2026-06-20")

    assert calls["search"] == 1
    assert calls["avail"] == 1


# ── near_me 반경 검색(챗봇 "내 주변" — 좌표는 graph config로 주입, LLM 비노출) ──


def _fake_radius_search(captured: dict[str, Any]) -> Any:
    """search_rooms 대역 — 반경/지역 인자를 captured에 담고 후보 1곳을 돌려준다."""

    def fake_search(
        session: Any,
        region_code: str | None = None,
        *,
        center_lat: float | None = None,
        center_lng: float | None = None,
        radius_km: float | None = None,
        **kw: Any,
    ) -> list[Any]:
        captured.update(
            region_code=region_code,
            center_lat=center_lat,
            center_lng=center_lng,
            radius_km=radius_km,
        )
        return [_item("근처룸")]

    return fake_search


def test_reservation_tool_near_me_radius_search(monkeypatch: pytest.MonkeyPatch) -> None:
    # near_me=True + config 주입 좌표 → 반경 검색(기본 5km). region이 함께 와도 좌표 우선(region 무시).
    captured: dict[str, Any] = {}
    monkeypatch.setattr(tools_mod, "search_rooms", _fake_radius_search(captured))
    result = search_available_rooms.invoke(
        {"near_me": True, "region": "강남"},
        config={"configurable": {"user_coords": (37.5, 127.18)}},
    )
    assert captured["center_lat"] == 37.5
    assert captured["center_lng"] == 127.18
    assert captured["radius_km"] == 5.0  # 기본 5km
    assert captured["region_code"] is None  # near_me면 region 미적용
    assert "근처룸" in result


def test_reservation_tool_near_me_radius_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    # 과도한 반경(50km) 요청 → 최대 10km로 절삭.
    captured: dict[str, Any] = {}
    monkeypatch.setattr(tools_mod, "search_rooms", _fake_radius_search(captured))
    search_available_rooms.invoke(
        {"near_me": True, "radius_km": 50},
        config={"configurable": {"user_coords": (37.5, 127.18)}},
    )
    assert captured["radius_km"] == 10.0


def test_reservation_tool_near_me_no_coords_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # near_me인데 config에 좌표 없음(권한 거부·미측정) → 명시 신호. 검색은 수행하지 않는다.
    called = {"search": False}

    def fake_search(*a: Any, **k: Any) -> list[Any]:
        called["search"] = True
        return [_item("룸")]

    monkeypatch.setattr(tools_mod, "search_rooms", fake_search)
    out = search_available_rooms.invoke({"near_me": True}, config={"configurable": {}})
    assert out == LOCATION_UNAVAILABLE
    assert called["search"] is False
