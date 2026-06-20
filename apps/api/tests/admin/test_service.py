"""admin 서비스 테스트 (Story 8.1, AC4 — list_accounts).

DB 불필요 — **Fake 세션이 쿼리를 충실히 해석**한다(인자 무시 자기충족 Fake 금지, 회고 A2):
count(entity=None)는 role 필터를 적용한 건수를, list(entity=User)는 role 필터 +
``(created_at desc, id)`` 정렬 + offset/limit 슬라이스를 돌려준다. 이로써 admin 제외·정렬
보조키·페이지네이션을 라이브 DB 없이 단언한다.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.admin.service import (
    deactivate_account,
    force_cancel_reservation,
    list_accounts,
    list_reservations,
)
from app.auth.models import User
from app.core.errors import DomainError, ErrorCode
from app.notifications.models import Notification, NotificationType
from app.reservations.models import Reservation, ReservationStatus
from app.rooms.models import Room
from tests.reservations.test_service import (
    _apply_conditional_terminal_update,
    _is_update,
)

# 보조 정렬키(id) 실증용 고정 UUID — str(LOW) < str(HIGH)(PG uuid 정렬 = 정규문자열 사전순).
ID_LOW = uuid.UUID("00000000-0000-0000-0000-000000000001")
ID_HIGH = uuid.UUID("00000000-0000-0000-0000-000000000002")


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def one(self) -> Any:
        return self._value  # select(func.count()) — 스칼라 집계

    def all(self) -> list[Any]:
        return list(self._value)


class FakeAdminSession:
    """list_accounts 읽기 전용 Fake — 컴파일된 쿼리를 해석해 필터/정렬/슬라이스를 재현한다.

    - count 쿼리(``entity is None``): role 필터 적용 건수를 ``.one()``으로.
    - list 쿼리(``entity is User``): role 필터 + ORDER BY 존재 시 ``(created_at desc, id asc)``
      안정 정렬 + ``offset``/``limit`` 슬라이스를 ``.all()``로.
    role 필터는 컴파일된 ``role_1`` 파라미터로 재현한다(서비스가 where를 빼면 필터 미적용 →
    admin 포함되어 테스트가 깨짐). 읽기 전용이라 add/delete/commit을 노출하지 않는다.
    """

    def __init__(self, users: list[User]) -> None:
        self.users = list(users)
        self.exec_entities: list[Any] = []

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        descriptions = getattr(statement, "column_descriptions", None)
        entity = descriptions[0].get("entity") if descriptions else None
        self.exec_entities.append(entity)

        excluded = statement.compile().params.get("role_1")
        filtered = [u for u in self.users if excluded is None or u.role != excluded]

        if entity is None:  # select(func.count()) — 같은 where로 집계
            return _FakeResult(len(filtered))

        ordered = filtered
        if "ORDER BY" in str(statement):
            # 안정 정렬로 (created_at desc, id asc) 재현 — id asc 먼저, created_at desc 나중.
            ordered = sorted(filtered, key=lambda u: str(u.id))
            ordered = sorted(ordered, key=lambda u: u.created_at, reverse=True)

        offset = (
            statement._offset_clause.value if statement._offset_clause is not None else 0
        )
        limit = (
            statement._limit_clause.value if statement._limit_clause is not None else None
        )
        sliced = ordered[offset : offset + limit] if limit is not None else ordered[offset:]
        return _FakeResult(sliced)


def _user(
    *,
    role: str = "booker",
    created_at: datetime,
    user_id: uuid.UUID | None = None,
    is_active: bool = True,
    email: str | None = None,
) -> User:
    uid = user_id if user_id is not None else uuid.uuid4()
    return User(
        id=uid,
        email=email if email is not None else f"{uid}@example.com",
        password_hash="$argon2id$x",
        role=role,
        is_active=is_active,
        created_at=created_at,
    )


def _room(*, provider_id: uuid.UUID, is_active: bool = True) -> Room:
    """캐스케이드 검증용 최소 Room. provider_id·is_active만 의미를 가진다."""
    return Room(
        id=uuid.uuid4(),
        provider_id=provider_id,
        name="테스트룸",
        price_per_hour=10000,
        capacity=1,
        room_type="open",
        lat=37.5,
        lng=127.0,
        admin_dong_code="1111010100",
        is_active=is_active,
        created_at=datetime(2026, 6, 18, tzinfo=UTC),
    )


class _FakeWriteResult:
    """조건부 UPDATE 결과 — service가 ``result.rowcount``(멱등 판정)만 읽는다."""

    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class FakeDeactivateSession:
    """deactivate_account 쓰기 Fake — 컴파일된 UPDATE를 충실히 해석한다(자기충족 Fake 금지).

    - ``get(User, pk)``: 주입한 사용자(또는 None=미존재).
    - ``exec(update(...))``: 대상 테이블(users/rooms)을 식별하고 ``WHERE ... AND is_active=true``
      조건부 의미를 재현해 **이미 비활성 행은 변경하지 않으며**(멱등) 변경 건수를 ``rowcount``로
      돌려준다. SET 값은 statement에서 읽어 적용한다(하드코딩 아님). provider_id로 룸을 격리하므로
      타 provider 룸은 불변이다.
    - ``commit``/``refresh``: in-memory 객체가 이미 갱신을 반영하므로 refresh는 no-op.
    - ``executed_tables``: 실행된 UPDATE의 테이블명 기록 — reservations/슬롯 미터치(AC2) 단언용.
    """

    def __init__(self, users: list[User], rooms: list[Room] | None = None) -> None:
        self.users = {u.id: u for u in users}
        self.rooms = list(rooms or [])
        self.committed = False
        self.executed_tables: list[str] = []

    def get(self, model: Any, pk: uuid.UUID) -> Any:
        if model is User:
            return self.users.get(pk)
        return None

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeWriteResult:
        table = statement.table.name
        self.executed_tables.append(table)
        params = statement.compile().params
        new_active = params["is_active"]  # SET 값(statement에서 읽음 — 하드코딩 아님)
        # WHERE의 대상 id(users=id / rooms=provider_id) — 유일한 UUID 파라미터.
        target_id = next(v for v in params.values() if isinstance(v, uuid.UUID))

        changed = 0
        if table == "users":
            u = self.users.get(target_id)
            if u is not None and u.is_active is True:  # 조건부(AND is_active=true) 재현
                u.is_active = new_active
                changed = 1
        elif table == "rooms":
            for r in self.rooms:  # WHERE provider_id로 격리 — 타 provider 룸 불변
                if r.provider_id == target_id and r.is_active is True:
                    r.is_active = new_active
                    changed += 1
        return _FakeWriteResult(changed)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, obj: Any) -> None:
        return None  # in-memory 객체가 이미 갱신 반영


# ── deactivate_account (Story 8.2, AC1·2·4) ───────────────────────────────────
def test_deactivate_booker_no_cascade() -> None:
    """ⓐ booker 비활성 → User.is_active=False, 룸 캐스케이드 없음, 반환 item is_active=False."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    session = FakeDeactivateSession([booker])

    item = deactivate_account(session, account_id=booker.id)

    assert booker.is_active is False
    assert item.is_active is False and item.id == booker.id
    assert session.committed is True
    assert "rooms" not in session.executed_tables  # booker는 룸 미소유 → 캐스케이드 없음


