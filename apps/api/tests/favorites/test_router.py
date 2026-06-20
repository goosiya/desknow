"""favorites 라우터 통합 테스트 (Story 3.7 — AC1·AC2·AC3·AC4·AC5 인증 게이팅).

**DB 불필요** — ``app.dependency_overrides[get_session]``로 세션을 Fake로 교체하고,
``TestClient(app)``(모듈 레벨, lifespan 미실행 — 1.4 불변식)로 엔드포인트를 검증한다. 실 booker
access 토큰으로 인증(로그인 201/204/200·무토큰 401)을, ``get_current_principal``(역할 무관)로
provider도 통과함을 실증한다(``require_role`` 아님 — 403 회피).
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.core.db import get_session
from app.core.security import create_access_token
from app.main import app
from tests.favorites.test_service import FakeFavoriteSession, _fav, _room

client = TestClient(app)

_FAVORITE_ITEM_KEYS = {
    "room_id",
    "name",
    "price_per_hour",
    "room_type",
    "amenities",
    "remaining_slots",
    "is_active",
    "favorited_at",
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


def _booker_token() -> str:
    return create_access_token(uuid.uuid4(), "booker")


def _provider_token() -> str:
    return create_access_token(uuid.uuid4(), "provider")


# ── POST /api/v1/favorites (추가 — AC1·AC4·AC5) ──────────────────────────────────
def test_add_favorite_returns_201_item(auth_env: None) -> None:
    """로그인 + 룸 존재 → 201 + FavoriteRoomItem(is_active·remaining_slots·favorited_at Z)."""
    room = _room()  # 활성·영업시간 없음 → remaining_slots 0(날짜 무의존)
    with _override_session(FakeFavoriteSession(rooms=[room])):
        resp = client.post(
            "/api/v1/favorites",
            json={"room_id": str(room.id)},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == _FAVORITE_ITEM_KEYS
    assert body["room_id"] == str(room.id)
    assert body["is_active"] is True
    assert body["remaining_slots"] == 0
    assert body["favorited_at"].endswith("Z")


def test_add_favorite_provider_allowed(auth_env: None) -> None:
    """provider 토큰도 통과(get_current_principal 역할 무관 — 403 회피, AC4 경계)."""
    room = _room()
    with _override_session(FakeFavoriteSession(rooms=[room])):
        resp = client.post(
            "/api/v1/favorites",
            json={"room_id": str(room.id)},
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )
    assert resp.status_code == 201, resp.text


def test_add_favorite_duplicate_returns_201_idempotent(auth_env: None) -> None:
    """이미 즐겨찾기(uq 위반) → 멱등 201(기존 행 기준)."""
    user_id = uuid.uuid4()
    room = _room()
    existing = _fav(user_id, room.id)
    session = FakeFavoriteSession(
        rooms=[room],
        favorites=[existing],
        raise_on_commit=True,
        commit_violation="uq_favorites_user_id_room_id",
    )
    with _override_session(session):
        resp = client.post(
            "/api/v1/favorites",
            json={"room_id": str(room.id)},
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["room_id"] == str(room.id)


def test_add_favorite_unknown_room_returns_404(auth_env: None) -> None:
    """미존재 룸 → 404 ROOM_NOT_FOUND."""
    with _override_session(FakeFavoriteSession(rooms=[])):
        resp = client.post(
            "/api/v1/favorites",
            json={"room_id": str(uuid.uuid4())},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ROOM_NOT_FOUND"


def test_add_favorite_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401 UNAUTHENTICATED(AC5 인증 게이팅)."""
    with _override_session(FakeFavoriteSession(rooms=[])):
        resp = client.post("/api/v1/favorites", json={"room_id": str(uuid.uuid4())})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── DELETE /api/v1/favorites/{room_id} (제거 — AC1·AC5) ──────────────────────────
