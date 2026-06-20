"""rooms 라우터 통합 테스트 (Story 2.2 — AC1·AC2·AC4·AC5 RBAC).

**DB 불필요** — ``app.dependency_overrides[get_session]``로 세션을 Fake로 교체하고,
``TestClient(app)``(모듈 레벨, lifespan 미실행 — 1.4 불변식 유지)로 엔드포인트를 검증한다.
실 provider/booker access 토큰으로 RBAC(provider 201/200·booker 403·무토큰 401)를 실증한다.
지오코딩은 ``service._geocode_client``를 monkeypatch해 라이브 카카오 호출 없이 검증한다.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.db import get_session
from app.core.security import create_access_token
from app.main import app
from app.rooms import service
from tests.rooms.test_service import (
    FAR_COORDS,
    NEAR_COORDS,
    RADIUS_CENTER,
    FakeAvailabilitySession,
    FakeRoomSession,
    _avail_room,
    _mock_geocode_client,
    _room_bh,
)

client = TestClient(app)

_VALID_ROOM_BODY: dict[str, Any] = {
    "name": "테스트룸",
    "price_per_hour": 10000,
    "capacity": 4,
    "room_type": "open",
    "amenities": ["wifi", "parking"],
    "lat": 37.5,
    "lng": 127.0,
    "admin_dong_code": "1168010100",
    "business_hours": [
        {"weekday": 0, "open_time": "09:00:00", "close_time": "22:00:00"}
    ],
}


@contextmanager
def _override_session(session: Any) -> Iterator[None]:
    def _fake_get_session() -> Iterator[Any]:
        yield session

    app.dependency_overrides[get_session] = _fake_get_session
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def _provider_token() -> str:
    return create_access_token(uuid.uuid4(), "provider")


def _booker_token() -> str:
    return create_access_token(uuid.uuid4(), "booker")


# ── POST /api/v1/rooms (등록 — AC1·AC4·AC5) ───────────────────────────────────
def test_create_room_provider_returns_201(auth_env: None) -> None:
    """provider 토큰 → 201 + RoomPublic(created_at ...Z·해시류 없음)."""
    with _override_session(FakeRoomSession(existing_room=None)):
        resp = client.post(
            "/api/v1/rooms",
            json=_VALID_ROOM_BODY,
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == {
        "id", "provider_id", "name", "price_per_hour", "capacity", "room_type",
        "amenities", "lat", "lng", "admin_dong_code", "is_active", "created_at",
    }
    assert body["room_type"] == "open"
    assert body["amenities"] == ["wifi", "parking"]
    assert body["is_active"] is True
    assert body["created_at"].endswith("Z")


def test_create_room_booker_returns_403(auth_env: None) -> None:
    """booker 토큰 → 403 FORBIDDEN_ROLE(provider만 등록 — AC5)."""
    with _override_session(FakeRoomSession(existing_room=None)):
        resp = client.post(
            "/api/v1/rooms",
            json=_VALID_ROOM_BODY,
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_create_room_no_token_returns_401(auth_env: None) -> None:
    """토큰 없음 → 401 UNAUTHENTICATED."""
    with _override_session(FakeRoomSession(existing_room=None)):
        resp = client.post("/api/v1/rooms", json=_VALID_ROOM_BODY)

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_create_room_midnight_crossing_returns_422(auth_env: None) -> None:
    """자정 넘김 영업시간(22:00~02:00) → 422 VALIDATION_ERROR(AC3)."""
    body = {
        **_VALID_ROOM_BODY,
        "business_hours": [
            {"weekday": 0, "open_time": "22:00:00", "close_time": "02:00:00"}
        ],
    }
    with _override_session(FakeRoomSession(existing_room=None)):
        resp = client.post(
            "/api/v1/rooms",
            json=body,
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_create_room_existing_returns_409(auth_env: None) -> None:
    """이미 룸 보유 제공자 → 409 ROOM_LIMIT_REACHED(AC4)."""
    from app.rooms.models import Room

    existing = Room(
        provider_id=uuid.uuid4(),
        name="기존",
        price_per_hour=5000,
        capacity=2,
        room_type="private",
        amenities=[],
        lat=37.0,
        lng=127.0,
        admin_dong_code="1100000000",
    )
    with _override_session(FakeRoomSession(existing_room=existing)):
        resp = client.post(
            "/api/v1/rooms",
            json=_VALID_ROOM_BODY,
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "ROOM_LIMIT_REACHED"


# ── GET /api/v1/rooms/geocode (주소 검색 — AC2·RBAC) ──────────────────────────
def test_geocode_provider_returns_200(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """provider + mock httpx → 200 + 결과 리스트."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "documents": [
                    {
                        "address_name": "서울특별시 강남구 역삼동",
                        "x": "127.03",
                        "y": "37.50",
                        "address": {"b_code": "1168010100"},
                    }
                ]
            },
        )

    monkeypatch.setattr(service, "_geocode_client", _mock_geocode_client(handler))
    resp = client.get(
        "/api/v1/rooms/geocode",
        params={"query": "역삼동"},
        headers={"Authorization": f"Bearer {_provider_token()}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 1
    assert data[0]["admin_dong_code"] == "1168010100"
    assert data[0]["lat"] == pytest.approx(37.50)
    assert data[0]["lng"] == pytest.approx(127.03)


def test_geocode_booker_returns_403(auth_env: None) -> None:
    """booker 토큰 → 403(provider 전용 — RBAC가 카카오 호출 전에 차단)."""
    resp = client.get(
        "/api/v1/rooms/geocode",
        params={"query": "역삼동"},
        headers={"Authorization": f"Bearer {_booker_token()}"},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


# ── PATCH /api/v1/rooms/{room_id} (수정 — AC1·AC4·AC5) ────────────────────────
def _owned_room_for(provider_id: uuid.UUID) -> Any:
    from app.rooms.models import Room

    return Room(
        provider_id=provider_id,
        name="원래룸",
        price_per_hour=10000,
        capacity=4,
        room_type="open",
        amenities=["wifi"],
        lat=37.5,
        lng=127.0,
        admin_dong_code="1168010100",
    )


def test_update_room_provider_returns_200(auth_env: None) -> None:
    """provider 본인 room PATCH → 200 + RoomPublic(부분 수정 — AC1)."""
    provider_id = uuid.uuid4()
    room = _owned_room_for(provider_id)
    token = create_access_token(provider_id, "provider")
    with _override_session(FakeRoomSession(stored_room=room)):
        resp = client.patch(
            f"/api/v1/rooms/{room.id}",
            json={"name": "새이름", "capacity": 8},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "새이름"
    assert body["capacity"] == 8
    assert body["created_at"].endswith("Z")
    # RoomPublic은 business_hours 미포함(2.2 create와 대칭).
    assert "business_hours" not in body


def test_update_room_booker_returns_403(auth_env: None) -> None:
    """booker 토큰 → 403 FORBIDDEN_ROLE(provider만 수정 — AC4)."""
    with _override_session(FakeRoomSession(stored_room=None)):
        resp = client.patch(
            f"/api/v1/rooms/{uuid.uuid4()}",
            json={"name": "x"},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_update_room_no_token_returns_401(auth_env: None) -> None:
    """토큰 없음 → 401 UNAUTHENTICATED."""
    with _override_session(FakeRoomSession(stored_room=None)):
        resp = client.patch(f"/api/v1/rooms/{uuid.uuid4()}", json={"name": "x"})

    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_update_room_other_or_missing_returns_404(auth_env: None) -> None:
    """타인/미존재 room_id → 404 ROOM_NOT_FOUND(소유권 백엔드 최종 — AC4)."""
    with _override_session(FakeRoomSession(stored_room=None)):  # get → None
        resp = client.patch(
            f"/api/v1/rooms/{uuid.uuid4()}",
            json={"name": "x"},
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ROOM_NOT_FOUND"


def test_update_room_midnight_crossing_returns_422(auth_env: None) -> None:
    """자정 넘김 영업시간(22:00~02:00) → 422 VALIDATION_ERROR(AC5)."""
    provider_id = uuid.uuid4()
    room = _owned_room_for(provider_id)
    token = create_access_token(provider_id, "provider")
    body = {
        "business_hours": [
            {"weekday": 0, "open_time": "22:00:00", "close_time": "02:00:00"}
        ]
    }
    with _override_session(FakeRoomSession(stored_room=room)):
        resp = client.patch(
            f"/api/v1/rooms/{room.id}",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_update_room_explicit_null_returns_422(auth_env: None) -> None:
    """명시적 JSON null(예: name=null) → 422 VALIDATION_ERROR(미처리 500 방지 — code-review patch).

    과거: 모든 필드가 ``X | None``이라 null이 통과해 setattr(None) → NOT NULL/JSONB
    IntegrityError나 business_hours 가드로 500이 누출됐다. ``_reject_explicit_null``이 422로
    단일화한다.
    """
    provider_id = uuid.uuid4()
    room = _owned_room_for(provider_id)
    token = create_access_token(provider_id, "provider")
    with _override_session(FakeRoomSession(stored_room=room)):
        resp = client.patch(
            f"/api/v1/rooms/{room.id}",
            json={"name": None},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


# ── GET /api/v1/rooms/availability (가용성 집계 — AC1·AC3 공개) ────────────────
def test_availability_public_returns_200() -> None:
    """토큰 없이 GET /rooms/availability → 200 + 리스트(공개 접근 실증, AC1).

    탐색 첫 화면 핀은 비로그인 접근이므로 인증 헤더 없이 200이어야 한다(auth_env 불필요 —
    JWT 미사용). FakeAvailabilitySession을 주입해 라이브 DB와 무관하게 검증한다.
    """
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )
    with _override_session(session):
        resp = client.get("/api/v1/rooms/availability")  # 토큰 없음

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    # AC3: 응답 항목 키가 정확히 집계값 둘 뿐 — 좌표/가격 등 메타 누출 없음.
    assert set(data[0]) == {"room_id", "remaining_slots"}
    assert data[0]["room_id"] == str(room.id)  # 와이어 snake_case 유지
    assert isinstance(data[0]["remaining_slots"], int)


def test_availability_empty_when_no_active_rooms() -> None:
    """활성 룸 0개 → 200 + 빈 리스트(에러 아님)."""
    with _override_session(FakeAvailabilitySession(rooms=[])):
        resp = client.get("/api/v1/rooms/availability")

    assert resp.status_code == 200
    assert resp.json() == []


# ── GET /api/v1/rooms (룸 목록 — AC1·AC2 공개 핀 좌표 공급) ────────────────────
def test_rooms_list_public_returns_200() -> None:
    """토큰 없이 GET /api/v1/rooms → 200 + 핀 메타 리스트(공개, AC1).

    탐색 첫 화면 핀 좌표는 비로그인 접근이므로 인증 헤더 없이 200이어야 한다(auth_env 불필요).
    응답 항목 키가 정확히 {room_id, name, lat, lng}인지 단언 — 메타 누출 0·provider_id 미노출.
    """
    room = _avail_room()
    with _override_session(FakeAvailabilitySession(rooms=[room])):
        resp = client.get("/api/v1/rooms")  # 토큰 없음

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    # AC2: 키가 정확히 핀 메타 넷뿐 — provider_id·price·created_at 등 누출 없음.
    assert set(data[0]) == {"room_id", "name", "lat", "lng"}
    assert data[0]["room_id"] == str(room.id)  # 와이어 snake_case 유지
    assert data[0]["name"] == room.name
    assert "provider_id" not in data[0]


def test_rooms_list_empty_when_no_active_rooms() -> None:
    """활성 룸 0개 → 200 + 빈 리스트(에러 아님)."""
    with _override_session(FakeAvailabilitySession(rooms=[])):
        resp = client.get("/api/v1/rooms")

    assert resp.status_code == 200
    assert resp.json() == []


# ── GET /api/v1/rooms/{room_id} (바텀시트 단일 룸 요약 — AC1·AC4 공개) ──────────
def test_get_room_public_returns_200() -> None:
    """토큰 없이 GET /api/v1/rooms/{uuid} → 200 + RoomSummary(공개, AC1·AC4·4.2 AC4).

    바텀시트/상세 신선 요약은 핀 탭(비로그인)이므로 인증 헤더 없이 200이어야 한다(auth_env 불필요).
    위치 미니 지도(4.2)용 lat/lng는 노출하되 provider_id·is_active·admin_dong_code는 없음을
    단언(공개·노출 회피). FakeAvailabilitySession 주입.
    """
    room = _avail_room(lat=37.5, lng=127.0)
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )
    with _override_session(session):
        resp = client.get(f"/api/v1/rooms/{room.id}")  # 토큰 없음

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 공개 요약 — 키가 정확히 요약 필드 + 좌표(provider_id·is_active·admin_dong_code 누출 없음).
    assert set(body) == {
        "room_id", "name", "price_per_hour", "capacity", "room_type",
        "amenities", "business_hours", "remaining_slots", "is_closed_today",
        "lat", "lng", "address",  # address = 표시용 주소(provider 입력, 미입력 null)
    }
    assert body["room_id"] == str(room.id)  # 와이어 snake_case 유지
    # 4.2: 위치 미니 지도용 좌표 노출(저장 좌표 그대로).
    assert body["lat"] == pytest.approx(37.5)
    assert body["lng"] == pytest.approx(127.0)
    assert "provider_id" not in body
    assert "is_active" not in body
    assert "admin_dong_code" not in body  # 지역 코드 미노출 유지
    assert isinstance(body["remaining_slots"], int)
    # business_hours는 "HH:MM:SS" 직렬화(시트가 절단해 표시).
    assert body["business_hours"][0]["open_time"] == "09:00:00"


def test_get_room_404() -> None:
    """미존재 room_id → 404 + detail.code == ROOM_NOT_FOUND(공개·get None)."""
    with _override_session(FakeAvailabilitySession(rooms=[])):
        resp = client.get(f"/api/v1/rooms/{uuid.uuid4()}")

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "ROOM_NOT_FOUND"


def test_get_room_inactive_returns_404() -> None:
    """비활성 룸 → 404 ROOM_NOT_FOUND(탐색 핀은 활성만 — 미존재와 합침)."""
    room = _avail_room(is_active=False)
    with _override_session(FakeAvailabilitySession(rooms=[room])):
        resp = client.get(f"/api/v1/rooms/{room.id}")

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ROOM_NOT_FOUND"


# ── GET /api/v1/rooms/{room_id}/slots (날짜별 슬롯 — Story 4.3 AC1 공개) ─────────
def test_get_room_slots_public_returns_200() -> None:
    """토큰 없이 GET /api/v1/rooms/{id}/slots?date= → 200 + {date, slots, next_available_date}.

    상세·슬롯은 비로그인(공개 — PRD §FR-2, get_room 동일 근거). 응답 슬롯 항목 키가 정확히
    {slot_start, status}(룸 메타 누출 0)이고 slot_start가 ...Z(UTC) 직렬화임을 단언한다.
    2026-06-16=화요일(weekday=1)이라 weekday=1 영업행이면 슬롯이 비어있지 않다(now 무관).
    """
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 1, 9, 22)]  # 화요일 영업
    )
    with _override_session(session):
        resp = client.get(f"/api/v1/rooms/{room.id}/slots?date=2026-06-16")  # 토큰 없음

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"date", "slots", "next_available_date"}
    assert body["date"] == "2026-06-16"  # 요청 날짜 echo(ROOM_TZ)
    assert isinstance(body["slots"], list)
    assert body["slots"]  # weekday=1 영업행 → 비어있지 않음
    first = body["slots"][0]
    # 슬롯 항목 키는 정확히 {slot_start, status} — 가격·이름 등 룸 메타 누출 0.
    assert set(first) == {"slot_start", "status"}
    assert first["status"] in {"available", "past", "reserved"}
    # slot_start는 ...Z(UTC) 와이어 규약(core/time isoformat_utc — RoomPublic 선례).
    assert first["slot_start"].endswith("Z")


def test_get_room_slots_invalid_date_422() -> None:
    """date=notadate(오형식) → 422 VALIDATION_ERROR(Pydantic Query 파싱→1.5 핸들러)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 1, 9, 22)]
    )
    with _override_session(session):
        resp = client.get(f"/api/v1/rooms/{room.id}/slots?date=notadate")

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_get_room_slots_missing_date_422() -> None:
    """date 누락(필수 쿼리) → 422 VALIDATION_ERROR."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 1, 9, 22)]
    )
    with _override_session(session):
        resp = client.get(f"/api/v1/rooms/{room.id}/slots")

    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_get_room_slots_not_found_404() -> None:
    """미존재 room_id → 404 + detail.code == ROOM_NOT_FOUND(공개·get None)."""
    with _override_session(FakeAvailabilitySession(rooms=[])):
        resp = client.get(f"/api/v1/rooms/{uuid.uuid4()}/slots?date=2026-06-16")

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "ROOM_NOT_FOUND"


# ── GET /api/v1/rooms/regions (콤보 트리 — AC1 공개) ──────────────────────────
def test_regions_public_returns_200() -> None:
    """토큰 없이 GET /rooms/regions → 200 + 시군구 그룹 리스트(공개, AC1).

    탐색은 비로그인 접근이므로 인증 헤더 없이 200이어야 한다(auth_env 불필요).
    FakeAvailabilitySession 주입(라이브 DB 무관). 그룹·동 라벨이 번들 참조로 채워진다.
    """
    room = _avail_room(admin_dong_code="1168010100")  # 강남구 역삼동
    with _override_session(FakeAvailabilitySession(rooms=[room])):
        resp = client.get("/api/v1/rooms/regions")  # 토큰 없음

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    group = data[0]
    assert group["name"] == "서울특별시 강남구"  # 시도 포함 라벨
    assert group["room_count"] == 1
    assert group["dongs"][0]["name"] == "역삼동"  # 동 짧은 라벨
    assert group["code"] == "1168000000"  # 와이어 snake_case 유지


def test_regions_empty_when_no_rooms() -> None:
    """활성 룸 0개 → 200 + 빈 리스트(에러 아님)."""
    with _override_session(FakeAvailabilitySession(rooms=[])):
        resp = client.get("/api/v1/rooms/regions")

    assert resp.status_code == 200
    assert resp.json() == []


# ── GET /api/v1/rooms/search (지역 목록 — AC1·AC4 공개) ────────────────────────
def test_search_public_returns_200_and_omits_internal_fields() -> None:
    """토큰 없이 GET /rooms/search → 200 + RoomListItem 리스트, 내부 필드 미노출(공개, AC1·AC4).

    응답 키가 정확히 공개 표면 필드뿐(provider_id·lat/lng·admin_dong_code 누출 없음)임을 단언한다.
    """
    room = _avail_room(admin_dong_code="1168010100")
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )
    with _override_session(session):
        resp = client.get("/api/v1/rooms/search")  # region_code 미지정 = 전체

    assert resp.status_code == 200, resp.text
    data = resp.json()["items"]
    assert len(data) == 1
    assert set(data[0]) == {
        "room_id", "name", "price_per_hour", "room_type", "amenities", "remaining_slots",
    }
    assert data[0]["room_id"] == str(room.id)  # 와이어 snake_case 유지
    assert "provider_id" not in data[0]
    assert "lat" not in data[0]
    assert "admin_dong_code" not in data[0]
    assert isinstance(data[0]["remaining_slots"], int)