def test_deactivate_provider_cascades_rooms() -> None:
    """ⓑ provider 비활성 → provider AND 그의 룸(들) is_active=False. 타 provider 룸은 불변."""
    provider = _user(role="provider", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    other = _user(role="provider", created_at=datetime(2026, 6, 16, tzinfo=UTC))
    my_room1 = _room(provider_id=provider.id)
    my_room2 = _room(provider_id=provider.id)  # uq는 1개이나 0..n 격리 안전 검증
    other_room = _room(provider_id=other.id)
    session = FakeDeactivateSession([provider, other], [my_room1, my_room2, other_room])

    item = deactivate_account(session, account_id=provider.id)

    assert provider.is_active is False and item.is_active is False
    assert my_room1.is_active is False and my_room2.is_active is False  # 캐스케이드
    assert other_room.is_active is True  # 타 provider 룸 격리(WHERE provider_id)


def test_deactivate_is_idempotent() -> None:
    """ⓒ 이미 비활성 계정 재호출 → 추가 쓰기 0(rowcount 0 경로), 예외 없이 현재 상태 반환."""
    booker = _user(
        role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC), is_active=False
    )
    session = FakeDeactivateSession([booker])

    item = deactivate_account(session, account_id=booker.id)

    assert item.is_active is False  # 멱등 — 그대로 비활성
    assert booker.is_active is False  # 변경 없음(이미 비활성)