def test_remove_favorite_returns_204(auth_env: None) -> None:
    """로그인 + 매칭 행 → 204."""
    user_id = uuid.uuid4()
    room = _room()
    session = FakeFavoriteSession(favorites=[_fav(user_id, room.id)])
    with _override_session(session):
        resp = client.delete(
            f"/api/v1/favorites/{room.id}",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 204, resp.text


def test_remove_favorite_no_row_returns_204(auth_env: None) -> None:
    """없는 행 제거도 204(멱등)."""
    with _override_session(FakeFavoriteSession(favorites=[])):
        resp = client.delete(
            f"/api/v1/favorites/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 204, resp.text


def test_remove_favorite_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401."""
    with _override_session(FakeFavoriteSession(favorites=[])):
        resp = client.delete(f"/api/v1/favorites/{uuid.uuid4()}")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── GET /api/v1/favorites (목록 — AC2·AC3·AC5) ───────────────────────────────────
def test_list_favorites_returns_items_with_active_flag(auth_env: None) -> None:
    """로그인 → 200 + 비활성 포함 목록(is_active 플래그·favorited_at Z)."""
    user_id = uuid.uuid4()
    active = _room(is_active=True)
    inactive = _room(is_active=False)
    favs = [_fav(user_id, active.id), _fav(user_id, inactive.id)]
    session = FakeFavoriteSession(rooms=[active, inactive], favorites=favs)
    with _override_session(session):
        resp = client.get(
            "/api/v1/favorites",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()["items"]
    assert len(body) == 2
    for item in body:
        assert set(item) == _FAVORITE_ITEM_KEYS
        assert item["favorited_at"].endswith("Z")
    actives = {item["room_id"]: item["is_active"] for item in body}
    assert actives[str(active.id)] is True
    assert actives[str(inactive.id)] is False  # AC3 — 비활성 룸도 포함·플래그 노출


def test_list_favorites_empty_returns_200(auth_env: None) -> None:
    """즐겨찾기 없음 → 200 + 빈 리스트."""
    with _override_session(FakeFavoriteSession(favorites=[])):
        resp = client.get(
            "/api/v1/favorites",
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["next_cursor"] is None


def test_list_favorites_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401."""
    with _override_session(FakeFavoriteSession(favorites=[])):
        resp = client.get("/api/v1/favorites")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ═══════════════════════════════════════════════════════════════════════════════════
# 커서 페이징 (F — 즐겨찾기 무한스크롤): keyset 페이지 경계·전수 일치·손상 커서 422
# ═══════════════════════════════════════════════════════════════════════════════════


def _seed_favorites(user_id: uuid.UUID, count: int):
    """서로 다른 활성 룸을 가리키는 즐겨찾기 count건을 created_at 내림차순으로 시드한다.

    각 룸이 달라야 응답 item(``room_id`` 키)으로 페이지 항목을 식별·전수 비교할 수 있다.
    created_at은 1시간 간격으로 분리해 keyset (created_at desc, id desc) 경계를 결정적으로 만든다.

    Returns:
        ``(rooms, favorites)`` — favorites는 최신(인덱스 0)→과거 순.
    """
    base = datetime(2026, 6, 17, tzinfo=UTC)
    rooms = []
    favs = []
    for i in range(count):
        room = _room(is_active=True)
        fav = _fav(user_id, room.id)
        fav.created_at = base - timedelta(hours=i)  # i=0이 가장 최근
        rooms.append(room)
        favs.append(fav)
    return rooms, favs


def test_list_favorites_pagination_walks_all_pages(auth_env: None) -> None:
    """limit=2로 5건 페이징 → 첫 페이지 2건+next_cursor, 전 페이지 합집합이 전체와 순서까지 일치."""
    user_id = uuid.uuid4()
    rooms, favs = _seed_favorites(user_id, 5)
    session = FakeFavoriteSession(rooms=rooms, favorites=list(favs))
    token = create_access_token(user_id, "booker")

    def _get(cursor: str | None):
        params = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        with _override_session(session):
            return client.get(
                "/api/v1/favorites",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )

    first = _get(None).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    # 전 페이지 순회 — 중복/누락 0, favorited_at desc(=시드 순서)와 정확히 일치.
    collected: list[dict] = []
    cursor: str | None = None
    while True:
        body = _get(cursor).json()
        collected.extend(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    room_ids = [item["room_id"] for item in collected]
    assert room_ids == [str(room.id) for room in rooms]  # 최신순 전수 일치(순서 포함)
    assert len(room_ids) == len(set(room_ids)) == 5  # 중복 없음


def test_list_favorites_pagination_last_page_cursor_none(auth_env: None) -> None:
    """항목 수가 limit의 배수면 마지막 페이지에서도 next_cursor None."""
    user_id = uuid.uuid4()
    rooms, favs = _seed_favorites(user_id, 4)  # limit=2 → 딱 2페이지
    session = FakeFavoriteSession(rooms=rooms, favorites=list(favs))
    token = create_access_token(user_id, "booker")
    with _override_session(session):
        first = client.get(
            "/api/v1/favorites",
            params={"limit": 2},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    assert first["next_cursor"] is not None
    with _override_session(session):
        second = client.get(
            "/api/v1/favorites",
            params={"limit": 2, "cursor": first["next_cursor"]},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    assert len(second["items"]) == 2
    assert second["next_cursor"] is None


def test_list_favorites_invalid_cursor_returns_422(auth_env: None) -> None:
    """손상 커서 → 422 VALIDATION_ERROR(조용한 1페이지 폴백 금지)."""
    user_id = uuid.uuid4()
    session = FakeFavoriteSession(favorites=[])
    with _override_session(session):
        resp = client.get(
            "/api/v1/favorites",
            params={"cursor": "!!!invalid"},
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"