def test_search_filters_by_region_code() -> None:
    """region_code 쿼리 → 그 지역 룸만(시군구 코드=구 전체)."""
    gn = _avail_room(admin_dong_code="1168010100")  # 강남구
    jn = _avail_room(admin_dong_code="1111010100")  # 종로구
    session = FakeAvailabilitySession(rooms=[gn, jn])
    with _override_session(session):
        resp = client.get(
            "/api/v1/rooms/search", params={"region_code": "1168000000"}
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["items"]
    assert {d["room_id"] for d in data} == {str(gn.id)}  # 강남구만


def test_search_unmapped_region_code_returns_empty() -> None:
    """미매핑/미존재 region_code → 200 + 빈 리스트(에러 계약 없음 — graceful)."""
    room = _avail_room(admin_dong_code="1168010100")
    with _override_session(FakeAvailabilitySession(rooms=[room])):
        resp = client.get(
            "/api/v1/rooms/search", params={"region_code": "9999900000"}
        )

    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["next_cursor"] is None


def test_search_radius_filters_by_distance() -> None:
    """lat/lng/radius_km 쿼리 → 반경 내 룸만(반경 밖 제외, 공개·AC1·AC4)."""
    near = _avail_room(lat=NEAR_COORDS[0], lng=NEAR_COORDS[1])
    far = _avail_room(lat=FAR_COORDS[0], lng=FAR_COORDS[1])  # ≈8km
    session = FakeAvailabilitySession(rooms=[near, far])
    with _override_session(session):
        resp = client.get(
            "/api/v1/rooms/search",
            params={
                "lat": RADIUS_CENTER[0],
                "lng": RADIUS_CENTER[1],
                "radius_km": 3.0,
            },
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["items"]
    assert {d["room_id"] for d in data} == {str(near.id)}  # 반경 내만
    # 반경 결과도 내부 필드 미노출(3.4 단언 확장 — AC4④).
    assert "lat" not in data[0]
    assert "provider_id" not in data[0]
    assert "admin_dong_code" not in data[0]


def test_search_partial_coords_no_radius_filter() -> None:
    """lat만(부분 좌표) → 반경 미적용, 전체 활성 룸(graceful — AC4①)."""
    near = _avail_room(lat=NEAR_COORDS[0], lng=NEAR_COORDS[1])
    far = _avail_room(lat=FAR_COORDS[0], lng=FAR_COORDS[1])
    session = FakeAvailabilitySession(rooms=[near, far])
    with _override_session(session):
        resp = client.get(
            "/api/v1/rooms/search", params={"lat": RADIUS_CENTER[0]}  # lng 없음
        )

    assert resp.status_code == 200, resp.text
    assert {d["room_id"] for d in resp.json()["items"]} == {str(near.id), str(far.id)}


def test_search_out_of_range_lat_returns_422() -> None:
    """범위 밖 위도(lat=999) → 422(Query 검증→1.5 핸들러, 신규 ErrorCode 0 — AC4②)."""
    with _override_session(FakeAvailabilitySession(rooms=[])):
        resp = client.get("/api/v1/rooms/search", params={"lat": 999, "lng": 127})
    assert resp.status_code == 422, resp.text


def test_search_nonpositive_radius_returns_422() -> None:
    """radius_km≤0 → 422(gt=0 Query 검증 — AC4②)."""
    with _override_session(FakeAvailabilitySession(rooms=[])):
        resp = client.get(
            "/api/v1/rooms/search",
            params={"lat": 37.5, "lng": 127.0, "radius_km": 0},
        )
    assert resp.status_code == 422, resp.text


def test_static_routes_declared_before_dynamic_room_id() -> None:
    """라우팅 순서 회귀: 정적 /rooms/geocode·/availability·GET ""·/regions·/search가 동적
    /rooms/{room_id}(GET·PATCH 둘 다)보다 먼저 선언돼야 한다.

    PATCH /{room_id}(2.3)·GET /{room_id}(3.3) 추가, 그리고 3.4 정적 /regions·/search 추가 후에도
    정적 경로가 room_id로 잡히지 않도록(UUID 변환 422 방지) 선언 순서를 고정한다(2.2/3.1/3.3/3.4
    router docstring 경고 — 회귀 락). 선언 순서를 직접 검사한다(FastAPI는 선언 순서대로 매칭).
    """
    from app.rooms.router import router

    paths = [getattr(r, "path", None) for r in router.routes]
    # /{room_id}는 GET·PATCH 둘 다 존재 → 첫 등장(가장 이른 동적 라우트) 인덱스를 기준으로 한다.
    first_dynamic_idx = paths.index("/rooms/{room_id}")
    assert paths.index("/rooms/geocode") < first_dynamic_idx
    assert paths.index("/rooms/availability") < first_dynamic_idx
    assert paths.index("/rooms/regions") < first_dynamic_idx  # 3.4
    assert paths.index("/rooms/search") < first_dynamic_idx  # 3.4


# ── GET /api/v1/rooms/search 커서 페이징 (F — 탐색 무한스크롤, offset) ─────────────
def test_search_pagination_walks_all_pages() -> None:
    """offset 커서 limit=2로 5개 활성 룸 페이징 → 첫 페이지 2개+next_cursor, 합집합 전수 일치.

    검색은 거리/지역 계산 정렬이라 offset 커서를 쓴다. 같은 region_code의 활성 룸 5개를 시드해
    페이지를 나누고, 전 페이지 합집합이 전체 룸 집합과 정확히 일치(중복/누락 0)함을 단언한다.
    """
    rooms = [_avail_room(admin_dong_code="1168010100") for _ in range(5)]
    session = FakeAvailabilitySession(rooms=rooms)

    def _get(cursor: str | None):
        params: dict[str, Any] = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        with _override_session(session):
            return client.get("/api/v1/rooms/search", params=params)

    first = _get(None).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    collected: list[dict] = []
    cursor: str | None = None
    seen: set[str] = set()
    while True:
        body = _get(cursor).json()
        collected.extend(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
        assert cursor not in seen, "커서 무한 루프"
        seen.add(cursor)

    room_ids = {item["room_id"] for item in collected}
    assert room_ids == {str(room.id) for room in rooms}  # 전수 일치(중복/누락 0)
    assert len(collected) == 5  # 중복 없음(합집합 = 전체)


def test_search_pagination_last_page_cursor_none() -> None:
    """항목 수가 limit의 배수면 마지막 페이지에서도 next_cursor None(offset == total)."""
    rooms = [_avail_room(admin_dong_code="1168010100") for _ in range(4)]
    session = FakeAvailabilitySession(rooms=rooms)
    with _override_session(session):
        first = client.get("/api/v1/rooms/search", params={"limit": 2}).json()
    assert first["next_cursor"] is not None
    with _override_session(session):
        second = client.get(
            "/api/v1/rooms/search",
            params={"limit": 2, "cursor": first["next_cursor"]},
        ).json()
    assert len(second["items"]) == 2
    assert second["next_cursor"] is None  # offset+limit == total → 끝


def test_search_invalid_cursor_returns_422() -> None:
    """손상 offset 커서 → 422 VALIDATION_ERROR(조용한 1페이지 폴백 금지)."""
    with _override_session(FakeAvailabilitySession(rooms=[])):
        resp = client.get("/api/v1/rooms/search", params={"cursor": "!!!invalid"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"