def test_deactivate_admin_target_rejected() -> None:
    """ⓓ admin 대상(자기/타admin) → ACCOUNT_NOT_FOUND(존재 누설·비활성 금지)."""
    admin = _user(role="admin", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    session = FakeDeactivateSession([admin])

    with pytest.raises(DomainError) as exc:
        deactivate_account(session, account_id=admin.id)
    assert exc.value.code == ErrorCode.ACCOUNT_NOT_FOUND
    assert admin.is_active is True  # 비활성되지 않음
    assert session.committed is False


def test_deactivate_missing_target_rejected() -> None:
    """ⓔ 미존재 account_id → ACCOUNT_NOT_FOUND."""
    session = FakeDeactivateSession([])

    with pytest.raises(DomainError) as exc:
        deactivate_account(session, account_id=uuid.uuid4())
    assert exc.value.code == ErrorCode.ACCOUNT_NOT_FOUND


def test_deactivate_never_touches_reservations() -> None:
    """ⓕ provider 비활성은 users/rooms만 UPDATE — reservations/슬롯은 절대 건드리지 않는다(AC2)."""
    provider = _user(role="provider", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    room = _room(provider_id=provider.id)
    session = FakeDeactivateSession([provider], [room])

    deactivate_account(session, account_id=provider.id)

    # 기존 확정 예약 유지(AC2 핵심) — 예약/슬롯 테이블 쓰기가 전혀 없어야 한다.
    assert set(session.executed_tables) == {"users", "rooms"}
    assert "reservations" not in session.executed_tables
    assert "reservation_slots" not in session.executed_tables


def test_list_accounts_excludes_admin() -> None:
    """admin 계정은 목록·total에서 제외된다(booker/provider만 — 시드 운영자 노출 방지)."""
    users = [
        _user(role="admin", created_at=datetime(2026, 6, 18, tzinfo=UTC)),
        _user(role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC)),
        _user(role="provider", created_at=datetime(2026, 6, 16, tzinfo=UTC)),
    ]
    result = list_accounts(FakeAdminSession(users), page=1, page_size=20)

    assert result.total == 2  # admin 제외
    assert {item.role for item in result.items} == {"booker", "provider"}
    assert all(item.role != "admin" for item in result.items)


def test_list_accounts_orders_created_at_desc_then_id() -> None:
    """정렬은 created_at 내림차순 + id 오름차순(동률 created_at의 비결정 정렬을 보조키로 막음)."""
    same = datetime(2026, 6, 17, tzinfo=UTC)
    newer = datetime(2026, 6, 18, tzinfo=UTC)
    # 입력 순서를 일부러 뒤섞어(id_high 먼저) 삽입 순서가 아니라 정렬이 작동함을 실증.
    users = [
        _user(role="booker", created_at=same, user_id=ID_HIGH),
        _user(role="booker", created_at=newer),  # 가장 최신 → 맨 앞
        _user(role="provider", created_at=same, user_id=ID_LOW),
    ]
    result = list_accounts(FakeAdminSession(users), page=1, page_size=20)

    ids = [item.id for item in result.items]
    # 최신(newer)이 먼저, 그다음 동률 두 건은 id 오름차순(LOW → HIGH).
    assert ids[0] not in (ID_LOW, ID_HIGH)  # newer(랜덤 id)가 선두
    assert ids[1] == ID_LOW and ids[2] == ID_HIGH  # 보조키 asc 실증


def test_list_accounts_paginates() -> None:
    """page/page_size에 따른 슬라이스가 정확하고 total은 전체(페이지 무관)를 센다."""
    # created_at 내림차순이 예측 가능하도록 분 단위로 차등(분이 클수록 최신 → 앞).
    base = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)
    users = [
        _user(role="booker", created_at=base.replace(minute=m)) for m in range(5)
    ]
    page1 = list_accounts(FakeAdminSession(users), page=1, page_size=2)
    page2 = list_accounts(FakeAdminSession(users), page=2, page_size=2)
    page3 = list_accounts(FakeAdminSession(users), page=3, page_size=2)

    assert page1.total == 5 and page2.total == 5  # total은 페이지 무관 전체
    assert len(page1.items) == 2 and len(page2.items) == 2 and len(page3.items) == 1
    # 최신(minute=4)이 page1 선두, page3엔 가장 오래된(minute=0) 1건.
    assert page1.items[0].created_at == base.replace(minute=4)
    assert page3.items[0].created_at == base.replace(minute=0)
    # 페이지 간 중복 없음(슬라이스 경계 정확).
    seen = {i.id for i in page1.items} | {i.id for i in page2.items} | {i.id for i in page3.items}
    assert len(seen) == 5


