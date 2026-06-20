"""notifications 라우터 통합 테스트 (Story 5.1 — AC3·AC5 인증 게이팅·소유권·room_name 합성).

**DB 불필요** — ``app.dependency_overrides[get_session]``로 세션을 Fake로 교체하고,
``TestClient(app)``(모듈 레벨, lifespan 미실행 — 1.4 불변식)로 엔드포인트를 검증한다. 실 booker
access 토큰으로 인증(로그인 200/204·무토큰 401)을, ``get_current_principal``(역할 무관)로
provider도 통과함을 실증한다. room_name은 라우터의 2-홉(``Reservation``→``Room``) PK 합성으로
채워지고, 룸 누락은 None 폴백한다.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.core.db import get_session
from app.core.security import create_access_token
from app.core.time import isoformat_utc, now_utc
from app.main import app
from app.notifications.models import Notification, NotificationType
from app.reservations.models import Reservation, ReservationStatus
from app.rooms.models import Room

client = TestClient(app)

_NOTIFICATION_ITEM_KEYS = {
    "id",
    "type",
    "reservation_id",
    "reason",
    "room_name",
    "slot_start",
    "created_at",
}


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


class FakeNotificationSession:
    """라우터 통합용 Fake 세션 — exec를 select 대상으로 라우팅(5.2 GET 머지는 3종 쿼리를 호출).

    ``exec``는 ``statement.column_descriptions[0]["name"]``로 분기해 실 WHERE를 모사한다:

    - ``"Reservation"`` → ``list_booker_reservations`` → 보유 예약 그대로(booker 필터는 fake 생략).
    - ``"reservation_id"`` → ``dismissed_reminder_reservation_ids`` → **reservation_reminder +
      dismissed_at NOT NULL** 행의 reservation_id(억제건 — '억제 후 미도출'을 실증).
    - ``"Notification"``(전체 엔티티) → ``list_pending`` → **dismissed_at IS NULL** 통지.

    ``add``는 ``notifications``에 append해(``suppress_reminder``의 create→dismiss가 방금 만든 행을
    ``get``으로 찾도록) FK/uq 없는 happy-path를 모사한다. ``get``은 PK로 각 풀을 조회한다.
    """

    def __init__(
        self,
        *,
        notifications: list[Notification] | None = None,
        reservations: list[Reservation] | None = None,
        rooms: list[Room] | None = None,
    ) -> None:
        self.notifications = notifications or []
        self.reservations = reservations or []
        self.rooms = rooms or []
        self.committed = False

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        name = statement.column_descriptions[0]["name"]
        if name == "Reservation":
            return _Result(self.reservations)
        if name == "reservation_id":  # dismissed_reminder_reservation_ids(억제건)
            return _Result(
                [
                    n.reservation_id
                    for n in self.notifications
                    if n.type == "reservation_reminder" and n.dismissed_at is not None
                ]
            )
        # name == "Notification" → list_pending(미확인 status_change만 — dismissed 제외 모사).
        return _Result([n for n in self.notifications if n.dismissed_at is None])

    def get(self, model: Any, pk: Any) -> Any:
        pool = {
            Notification: self.notifications,
            Reservation: self.reservations,
            Room: self.rooms,
        }.get(model, [])
        for row in pool:
            if getattr(row, "id", None) == pk:
                return row
        return None

    def add(self, obj: Any) -> None:
        # suppress_reminder의 create_notification이 만든 행을 이어지는 dismiss_notification이
        # get으로 찾도록 풀에 넣는다(FK/uq 없는 happy-path 모사). Notification만 추적.
        if isinstance(obj, Notification):
            self.notifications.append(obj)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, obj: Any) -> None:
        pass

    def rollback(self) -> None:
        pass


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


def _room(name: str = "통지룸") -> Room:
    return Room(
        provider_id=uuid.uuid4(),
        name=name,
        price_per_hour=12000,
        capacity=4,
        room_type="open",
        amenities=["wifi"],
        lat=37.5,
        lng=127.0,
        admin_dong_code="1168010100",
        is_active=True,
    )


def _reservation(room_id: uuid.UUID) -> Reservation:
    return Reservation(booker_id=uuid.uuid4(), room_id=room_id)


def _notification(
    user_id: uuid.UUID,
    reservation_id: uuid.UUID,
    *,
    type: NotificationType = NotificationType.STATUS_CHANGE,
    reason: str | None = "cancelled",
) -> Notification:
    return Notification(
        user_id=user_id,
        reservation_id=reservation_id,
        type=str(type),
        reason=reason,
    )


def _confirmed_reservation(
    room_id: uuid.UUID, booker_id: uuid.UUID, *, hours_ahead: float
) -> Reservation:
    """``hours_ahead`` 시간 뒤 시작하는 confirmed 예약(slot_starts ISO ...Z 스냅샷, 5.2 도출용)."""
    start = now_utc() + timedelta(hours=hours_ahead)
    return Reservation(
        booker_id=booker_id,
        room_id=room_id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=[isoformat_utc(start)],
    )


def _dismissed_reminder(user_id: uuid.UUID, reservation_id: uuid.UUID) -> Notification:
    """'다시 보지 않기'된 억제행(reservation_reminder · dismissed_at 설정 — born-dismissed)."""
    return Notification(
        user_id=user_id,
        reservation_id=reservation_id,
        type=str(NotificationType.RESERVATION_REMINDER),
        reason=None,
        dismissed_at=now_utc(),
    )


# ── GET /api/v1/notifications (목록 — AC3·AC4) ────────────────────────────────────
def test_list_notifications_returns_items_with_room_name(auth_env: None) -> None:
    """로그인 → 200 + 통지 목록(room_name 2-홉 합성·created_at Z·키 집합)."""
    user_id = uuid.uuid4()
    room = _room("스터디카페A")
    reservation = _reservation(room.id)
    notification = _notification(user_id, reservation.id, reason="rejected")
    session = FakeNotificationSession(
        notifications=[notification], reservations=[reservation], rooms=[room]
    )
    with _override_session(session):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    item = body[0]
    assert set(item) == _NOTIFICATION_ITEM_KEYS
    assert item["type"] == "status_change"
    assert item["reason"] == "rejected"
    assert item["room_name"] == "스터디카페A"
    assert item["reservation_id"] == str(reservation.id)
    assert item["created_at"].endswith("Z")


def test_list_status_change_surfaces_slot_start(auth_env: None) -> None:
    """status_change 항목이 linked 예약 slot_starts[0]을 slot_start ...Z로 표면화(본 스토리·AC1)."""
    user_id = uuid.uuid4()
    room = _room("표면화룸")
    start = now_utc() + timedelta(hours=5)
    reservation = Reservation(
        booker_id=user_id,
        room_id=room.id,
        status=ReservationStatus.REJECTED,  # 거절 후에도 slot_starts 스냅샷 보존(4.8)
        slot_starts=[isoformat_utc(start)],
    )
    notification = _notification(user_id, reservation.id, reason="rejected")
    session = FakeNotificationSession(
        notifications=[notification], reservations=[reservation], rooms=[room]
    )
    with _override_session(session):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    item = body[0]
    assert item["type"] == "status_change"
    assert item["slot_start"] is not None
    assert item["slot_start"].endswith("Z")  # linked slot_starts[0] 합성(추가 쿼리 0)


def test_list_status_change_corrupt_slot_starts_falls_back_to_null(auth_env: None) -> None:
    """손상 slot_starts status_change → slot_start null 폴백 + GET 200(500 아님·L7 회수·AC4)."""
    user_id = uuid.uuid4()
    room = _room("손상룸")
    reservation = Reservation(
        booker_id=user_id,
        room_id=room.id,
        status=ReservationStatus.CANCELLED,
        slot_starts=["totally-not-iso"],  # 손상 비-ISO(수동 DB 조작 가정)
    )
    notification = _notification(user_id, reservation.id, reason="cancelled")
    session = FakeNotificationSession(
        notifications=[notification], reservations=[reservation], rooms=[room]
    )
    with _override_session(session):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text  # 손상 한 건이 전체 GET을 죽이지 않음
    body = resp.json()
    assert len(body) == 1
    assert body[0]["slot_start"] is None  # None 폴백(GET 500 회피)
    assert body[0]["room_name"] == "손상룸"  # 나머지 필드는 정상 표시


def test_list_status_change_naive_slot_starts_falls_back_to_null(auth_env: None) -> None:
    """naive(무-Z) slot_starts status_change → slot_start null 폴백 + GET 200(500 아님·5.3 리뷰)."""
    user_id = uuid.uuid4()
    room = _room("naive룸")
    reservation = Reservation(
        booker_id=user_id,
        room_id=room.id,
        status=ReservationStatus.REJECTED,
        slot_starts=["2026-06-17T10:00:00"],  # 유효 ISO지만 tz 없음(naive) — 직렬화 500 유발하던 값
    )
    notification = _notification(user_id, reservation.id, reason="rejected")
    session = FakeNotificationSession(
        notifications=[notification], reservations=[reservation], rooms=[room]
    )
    with _override_session(session):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text  # naive 한 건이 전체 GET을 죽이지 않음
    body = resp.json()
    assert len(body) == 1
    assert body[0]["slot_start"] is None  # None 폴백(직렬화 isoformat_utc 500 회피)
    assert body[0]["room_name"] == "naive룸"


def test_list_notifications_missing_room_falls_back_to_none(auth_env: None) -> None:
    """예약/룸 누락 → room_name None 폴백(막다른 화면 금지·행은 표시)."""
    user_id = uuid.uuid4()
    notification = _notification(user_id, uuid.uuid4())  # 대응 예약/룸 없음
    session = FakeNotificationSession(notifications=[notification])
    with _override_session(session):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["room_name"] is None


def test_list_notifications_provider_allowed(auth_env: None) -> None:
    """provider 토큰도 통과(get_current_principal 역할 무관 — 403 회피)."""
    with _override_session(FakeNotificationSession()):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )
    assert resp.status_code == 200, resp.text


def test_list_notifications_empty_returns_200(auth_env: None) -> None:
    """미확인 통지 없음 → 200 + 빈 리스트."""
    with _override_session(FakeNotificationSession()):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_notifications_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401 UNAUTHENTICATED(AC3 — 로그인 필요)."""
    with _override_session(FakeNotificationSession()):
        resp = client.get("/api/v1/notifications")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── POST /api/v1/notifications/{id}/dismiss (소멸 — AC5) ───────────────────────────
