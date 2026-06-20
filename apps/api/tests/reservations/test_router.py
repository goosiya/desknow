"""reservations 라우터 통합 테스트 (Story 4.5 — AC1·AC2 + RBAC·신선 재검증·에러 와이어).

**DB 불필요** — ``app.dependency_overrides[get_session]``로 세션을 Fake로 교체하고,
``TestClient(app)``(모듈 레벨, lifespan 미실행 — 1.4 불변식)로 엔드포인트를 검증한다. 실 booker
access 토큰으로 인증(201/403/401)을, Fake 세션의 슬롯 도출(``get_room_slots`` 재사용 경로)로
신선 재검증(과거/영업시간외 → 409)·룸 404·UNIQUE 충돌(commit IntegrityError → 409)을 실증한다.

**신선 재검증 시각 결정성:** 라우터는 ``get_room_slots``를 ``now`` 주입 없이 호출하므로(실
``now_utc()``) 슬롯 status가 실시간에 의존한다. 이를 피하려고 **먼 미래 날짜**(2099)를 써서 영업
슬롯이 항상 ``available``이 되게 한다(과거 의존 제거). "지금 잡을 수 없는 슬롯"은 영업시간 밖
시각으로 만들어(도출 자체가 안 됨) now와 무관하게 결정적으로 409가 나게 한다.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.db import get_session
from app.core.security import create_access_token
from app.core.time import ROOM_TZ
from app.main import app
from app.notifications.models import Notification, NotificationType
from app.reservations.models import Reservation, ReservationSlot, ReservationStatus
from app.reservations.schemas import booker_display_label
from app.reviews.models import Review, ReviewReply
from app.rooms.models import BusinessHours, HolidayException, Room
from tests.core.keyset_fake import apply_keyset
from tests.reservations.test_service import (
    _apply_conditional_terminal_update,
    _is_update,
)
from tests.rooms.test_service import (
    _avail_room,
    _FakeOrig,
    _FakeResult,
    _res_slot,
    _room_bh,
)

client = TestClient(app)

_RESERVATION_KEYS = {"id", "room_id", "booker_id", "status", "created_at", "slot_starts"}

# 먼 미래 월요일(영업 슬롯이 now와 무관하게 항상 available — 신선 재검증 결정성). 2099-01-05=월요일.
_FUTURE_DATE = date(2099, 1, 5)


class FakeReservationSession:
    """예약 라우터용 Fake 세션 — 슬롯 도출(읽기) + 예약 생성(쓰기)을 함께 모사한다.

    ``get_room_slots``(신선 재검증)는 ``get(Room)``·``exec(BusinessHours|HolidayException)``를,
    ``create_reservation``(확정)은 ``add``/``commit``/``refresh``/``rollback``을 호출한다. ORM
    introspection으로 조회를 분기한다(``FakeAvailabilitySession`` 선례). ``raise_on_commit``으로
    UNIQUE 충돌(commit IntegrityError → SLOT_CONFLICT 변환)을 실증한다.
    """

    def __init__(
        self,
        *,
        rooms: list[Any] | None = None,
        business_hours: list[BusinessHours] | None = None,
        holidays: list[HolidayException] | None = None,
        reservation_slots: list[ReservationSlot] | None = None,
        raise_on_commit: bool = False,
        commit_violation: str | None = None,
    ) -> None:
        self.rooms = rooms or []
        self.business_hours = business_hours or []
        self.holidays = holidays or []
        # Story 4.9: get_room_slots(신선 재검증 경로)가 confirmed_slot_starts로 조회하는 활성 점유.
        # 기본 [] → 차감 없음(4.9 전 라우터 테스트 동작 보존).
        self.reservation_slots = reservation_slots or []
        self.raise_on_commit = raise_on_commit
        self.commit_violation = commit_violation
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False
        self.refreshed = 0

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        entity = None
        descriptions = getattr(statement, "column_descriptions", None)
        if descriptions:
            entity = descriptions[0].get("entity")
        if entity is BusinessHours:
            return _FakeResult(self.business_hours)
        if entity is HolidayException:
            return _FakeResult(self.holidays)
        if entity is ReservationSlot:
            # 4.9 예약 차감 reader. get_room_slots는 단건(1-컬럼 slot_start)으로 조회 — 컴파일
            # 파라미터로 room_id(==) 필터를 재현해 그 룸 점유만 돌려준다(FakeAvailability 동형).
            params = statement.compile().params
            room_filter = params.get("room_id_1")
            rows = [
                r.slot_start
                for r in self.reservation_slots
                if room_filter is None or r.room_id == room_filter
            ]
            return _FakeResult(rows)
        return _FakeResult([r for r in self.rooms if r.is_active])

    def get(self, model: Any, pk: Any) -> Any:
        for room in self.rooms:
            if getattr(room, "id", None) == pk:
                return room
        return None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        if self.raise_on_commit:
            raise IntegrityError("stmt", {}, _FakeOrig(self.commit_violation))
        self.committed = True

    def refresh(self, obj: Any) -> None:
        self.refreshed += 1

    def rollback(self) -> None:
        self.rolled_back = True


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


def _admin_token() -> str:
    return create_access_token(uuid.uuid4(), "admin")


def _utc_slot(target_date: date, kst_hour: int) -> str:
    """target_date의 KST 벽시계 ``kst_hour``시 → UTC ISO 문자열(derive_slots 출력과 동형)."""
    wall = datetime.combine(target_date, time(kst_hour, 0)).replace(tzinfo=ROOM_TZ)
    return wall.astimezone(UTC).isoformat()


def _room_with_hours(open_h: int = 9, close_h: int = 22) -> tuple[Any, list[BusinessHours]]:
    """활성 룸 + 그 룸의 _FUTURE_DATE 요일 영업시간(기본 09–22)."""
    room = _avail_room()
    bh = _room_bh(room.id, _FUTURE_DATE.weekday(), open_h, close_h)
    return room, [bh]


def _url(room_id: Any) -> str:
    return f"/api/v1/rooms/{room_id}/reservations"


# ── POST 성공 (AC1) ──────────────────────────────────────────────────────────────
def test_create_reservation_booker_returns_201(auth_env: None) -> None:
    """booker + 빈 연속 슬롯 → 201 + ReservationPublic(status confirmed·slot_starts ...Z)."""
    room, hours = _room_with_hours()
    session = FakeReservationSession(rooms=[room], business_hours=hours)
    slots = [_utc_slot(_FUTURE_DATE, 14), _utc_slot(_FUTURE_DATE, 15)]
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": slots},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == _RESERVATION_KEYS
    assert body["room_id"] == str(room.id)
    assert body["status"] == "confirmed"
    assert body["created_at"].endswith("Z")
    assert len(body["slot_starts"]) == 2
    assert all(s.endswith("Z") for s in body["slot_starts"])
    # 확정 = 예약 1 + 점유 행 2 = 3행 add + 단일 commit(all-or-nothing).
    assert len(session.added) == 3
    assert session.committed is True


# ── RBAC (범위 결정 #1) ──────────────────────────────────────────────────────────
def test_create_reservation_provider_returns_403(auth_env: None) -> None:
    """provider 토큰 → 403 FORBIDDEN_ROLE(예약 생성은 booker 전용)."""
    room, hours = _room_with_hours()
    session = FakeReservationSession(rooms=[room], business_hours=hours)
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": [_utc_slot(_FUTURE_DATE, 14)]},
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_create_reservation_admin_returns_403(auth_env: None) -> None:
    """admin 토큰도 → 403(booker만 통과 — require_role("booker"))."""
    room, hours = _room_with_hours()
    session = FakeReservationSession(rooms=[room], business_hours=hours)
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": [_utc_slot(_FUTURE_DATE, 14)]},
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_create_reservation_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401 UNAUTHENTICATED."""
    room, hours = _room_with_hours()
    session = FakeReservationSession(rooms=[room], business_hours=hours)
    with _override_session(session):
        resp = client.post(
            _url(room.id), json={"slot_starts": [_utc_slot(_FUTURE_DATE, 14)]}
        )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── 룸 가드 (AC2) ────────────────────────────────────────────────────────────────