def test_list_accounts_serializes_created_at_with_z() -> None:
    """created_at은 ...Z(UTC ISO-8601)로 직렬화된다(UserPublic 동일 규약)·password_hash 부재."""
    users = [_user(role="booker", created_at=datetime(2026, 6, 18, 5, 0, tzinfo=UTC))]
    result = list_accounts(FakeAdminSession(users), page=1, page_size=20)

    dumped = result.items[0].model_dump()
    assert "password_hash" not in dumped
    assert result.items[0].model_dump(mode="json")["created_at"].endswith("Z")


# ── 예약 임의취소 + 확정 예약 목록 (Story 8.3) ─────────────────────────────────
def _reservation(
    *,
    booker_id: uuid.UUID,
    room_id: uuid.UUID,
    status: ReservationStatus = ReservationStatus.CONFIRMED,
    created_at: datetime | None = None,
    slot_starts: list[str] | None = None,
    reservation_id: uuid.UUID | None = None,
) -> Reservation:
    return Reservation(
        id=reservation_id if reservation_id is not None else uuid.uuid4(),
        booker_id=booker_id,
        room_id=room_id,
        status=status,
        slot_starts=slot_starts if slot_starts is not None else ["2099-01-05T05:00:00Z"],
        created_at=created_at if created_at is not None else datetime(2026, 6, 18, tzinfo=UTC),
    )


class FakeForceCancelSession:
    """force_cancel_reservation Fake — get(Reservation)+전이 프리미티브(UPDATE/DELETE/통지)+합성.

    admin.service가 ``get(Reservation)`` → reservations 프리미티브(``exec(update)`` 조건부 종료 +
    ``exec(delete)`` 슬롯 재활성 + ``add(Notification)`` + ``commit``/``refresh``) → ``get(Room)``/
    ``get(User)`` 합성을 호출한다. 조건부 UPDATE는 reservations 테스트의 공유 헬퍼로 충실히 해석한다
    (자기충족 Fake 금지). ``notifications`` 프로퍼티로 통지 staging을 단언한다(spy).
    """

    def __init__(
        self,
        *,
        reservation: Reservation | None,
        room: Room | None = None,
        booker: User | None = None,
    ) -> None:
        self.stored = reservation
        self.room = room
        self.booker = booker
        self.added: list[Any] = []
        self.committed = 0
        self.exec_calls: list[Any] = []

    def get(self, model: Any, pk: uuid.UUID) -> Any:
        if model is Reservation and self.stored is not None and self.stored.id == pk:
            return self.stored
        if model is Room and self.room is not None and self.room.id == pk:
            return self.room
        if model is User and self.booker is not None and self.booker.id == pk:
            return self.booker
        return None

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        self.exec_calls.append(statement)
        if _is_update(statement):
            return _apply_conditional_terminal_update(
                statement, [self.stored] if self.stored is not None else []
            )
        return None  # _release_slots DELETE(반환값 무시)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.committed += 1

    def refresh(self, obj: Any) -> None:
        return None  # Fake는 in-memory flip이 net 효과 반영

    @property
    def notifications(self) -> list[Notification]:
        return [o for o in self.added if isinstance(o, Notification)]


