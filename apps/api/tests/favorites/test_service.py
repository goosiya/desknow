"""favorites 서비스 테스트 (Story 3.7 — AC1·AC2·AC3 멱등성·신선 슬롯·비활성 포함).

DB 불필요 — ``FakeFavoriteSession``으로 멱등 add(중복=기존 반환)·멱등 remove(없는 행=무에러)·
list(비활성 포함·신선 remaining_slots)를 실증한다. Fake 충실도(반복함정 프리플라이트): add는
``IntegrityError`` 제약명 분기를, remove는 매칭 행 삭제를, list는 favorites⨝rooms 신선 집계를
정확히 반영한다. 슬롯 수는 ``now`` 주입으로 결정적 단언한다(라이브 DB·날짜 의존 0).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, time
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import DomainError, ErrorCode
from app.favorites import service
from app.favorites.models import Favorite
from app.rooms.models import BusinessHours, Room
from tests.core.keyset_fake import apply_keyset

# 요일이 명확한 고정 순간: 2026-06-15 00:00 UTC = 09:00 KST 월요일(weekday()==0).
MONDAY_0900_KST = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)


# ── psycopg orig 모방(P2 violated_constraint 실증 — rooms 선례) ──────────────────
class _FakeDiag:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _FakeOrig(Exception):
    def __init__(self, constraint_name: str | None) -> None:
        super().__init__("integrity violation")
        self.diag = _FakeDiag(constraint_name)


class _FavResult:
    """exec 결과 — ``.first()``(첫 행/None)·``.all()``(리스트) 양쪽 지원."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


class FakeFavoriteSession:
    """favorites 서비스용 Fake 세션(add/remove/list — 2.2/3.1 Fake 충실도 선례 계승).

    - ``exec(select(Favorite))`` → ``favorites``(list의 ``.all()`` · 멱등 조회의 ``.first()``).
    - ``exec(select(BusinessHours))``/``exec(select(HolidayException))`` → 슬롯 집계 입력.
    - ``get(Room, pk)`` → 활성/비활성 무관 PK 일치 행(실 ``Session.get`` 모사) 또는 ``None``.
    - ``commit``은 ``raise_on_commit`` 시 제약명 있는 ``IntegrityError``를 던진다(P2 분기 실증).
    """

    def __init__(
        self,
        *,
        rooms: list[Room] | None = None,
        favorites: list[Favorite] | None = None,
        business_hours: list[BusinessHours] | None = None,
        holidays: list[Any] | None = None,
        raise_on_commit: bool = False,
        commit_violation: str | None = None,
    ) -> None:
        self.rooms = rooms or []
        self.favorites = favorites or []
        self.business_hours = business_hours or []
        self.holidays = holidays or []
        self.raise_on_commit = raise_on_commit
        self.commit_violation = commit_violation
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.committed = False
        self.rolled_back = False

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _FavResult:
        entity = None
        descriptions = getattr(statement, "column_descriptions", None)
        if descriptions:
            entity = descriptions[0].get("entity")
        if entity is BusinessHours:
            return _FavResult(self.business_hours)
        if entity is not Favorite and entity is not Room:
            # HolidayException 등 — 슬롯 집계 휴무 입력(빈 리스트 기본).
            return _FavResult(self.holidays)
        # 페이징 select(limit 있음 = list_favorites_page)는 실제 DB와 동일하게 keyset 정렬·커서
        # 필터·절단한다(F 무한스크롤). 멱등 조회(.first())·제거(.all()) 경로는 limit이 없어 무가공.
        if getattr(statement, "_limit", None) is not None:
            return _FavResult(apply_keyset(statement, self.favorites))
        return _FavResult(self.favorites)

    def get(self, model: Any, pk: Any) -> Any:
        for room in self.rooms:
            if getattr(room, "id", None) == pk:
                return room
        return None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    def commit(self) -> None:
        if self.raise_on_commit:
            raise IntegrityError("stmt", {}, _FakeOrig(self.commit_violation))
        self.committed = True

    def refresh(self, obj: Any) -> None:
        pass

    def rollback(self) -> None:
        self.rolled_back = True


def _room(*, is_active: bool = True) -> Room:
    """테스트용 룸(id 자동 — 즐겨찾기 room_id 매칭 키)."""
    return Room(
        provider_id=uuid.uuid4(),
        name="즐겨찾기룸",
        price_per_hour=12000,
        capacity=4,
        room_type="open",
        amenities=["wifi"],
        lat=37.5,
        lng=127.0,
        admin_dong_code="1168010100",
        is_active=is_active,
    )


def _fav(user_id: uuid.UUID, room_id: uuid.UUID) -> Favorite:
    return Favorite(user_id=user_id, room_id=room_id)


def _bh(weekday: int, open_h: int, close_h: int, room_id: uuid.UUID) -> BusinessHours:
    return BusinessHours(
        room_id=room_id, weekday=weekday, open_time=time(open_h, 0), close_time=time(close_h, 0)
    )