def test_create_reservation_unknown_room_returns_404(auth_env: None) -> None:
    """미존재/비활성 룸 → 404 ROOM_NOT_FOUND(get_room_slots 공유 404 가드)."""
    session = FakeReservationSession(rooms=[])  # 룸 없음
    with _override_session(session):
        resp = client.post(
            _url(uuid.uuid4()),
            json={"slot_starts": [_utc_slot(_FUTURE_DATE, 14)]},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ROOM_NOT_FOUND"


def test_create_reservation_inactive_room_returns_404(auth_env: None) -> None:
    """비활성 룸 → 404 ROOM_NOT_FOUND(미존재와 동일 합침)."""
    room = _avail_room(is_active=False)
    bh = _room_bh(room.id, _FUTURE_DATE.weekday(), 9, 22)
    session = FakeReservationSession(rooms=[room], business_hours=[bh])
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": [_utc_slot(_FUTURE_DATE, 14)]},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ROOM_NOT_FOUND"


# ── 신선 재검증 (AC2 — stale/영업시간외 → SLOT_CONFLICT) ──────────────────────────
def test_create_reservation_slot_outside_hours_returns_409(auth_env: None) -> None:
    """영업시간 밖 슬롯(도출 불가) 요청 → 409 SLOT_CONFLICT(신선 재검증 차단)."""
    room, hours = _room_with_hours(open_h=9, close_h=22)
    session = FakeReservationSession(rooms=[room], business_hours=hours)
    # 03:00 KST는 영업(09–22) 밖이라 derive_slots가 만들지 않는다 → 가용 집합에 없음 → 409.
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": [_utc_slot(_FUTURE_DATE, 3)]},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "SLOT_CONFLICT"
    assert session.committed is False  # 확정 미진입(검증 단계 차단)


def test_create_reservation_holiday_returns_409(auth_env: None) -> None:
    """휴무일 슬롯 요청 → 409 SLOT_CONFLICT(derive_slots가 휴무면 [] → 가용 없음)."""
    room, hours = _room_with_hours()
    holiday = HolidayException(room_id=room.id, holiday_date=_FUTURE_DATE)
    session = FakeReservationSession(
        rooms=[room], business_hours=hours, holidays=[holiday]
    )
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": [_utc_slot(_FUTURE_DATE, 14)]},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "SLOT_CONFLICT"


def test_create_reservation_already_reserved_slot_returns_409(auth_env: None) -> None:
    """Story 4.9: 이미 예약된 슬롯 요청 → 신선 재검증이 차감으로 차단(409 SLOT_CONFLICT).

    4.9 배선으로 get_room_slots가 점유 슬롯을 status="reserved"로 표시 → available 집합에서 빠진다.
    요청 ⊆ available 위반 → 확정 진입 전 409(이중 방어의 **검증** 계층 — UNIQUE 백스톱과 별개).
    """
    room, hours = _room_with_hours()
    reserved_at = _utc_slot(_FUTURE_DATE, 14)  # 14:00 KST 슬롯이 이미 점유됨
    session = FakeReservationSession(
        rooms=[room],
        business_hours=hours,
        reservation_slots=[
            _res_slot(room.id, datetime.fromisoformat(reserved_at)),
        ],
    )
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": [reserved_at]},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "SLOT_CONFLICT"
    assert session.committed is False  # 검증 단계에서 차단 — 확정 미진입


# ── UNIQUE 충돌 (AC2 — 이미 점유된 슬롯, 이중 방어 하한) ──────────────────────────
def test_create_reservation_already_occupied_returns_409(auth_env: None) -> None:
    """신선 재검증 통과(available)했으나 INSERT 시 UNIQUE 충돌 → 409 SLOT_CONFLICT(4.1 변환)."""
    room, hours = _room_with_hours()
    # 이 Fake엔 점유 행을 안 넣어(reservation_slots=[]) 신선 재검증은 available로 통과한다 →
    # commit에서 uq_reservation_slots_room_slot 위반(동시 점유 race)으로 SLOT_CONFLICT가 난다
    # (4.9 차감의 검증 계층이 못 잡는 동시성 틈을 UNIQUE 백스톱이 막는 이중 방어 하한).
    session = FakeReservationSession(
        rooms=[room],
        business_hours=hours,
        raise_on_commit=True,
        commit_violation="uq_reservation_slots_room_slot",
    )
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": [_utc_slot(_FUTURE_DATE, 14)]},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "SLOT_CONFLICT"
    assert session.rolled_back is True  # 전체 ROLLBACK(부분 점유 0)


# ── 입력 형식 422 (AC2 — service ValueError가 500으로 새지 않게 스키마 선차단) ────
def test_create_reservation_empty_slots_returns_422(auth_env: None) -> None:
    """빈 slot_starts → 422 VALIDATION_ERROR(min_length=1)."""
    room, hours = _room_with_hours()
    session = FakeReservationSession(rooms=[room], business_hours=hours)
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": []},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_create_reservation_naive_datetime_returns_422(auth_env: None) -> None:
    """naive datetime(tz 없음) → 422 VALIDATION_ERROR(스키마 선차단)."""
    room, hours = _room_with_hours()
    session = FakeReservationSession(rooms=[room], business_hours=hours)
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": ["2099-01-05T05:00:00"]},  # tz 접미사 없음 = naive
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_create_reservation_duplicate_slots_returns_422(auth_env: None) -> None:
    """동일 호출 내 중복 슬롯 → 422(자기충돌이 SLOT_CONFLICT로 오변환되는 것 방지)."""
    room, hours = _room_with_hours()
    session = FakeReservationSession(rooms=[room], business_hours=hours)
    slot = _utc_slot(_FUTURE_DATE, 14)
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": [slot, slot]},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_create_reservation_cross_day_returns_422(auth_env: None) -> None:
    """서로 다른 ROOM_TZ 날짜의 슬롯을 한 예약에 섞으면 → 422(교차일 거부)."""
    room, hours = _room_with_hours()
    session = FakeReservationSession(rooms=[room], business_hours=hours)
    slots = [_utc_slot(_FUTURE_DATE, 14), _utc_slot(date(2099, 1, 6), 14)]
    with _override_session(session):
        resp = client.post(
            _url(room.id),
            json={"slot_starts": slots},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


# ── 에러 와이어 형식 ─────────────────────────────────────────────────────────────
def test_create_reservation_error_wire_shape(auth_env: None) -> None:
    """에러 응답은 표준 스키마 {"detail":{"code","message"}} 형식이다."""
    session = FakeReservationSession(rooms=[])
    with _override_session(session):
        resp = client.post(
            _url(uuid.uuid4()),
            json={"slot_starts": [_utc_slot(_FUTURE_DATE, 14)]},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    detail = resp.json()["detail"]
    assert set(detail) == {"code", "message"}
    assert isinstance(detail["message"], str)


# ═══════════════════════════════════════════════════════════════════════════════════
# 취소 엔드포인트 POST .../{reservation_id}/cancel (Story 4.7 — AC1·AC2·AC3·AC4)
# ═══════════════════════════════════════════════════════════════════════════════════

# 취소 윈도우 거부 시 고정 한국어 카피(UX-DR10 — 정확 문자열 단언, UTF-8).
_CANCEL_COPY = "이제 6시간이 안 남아서 취소가 어려워요."

# 6h 게이트 결정성: 라우터는 now 주입 없이 now_utc()를 쓰므로 슬롯 시각으로 경계를 고정한다.
# 먼 미래(2099) = 항상 취소 가능, 먼 과거(2020) = 항상 6h 경과(차단).
_FAR_FUTURE_SLOT = datetime(2099, 1, 5, 5, 0, tzinfo=UTC)
_FAR_PAST_SLOT = datetime(2020, 1, 5, 5, 0, tzinfo=UTC)


class FakeCancelSession:
    """취소 라우터용 Fake 세션 — ``get(Reservation)`` + 슬롯 도출(읽기) + 취소(쓰기) 모사.

    라우터는 ``get(Reservation, id)``로 소유권을 검사하고, service 래퍼가
    ``exec(select).all()``(``earliest_slot_start``) → ``add``/``exec(delete)``/``commit``
    /``refresh``(``cancel_reservation``)를 호출한다. ``slot_starts``로 6h 게이트 입력을,
    ``stored``로 소유권 분기를 제어한다.
    """

    def __init__(
        self,
        *,
        stored: Reservation | None = None,
        slot_starts: list[datetime] | None = None,
    ) -> None:
        self.stored = stored
        self.slot_starts = slot_starts or []
        self.added: list[Any] = []
        self.committed = False
        self.refreshed = 0
        self.exec_calls: list[Any] = []

    def get(self, model: Any, pk: Any) -> Any:
        if self.stored is not None and self.stored.id == pk:
            return self.stored
        return None

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        self.exec_calls.append(statement)
        if _is_update(statement):
            # 조건부 종료 전이 UPDATE — stored(라우터가 get한 동일 객체)를 flip(승자=rowcount 1).
            return _apply_conditional_terminal_update(
                statement, [self.stored] if self.stored is not None else []
            )
        return _FakeResult(self.slot_starts)  # earliest_slot_start의 .all() 경로

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, obj: Any) -> None:
        self.refreshed += 1


def _reservation(
    *, booker_id: uuid.UUID, room_id: uuid.UUID, status: ReservationStatus
) -> Reservation:
    return Reservation(
        id=uuid.uuid4(), booker_id=booker_id, room_id=room_id, status=status
    )


def _cancel_url(room_id: Any, reservation_id: Any) -> str:
    return f"/api/v1/rooms/{room_id}/reservations/{reservation_id}/cancel"


# ── 성공 취소 (AC1·AC2) ───────────────────────────────────────────────────────────
def test_cancel_reservation_owner_returns_200(auth_env: None) -> None:
    """booker 본인 confirmed 예약(6h+ 남음) 취소 → 200·cancelled·slot_starts=[]."""
    booker_id = uuid.uuid4()
    room_id = uuid.uuid4()
    reservation = _reservation(
        booker_id=booker_id, room_id=room_id, status=ReservationStatus.CONFIRMED
    )
    session = FakeCancelSession(stored=reservation, slot_starts=[_FAR_FUTURE_SLOT])
    with _override_session(session):
        resp = client.post(
            _cancel_url(room_id, reservation.id),
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == _RESERVATION_KEYS
    assert body["status"] == "cancelled"
    assert body["slot_starts"] == []  # 취소 후 점유 0(재활성)
    assert session.committed is True


# ── 멱등 (AC3) ────────────────────────────────────────────────────────────────────
def test_cancel_reservation_idempotent_returns_200(auth_env: None) -> None:
    """이미 cancelled인 예약 재취소 → 200·현재 상태·DB 쓰기 0(6h 검사도 안 함)."""
    booker_id = uuid.uuid4()
    room_id = uuid.uuid4()
    reservation = _reservation(
        booker_id=booker_id, room_id=room_id, status=ReservationStatus.CANCELLED
    )
    session = FakeCancelSession(stored=reservation, slot_starts=[])
    with _override_session(session):
        resp = client.post(
            _cancel_url(room_id, reservation.id),
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"
    assert session.committed is False  # 멱등 no-op(쓰기 0)
    assert session.exec_calls == []  # earliest 조회·6h 검사 진입 안 함


# ── 6h 게이트 (AC1) ───────────────────────────────────────────────────────────────
def test_cancel_reservation_window_passed_returns_409(auth_env: None) -> None:
    """6h 미만(과거 시작) 예약 취소 → 409 CANCEL_WINDOW_PASSED·고정 카피·상태 변경 0."""
    booker_id = uuid.uuid4()
    room_id = uuid.uuid4()
    reservation = _reservation(
        booker_id=booker_id, room_id=room_id, status=ReservationStatus.CONFIRMED
    )
    session = FakeCancelSession(stored=reservation, slot_starts=[_FAR_PAST_SLOT])
    with _override_session(session):
        resp = client.post(
            _cancel_url(room_id, reservation.id),
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "CANCEL_WINDOW_PASSED"
    assert detail["message"] == _CANCEL_COPY  # 고정 카피(코드·숫자 노출 X)
    assert session.committed is False  # 상태 전이·슬롯 변경 0


# ── 소유권·인증 (AC4) ─────────────────────────────────────────────────────────────
def test_cancel_reservation_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401 UNAUTHENTICATED."""
    session = FakeCancelSession(stored=None)
    with _override_session(session):
        resp = client.post(_cancel_url(uuid.uuid4(), uuid.uuid4()))
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_cancel_reservation_provider_returns_403(auth_env: None) -> None:
    """provider 토큰 → 403 FORBIDDEN_ROLE(취소는 booker 전용)."""
    session = FakeCancelSession(stored=None)
    with _override_session(session):
        resp = client.post(
            _cancel_url(uuid.uuid4(), uuid.uuid4()),
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_cancel_reservation_unknown_id_returns_404(auth_env: None) -> None:
    """미존재 예약 id → 404 RESERVATION_NOT_FOUND."""
    session = FakeCancelSession(stored=None)  # get → None
    with _override_session(session):
        resp = client.post(
            _cancel_url(uuid.uuid4(), uuid.uuid4()),
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RESERVATION_NOT_FOUND"


def test_cancel_reservation_other_owner_returns_404(auth_env: None) -> None:
    """타인 예약 취소 시도 → 404 RESERVATION_NOT_FOUND(403 아님 — 존재 누설 금지)."""
    room_id = uuid.uuid4()
    # 예약 소유자는 다른 사람(stored.booker_id)인데 요청자는 _booker_token()의 임의 uuid.
    reservation = _reservation(
        booker_id=uuid.uuid4(), room_id=room_id, status=ReservationStatus.CONFIRMED
    )
    session = FakeCancelSession(stored=reservation, slot_starts=[_FAR_FUTURE_SLOT])
    with _override_session(session):
        resp = client.post(
            _cancel_url(room_id, reservation.id),
            headers={"Authorization": f"Bearer {create_access_token(uuid.uuid4(), 'booker')}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RESERVATION_NOT_FOUND"
    assert session.committed is False


def test_cancel_reservation_room_mismatch_returns_404(auth_env: None) -> None:
    """경로 room_id가 예약 room_id와 불일치 → 404(경로 일관성 가드, 누설 금지)."""
    booker_id = uuid.uuid4()
    reservation = _reservation(
        booker_id=booker_id, room_id=uuid.uuid4(), status=ReservationStatus.CONFIRMED
    )
    session = FakeCancelSession(stored=reservation, slot_starts=[_FAR_FUTURE_SLOT])
    with _override_session(session):
        resp = client.post(
            _cancel_url(uuid.uuid4(), reservation.id),  # 다른 room_id 경로
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RESERVATION_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════════════
# 본인 예약현황 목록 GET /reservations (Story 4.8 — AC1·AC2·AC4)
# ═══════════════════════════════════════════════════════════════════════════════════

_LIST_KEYS = {
    "id", "room_id", "room_name", "status", "slot_starts", "created_at", "is_active",
    "has_review",  # Story 5.5 — 후기 작성 게이팅
    "review",  # 본인 후기 내용+사장님 답글(없으면 null) — KTH 2026-06-19
}
_LIST_URL = "/api/v1/reservations"


class FakeListSession:
    """예약현황 목록용 Fake 세션 — ``exec(select(Reservation))`` + ``get(Room)`` 합성 모사.

    라우터는 ``service.list_booker_reservations``(``exec(select).all()``)로 본인 예약을 받고, 각
    예약마다 ``get(Room, room_id)``로 이름·is_active를 합성한다. ``owner_id``로 SQL WHERE(본인만)를
    경계에서 모사하고(타 booker 행 제외), ``created_at`` desc 정렬도 미러한다.
    """

    def __init__(
        self,
        *,
        reservations: list[Reservation] | None = None,
        rooms: list[Any] | None = None,
        owner_id: uuid.UUID | None = None,
        reviews: list[Review] | None = None,
        replies: list[ReviewReply] | None = None,
    ) -> None:
        self.reservations = reservations or []
        self.rooms = rooms or []
        self.owner_id = owner_id
        # Story 5.5/5.6: reviews_by_booker(본인 후기 — has_review·내용 합성)가 돌려줄 후기 객체.
        # 기본 [] → 전부 has_review=False·review=None(5.5 전 동작 보존). replies는 그 후기들의 답글.
        self.reviews = reviews or []
        self.replies = replies or []
        self.committed = False

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        # 본인 후기(select(Review))·답글(select(ReviewReply)) 합성 — has_review·내용·답글 노출.
        descriptions = getattr(statement, "column_descriptions", None)
        entity = descriptions[0].get("entity") if descriptions else None
        if entity is Review:
            return _FakeResult(self.reviews)
        if entity is ReviewReply:
            return _FakeResult(self.replies)
        # 본인(owner_id) 예약만 — SQL WHERE를 경계에서 미러. 페이징 select(keyset 술어·limit)는
        # apply_keyset으로 실제 DB와 동일하게 정렬·커서 필터·절단한다(F 무한스크롤 통합 검증).
        rows = [r for r in self.reservations if r.booker_id == self.owner_id]
        return _FakeResult(apply_keyset(statement, rows))

    def get(self, model: Any, pk: Any) -> Any:
        for room in self.rooms:
            if getattr(room, "id", None) == pk:
                return room
        return None

    def commit(self) -> None:
        self.committed = True


def _list_reservation(
    *,
    booker_id: uuid.UUID,
    room_id: uuid.UUID,
    status: ReservationStatus,
    slot_starts: list[str],
    created_at: datetime,
) -> Reservation:
    return Reservation(
        id=uuid.uuid4(),
        booker_id=booker_id,
        room_id=room_id,
        status=status,
        slot_starts=slot_starts,
        created_at=created_at,
    )


def test_list_reservations_booker_returns_own_only(auth_env: None) -> None:
    """booker 본인 예약만 룸 이름·status·slot_starts·is_active로 반환(타 booker 제외, AC1·AC4)."""
    booker_id = uuid.uuid4()
    room = _avail_room()
    mine = _list_reservation(
        booker_id=booker_id,
        room_id=room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2099-01-05T05:00:00Z", "2099-01-05T06:00:00Z"],
        created_at=datetime(2026, 6, 17, 0, tzinfo=UTC),
    )
    # 타인 예약(같은 룸) — owner_id 필터로 제외되어야 한다.
    other = _list_reservation(
        booker_id=uuid.uuid4(),
        room_id=room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2099-01-06T05:00:00Z"],
        created_at=datetime(2026, 6, 17, 0, tzinfo=UTC),
    )
    session = FakeListSession(
        reservations=[mine, other], rooms=[room], owner_id=booker_id
    )
    with _override_session(session):
        resp = client.get(
            _LIST_URL,
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()["items"]
    assert len(body) == 1  # 본인 1건만(타인 제외)
    item = body[0]
    assert set(item) == _LIST_KEYS
    assert item["id"] == str(mine.id)
    assert item["room_id"] == str(room.id)
    assert item["room_name"] == room.name
    assert item["status"] == "confirmed"
    assert item["is_active"] is True
    assert item["slot_starts"] == ["2099-01-05T05:00:00Z", "2099-01-05T06:00:00Z"]
    assert all(s.endswith("Z") for s in item["slot_starts"])
    assert item["created_at"].endswith("Z")


def test_list_reservations_orders_created_at_desc(auth_env: None) -> None:
    """본인 예약을 created_at 내림차순(최근 먼저)으로 반환한다(AC1)."""
    booker_id = uuid.uuid4()
    room = _avail_room()
    older = _list_reservation(
        booker_id=booker_id,
        room_id=room.id,
        status=ReservationStatus.CANCELLED,
        slot_starts=["2099-01-05T05:00:00Z"],
        created_at=datetime(2026, 6, 10, 0, tzinfo=UTC),
    )
    newer = _list_reservation(
        booker_id=booker_id,
        room_id=room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2099-01-06T05:00:00Z"],
        created_at=datetime(2026, 6, 16, 0, tzinfo=UTC),
    )
    session = FakeListSession(
        reservations=[older, newer], rooms=[room], owner_id=booker_id
    )
    with _override_session(session):
        resp = client.get(
            _LIST_URL,
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    ids = [item["id"] for item in resp.json()["items"]]
    assert ids == [str(newer.id), str(older.id)]  # 최근 먼저


def test_list_reservations_cancelled_retains_snapshot(auth_env: None) -> None:
    """취소된 예약도 목록에 status=cancelled·slot_starts(스냅샷) 잔존으로 표시된다(범위 결정 #1)."""
    booker_id = uuid.uuid4()
    room = _avail_room()
    cancelled = _list_reservation(
        booker_id=booker_id,
        room_id=room.id,
        status=ReservationStatus.CANCELLED,
        slot_starts=["2099-01-05T05:00:00Z"],  # 점유 행은 DELETE됐어도 스냅샷 잔존
        created_at=datetime(2026, 6, 17, 0, tzinfo=UTC),
    )
    session = FakeListSession(
        reservations=[cancelled], rooms=[room], owner_id=booker_id
    )
    with _override_session(session):
        resp = client.get(
            _LIST_URL,
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["status"] == "cancelled"
    assert item["slot_starts"] == ["2099-01-05T05:00:00Z"]  # 히스토리 시간 표시


def test_list_reservations_inactive_room_shows_name(auth_env: None) -> None:
    """비활성 룸의 예약도 이름·히스토리를 표시한다(is_active=false로 상세 진입은 FE가 차단)."""
    booker_id = uuid.uuid4()
    room = _avail_room(is_active=False)
    reservation = _list_reservation(
        booker_id=booker_id,
        room_id=room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2099-01-05T05:00:00Z"],
        created_at=datetime(2026, 6, 17, 0, tzinfo=UTC),
    )
    session = FakeListSession(
        reservations=[reservation], rooms=[room], owner_id=booker_id
    )
    with _override_session(session):
        resp = client.get(
            _LIST_URL,
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["room_name"] == room.name  # 비활성이어도 이름 표시
    assert item["is_active"] is False


def test_list_reservations_has_review_synthesis(auth_env: None) -> None:
    """Story 5.5/5.6: 후기 작성 예약=has_review True + review·답글 합성, 미작성=False."""
    booker_id = uuid.uuid4()
    room = _avail_room()
    reviewed = _list_reservation(
        booker_id=booker_id,
        room_id=room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2020-01-05T05:00:00Z"],  # 이용 완료(과거)
        created_at=datetime(2026, 6, 17, 1, tzinfo=UTC),
    )
    not_reviewed = _list_reservation(
        booker_id=booker_id,
        room_id=room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2020-01-06T05:00:00Z"],
        created_at=datetime(2026, 6, 17, 0, tzinfo=UTC),
    )
    # reviewed 예약에 본인 후기 + 사장님 답글(노출 검증용).
    review = Review(
        id=uuid.uuid4(),
        reservation_id=reviewed.id,
        room_id=room.id,
        booker_id=booker_id,
        rating=5,
        text="조용하고 좋았어요",
        created_at=datetime(2026, 6, 17, 2, tzinfo=UTC),
    )
    reply = ReviewReply(
        id=uuid.uuid4(),
        review_id=review.id,
        provider_id=uuid.uuid4(),
        text="이용해 주셔서 감사합니다",
        created_at=datetime(2026, 6, 17, 3, tzinfo=UTC),
    )
    session = FakeListSession(
        reservations=[reviewed, not_reviewed],
        rooms=[room],
        owner_id=booker_id,
        reviews=[review],  # reviewed 예약만 후기 존재
        replies=[reply],
    )
    with _override_session(session):
        resp = client.get(
            _LIST_URL,
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 200, resp.text
    by_id = {item["id"]: item for item in resp.json()["items"]}
    # 후기 작성 예약 — has_review True + review 내용(별점·텍스트·작성일 ...Z) + 사장님 답글.
    reviewed_item = by_id[str(reviewed.id)]
    assert reviewed_item["has_review"] is True
    assert reviewed_item["review"]["rating"] == 5
    assert reviewed_item["review"]["text"] == "조용하고 좋았어요"
    assert reviewed_item["review"]["created_at"].endswith("Z")
    assert reviewed_item["review"]["reply"]["text"] == "이용해 주셔서 감사합니다"
    assert reviewed_item["review"]["reply"]["created_at"].endswith("Z")
    # 미작성 예약 — has_review False + review None.
    not_reviewed_item = by_id[str(not_reviewed.id)]
    assert not_reviewed_item["has_review"] is False
    assert not_reviewed_item["review"] is None


def test_list_reservations_empty_returns_200(auth_env: None) -> None:
    """예약이 없으면 빈 리스트(정상 200)."""
    booker_id = uuid.uuid4()
    session = FakeListSession(reservations=[], rooms=[], owner_id=booker_id)
    with _override_session(session):
        resp = client.get(
            _LIST_URL,
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["next_cursor"] is None


def test_list_reservations_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401 UNAUTHENTICATED."""
    session = FakeListSession()
    with _override_session(session):
        resp = client.get(_LIST_URL)
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_list_reservations_provider_returns_403(auth_env: None) -> None:
    """provider 토큰 → 403 FORBIDDEN_ROLE(예약현황은 booker 전용)."""
    session = FakeListSession()
    with _override_session(session):
        resp = client.get(
            _LIST_URL, headers={"Authorization": f"Bearer {_provider_token()}"}
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


# ═══════════════════════════════════════════════════════════════════════════════════
# 제공자 예약현황 목록 GET /provider/reservations (Story 6.1 — AC1·AC2·AC3)
# ═══════════════════════════════════════════════════════════════════════════════════

_PROVIDER_KEYS = {
    "id", "room_id", "room_name", "booker_label", "status", "slot_starts", "created_at",
}
_PROVIDER_URL = "/api/v1/provider/reservations"


class FakeProviderSession:
    """제공자 예약현황용 Fake 세션 — ``exec(select(Room))`` + ``exec(select(Reservation))`` 합성.

    라우터는 ``rooms_service.list_provider_rooms``(소유 룸 — ``where(provider_id==X)``)와
    ``service.list_reservations_for_rooms``(그 룸들의 예약 — ``where(room_id IN [...])``)를 한
    세션으로 호출한다. ORM introspection으로 분기하고, 컴파일된 bind 파라미터로 ``provider_id``
    (소유권 필터)·``room_id IN``(룸 격리)·``created_at`` desc를 경계에서 충실히 재현한다
    (``FakeAvailabilitySession``·``FakeListSession`` 선례). 읽기 전용(commit은 무해 기록).
    """

    def __init__(
        self,
        *,
        rooms: list[Any] | None = None,
        reservations: list[Reservation] | None = None,
    ) -> None:
        self.rooms = rooms or []
        self.reservations = reservations or []
        self.committed = False

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        entity = None
        descriptions = getattr(statement, "column_descriptions", None)
        if descriptions:
            entity = descriptions[0].get("entity")
        params = statement.compile().params
        if entity is Reservation:
            # 룸 단위 예약 조회 — room_id IN [...] 필터(SQL 미러) + 페이징(keyset 술어·limit)을
            # apply_keyset으로 실제 DB와 동일하게 정렬·커서 필터·절단한다(F 무한스크롤 통합 검증).
            room_filter = params.get("room_id_1")
            rows = [
                r
                for r in self.reservations
                if room_filter is None or r.room_id in room_filter
            ]
            return _FakeResult(apply_keyset(statement, rows))
        # Room: 소유권 where(provider_id == X) 미러 — is_active 무관(소유자 뷰).
        provider_filter = params.get("provider_id_1")
        rooms = [
            r
            for r in self.rooms
            if provider_filter is None or r.provider_id == provider_filter
        ]
        return _FakeResult(rooms)

    def commit(self) -> None:
        self.committed = True


def _owned_room(provider_id: uuid.UUID, *, is_active: bool = True) -> Room:
    """제공자 소유 룸(provider_id 명시 — 소유권 필터 테스트용)."""
    return Room(
        provider_id=provider_id,
        name="소유공간",
        price_per_hour=10000,
        capacity=4,
        room_type="open",
        amenities=[],
        lat=37.5,
        lng=127.0,
        admin_dong_code="1168010100",
        is_active=is_active,
    )


def test_list_provider_reservations_returns_owned(auth_env: None) -> None:
    """provider 소유 룸 예약을 room_name·booker_label·status·slot_starts로 반환(AC1)."""
    provider_id = uuid.uuid4()
    booker_id = uuid.uuid4()
    room = _owned_room(provider_id)
    reservation = _list_reservation(
        booker_id=booker_id,
        room_id=room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2099-01-05T05:00:00Z", "2099-01-05T06:00:00Z"],
        created_at=datetime(2026, 6, 17, 0, tzinfo=UTC),
    )
    session = FakeProviderSession(rooms=[room], reservations=[reservation])
    with _override_session(session):
        resp = client.get(
            _PROVIDER_URL,
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()["items"]
    assert len(body) == 1
    item = body[0]
    assert set(item) == _PROVIDER_KEYS  # 식별/내부 필드(email·booker_id) 부재(AC2)
    assert item["id"] == str(reservation.id)
    assert item["room_id"] == str(room.id)
    assert item["room_name"] == room.name
    assert item["booker_label"].startswith("예약자 #")  # 익명 라벨
    assert item["status"] == "confirmed"
    assert item["slot_starts"] == ["2099-01-05T05:00:00Z", "2099-01-05T06:00:00Z"]
    assert item["created_at"].endswith("Z")


def test_list_provider_reservations_hides_booker_identity(auth_env: None) -> None:
    """★AC2 핵심: 응답 본문에 예약자 raw booker_id·email 문자열이 절대 노출되지 않는다."""
    provider_id = uuid.uuid4()
    booker_id = uuid.uuid4()
    room = _owned_room(provider_id)
    reservation = _list_reservation(
        booker_id=booker_id,
        room_id=room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2099-01-05T05:00:00Z"],
        created_at=datetime(2026, 6, 17, 0, tzinfo=UTC),
    )
    session = FakeProviderSession(rooms=[room], reservations=[reservation])
    with _override_session(session):
        resp = client.get(
            _PROVIDER_URL,
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 200, resp.text
    # raw booker_id UUID·"email" 필드가 직렬화 본문 어디에도 없어야 한다(FR-23 Privacy).
    assert str(booker_id) not in resp.text
    assert "email" not in resp.text
    assert "booker_id" not in resp.text
    # 같은 예약자 → 같은 라벨(결정적, 제공자가 구분·집계 가능).
    item = resp.json()["items"][0]
    assert item["booker_label"] == booker_display_label(booker_id)


def test_list_provider_reservations_excludes_other_providers(auth_env: None) -> None:
    """타 제공자 룸의 예약은 노출되지 않는다(소유권 필터 — AC3)."""
    me = uuid.uuid4()
    my_room = _owned_room(me)
    other_room = _owned_room(uuid.uuid4())  # 타 제공자 룸
    mine = _list_reservation(
        booker_id=uuid.uuid4(),
        room_id=my_room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2099-01-05T05:00:00Z"],
        created_at=datetime(2026, 6, 17, 0, tzinfo=UTC),
    )
    theirs = _list_reservation(
        booker_id=uuid.uuid4(),
        room_id=other_room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2099-01-06T05:00:00Z"],
        created_at=datetime(2026, 6, 17, 0, tzinfo=UTC),
    )
    # 두 룸·두 예약을 모두 세션에 담아도, 소유 룸(me)만 조회 대상이라 타 제공자 예약은 빠진다.
    session = FakeProviderSession(rooms=[my_room, other_room], reservations=[mine, theirs])
    with _override_session(session):
        resp = client.get(
            _PROVIDER_URL,
            headers={"Authorization": f"Bearer {create_access_token(me, 'provider')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()["items"]
    assert [item["id"] for item in body] == [str(mine.id)]  # 본인 룸 예약만


def test_list_provider_reservations_orders_created_at_desc(auth_env: None) -> None:
    """소유 룸 예약을 created_at 내림차순(최근 먼저)으로 반환한다(AC1)."""
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    older = _list_reservation(
        booker_id=uuid.uuid4(),
        room_id=room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2099-01-05T05:00:00Z"],
        created_at=datetime(2026, 6, 10, 0, tzinfo=UTC),
    )
    newer = _list_reservation(
        booker_id=uuid.uuid4(),
        room_id=room.id,
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2099-01-06T05:00:00Z"],
        created_at=datetime(2026, 6, 16, 0, tzinfo=UTC),
    )
    session = FakeProviderSession(rooms=[room], reservations=[older, newer])
    with _override_session(session):
        resp = client.get(
            _PROVIDER_URL,
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 200, resp.text
    ids = [item["id"] for item in resp.json()["items"]]
    assert ids == [str(newer.id), str(older.id)]  # 최근 먼저


def test_list_provider_reservations_terminal_retains_snapshot(auth_env: None) -> None:
    """취소/거절 예약도 status·slot_starts(스냅샷)으로 잔존 표시된다(점유 행 DELETE 무관, AC1)."""
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    rejected = _list_reservation(
        booker_id=uuid.uuid4(),
        room_id=room.id,
        status=ReservationStatus.REJECTED,
        slot_starts=["2099-01-05T05:00:00Z"],  # 점유 행 DELETE됐어도 스냅샷 잔존
        created_at=datetime(2026, 6, 17, 1, tzinfo=UTC),
    )
    cancelled = _list_reservation(
        booker_id=uuid.uuid4(),
        room_id=room.id,
        status=ReservationStatus.CANCELLED,
        slot_starts=["2099-01-06T05:00:00Z"],
        created_at=datetime(2026, 6, 17, 0, tzinfo=UTC),
    )
    session = FakeProviderSession(rooms=[room], reservations=[rejected, cancelled])
    with _override_session(session):
        resp = client.get(
            _PROVIDER_URL,
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 200, resp.text
    by_id = {item["id"]: item for item in resp.json()["items"]}
    assert by_id[str(rejected.id)]["status"] == "rejected"
    assert by_id[str(rejected.id)]["slot_starts"] == ["2099-01-05T05:00:00Z"]
    assert by_id[str(cancelled.id)]["status"] == "cancelled"


def test_list_provider_reservations_no_rooms_returns_empty(auth_env: None) -> None:
    """소유 룸이 0개면 빈 리스트(정상 200 — 예약 조회 자체 미발행)."""
    session = FakeProviderSession(rooms=[], reservations=[])
    with _override_session(session):
        resp = client.get(
            _PROVIDER_URL,
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["next_cursor"] is None


def test_list_provider_reservations_no_reservations_returns_empty(auth_env: None) -> None:
    """소유 룸은 있으나 예약이 0개면 빈 리스트(정상 200)."""
    provider_id = uuid.uuid4()
    session = FakeProviderSession(rooms=[_owned_room(provider_id)], reservations=[])
    with _override_session(session):
        resp = client.get(
            _PROVIDER_URL,
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["next_cursor"] is None


def test_list_provider_reservations_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401 UNAUTHENTICATED."""
    session = FakeProviderSession()
    with _override_session(session):
        resp = client.get(_PROVIDER_URL)
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_list_provider_reservations_booker_returns_403(auth_env: None) -> None:
    """booker 토큰 → 403 FORBIDDEN_ROLE(제공자 예약현황은 provider 전용)."""
    session = FakeProviderSession()
    with _override_session(session):
        resp = client.get(
            _PROVIDER_URL, headers={"Authorization": f"Bearer {_booker_token()}"}
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_list_provider_reservations_admin_returns_403(auth_env: None) -> None:
    """admin 토큰 → 403 FORBIDDEN_ROLE(provider 전용 — 본인 소유 룸 경계)."""
    session = FakeProviderSession()
    with _override_session(session):
        resp = client.get(
            _PROVIDER_URL, headers={"Authorization": f"Bearer {_admin_token()}"}
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


# ═══════════════════════════════════════════════════════════════════════════════════
# 제공자 거절 엔드포인트 POST /provider/reservations/{id}/reject (Story 6.2 — AC1~AC5)
# ═══════════════════════════════════════════════════════════════════════════════════

# 거절 시작-후 게이트 거부 시 고정 한국어 카피(UX-DR10 — 정확 문자열 단언, UTF-8).
_REJECT_COPY = "이미 시작된 예약은 거절할 수 없어요."
_REJECT_URL = "/api/v1/provider/reservations"


class FakeRejectSession:
    """제공자 거절 엔드포인트용 Fake 세션 — get(Reservation)+get(Room) 소유권 + 거절 전이 + 통지.

    라우터는 ``get(Reservation, id)``·``get(Room, room_id)``로 소유권을 검사하고, service 래퍼가
    ``exec(select).all()``(earliest_slot_start) → ``exec(update)``(조건부 종료 전이) →
    ``exec(delete)``(슬롯 재활성) → ``add(Notification)``(통지 staging) → ``commit``/``refresh``를
    호출한다. **통지 원자화(Story 8.3):** 거절 통지는 이제 라우터의 별도 ``create_notification``이
    아니라 **service가 전이 commit과 동일 트랜잭션에서 staged**한다(``stage_status_change``
    → ``session.add(Notification)``, commit은 전이가). ``added``의 Notification으로 통지 생성 여부·
    필드를 단언하는 spy는 staging 위치가 router→service로 옮겨가도 그대로 동작한다(통지 row 존재
    단언 — caller 무관). ``slot_starts``로 시작-전/후 게이트 입력을, ``stored``/``room``으로 소유권
    분기를 제어한다.
    """

    def __init__(
        self,
        *,
        stored: Reservation | None = None,
        room: Room | None = None,
        slot_starts: list[datetime] | None = None,
    ) -> None:
        self.stored = stored
        self.room = room
        self.slot_starts = slot_starts or []
        self.added: list[Any] = []
        self.committed = False
        self.refreshed = 0
        self.rolled_back = False
        self.exec_calls: list[Any] = []

    def get(self, model: Any, pk: Any) -> Any:
        if model is Reservation and self.stored is not None and self.stored.id == pk:
            return self.stored
        if model is Room and self.room is not None and self.room.id == pk:
            return self.room
        return None

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        self.exec_calls.append(statement)
        if _is_update(statement):
            return _apply_conditional_terminal_update(
                statement, [self.stored] if self.stored is not None else []
            )
        return _FakeResult(self.slot_starts)  # earliest_slot_start의 .all() 경로

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, obj: Any) -> None:
        self.refreshed += 1

    def rollback(self) -> None:
        self.rolled_back = True

    @property
    def created_notifications(self) -> list[Notification]:
        return [o for o in self.added if isinstance(o, Notification)]


def _reject_url(reservation_id: Any) -> str:
    return f"{_REJECT_URL}/{reservation_id}/reject"


# ── 성공 거절 + 통지 생성 (AC1·AC2) ────────────────────────────────────────────
def test_reject_reservation_owner_returns_200(auth_env: None) -> None:
    """provider 본인 룸 confirmed 예약(시작 전) 거절 → 200·rejected·slot_starts=[]·통지 1건."""
    provider_id = uuid.uuid4()
    booker_id = uuid.uuid4()
    room = _owned_room(provider_id)
    reservation = _reservation(
        booker_id=booker_id, room_id=room.id, status=ReservationStatus.CONFIRMED
    )
    session = FakeRejectSession(
        stored=reservation, room=room, slot_starts=[_FAR_FUTURE_SLOT]
    )
    with _override_session(session):
        resp = client.post(
            _reject_url(reservation.id),
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == _RESERVATION_KEYS
    assert body["status"] == "rejected"
    assert body["slot_starts"] == []  # 거절 후 점유 0(재활성)
    assert session.committed is True
    # AC2: 예약자에게 status_change/reason='rejected' 통지 1건 생성(거절 성공 시).
    notes = session.created_notifications
    assert len(notes) == 1
    note = notes[0]
    assert note.user_id == booker_id  # 예약자에게(provider 아님)
    assert note.reservation_id == reservation.id
    assert note.type == str(NotificationType.STATUS_CHANGE)
    assert note.reason == "rejected"  # 정확히 'rejected'(오타 금지 — FE 분기 키)


# ── 멱등: 이미 종료 상태 (AC2·AC3) ─────────────────────────────────────────────
def test_reject_reservation_already_rejected_idempotent(auth_env: None) -> None:
    """이미 rejected인 예약 재거절 → 200·현재 상태·통지 0(was_confirmed 거짓 — 멱등)."""
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    reservation = _reservation(
        booker_id=uuid.uuid4(), room_id=room.id, status=ReservationStatus.REJECTED
    )
    session = FakeRejectSession(stored=reservation, room=room, slot_starts=[])
    with _override_session(session):
        resp = client.post(
            _reject_url(reservation.id),
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"
    assert session.committed is False  # 멱등 no-op(쓰기 0)
    assert session.created_notifications == []  # 통지 0(전이 미수행)


def test_reject_reservation_already_cancelled_no_notification(auth_env: None) -> None:
    """booker가 먼저 취소(cancelled)한 예약 거절 시도 → 200·cancelled·통지 0(AC2 race 정확성).

    was_confirmed 거짓(종료 상태) → 통지 생성 안 함. "거절 안 했는데 거절 통지" 비결정성 제거.
    """
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    reservation = _reservation(
        booker_id=uuid.uuid4(), room_id=room.id, status=ReservationStatus.CANCELLED
    )
    session = FakeRejectSession(stored=reservation, room=room, slot_starts=[])
    with _override_session(session):
        resp = client.post(
            _reject_url(reservation.id),
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"  # 취소 상태 유지(거절로 둔갑 안 함)
    assert session.created_notifications == []  # 거절 통지 0(was_confirmed 거짓)


# ── 시작 후 게이트 (AC3) ────────────────────────────────────────────────────────
def test_reject_reservation_after_start_returns_409(auth_env: None) -> None:
    """이미 시작된(earliest <= now) 예약 거절 → 409 REJECT_WINDOW_PASSED·고정 카피·전이/통지 0."""
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    reservation = _reservation(
        booker_id=uuid.uuid4(), room_id=room.id, status=ReservationStatus.CONFIRMED
    )
    session = FakeRejectSession(
        stored=reservation, room=room, slot_starts=[_FAR_PAST_SLOT]
    )
    with _override_session(session):
        resp = client.post(
            _reject_url(reservation.id),
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "REJECT_WINDOW_PASSED"
    assert detail["message"] == _REJECT_COPY  # 고정 카피(코드·숫자 노출 X)
    assert session.committed is False  # 상태 전이·슬롯 변경 0
    assert session.created_notifications == []  # 통지 0


# ── RBAC + 소유권 (AC5) ─────────────────────────────────────────────────────────
def test_reject_reservation_other_provider_room_returns_404(auth_env: None) -> None:
    """타 제공자 룸의 예약 거절 시도 → 404 RESERVATION_NOT_FOUND(403 아님 — 존재 누설 금지)."""
    me = uuid.uuid4()
    other_provider = uuid.uuid4()
    room = _owned_room(other_provider)  # 타 제공자 소유 룸
    reservation = _reservation(
        booker_id=uuid.uuid4(), room_id=room.id, status=ReservationStatus.CONFIRMED
    )
    session = FakeRejectSession(
        stored=reservation, room=room, slot_starts=[_FAR_FUTURE_SLOT]
    )
    with _override_session(session):
        resp = client.post(
            _reject_url(reservation.id),
            headers={"Authorization": f"Bearer {create_access_token(me, 'provider')}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RESERVATION_NOT_FOUND"
    assert session.committed is False
    assert session.created_notifications == []


def test_reject_reservation_unknown_id_returns_404(auth_env: None) -> None:
    """미존재 예약 id → 404 RESERVATION_NOT_FOUND."""
    session = FakeRejectSession(stored=None)  # get → None
    with _override_session(session):
        resp = client.post(
            _reject_url(uuid.uuid4()),
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RESERVATION_NOT_FOUND"


def test_reject_reservation_room_missing_returns_404(auth_env: None) -> None:
    """예약은 있으나 룸을 못 찾으면 → 404(도달 불가 방어 경로 — 소유권 판정 불가)."""
    provider_id = uuid.uuid4()
    reservation = _reservation(
        booker_id=uuid.uuid4(), room_id=uuid.uuid4(), status=ReservationStatus.CONFIRMED
    )
    # room=None → 소유권 판정 불가 → 404(누설 금지).
    session = FakeRejectSession(stored=reservation, room=None, slot_starts=[_FAR_FUTURE_SLOT])
    with _override_session(session):
        resp = client.post(
            _reject_url(reservation.id),
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RESERVATION_NOT_FOUND"


def test_reject_reservation_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401 UNAUTHENTICATED."""
    session = FakeRejectSession(stored=None)
    with _override_session(session):
        resp = client.post(_reject_url(uuid.uuid4()))
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_reject_reservation_booker_returns_403(auth_env: None) -> None:
    """booker 토큰 → 403 FORBIDDEN_ROLE(거절은 provider 전용)."""
    session = FakeRejectSession(stored=None)
    with _override_session(session):
        resp = client.post(
            _reject_url(uuid.uuid4()),
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_reject_reservation_admin_returns_403(auth_env: None) -> None:
    """admin 토큰 → 403 FORBIDDEN_ROLE(provider 전용)."""
    session = FakeRejectSession(stored=None)
    with _override_session(session):
        resp = client.post(
            _reject_url(uuid.uuid4()),
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


# ═══════════════════════════════════════════════════════════════════════════════════
# 커서 페이징 (F — 목록 무한스크롤): 본인/제공자 예약현황 keyset 페이지 경계·전수 일치
# ═══════════════════════════════════════════════════════════════════════════════════


def _seed_booker_reservations(
    booker_id: uuid.UUID, room: Any, count: int
) -> list[Reservation]:
    """한 booker의 예약 count건을 created_at 내림차순으로 시드한다(최신=인덱스 0).

    created_at은 1시간 간격으로 분리해 keyset (created_at desc, id desc) 경계를 결정적으로 만든다.
    """
    base = datetime(2026, 6, 17, tzinfo=UTC)
    return [
        _list_reservation(
            booker_id=booker_id,
            room_id=room.id,
            status=ReservationStatus.CONFIRMED,
            slot_starts=["2099-01-05T05:00:00Z"],
            created_at=base - timedelta(hours=i),  # i=0이 가장 최근
        )
        for i in range(count)
    ]


def _walk_pages(client_get) -> list[dict]:
    """첫 페이지부터 next_cursor를 따라 끝까지 순회해 모든 item을 순서대로 모은다.

    ``client_get(cursor)``는 cursor(None=첫 페이지)를 받아 응답을 돌려주는 콜러블이다. 마지막
    페이지의 ``next_cursor``는 None이어야 한다(루프 종료 조건 = 전수 일치·중복/누락 0 검증의 토대).
    """
    collected: list[dict] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        resp = client_get(cursor)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        collected.extend(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
        assert cursor not in seen_cursors, "커서 무한 루프(동일 토큰 재방문)"
        seen_cursors.add(cursor)
    return collected


def test_list_reservations_pagination_walks_all_pages(auth_env: None) -> None:
    """limit=2로 5건 페이징 → 첫 페이지 2건+next_cursor, 합집합이 전체와 순서까지 일치."""
    booker_id = uuid.uuid4()
    room = _avail_room()
    seeded = _seed_booker_reservations(booker_id, room, 5)
    session = FakeListSession(
        reservations=list(seeded), rooms=[room], owner_id=booker_id
    )
    token = create_access_token(booker_id, "booker")

    def _get(cursor: str | None):
        params = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        with _override_session(session):
            return client.get(
                _LIST_URL, params=params, headers={"Authorization": f"Bearer {token}"}
            )

    # 첫 페이지 — 정확히 limit개 + next_cursor 존재.
    first = _get(None).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    # 전 페이지 순회 — 중복/누락 0, created_at desc(=시드 인덱스 순서)와 정확히 일치.
    collected = _walk_pages(_get)
    ids = [item["id"] for item in collected]
    assert ids == [str(r.id) for r in seeded]  # 최신순 전수 일치(순서 포함)
    assert len(ids) == len(set(ids)) == 5  # 중복 없음


def test_list_reservations_pagination_last_page_cursor_none(auth_env: None) -> None:
    """항목 수가 limit의 배수면 마지막 페이지(잔여 0)에서도 next_cursor는 None이다."""
    booker_id = uuid.uuid4()
    room = _avail_room()
    seeded = _seed_booker_reservations(booker_id, room, 4)  # limit=2 → 2페이지 딱 맞음
    session = FakeListSession(
        reservations=list(seeded), rooms=[room], owner_id=booker_id
    )
    token = create_access_token(booker_id, "booker")
    with _override_session(session):
        first = client.get(
            _LIST_URL, params={"limit": 2}, headers={"Authorization": f"Bearer {token}"}
        ).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None
    with _override_session(session):
        second = client.get(
            _LIST_URL,
            params={"limit": 2, "cursor": first["next_cursor"]},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
    assert len(second["items"]) == 2
    assert second["next_cursor"] is None  # 마지막 페이지(잔여 0)


def test_list_reservations_invalid_cursor_returns_422(auth_env: None) -> None:
    """손상 커서(base64 아님) → 422 VALIDATION_ERROR(조용한 1페이지 폴백 금지)."""
    booker_id = uuid.uuid4()
    session = FakeListSession(reservations=[], rooms=[], owner_id=booker_id)
    with _override_session(session):
        resp = client.get(
            _LIST_URL,
            params={"cursor": "!!!invalid"},
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def _seed_provider_reservations(room: Any, count: int) -> list[Reservation]:
    """한 룸의 예약 count건을 created_at 내림차순으로 시드한다(예약자는 임의)."""
    base = datetime(2026, 6, 17, tzinfo=UTC)
    return [
        _list_reservation(
            booker_id=uuid.uuid4(),
            room_id=room.id,
            status=ReservationStatus.CONFIRMED,
            slot_starts=["2099-01-05T05:00:00Z"],
            created_at=base - timedelta(hours=i),
        )
        for i in range(count)
    ]


def test_list_provider_reservations_pagination_walks_all_pages(auth_env: None) -> None:
    """provider limit=2로 5건 페이징 → 첫 페이지 2건+next_cursor, 합집합이 전체와 순서까지 일치."""
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    seeded = _seed_provider_reservations(room, 5)
    session = FakeProviderSession(rooms=[room], reservations=list(seeded))
    token = create_access_token(provider_id, "provider")

    def _get(cursor: str | None):
        params = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        with _override_session(session):
            return client.get(
                _PROVIDER_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )

    first = _get(None).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    collected = _walk_pages(_get)
    ids = [item["id"] for item in collected]
    assert ids == [str(r.id) for r in seeded]  # created_at desc 전수 일치(순서 포함)
    assert len(ids) == len(set(ids)) == 5  # 중복 없음


def test_list_provider_reservations_invalid_cursor_returns_422(auth_env: None) -> None:
    """provider 손상 커서 → 422 VALIDATION_ERROR."""
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    session = FakeProviderSession(rooms=[room], reservations=[])
    with _override_session(session):
        resp = client.get(
            _PROVIDER_URL,
            params={"cursor": "!!!invalid"},
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"