def test_force_cancel_reservation_cancels_and_notifies() -> None:
    """ⓐ confirmed force-cancel → AdminReservationItem.status='cancelled'·통지 생성·합성 정확."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    room = _room(provider_id=uuid.uuid4())
    reservation = _reservation(booker_id=booker.id, room_id=room.id)
    session = FakeForceCancelSession(reservation=reservation, room=room, booker=booker)

    item = force_cancel_reservation(session, reservation_id=reservation.id)

    assert item.status == "cancelled"  # 전이 적용(reservations 프리미티브 위임)
    assert item.id == reservation.id
    assert item.room_name == room.name  # Room PK 합성
    assert item.booker_email == booker.email  # 운영자라 실 이메일(익명 라벨 아님)
    assert item.booker_id == booker.id
    assert session.committed == 1  # 단일 트랜잭션 commit(status flip + 슬롯 DELETE + 통지)
    assert len(session.notifications) == 1  # status_change/cancelled 통지 1건
    assert session.notifications[0].reason == "cancelled"
    assert session.notifications[0].type == str(NotificationType.STATUS_CHANGE)
    # password_hash는 스키마 부재 — 절대 노출 안 됨.
    assert "password_hash" not in item.model_dump()


def test_force_cancel_reservation_missing_raises_not_found() -> None:
    """ⓑ 미존재 reservation_id → DomainError(RESERVATION_NOT_FOUND·누설 방지)."""
    session = FakeForceCancelSession(reservation=None)

    with pytest.raises(DomainError) as exc:
        force_cancel_reservation(session, reservation_id=uuid.uuid4())
    assert exc.value.code == ErrorCode.RESERVATION_NOT_FOUND
    assert session.committed == 0


@pytest.mark.parametrize(
    "terminal_status",
    [ReservationStatus.CANCELLED, ReservationStatus.REJECTED],
)
def test_force_cancel_reservation_already_terminal_is_idempotent(
    terminal_status: ReservationStatus,
) -> None:
    """ⓒ 이미 종료 상태 → 멱등 no-op(현재 상태 반환·통지 0·commit 0)."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    room = _room(provider_id=uuid.uuid4())
    reservation = _reservation(
        booker_id=booker.id, room_id=room.id, status=terminal_status
    )
    session = FakeForceCancelSession(reservation=reservation, room=room, booker=booker)

    item = force_cancel_reservation(session, reservation_id=reservation.id)

    assert item.status == str(terminal_status)  # 현재 상태 그대로(전이 무시)
    assert session.committed == 0  # 멱등 no-op(쓰기 0)
    assert session.notifications == []  # 통지 0(winner 아님)


class FakeReservationListSession:
    """list_reservations Fake — 컴파일된 쿼리를 해석해 confirmed 필터/정렬/슬라이스 + 배치 합성.

    - count(``entity is None``): confirmed 건수를 ``.one()``으로.
    - Reservation 쿼리: confirmed 필터 + ``(created_at desc, id)`` 안정 정렬 + offset/limit.
    - Room/User 쿼리: ``IN`` 파라미터의 UUID로 필터해 반환(자기충족 Fake 금지 — 실제 in-set만).
    ``exec_entities``로 N+1 회피(Room/User 각 1쿼리)를 단언한다.
    """

    def __init__(
        self,
        reservations: list[Reservation],
        rooms: list[Room],
        users: list[User],
    ) -> None:
        self.reservations = list(reservations)
        self.rooms = {r.id: r for r in rooms}
        self.users = {u.id: u for u in users}
        self.exec_entities: list[Any] = []

    @staticmethod
    def _in_uuids(statement: Any) -> set[uuid.UUID]:
        # SQLAlchemy ``.in_()``은 expanding bindparam이라 값이 단일 UUID가 아니라 리스트로 올 수
        # 있다 → UUID·UUID 컨테이너 둘 다 평탄화해 in-set을 복원한다(충실 해석).
        found: set[uuid.UUID] = set()
        for value in statement.compile().params.values():
            if isinstance(value, uuid.UUID):
                found.add(value)
            elif isinstance(value, (list, tuple, set)):
                found.update(v for v in value if isinstance(v, uuid.UUID))
        return found

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        descriptions = getattr(statement, "column_descriptions", None)
        entity = descriptions[0].get("entity") if descriptions else None
        self.exec_entities.append(entity)

        confirmed = [
            r for r in self.reservations if r.status == ReservationStatus.CONFIRMED
        ]

        if entity is None:  # select(func.count()) — confirmed 집계
            return _FakeResult(len(confirmed))

        if entity is Reservation:
            ordered = confirmed
            if "ORDER BY" in str(statement):
                ordered = sorted(confirmed, key=lambda r: str(r.id))
                ordered = sorted(ordered, key=lambda r: r.created_at, reverse=True)
            offset = (
                statement._offset_clause.value
                if statement._offset_clause is not None
                else 0
            )
            limit = (
                statement._limit_clause.value
                if statement._limit_clause is not None
                else None
            )
            sliced = (
                ordered[offset : offset + limit]
                if limit is not None
                else ordered[offset:]
            )
            return _FakeResult(sliced)

        if entity is Room:
            ids = self._in_uuids(statement)
            return _FakeResult([self.rooms[i] for i in ids if i in self.rooms])

        if entity is User:
            ids = self._in_uuids(statement)
            return _FakeResult([self.users[i] for i in ids if i in self.users])

        return _FakeResult([])