# ── add_favorite (AC1 — 멱등·404·선별 변환) ──────────────────────────────────────
def test_add_favorite_creates_and_commits() -> None:
    """룸 존재 + 신규 → Favorite add+commit 후 반환."""
    user_id = uuid.uuid4()
    room = _room()
    session = FakeFavoriteSession(rooms=[room])

    result = service.add_favorite(session, user_id, room.id)

    assert isinstance(result, Favorite)
    assert result.user_id == user_id and result.room_id == room.id
    assert session.committed is True
    assert result in session.added


def test_add_favorite_missing_room_raises_404() -> None:
    """미존재 룸 추가 → 404 ROOM_NOT_FOUND(신규 ErrorCode 0 — 재사용)."""
    session = FakeFavoriteSession(rooms=[])  # get(Room) → None
    with pytest.raises(DomainError) as exc:
        service.add_favorite(session, uuid.uuid4(), uuid.uuid4())
    assert exc.value.code is ErrorCode.ROOM_NOT_FOUND
    assert exc.value.status_code == 404


def test_add_favorite_duplicate_is_idempotent() -> None:
    """uq 위반(이미 즐겨찾기) → rollback 후 기존 행 반환(멱등 — 토글 견고성)."""
    user_id = uuid.uuid4()
    room = _room()
    existing = _fav(user_id, room.id)
    session = FakeFavoriteSession(
        rooms=[room],
        favorites=[existing],
        raise_on_commit=True,
        commit_violation="uq_favorites_user_id_room_id",
    )

    result = service.add_favorite(session, user_id, room.id)

    assert result is existing  # 기존 행 그대로 반환
    assert session.rolled_back is True


def test_add_favorite_unknown_constraint_reraises() -> None:
    """무관한 제약 위반은 오변환 없이 re-raise(과대캐치 금지 — P2)."""
    room = _room()
    session = FakeFavoriteSession(
        rooms=[room],
        raise_on_commit=True,
        commit_violation="some_other_constraint",
    )
    with pytest.raises(IntegrityError):
        service.add_favorite(session, uuid.uuid4(), room.id)
    assert session.rolled_back is True


# ── remove_favorite (AC1 — 멱등) ────────────────────────────────────────────────
def test_remove_favorite_deletes_matching_row() -> None:
    """매칭 행 삭제 후 commit."""
    user_id = uuid.uuid4()
    room = _room()
    existing = _fav(user_id, room.id)
    session = FakeFavoriteSession(favorites=[existing])

    service.remove_favorite(session, user_id, room.id)

    assert existing in session.deleted
    assert session.committed is True


def test_remove_favorite_no_row_is_idempotent() -> None:
    """없는 행 삭제도 에러 없이 통과(멱등) — delete 0건·commit O."""
    session = FakeFavoriteSession(favorites=[])

    service.remove_favorite(session, uuid.uuid4(), uuid.uuid4())

    assert session.deleted == []
    assert session.committed is True


# ── list_favorites (AC2·AC3 — 비활성 포함·신선 슬롯·활성 플래그) ──────────────────
def test_list_favorites_includes_inactive_with_flag_and_fresh_slots() -> None:
    """비활성 룸도 포함(AC3) + 활성 룸은 신선 remaining_slots, 비활성은 0."""
    user_id = uuid.uuid4()
    active = _room(is_active=True)
    inactive = _room(is_active=False)
    favs = [_fav(user_id, active.id), _fav(user_id, inactive.id)]
    # 활성 룸: 월요일 09~22시 → 09:00 KST(=now) 이후 13슬롯. 비활성 룸은 슬롯 집계 자체를 건너뜀.
    hours = [_bh(0, 9, 22, active.id)]
    session = FakeFavoriteSession(
        rooms=[active, inactive], favorites=favs, business_hours=hours
    )

    items = service.list_favorites(session, user_id, now=MONDAY_0900_KST)

    assert len(items) == 2
    by_room = {item.room_id: item for item in items}
    assert by_room[active.id].is_active is True
    assert by_room[active.id].remaining_slots == 13  # 09,10,...,21시 시작 = 13개
    assert by_room[inactive.id].is_active is False
    assert by_room[inactive.id].remaining_slots == 0  # 비활성 룸은 슬롯 0(AC3)


def test_list_favorites_empty_returns_empty_list() -> None:
    """즐겨찾기 없음 → 빈 리스트(정상)."""
    assert service.list_favorites(FakeFavoriteSession(), uuid.uuid4()) == []


def test_build_favorite_item_shape() -> None:
    """단일 항목 빌드 — favorited_at=created_at, amenities 복사, 활성여부 노출."""
    user_id = uuid.uuid4()
    room = _room()
    fav = _fav(user_id, room.id)
    session = FakeFavoriteSession(rooms=[room], favorites=[fav])

    item = service.build_favorite_item(session, fav, now=MONDAY_0900_KST)

    assert item.room_id == room.id
    assert item.name == room.name
    assert item.price_per_hour == room.price_per_hour
    assert item.amenities == ["wifi"]
    assert item.is_active is True
    assert item.favorited_at == fav.created_at