def test_dismiss_notification_returns_204(auth_env: None) -> None:
    """본인 미확인 통지 → 204(소멸 영속)."""
    user_id = uuid.uuid4()
    notification = _notification(user_id, uuid.uuid4())
    session = FakeNotificationSession(notifications=[notification])
    with _override_session(session):
        resp = client.post(
            f"/api/v1/notifications/{notification.id}/dismiss",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 204, resp.text
    assert session.committed is True


def test_dismiss_notification_other_user_returns_404(auth_env: None) -> None:
    """타인 통지 dismiss → 404 NOTIFICATION_NOT_FOUND(존재 누설 금지)."""
    owner_id = uuid.uuid4()
    notification = _notification(owner_id, uuid.uuid4())
    session = FakeNotificationSession(notifications=[notification])
    with _override_session(session):
        resp = client.post(
            f"/api/v1/notifications/{notification.id}/dismiss",
            headers={"Authorization": f"Bearer {_booker_token()}"},  # 다른 사용자
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NOTIFICATION_NOT_FOUND"


def test_dismiss_notification_missing_returns_404(auth_env: None) -> None:
    """미존재 통지 dismiss → 404."""
    with _override_session(FakeNotificationSession()):
        resp = client.post(
            f"/api/v1/notifications/{uuid.uuid4()}/dismiss",
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NOTIFICATION_NOT_FOUND"


def test_dismiss_notification_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401."""
    with _override_session(FakeNotificationSession()):
        resp = client.post(f"/api/v1/notifications/{uuid.uuid4()}/dismiss")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── GET 도래 리마인드 도출 (Story 5.2 — AC1·AC4) ──────────────────────────────────
def test_list_derives_reminder_within_window(auth_env: None) -> None:
    """confirmed·24h 이내 예약 → reminder 도출(id=None·slot_start ...Z·room_name 합성·쓰기 0)."""
    user_id = uuid.uuid4()
    room = _room("스터디카페R")
    reservation = _confirmed_reservation(room.id, user_id, hours_ahead=2)
    session = FakeNotificationSession(reservations=[reservation], rooms=[room])
    with _override_session(session):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    item = body[0]
    assert set(item) == _NOTIFICATION_ITEM_KEYS
    assert item["type"] == "reservation_reminder"
    assert item["id"] is None  # 도출 — 행 없음(FE는 reservation_id 키로 dismiss)
    assert item["reservation_id"] == str(reservation.id)
    assert item["reason"] is None
    assert item["created_at"] is None
    assert item["room_name"] == "스터디카페R"
    assert item["slot_start"].endswith("Z")
    assert session.committed is False  # GET은 읽기전용(DB 쓰기 0)


def test_list_excludes_reminder_outside_window(auth_env: None) -> None:
    """48h 뒤(24h 밖) confirmed → 미도출(빈 목록)."""
    user_id = uuid.uuid4()
    room = _room()
    reservation = _confirmed_reservation(room.id, user_id, hours_ahead=48)
    session = FakeNotificationSession(reservations=[reservation], rooms=[room])
    with _override_session(session):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_list_excludes_suppressed_reminder(auth_env: None) -> None:
    """'다시 보지 않기'된 예약(억제행 존재) → 24h 이내여도 미도출."""
    user_id = uuid.uuid4()
    room = _room()
    reservation = _confirmed_reservation(room.id, user_id, hours_ahead=2)
    suppressed = _dismissed_reminder(user_id, reservation.id)  # born-dismissed 억제행
    session = FakeNotificationSession(
        notifications=[suppressed], reservations=[reservation], rooms=[room]
    )
    with _override_session(session):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []  # 억제행이 list_pending(미확인)엔 안 나오고 도출에서도 제외


def test_list_merges_reminder_and_status_change_in_order(auth_env: None) -> None:
    """리마인드(도출)와 status_change(stored) 공존 → 리마인드 먼저·status_change 다음(결정적)."""
    user_id = uuid.uuid4()
    room = _room("머지룸")
    reminder_res = _confirmed_reservation(room.id, user_id, hours_ahead=2)
    status_res = _reservation(room.id)  # status_change 대상(slot_starts 비어 도출 안 됨)
    status_notif = _notification(user_id, status_res.id, reason="rejected")
    session = FakeNotificationSession(
        notifications=[status_notif],
        reservations=[reminder_res, status_res],
        rooms=[room],
    )
    with _override_session(session):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert body[0]["type"] == "reservation_reminder"  # 리마인드 먼저
    assert body[0]["reservation_id"] == str(reminder_res.id)
    assert body[1]["type"] == "status_change"  # status_change 다음
    assert body[1]["reason"] == "rejected"


def test_list_reminder_missing_room_falls_back_to_none(auth_env: None) -> None:
    """리마인드 룸 누락 → room_name None 폴백(막다른 화면 금지·행은 도출)."""
    user_id = uuid.uuid4()
    reservation = _confirmed_reservation(uuid.uuid4(), user_id, hours_ahead=2)  # 룸 풀에 없음
    session = FakeNotificationSession(reservations=[reservation])
    with _override_session(session):
        resp = client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["room_name"] is None
    assert body[0]["type"] == "reservation_reminder"


# ── POST /reminders/{reservation_id}/dismiss (Story 5.2 — AC2) ────────────────────
def test_dismiss_reminder_returns_204(auth_env: None) -> None:
    """본인 예약 리마인드 '다시 보지 않기' → 204(억제행 born-dismissed 생성)."""
    user_id = uuid.uuid4()
    reservation = _reservation(uuid.uuid4())
    reservation.booker_id = user_id  # 소유권 통과
    session = FakeNotificationSession(reservations=[reservation])
    with _override_session(session):
        resp = client.post(
            f"/api/v1/notifications/reminders/{reservation.id}/dismiss",
            headers={"Authorization": f"Bearer {create_access_token(user_id, 'booker')}"},
        )
    assert resp.status_code == 204, resp.text
    assert session.committed is True


def test_dismiss_reminder_idempotent(auth_env: None) -> None:
    """재클릭 → 204(멱등 — HTTP 레벨 안전)."""
    user_id = uuid.uuid4()
    reservation = _reservation(uuid.uuid4())
    reservation.booker_id = user_id
    session = FakeNotificationSession(reservations=[reservation])
    with _override_session(session):
        token = create_access_token(user_id, "booker")
        first = client.post(
            f"/api/v1/notifications/reminders/{reservation.id}/dismiss",
            headers={"Authorization": f"Bearer {token}"},
        )
        second = client.post(
            f"/api/v1/notifications/reminders/{reservation.id}/dismiss",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert first.status_code == 204, first.text
    assert second.status_code == 204, second.text


def test_dismiss_reminder_missing_reservation_returns_404(auth_env: None) -> None:
    """미존재 예약 리마인드 dismiss → 404 NOTIFICATION_NOT_FOUND(FK 500 회피·누설 금지)."""
    with _override_session(FakeNotificationSession()):
        resp = client.post(
            f"/api/v1/notifications/reminders/{uuid.uuid4()}/dismiss",
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NOTIFICATION_NOT_FOUND"


def test_dismiss_reminder_other_user_returns_404(auth_env: None) -> None:
    """타인 예약 리마인드 dismiss → 404(소유권 누설 금지·403 아님)."""
    owner_id = uuid.uuid4()
    reservation = _reservation(uuid.uuid4())
    reservation.booker_id = owner_id
    session = FakeNotificationSession(reservations=[reservation])
    with _override_session(session):
        resp = client.post(
            f"/api/v1/notifications/reminders/{reservation.id}/dismiss",
            headers={"Authorization": f"Bearer {_booker_token()}"},  # 다른 사용자
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NOTIFICATION_NOT_FOUND"


def test_dismiss_reminder_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401."""
    with _override_session(FakeNotificationSession()):
        resp = client.post(f"/api/v1/notifications/reminders/{uuid.uuid4()}/dismiss")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"