def test_list_reservations_confirmed_only_and_synthesizes() -> None:
    """ⓓ confirmed-only 필터·실 이메일/룸 이름 합성·N+1 0(Room/User 각 1쿼리)·password_hash 부재."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    room = _room(provider_id=uuid.uuid4())
    confirmed1 = _reservation(booker_id=booker.id, room_id=room.id)
    confirmed2 = _reservation(booker_id=booker.id, room_id=room.id)
    cancelled = _reservation(
        booker_id=booker.id, room_id=room.id, status=ReservationStatus.CANCELLED
    )
    rejected = _reservation(
        booker_id=booker.id, room_id=room.id, status=ReservationStatus.REJECTED
    )
    session = FakeReservationListSession(
        [confirmed1, confirmed2, cancelled, rejected], [room], [booker]
    )

    result = list_reservations(session, page=1, page_size=20)

    assert result.total == 2  # confirmed만(cancelled/rejected 제외)
    assert len(result.items) == 2
    assert all(item.status == "confirmed" for item in result.items)
    assert all(item.room_name == room.name for item in result.items)
    assert all(item.booker_email == booker.email for item in result.items)  # 실 이메일
    # N+1 회피 — Room/User 배치 조회는 각 1쿼리(행별 재조회 아님).
    assert sum(1 for e in session.exec_entities if e is Room) == 1
    assert sum(1 for e in session.exec_entities if e is User) == 1
    assert "password_hash" not in result.items[0].model_dump()


def test_list_reservations_orders_created_at_desc_then_id() -> None:
    """confirmed 목록도 created_at desc + id asc 안정 정렬(8.2 list_accounts 선반영 미러)."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    room = _room(provider_id=uuid.uuid4())
    same = datetime(2026, 6, 17, tzinfo=UTC)
    newer = datetime(2026, 6, 18, tzinfo=UTC)
    r_high = _reservation(
        booker_id=booker.id, room_id=room.id, created_at=same, reservation_id=ID_HIGH
    )
    r_newer = _reservation(booker_id=booker.id, room_id=room.id, created_at=newer)
    r_low = _reservation(
        booker_id=booker.id, room_id=room.id, created_at=same, reservation_id=ID_LOW
    )
    session = FakeReservationListSession([r_high, r_newer, r_low], [room], [booker])

    result = list_reservations(session, page=1, page_size=20)

    ids = [item.id for item in result.items]
    assert ids[0] not in (ID_LOW, ID_HIGH)  # newer(랜덤 id)가 선두
    assert ids[1] == ID_LOW and ids[2] == ID_HIGH  # 동률 created_at은 id 오름차순


def test_list_reservations_paginates() -> None:
    """page/page_size 슬라이스 정확·total은 confirmed 전체(페이지 무관)."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    room = _room(provider_id=uuid.uuid4())
    base = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)
    reservations = [
        _reservation(
            booker_id=booker.id, room_id=room.id, created_at=base.replace(minute=m)
        )
        for m in range(5)
    ]
    page1 = list_reservations(
        FakeReservationListSession(reservations, [room], [booker]), page=1, page_size=2
    )
    page3 = list_reservations(
        FakeReservationListSession(reservations, [room], [booker]), page=3, page_size=2
    )

    assert page1.total == 5 and page3.total == 5  # total은 페이지 무관 전체
    assert len(page1.items) == 2 and len(page3.items) == 1
    assert page1.items[0].created_at == base.replace(minute=4)  # 최신 선두
    assert page3.items[0].created_at == base.replace(minute=0)  # 가장 오래된


def test_list_reservations_empty_skips_batch_queries() -> None:
    """confirmed 0건이면 빈 목록·룸/유저 배치 조회를 발행하지 않는다(불필요한 IN () 회피)."""
    booker = _user(role="booker", created_at=datetime(2026, 6, 17, tzinfo=UTC))
    room = _room(provider_id=uuid.uuid4())
    cancelled = _reservation(
        booker_id=booker.id, room_id=room.id, status=ReservationStatus.CANCELLED
    )
    session = FakeReservationListSession([cancelled], [room], [booker])

    result = list_reservations(session, page=1, page_size=20)

    assert result.total == 0 and result.items == []
    # 빈 행 집합 → Room/User 쿼리 미발행(count + Reservation 목록 쿼리만).
    assert Room not in session.exec_entities
    assert User not in session.exec_entities


# ── 인제스트 트리거 (Story 8.4, AC1·3) ─────────────────────────────────────────
def test_trigger_ingest_maps_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """trigger_ingest가 ingest_corpus를 배선·호출하고 IngestReport→AdminIngestReport로 매핑한다.

    네트워크/실 DB 없이 — build_embedder·ingest_corpus를 monkeypatch해 페이크 리포트를 주입하고,
    와이어 매핑(failed 튜플→AdminIngestFailure·total 정확·removed 보고)만 검증한다.
    """
    from app.admin import service as admin_service
    from app.chatbot.ingest.service import IngestReport

    monkeypatch.setattr(admin_service, "build_embedder", lambda: object())
    report = IngestReport(
        succeeded=["a.md"],
        skipped=["b.md"],
        failed=[("c.md", "RuntimeError: boom")],
        removed=["d.md"],
    )
    monkeypatch.setattr(admin_service, "ingest_corpus", lambda *a, **k: report)

    result = admin_service.trigger_ingest(object())  # 세션은 monkeypatch된 코어가 미사용

    assert result.succeeded == ["a.md"]
    assert result.skipped == ["b.md"]
    assert result.removed == ["d.md"]
    # total = 성공+스킵+실패(=3). removed(정리분)는 총수에 미포함.
    assert result.total == 3
    # failed 튜플이 AdminIngestFailure(path, reason) 객체로 변환됨(ⓑ).
    assert len(result.failed) == 1
    assert result.failed[0].path == "c.md"
    assert result.failed[0].reason == "RuntimeError: boom"


# ── 인제스트 문서 목록 (상태 산출: ingested/stale/pending/orphan) ────────────────
def test_list_ingest_documents_statuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """list_ingest_documents가 디스크 corpus ∪ DB 적재분을 병합해 4상태를 정확히 산출한다.

    실 DB·임베더 없이 — 디스크는 tmp 실파일(해시 실계산), DB 적재분은 페이크 store로 주입한다.
    상태 규약: ingested(해시 동일)·stale(해시 상이)·pending(디스크만)·orphan(DB만).
    """
    from app.admin import service as admin_service
    from app.chatbot.ingest import compute_content_hash, load_document_text

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "faq.md").write_text("자주 묻는 질문 내용", encoding="utf-8")
    (corpus / "guide.md").write_text("변경된 이용 안내 내용", encoding="utf-8")
    (corpus / "new.md").write_text("아직 적재 안 된 신규 문서", encoding="utf-8")
    faq_hash = compute_content_hash(load_document_text(corpus / "faq.md"))

    class _FakeStore:
        def __init__(self, _session: object) -> None:
            pass

        def summarize_loaded_documents(self) -> dict[str, tuple[int, str]]:
            return {
                "faq.md": (3, faq_hash),  # 디스크 해시와 동일 → ingested
                "guide.md": (2, "OLD_HASH"),  # 해시 상이 → stale
                "gone.md": (1, "x"),  # 디스크에 없음 → orphan
            }

    monkeypatch.setattr(admin_service, "SqlDocumentChunkStore", _FakeStore)

    result = admin_service.list_ingest_documents(object(), corpus_dir=corpus)

    by_path = {d.source_path: d for d in result.documents}
    assert result.total == 4
    assert by_path["faq.md"].status == "ingested"
    assert by_path["faq.md"].chunk_count == 3
    assert by_path["guide.md"].status == "stale"
    assert by_path["new.md"].status == "pending"
    assert by_path["new.md"].chunk_count == 0
    assert by_path["gone.md"].status == "orphan"
    # source_path 사전순 결정적 정렬.
    assert [d.source_path for d in result.documents] == [
        "faq.md",
        "gone.md",
        "guide.md",
        "new.md",
    ]


def test_list_ingest_documents_empty_corpus_and_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """빈 corpus + 빈 DB면 빈 목록(total 0)을 반환한다(부작용·쓰기 0)."""
    from app.admin import service as admin_service

    class _EmptyStore:
        def __init__(self, _session: object) -> None:
            pass

        def summarize_loaded_documents(self) -> dict[str, tuple[int, str]]:
            return {}

    monkeypatch.setattr(admin_service, "SqlDocumentChunkStore", _EmptyStore)

    result = admin_service.list_ingest_documents(object(), corpus_dir=tmp_path)

    assert result.total == 0
    assert result.documents == []
