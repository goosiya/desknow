"""rooms 서비스 테스트 (Story 2.1 슬롯 도출 + 2.2 쓰기/지오코딩).

DB 불필요 — ``derive_slots``는 순수 함수라 입력→출력을 직접 단언한다(Fake 불필요).
``create_room``은 Fake 세션으로(제공자당 1개 선검사·P2 선별 변환), ``geocode_address``는
``httpx.MockTransport``로(라이브 카카오 호출 0 — 결정적, 회고 A2) 실증한다.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.db import violated_constraint
from app.core.errors import DomainError, ErrorCode
from app.reservations.models import ReservationSlot
from app.rooms import service
from app.rooms.models import BusinessHours, HolidayException, Room
from app.rooms.schemas import BusinessHoursInput, RoomCreateRequest, RoomUpdateRequest
from app.rooms.service import (
    _RESERVATION_HORIZON_DAYS,
    aggregate_availability,
    create_room,
    derive_slots,
    geocode_address,
    get_room_slots,
    get_room_summary,
    list_active_rooms,
    list_provider_rooms,
    list_regions,
    room_remaining_slots,
    search_rooms,
    update_room,
)


def _bh(weekday: int, open_h: int, close_h: int) -> BusinessHours:
    """테스트용 영업시간 행(정시 단위). room_id는 도출에 무관하나 모델 충실도 위해 채운다."""
    return BusinessHours(
        room_id=uuid.uuid4(),
        weekday=weekday,
        open_time=time(open_h, 0),
        close_time=time(close_h, 0),
    )


# 요일이 명확한 고정 날짜: 2026-06-15는 월요일(weekday()==0). 테스트는 .weekday()로 재확인.
MONDAY = date(2026, 6, 15)


def test_monday_full_day_13_slots_kst_to_utc() -> None:
    """09:00~22:00 KST 평일 → 1h 슬롯 13개. 첫=00:00:00Z(=09:00 KST−9h), 마지막=12:00:00Z."""
    assert MONDAY.weekday() == 0  # 월요일 전제 확인
    slots = derive_slots([_bh(0, 9, 22)], holiday_dates=set(), target_date=MONDAY)

    assert len(slots) == 13  # 09,10,...,21시 시작 = 13개(22시 시작은 22+1>22라 제외)
    # 09:00 KST = 00:00 UTC(같은 날짜), 21:00 KST = 12:00 UTC.
    assert slots[0] == datetime(2026, 6, 15, 0, 0, tzinfo=UTC)
    assert slots[-1] == datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    # 1시간 간격·오름차순(인접 쌍 — 의도적으로 한 칸 어긋난 zip이라 strict 불가).
    for earlier, later in zip(slots, slots[1:]):  # noqa: B905
        assert (later - earlier).total_seconds() == 3600


def test_all_returned_slot_starts_are_utc_aware() -> None:
    """모든 반환 slot_start의 tzinfo가 UTC다(AC3 — 저장은 UTC)."""
    slots = derive_slots([_bh(0, 9, 22)], holiday_dates=set(), target_date=MONDAY)
    assert slots  # 비어있지 않음
    assert all(s.tzinfo == UTC for s in slots)


def test_holiday_returns_empty() -> None:
    """휴무일이면 영업시간이 있어도 슬롯 0(규칙 ①)."""
    slots = derive_slots(
        [_bh(0, 9, 22)], holiday_dates={MONDAY}, target_date=MONDAY
    )
    assert slots == []


def test_non_business_weekday_returns_empty() -> None:
    """대상 날짜 요일에 영업행이 없으면 슬롯 0(규칙 ②). (행은 화요일=1, 대상은 월요일=0)"""
    slots = derive_slots([_bh(1, 9, 22)], holiday_dates=set(), target_date=MONDAY)
    assert slots == []


def test_no_business_hours_at_all_returns_empty() -> None:
    """영업시간 행이 전혀 없으면 슬롯 0."""
    assert derive_slots([], holiday_dates=set(), target_date=MONDAY) == []


def test_reserved_starts_are_subtracted() -> None:
    """reserved_starts에 든 slot_start는 제외된다(규칙 ⑤ — 비어있지 않은 집합 전달)."""
    full = derive_slots([_bh(0, 9, 22)], holiday_dates=set(), target_date=MONDAY)
    # 첫 슬롯(00:00Z)과 마지막 슬롯(12:00Z)을 예약 처리.
    reserved = {full[0], full[-1]}
    remaining = derive_slots(
        [_bh(0, 9, 22)], holiday_dates=set(), target_date=MONDAY, reserved_starts=reserved
    )
    assert len(remaining) == len(full) - 2
    assert full[0] not in remaining
    assert full[-1] not in remaining
    # 나머지는 그대로 보존.
    assert remaining == [s for s in full if s not in reserved]


def test_partial_trailing_hour_excluded() -> None:
    """부분 잔여 시간(<1h)은 제외 = 고정 1시간(규칙 ③).

    09:00~10:30 → 09:00 슬롯만(09+1=10:00<=10:30 OK, 10:00+1=11:00>10:30 제외).
    """
    bh = BusinessHours(
        room_id=uuid.uuid4(), weekday=0, open_time=time(9, 0), close_time=time(10, 30)
    )
    slots = derive_slots([bh], holiday_dates=set(), target_date=MONDAY)
    assert slots == [datetime(2026, 6, 15, 0, 0, tzinfo=UTC)]  # 09:00 KST = 00:00 UTC


def test_last_slot_exactly_meets_close() -> None:
    """마지막 슬롯이 정확히 close에 맞물리면 포함(경계: walltime+1h == close → <= 참)."""
    slots = derive_slots([_bh(0, 9, 11)], holiday_dates=set(), target_date=MONDAY)
    # 09:00, 10:00 시작 = 2개(10+1=11=close 포함, 11+1>11 제외).
    assert len(slots) == 2
    assert slots[-1] == datetime(2026, 6, 15, 1, 0, tzinfo=UTC)  # 10:00 KST = 01:00 UTC


def test_one_hour_window_yields_single_slot() -> None:
    """정확히 1시간 영업이면 슬롯 1개(경계 최소)."""
    slots = derive_slots([_bh(0, 9, 10)], holiday_dates=set(), target_date=MONDAY)
    assert slots == [datetime(2026, 6, 15, 0, 0, tzinfo=UTC)]


def test_evening_hours_stay_same_utc_date() -> None:
    """저녁 KST 영업의 UTC 변환 — 같은 UTC 날짜에 머문다(경계 미교차).

    18:00~22:00 KST = 09:00~13:00 UTC로 **target_date와 같은 UTC 날짜**(2026-06-15).
    KST 오후/저녁(09시 이후)은 −9h 해도 음수가 아니라 UTC 날짜가 유지된다. 진짜
    역방향 경계(전일 UTC로 넘어가는 경우)는 ``test_morning_hours_map_to_previous_utc_date``.
    """
    slots = derive_slots([_bh(0, 18, 22)], holiday_dates=set(), target_date=MONDAY)
    assert slots[0] == datetime(2026, 6, 15, 9, 0, tzinfo=UTC)  # 18:00 KST
    assert slots[-1] == datetime(2026, 6, 15, 12, 0, tzinfo=UTC)  # 21:00 KST
    assert len(slots) == 4  # 18,19,20,21시 시작
    assert all(s.date() == date(2026, 6, 15) for s in slots)  # UTC 날짜 = target_date


def test_morning_hours_map_to_previous_utc_date() -> None:
    """이른 아침 KST 영업 → slot_start의 UTC 날짜가 target_date **전일**이 된다(진짜 경계).

    06:00 KST = 전일 21:00 UTC(−9h). target_date=2026-06-15(월)인데 slot_start의 UTC
    날짜는 2026-06-14다. derive_slots는 target_date를 KST 벽시계 기준으로만 쓰고
    slot_start를 UTC 인스턴트로 변환하므로 두 날짜가 갈린다 — AC3(UTC 저장)의 핵심이
    실제로 동작함을 검증한다(기존 저녁 테스트는 경계를 넘지 않아 이 성질을 못 잡았다).
    """
    slots = derive_slots([_bh(0, 6, 9)], holiday_dates=set(), target_date=MONDAY)
    assert len(slots) == 3  # 06,07,08시 시작(08+1=09=close 포함)
    assert slots[0] == datetime(2026, 6, 14, 21, 0, tzinfo=UTC)  # 06:00 KST = 전일 21:00 UTC
    assert slots[-1] == datetime(2026, 6, 14, 23, 0, tzinfo=UTC)  # 08:00 KST = 전일 23:00 UTC
    # 모든 slot_start의 UTC 날짜가 target_date(06-15)와 다른 전일(06-14)이다.
    assert all(s.date() == date(2026, 6, 14) for s in slots)


def test_naive_reserved_start_rejected() -> None:
    """naive reserved_start는 ValueError로 거부된다(조용한 차감 실패 방지 — fail-fast)."""
    with pytest.raises(ValueError):
        derive_slots(
            [_bh(0, 9, 22)],
            holiday_dates=set(),
            target_date=MONDAY,
            reserved_starts={datetime(2026, 6, 15, 0, 0)},  # naive(tz 없음)
        )


def test_datetime_in_holiday_dates_rejected() -> None:
    """holiday_dates에 datetime이 섞이면 ValueError(date==datetime은 항상 False → 조용한 무시)."""
    with pytest.raises(ValueError):
        derive_slots(
            [_bh(0, 9, 22)],
            holiday_dates={datetime(2026, 6, 15, 0, 0)},  # date가 아닌 datetime
            target_date=MONDAY,
        )


def test_datetime_target_date_rejected() -> None:
    """target_date가 datetime이면 ValueError로 거부된다(date여야 함)."""
    with pytest.raises(ValueError):
        derive_slots(
            [_bh(0, 9, 22)], holiday_dates=set(), target_date=datetime(2026, 6, 15)
        )


# ── 쓰기 서비스 create_room (Story 2.2 — AC1·AC4·P2) ──────────────────────────
class _FakeDiag:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _FakeOrig(Exception):
    """psycopg orig 모방 — diag.constraint_name 노출(P2 violated_constraint 실증)."""

    def __init__(self, constraint_name: str | None) -> None:
        super().__init__("integrity violation")
        self.diag = _FakeDiag(constraint_name)


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def first(self) -> Any:
        return self._value

    def all(self) -> list[Any]:
        """select(BusinessHours) 결과(기존 영업시간 행 리스트)용 — 2.3 update_room."""
        return list(self._value) if isinstance(self._value, list) else []


class FakeRoomSession:
    """rooms 쓰기 서비스용 Fake 세션(create_room 2.2 + update_room 2.3).

    - ``exec(select(Room))`` → ``existing_room``(create 선검사). ``exec(select(BusinessHours))``
      → ``business_hours_rows``(update 영업시간 교체 — entity 분기, 1.8 introspection 확장 선례).
    - ``get(Room, pk)`` → ``stored_room``(pk 일치 시) 또는 ``None``(update 소유권/존재 검사).
    - ``delete``/``flush`` 기록(update 영업시간 교체 충실도 — 삭제 건수·flush 선행 단언).
    - ``commit``은 ``raise_on_commit`` 시 제약명 있는 ``IntegrityError``를 던진다(P2 분기 실증).
    """

    def __init__(
        self,
        existing_room: Room | None = None,
        raise_on_commit: bool = False,
        commit_violation: str | None = None,
        stored_room: Room | None = None,
        business_hours_rows: list[BusinessHours] | None = None,
    ) -> None:
        self.existing_room = existing_room
        self.raise_on_commit = raise_on_commit
        self.commit_violation = commit_violation
        self.stored_room = stored_room
        self.business_hours_rows = business_hours_rows or []
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.get_calls: list[tuple[Any, Any]] = []
        self.exec_entities: list[Any] = []  # exec가 조회한 ORM 엔티티(독립성 단언용)
        self.committed = False
        self.rolled_back = False
        self.flushed = False
        self.flushed_before_add = False  # DELETE flush가 신규 add보다 선행했는가

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        # 조회 대상 엔티티를 introspect해 분기한다(create=Room 선검사, update=BusinessHours 교체).
        entity = None
        descriptions = getattr(statement, "column_descriptions", None)
        if descriptions:
            entity = descriptions[0].get("entity")
        self.exec_entities.append(entity)
        if entity is BusinessHours:
            return _FakeResult(self.business_hours_rows)
        return _FakeResult(self.existing_room)

    def get(self, model: Any, pk: Any) -> Any:
        self.get_calls.append((model, pk))
        if self.stored_room is not None and getattr(self.stored_room, "id", None) == pk:
            return self.stored_room
        return None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    def flush(self) -> None:
        self.flushed = True
        # 이 시점에 아직 신규 BusinessHours가 add되지 않았다면 DELETE 선행이 보장된다.
        if not any(isinstance(o, BusinessHours) for o in self.added):
            self.flushed_before_add = True

    def commit(self) -> None:
        if self.raise_on_commit:
            raise IntegrityError("stmt", {}, _FakeOrig(self.commit_violation))
        self.committed = True

    def refresh(self, obj: Any) -> None:
        pass

    def rollback(self) -> None:
        self.rolled_back = True


class FakeAvailabilitySession:
    """가용성 집계용 Fake 세션(aggregate_availability 3.1 — 읽기 전용).

    ``create_room``의 ``.first()`` 선검사 시맨틱(``FakeRoomSession``)과 **분리**한다(회고 ⑤
    Fake 충실도). 집계는 Room/BusinessHours/HolidayException을 모두 ``.all()`` 리스트로 조회하므로
    entity introspection(``column_descriptions[0]["entity"]``, 2.3 선례)으로 분기해 각 리스트를
    돌려준다. Room 조회는 실 SQL ``where(is_active)``를 모사해 **활성 룸만** 반환한다(필터 충실도).
    읽기 전용이라 ``commit``/``add``/``delete``를 노출하지 않는다 — 집계가 그것들을 호출하면
    ``AttributeError``로 즉시 깨져 "쓰기 없음"(Task 2)을 구조적으로 단언한다.
    """

    def __init__(
        self,
        rooms: list[Room] | None = None,
        business_hours: list[BusinessHours] | None = None,
        holidays: list[HolidayException] | None = None,
        reservation_slots: list[ReservationSlot] | None = None,
    ) -> None:
        self.rooms = rooms or []
        self.business_hours = business_hours or []
        self.holidays = holidays or []
        # Story 4.9: 활성 점유 행(예약 차감 reader가 조회). 기본 [] → 차감 없음(4.9 전 동작 보존).
        self.reservation_slots = reservation_slots or []
        self.exec_entities: list[Any] = []  # 조회한 ORM 엔티티 기록(읽기 범위 단언용)

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        entity = None
        descriptions = getattr(statement, "column_descriptions", None)
        if descriptions:
            entity = descriptions[0].get("entity")
        self.exec_entities.append(entity)
        if entity is BusinessHours:
            return _FakeResult(self.business_hours)
        if entity is HolidayException:
            return _FakeResult(self.holidays)
        if entity is ReservationSlot:
            # Story 4.9 예약 차감 reader. 실 SQL의 room_id 필터(단건 ==·벌크 IN)와 on_or_after(>=)를
            # **컴파일된 bind 파라미터로 충실히 재현**한다(Fake가 쿼리를 해석 — 룸 격리/과거 제외를
            # 단위에서 단언 가능하게). 단건 reader는 1-컬럼(slot_start 스칼라), 벌크는 2-컬럼
            # (room_id, slot_start) 튜플을 반환한다.
            return _FakeResult(self._reservation_rows(statement, len(descriptions or [])))
        # Room: 실 SQL where(is_active)를 모사 — 활성 룸만 반환한다(비활성 제외 충실도).
        return _FakeResult([r for r in self.rooms if r.is_active])

    def _reservation_rows(self, statement: Any, n_cols: int) -> list[Any]:
        """ReservationSlot select에 room_id/on_or_after 필터를 적용한 행을 만든다(4.9 reader 모사).

        ``confirmed_slot_starts``(단건 ``where(room_id == X)``)는 ``room_id_1``이 단일 UUID,
        ``confirmed_slot_starts_by_room``(벌크 ``where(room_id.in_([...]))``)는 ``room_id_1``이
        UUID 리스트로 컴파일된다(둘 다 ``on_or_after`` 주면 ``slot_start_1``). 그 파라미터로
        실제 WHERE를 재현해, 단건=1-컬럼 스칼라 / 벌크=2-컬럼 튜플로 돌려준다.
        """
        params = statement.compile().params
        room_filter = params.get("room_id_1")
        on_or_after = params.get("slot_start_1")
        rows = list(self.reservation_slots)
        if on_or_after is not None:
            rows = [r for r in rows if r.slot_start >= on_or_after]
        if isinstance(room_filter, (list, tuple)):  # 벌크 IN
            rows = [r for r in rows if r.room_id in room_filter]
        elif room_filter is not None:  # 단건 ==
            rows = [r for r in rows if r.room_id == room_filter]
        if n_cols == 2:  # 벌크: (room_id, slot_start) 튜플
            return [(r.room_id, r.slot_start) for r in rows]
        return [r.slot_start for r in rows]  # 단건: slot_start 스칼라

    def get(self, model: Any, pk: Any) -> Any:
        """``session.get(Room, pk)`` 모사(get_room_summary 3.3 — 단일 룸 조회).

        실 ``Session.get``처럼 **활성/비활성 무관 PK 일치 행**을 돌려준다(is_active 판정은
        서비스 책임 — 비활성 룸을 404로 합치려면 get은 그것을 찾아줘야 한다). 읽기 전용이라
        쓰기 메서드는 여전히 노출하지 않는다(쓰기 호출 시 AttributeError로 깨짐 = 구조적 단언).
        """
        for room in self.rooms:
            if getattr(room, "id", None) == pk:
                return room
        return None


def _avail_room(
    *,
    is_active: bool = True,
    admin_dong_code: str = "1168010100",
    lat: float = 37.5,
    lng: float = 127.0,
) -> Room:
    """가용성 집계 대상 룸(id 자동 채움 — 그룹핑 키로 사용).

    ``admin_dong_code``는 3.4 지역 필터/콤보 그룹핑 테스트가 시군구/동을 달리하려고 주입한다
    (기본=역삼동 — 기존 3.1/3.2 테스트 호환). ``lat``/``lng``는 3.5 반경 필터 테스트가 중심에서의
    거리를 달리하려고 주입한다(기본=기존 좌표 — 호환).
    """
    return Room(
        provider_id=uuid.uuid4(),
        name="집계룸",
        price_per_hour=10000,
        capacity=4,
        room_type="open",
        amenities=[],
        lat=lat,
        lng=lng,
        admin_dong_code=admin_dong_code,
        is_active=is_active,
    )


def _room_bh(room_id: uuid.UUID, weekday: int, open_h: int, close_h: int) -> BusinessHours:
    """특정 룸에 묶인 영업시간 행(정시 단위)."""
    return BusinessHours(
        room_id=room_id,
        weekday=weekday,
        open_time=time(open_h, 0),
        close_time=time(close_h, 0),
    )


def _res_slot(room_id: uuid.UUID, slot_start: datetime) -> ReservationSlot:
    """특정 룸의 활성 점유 행(Story 4.9 예약 차감 — reservation_id는 무관하나 모델 충실도로 채움).

    ``slot_start``는 UTC aware여야 한다(derive_slots 출력·차감 매칭과 동형). 취소/거절은 점유
    행을 DELETE하므로 테스트에선 "활성 점유"만 이 헬퍼로 넣는다(취소=행 부재로 모사).
    """
    return ReservationSlot(
        reservation_id=uuid.uuid4(), room_id=room_id, slot_start=slot_start
    )


def _room_request(**overrides: Any) -> RoomCreateRequest:
    base: dict[str, Any] = dict(
        name="테스트룸",
        price_per_hour=10000,
        capacity=4,
        room_type="open",
        amenities=["wifi", "parking"],
        lat=37.5,
        lng=127.0,
        admin_dong_code="1168010100",
        business_hours=[BusinessHoursInput(weekday=0, open_time=time(9), close_time=time(22))],
    )
    base.update(overrides)
    return RoomCreateRequest(**base)


def _existing_room(provider_id: uuid.UUID) -> Room:
    return Room(
        provider_id=provider_id,
        name="기존룸",
        price_per_hour=5000,
        capacity=2,
        room_type="private",
        amenities=[],
        lat=37.0,
        lng=127.0,
        admin_dong_code="1100000000",
    )


def test_create_room_persists_room_and_business_hours() -> None:
    """정상 등록: Room + BusinessHours를 add하고 commit한다(원자 — AC1)."""
    provider_id = uuid.uuid4()
    session = FakeRoomSession(existing_room=None)
    req = _room_request(
        business_hours=[
            BusinessHoursInput(weekday=0, open_time=time(9), close_time=time(18)),
            BusinessHoursInput(weekday=1, open_time=time(10), close_time=time(20)),
        ]
    )

    room = create_room(session, provider_id, req)  # type: ignore[arg-type]

    assert isinstance(room, Room)
    assert room.provider_id == provider_id
    assert room.room_type == "open"
    assert room.amenities == ["wifi", "parking"]
    assert session.committed is True
    rooms = [o for o in session.added if isinstance(o, Room)]
    bhs = [o for o in session.added if isinstance(o, BusinessHours)]
    assert len(rooms) == 1
    assert len(bhs) == 2  # 영업시간 2행
    assert all(bh.room_id == room.id for bh in bhs)  # 같은 트랜잭션 FK 연결


def test_create_room_precheck_rejects_second_room() -> None:
    """이미 룸 보유 제공자는 선검사에서 409 ROOM_LIMIT_REACHED(AC4)."""
    provider_id = uuid.uuid4()
    session = FakeRoomSession(existing_room=_existing_room(provider_id))

    with pytest.raises(DomainError) as exc_info:
        create_room(session, provider_id, _room_request())  # type: ignore[arg-type]

    assert exc_info.value.code is ErrorCode.ROOM_LIMIT_REACHED
    assert exc_info.value.status_code == 409
    assert session.added == []  # 삽입 시도 없음


def test_create_room_converts_unique_violation_to_room_limit() -> None:
    """경합: uq_rooms_provider_id 위반 IntegrityError → ROOM_LIMIT_REACHED 변환(P2)."""
    provider_id = uuid.uuid4()
    session = FakeRoomSession(
        existing_room=None, raise_on_commit=True, commit_violation="uq_rooms_provider_id"
    )

    with pytest.raises(DomainError) as exc_info:
        create_room(session, provider_id, _room_request())  # type: ignore[arg-type]

    assert exc_info.value.code is ErrorCode.ROOM_LIMIT_REACHED
    assert session.rolled_back is True


def test_create_room_reraises_unrelated_integrity_error() -> None:
    """무관한 제약 위반은 ROOM_LIMIT_REACHED로 오변환하지 않고 re-raise한다(P2 핵심)."""
    provider_id = uuid.uuid4()
    session = FakeRoomSession(
        existing_room=None, raise_on_commit=True, commit_violation="ck_rooms_room_type"
    )

    with pytest.raises(IntegrityError):
        create_room(session, provider_id, _room_request())  # type: ignore[arg-type]

    assert session.rolled_back is True
    assert session.committed is False


# ── 수정 서비스 update_room (Story 2.3 — AC1·AC2·AC4·P2) ──────────────────────
def _owned_room(provider_id: uuid.UUID) -> Room:
    """update_room 대상 룸(소유자=provider_id). id가 채워져 get(Room, room.id)로 조회 가능."""
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


def test_update_room_partial_changes_only_provided_fields() -> None:
    """정상 부분 수정: name만 변경 → 다른 필드 불변, commit(PATCH 시맨틱 — AC1)."""
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    session = FakeRoomSession(stored_room=room)

    result = update_room(
        session,  # type: ignore[arg-type]
        provider_id,
        room.id,
        RoomUpdateRequest(name="새이름"),
    )

    assert result is room
    assert room.name == "새이름"
    assert room.price_per_hour == 10000  # 미제공 필드 불변
    assert room.capacity == 4
    assert room.amenities == ["wifi"]
    assert session.committed is True
    assert session.deleted == []  # business_hours 미제공 → 삭제 0
    assert not any(isinstance(o, BusinessHours) for o in session.added)


def test_update_room_replaces_business_hours_atomically() -> None:
    """영업시간 전체 교체: 기존 삭제 + 신규 삽입, DELETE flush 선행, 원자 commit(AC1)."""
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    old_rows = [
        BusinessHours(room_id=room.id, weekday=0, open_time=time(9), close_time=time(22)),
        BusinessHours(room_id=room.id, weekday=1, open_time=time(9), close_time=time(22)),
    ]
    session = FakeRoomSession(stored_room=room, business_hours_rows=old_rows)

    update_room(
        session,  # type: ignore[arg-type]
        provider_id,
        room.id,
        RoomUpdateRequest(
            business_hours=[
                BusinessHoursInput(weekday=0, open_time=time(10), close_time=time(12)),
            ]
        ),
    )

    assert session.deleted == old_rows  # 기존 2행 전부 삭제
    new_bhs = [o for o in session.added if isinstance(o, BusinessHours)]
    assert len(new_bhs) == 1  # 신규 1행
    assert new_bhs[0].weekday == 0
    assert new_bhs[0].open_time == time(10)
    assert all(bh.room_id == room.id for bh in new_bhs)
    assert session.flushed_before_add is True  # DELETE가 INSERT보다 선행(UNIQUE 충돌 방지)
    assert session.committed is True


def test_update_room_without_business_hours_leaves_hours_untouched() -> None:
    """business_hours 미제공 시 영업시간 불변(삭제 0건·조회 0건 — AC1 PATCH 시맨틱)."""
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    old_rows = [
        BusinessHours(room_id=room.id, weekday=0, open_time=time(9), close_time=time(22)),
    ]
    session = FakeRoomSession(stored_room=room, business_hours_rows=old_rows)

    update_room(
        session,  # type: ignore[arg-type]
        provider_id,
        room.id,
        RoomUpdateRequest(capacity=8),  # 영업시간 키 없음
    )

    assert room.capacity == 8
    assert session.deleted == []  # 영업시간 손대지 않음
    assert BusinessHours not in session.exec_entities  # 영업시간 조회조차 없음


def test_update_room_missing_room_id_returns_404() -> None:
    """미존재 room_id → 404 ROOM_NOT_FOUND(stored_room 없음 → get None)."""
    provider_id = uuid.uuid4()
    session = FakeRoomSession(stored_room=None)

    with pytest.raises(DomainError) as exc_info:
        update_room(
            session,  # type: ignore[arg-type]
            provider_id,
            uuid.uuid4(),
            RoomUpdateRequest(name="x"),
        )

    assert exc_info.value.code is ErrorCode.ROOM_NOT_FOUND
    assert exc_info.value.status_code == 404
    assert session.committed is False


def test_update_room_other_provider_returns_404() -> None:
    """타 provider 소유 room → 404(소유권 백엔드 최종 — 미존재와 동일 404로 합침, AC4)."""
    owner_id = uuid.uuid4()
    attacker_id = uuid.uuid4()
    room = _owned_room(owner_id)  # 소유자 = owner_id
    session = FakeRoomSession(stored_room=room)

    with pytest.raises(DomainError) as exc_info:
        update_room(
            session,  # type: ignore[arg-type]
            attacker_id,  # 다른 provider가 시도
            room.id,
            RoomUpdateRequest(name="탈취"),
        )

    assert exc_info.value.code is ErrorCode.ROOM_NOT_FOUND
    assert session.committed is False
    assert room.name == "원래룸"  # 변경 안 됨


def test_update_room_reraises_unrelated_integrity_error() -> None:
    """무관 IntegrityError는 오변환 없이 rollback 후 re-raise한다(P2)."""
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    session = FakeRoomSession(
        stored_room=room, raise_on_commit=True, commit_violation="ck_rooms_capacity_positive"
    )

    with pytest.raises(IntegrityError):
        update_room(
            session,  # type: ignore[arg-type]
            provider_id,
            room.id,
            RoomUpdateRequest(name="새이름"),
        )

    assert session.rolled_back is True
    assert session.committed is False


@pytest.mark.parametrize(
    "payload",
    [
        {"name": None},  # 스칼라 NOT NULL
        {"price_per_hour": None},
        {"room_type": None},
        {"lat": None},
        {"amenities": None},  # JSONB nullable=False
        {"business_hours": None},  # 교체 분기 가드(과거 AssertionError 500)
        {"name": "새이름", "capacity": None},  # 유효 필드 + 명시 null 혼합도 거부
    ],
)
def test_update_request_rejects_explicit_null(payload: dict[str, Any]) -> None:
    """명시적 JSON null은 422(ValidationError)로 거부된다 — 미처리 500 방지(code-review patch).

    모든 필드가 ``X | None``이라 명시 null이 Pydantic을 통과해 ``setattr(room, field, None)``에
    도달하면 NOT NULL/JSONB 위반 IntegrityError나 business_hours 가드로 500이 됐다.
    ``_reject_explicit_null``이 ``model_fields_set``으로 명시 제공된 null만 골라 422화한다.
    """
    with pytest.raises(ValidationError):
        RoomUpdateRequest.model_validate(payload)


def test_update_request_omitted_fields_stay_valid() -> None:
    """미제공 필드는 거부되지 않는다(불변 유지) — null 거부 가드가 model_fields_set만 본다."""
    req = RoomUpdateRequest.model_validate({"name": "새이름"})  # 나머지 전부 미제공
    provided = req.model_dump(exclude_unset=True)
    assert provided == {"name": "새이름"}  # 미제공 필드는 dump에 없음 → setattr 안 됨


def test_update_room_touches_no_reservation_data() -> None:
    """AC2 독립성(FR-22): update_room은 rooms·business_hours만 만지고 reservations를 안 건드린다.

    수정 서비스가 조회/삭제하는 ORM은 Room(get)·BusinessHours(exec)뿐이다 — reservation류
    데이터를 조회/삭제/재계산하지 않는다. E4 reservations 행은 자기 slot_start(UTC)를 보유하므로
    영업시간 변경에 독립이며(architecture.md L149-150), 본 함수는 그 불변식을 깨지 않는다.
    """
    provider_id = uuid.uuid4()
    room = _owned_room(provider_id)
    old_rows = [
        BusinessHours(room_id=room.id, weekday=0, open_time=time(9), close_time=time(22)),
    ]
    session = FakeRoomSession(stored_room=room, business_hours_rows=old_rows)

    update_room(
        session,  # type: ignore[arg-type]
        provider_id,
        room.id,
        RoomUpdateRequest(
            business_hours=[
                BusinessHoursInput(weekday=0, open_time=time(9), close_time=time(12)),
            ]
        ),
    )

    # exec가 조회한 엔티티는 BusinessHours뿐(reservation류 조회 0). get은 Room만.
    assert set(session.exec_entities) <= {BusinessHours}
    assert all(model is Room for model, _ in session.get_calls)


def test_business_hours_shrink_drops_slot_but_reservation_independent() -> None:
    """영업시간 축소 → derive_slots(신규 시간)에서 이전 슬롯이 빠지지만, 예약은 자체 보유로 독립.

    09:00~22:00에서 13:00 KST(04:00 UTC) 슬롯은 도출된다. 09:00~12:00으로 축소하면 derive_slots는
    그 슬롯을 더 이상 도출하지 않는다(슬롯은 도출값 — AC1). 그리고 그 시각을 reserved_starts로
    넘겨도 derive_slots는 그것을 "도출 가능"으로 되살리지 않는다(예약은 도출집합과 무관한 자체 보유
    데이터 — AC2). 즉 영업시간 변경은 reservations를 소급 변경하지 않는다(FR-22).
    """
    thirteen_kst_utc = datetime(2026, 6, 15, 4, 0, tzinfo=UTC)  # 13:00 KST = 04:00 UTC

    wide = derive_slots([_bh(0, 9, 22)], holiday_dates=set(), target_date=MONDAY)
    assert thirteen_kst_utc in wide  # 넓은 영업시간엔 13:00 KST 슬롯이 있다

    narrow = derive_slots([_bh(0, 9, 12)], holiday_dates=set(), target_date=MONDAY)
    assert thirteen_kst_utc not in narrow  # 축소 후엔 도출되지 않는다(AC1)

    # 축소 시간 + 그 시각을 reserved로 넘겨도 13:00 슬롯이 되살아나지 않는다(도출과 예약은 별개).
    narrow_with_reserved = derive_slots(
        [_bh(0, 9, 12)],
        holiday_dates=set(),
        target_date=MONDAY,
        reserved_starts={thirteen_kst_utc},
    )
    assert thirteen_kst_utc not in narrow_with_reserved


# ── violated_constraint 헬퍼 (P2) ─────────────────────────────────────────────
def test_violated_constraint_extracts_name() -> None:
    """orig.diag.constraint_name이 있으면 그 이름을 반환한다."""
    exc = IntegrityError("stmt", {}, _FakeOrig("uq_rooms_provider_id"))
    assert violated_constraint(exc) == "uq_rooms_provider_id"


def test_violated_constraint_none_when_no_diag() -> None:
    """orig/diag가 없으면 None(비-psycopg 드라이버·진단 부재)."""
    exc = IntegrityError("stmt", {}, Exception("no diag"))
    assert violated_constraint(exc) is None


# ── 카카오 지오코딩 geocode_address (Story 2.2 — AC2, httpx mock) ──────────────
def _mock_geocode_client(handler: Any) -> Any:
    """httpx.MockTransport로 카카오 응답을 주입한 동기 Client 팩토리(라이브 호출 0)."""
    return lambda: httpx.Client(transport=httpx.MockTransport(handler), timeout=10.0)


def test_geocode_maps_documents(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """정상 응답 → GeocodeResult(lat=y·lng=x·admin_dong_code=b_code)로 매핑한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("KakaoAK ")
        return httpx.Response(
            200,
            json={
                "documents": [
                    {
                        "address_name": "서울특별시 강남구 역삼동 736",
                        "x": "127.036508620542",  # 경도
                        "y": "37.5012667",  # 위도
                        "address": {"b_code": "1168010100", "address_name": "역삼동"},
                        "road_address": {"b_code": "1168010100"},
                    }
                ]
            },
        )

    monkeypatch.setattr(service, "_geocode_client", _mock_geocode_client(handler))
    results = geocode_address("역삼동 736")

    assert len(results) == 1
    r = results[0]
    assert r.lat == pytest.approx(37.5012667)  # y
    assert r.lng == pytest.approx(127.036508620542)  # x
    assert r.admin_dong_code == "1168010100"  # b_code
    assert "역삼동" in r.address


def test_geocode_zero_results_is_empty_list(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """결과 0건은 에러가 아니라 빈 리스트(200)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"documents": [], "meta": {"total_count": 0}})

    monkeypatch.setattr(service, "_geocode_client", _mock_geocode_client(handler))
    assert geocode_address("없는주소zzz") == []


def test_geocode_non_200_raises_502(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """카카오 비-200(키 무효·한도 초과) → 502 GEOCODING_UNAVAILABLE."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    monkeypatch.setattr(service, "_geocode_client", _mock_geocode_client(handler))
    with pytest.raises(DomainError) as exc_info:
        geocode_address("역삼동")
    assert exc_info.value.code is ErrorCode.GEOCODING_UNAVAILABLE
    assert exc_info.value.status_code == 502


def test_geocode_timeout_raises_502(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """타임아웃/전송 오류 → 502 GEOCODING_UNAVAILABLE."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    monkeypatch.setattr(service, "_geocode_client", _mock_geocode_client(handler))
    with pytest.raises(DomainError) as exc_info:
        geocode_address("역삼동")
    assert exc_info.value.code is ErrorCode.GEOCODING_UNAVAILABLE


def test_geocode_skips_documents_without_coords(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """좌표 없는 문서는 후보에서 제외한다(손상 항목 방어)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "documents": [
                    {"address_name": "좌표없음", "address": {"b_code": "1"}},  # x/y 없음
                    {
                        "address_name": "정상",
                        "x": "127.0",
                        "y": "37.0",
                        "address": {"b_code": "1168010100"},
                    },
                ]
            },
        )

    monkeypatch.setattr(service, "_geocode_client", _mock_geocode_client(handler))
    results = geocode_address("혼합")
    assert len(results) == 1
    assert results[0].admin_dong_code == "1168010100"


def test_geocode_documents_null_is_empty(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """documents 키가 존재+null이면 빈 리스트로 처리한다(code-review patch — TypeError 500 방지)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"documents": None})

    monkeypatch.setattr(service, "_geocode_client", _mock_geocode_client(handler))
    assert geocode_address("역삼동") == []


def test_geocode_documents_non_list_is_empty(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """documents가 리스트가 아니면(손상 응답) 빈 리스트로 처리한다(조용한 오작동 방지)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"documents": {"unexpected": "object"}})

    monkeypatch.setattr(service, "_geocode_client", _mock_geocode_client(handler))
    assert geocode_address("역삼동") == []


def test_geocode_non_json_body_raises_502(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """200이지만 본문이 비-JSON(점검 HTML 등)이면 502 GEOCODING_UNAVAILABLE(code-review patch).

    resp.json()의 JSONDecodeError는 httpx.HTTPError가 아니라 ValueError 하위라 별도 가드가 없으면
    미처리 500이 누출된다.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    monkeypatch.setattr(service, "_geocode_client", _mock_geocode_client(handler))
    with pytest.raises(DomainError) as exc_info:
        geocode_address("역삼동")
    assert exc_info.value.code is ErrorCode.GEOCODING_UNAVAILABLE
    assert exc_info.value.status_code == 502


# ── 가용성 집계 aggregate_availability (Story 3.1 — AC1·AC2·AC4) ────────────────
# now는 고정 UTC 값 주입(2.1 MONDAY 선례). target_date가 KST 기준이므로 UTC→KST 환산 주의:
#   · 2026-06-14 16:00 UTC = 2026-06-15 01:00 KST(월요일 새벽) → 그날 모든 슬롯이 미래.
#   · 2026-06-15 03:00 UTC = 2026-06-15 12:00 KST(월요일 정오).
MONDAY_EARLY_UTC = datetime(2026, 6, 14, 16, 0, tzinfo=UTC)  # KST 월 01:00 — 전 슬롯 미래
MONDAY_NOON_UTC = datetime(2026, 6, 15, 3, 0, tzinfo=UTC)  # KST 월 12:00


def test_aggregate_counts_remaining_slots_after_now() -> None:
    """월 09:00~22:00 룸 → 새벽 now면 13슬롯 전부 카운트, 정오 now면 현재시각 이후만 카운트(AC1).

    09:00~22:00 KST = 00:00~12:00 UTC 시작 13개(2.1 전일 카운트 일치). now를 정오(03:00 UTC)로
    올리면 그 이전 슬롯이 빠져 13→10으로 줄어든다(현재시각 이후 필터 실증).
    """
    assert MONDAY.weekday() == 0
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )

    early = aggregate_availability(session, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert len(early) == 1
    assert early[0].room_id == room.id
    assert early[0].remaining_slots == 13  # 전 슬롯 미래

    noon = aggregate_availability(session, now=MONDAY_NOON_UTC)  # type: ignore[arg-type]
    # 12:00 KST(03:00 UTC) 이후 시작 슬롯만: 03:00,04:00,...,12:00 UTC = 10개.
    assert noon[0].remaining_slots == 10
    assert noon[0].remaining_slots < early[0].remaining_slots  # 현재시각 이후 필터 동작


def test_aggregate_boundary_slot_at_now_is_included() -> None:
    """경계 규칙 >= : now와 정확히 같은 시각에 시작하는 슬롯은 포함된다(정책 못박기).

    now=04:00 UTC(=13:00 KST)이면 13:00 KST(=04:00 UTC) 시작 슬롯이 포함된다(09~22 룸).
    04:00,...,12:00 UTC = 9개.
    """
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )
    at_one_pm = datetime(2026, 6, 15, 4, 0, tzinfo=UTC)  # 13:00 KST = 04:00 UTC

    result = aggregate_availability(session, now=at_one_pm)  # type: ignore[arg-type]
    assert result[0].remaining_slots == 9  # 04:00..12:00 UTC 포함(경계 포함)


def test_aggregate_holiday_room_is_zero() -> None:
    """오늘이 휴무인 룸 → remaining_slots == 0(영업시간 있어도)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        holidays=[HolidayException(room_id=room.id, holiday_date=MONDAY)],
    )

    result = aggregate_availability(session, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert result[0].remaining_slots == 0


def test_aggregate_non_business_weekday_is_zero() -> None:
    """오늘(월) 요일에 영업행이 없는 룸(화요일만 영업) → 0."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 1, 9, 22)]  # 화요일=1
    )

    result = aggregate_availability(session, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert result[0].remaining_slots == 0


def test_aggregate_reservations_treated_empty() -> None:
    """reservations 부재 가정(AC2) — 영업 슬롯이 전부 카운트된다(예약 차감 없음, 4.9 전 동작 고정).

    aggregate_availability는 derive_slots에 reserved_starts=frozenset()을 명시 전달하므로
    예약에 의한 차감이 일어나지 않는다. 전 영업 슬롯(13)이 그대로 잔여로 집계됨을 단언한다.
    """
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )

    result = aggregate_availability(session, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert result[0].remaining_slots == 13  # 차감 없이 전 슬롯


def test_aggregate_does_not_mix_room_business_hours() -> None:
    """★AC4 회수 회귀(필수): 룸 간 영업시간이 섞이지 않는다(room_id 그룹핑 실증).

    룸 A(월 09~22 → 13슬롯)·룸 B(월 09~10 → 1슬롯)를 같은 세션에 넣고 집계하면 각자 13·1로
    도출돼야 한다. derive_slots는 weekday만 필터하고 room_id는 보지 않으므로(2.1 defer), 호출부가
    영업시간을 섞어 넘기면 B도 A의 행을 받아 14(또는 합산)가 된다 — 그 회귀를 잡는다.
    """
    room_a = _avail_room()
    room_b = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room_a, room_b],
        business_hours=[
            _room_bh(room_a.id, 0, 9, 22),  # A: 13슬롯
            _room_bh(room_b.id, 0, 9, 10),  # B: 1슬롯
        ],
    )

    result = aggregate_availability(session, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    by_room = {item.room_id: item.remaining_slots for item in result}
    assert by_room[room_a.id] == 13  # A는 자기 영업시간으로만
    assert by_room[room_b.id] == 1  # B는 자기 영업시간으로만(섞이면 13/14가 됨)


def test_aggregate_inactive_room_excluded() -> None:
    """is_active=False 룸은 결과에 없다(활성 룸만 집계 — DB where(is_active) 모사)."""
    active = _avail_room(is_active=True)
    inactive = _avail_room(is_active=False)
    session = FakeAvailabilitySession(
        rooms=[active, inactive],
        business_hours=[
            _room_bh(active.id, 0, 9, 22),
            _room_bh(inactive.id, 0, 9, 22),  # 있어도 비활성이라 집계 제외
        ],
    )

    result = aggregate_availability(session, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    room_ids = {item.room_id for item in result}
    assert active.id in room_ids
    assert inactive.id not in room_ids


def test_aggregate_empty_when_no_active_rooms() -> None:
    """활성 룸 0개 → 빈 리스트(정상 200, 에러 아님)."""
    session = FakeAvailabilitySession(rooms=[])
    assert aggregate_availability(session, now=MONDAY_EARLY_UTC) == []  # type: ignore[arg-type]


def test_aggregate_room_without_business_hours_is_zero() -> None:
    """영업시간 행이 전혀 없는 활성 룸 → 0(그룹에 없으면 빈 입력 → derive_slots []→0)."""
    room = _avail_room()
    session = FakeAvailabilitySession(rooms=[room], business_hours=[])

    result = aggregate_availability(session, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert len(result) == 1
    assert result[0].remaining_slots == 0


def test_aggregate_is_read_only_no_writes() -> None:
    """집계는 읽기 전용 — Room/BusinessHours/HolidayException만 조회하고 쓰기는 없다(Task 2).

    FakeAvailabilitySession은 commit/add/delete를 노출하지 않으므로, 집계가 그것들을 호출했다면
    AttributeError로 깨진다(여기 도달=쓰기 호출 0). 조회 엔티티도 그 3종으로 한정됨을 단언한다.
    """
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )

    aggregate_availability(session, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert set(session.exec_entities) <= {Room, BusinessHours, HolidayException, ReservationSlot}


# ── Story 4.9 예약 차감 — 카운트 4곳(aggregate/search/summary/remaining) ──────────
# MONDAY 09:00~22:00 KST = 시작 UTC 00:00..12:00(13개). 09:00 KST=00:00 UTC, 10:00 KST=01:00 UTC.
MON_0900_KST_UTC = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)  # 09:00 KST 슬롯 시작(UTC)
MON_1000_KST_UTC = datetime(2026, 6, 15, 1, 0, tzinfo=UTC)  # 10:00 KST 슬롯 시작(UTC)


def test_aggregate_deducts_reserved_slots() -> None:
    """활성 점유 행이 있으면 remaining_slots가 그만큼 차감된다(AC1 — 영업 − 휴무 − 예약).

    월 09~22(13슬롯)에서 09·10시 KST 2개를 예약하면 13→11. derive_slots가 starts − reserved로
    예약 슬롯을 빼므로 "남은 빈 슬롯 수"가 정확히 줄어든다.
    """
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        reservation_slots=[
            _res_slot(room.id, MON_0900_KST_UTC),
            _res_slot(room.id, MON_1000_KST_UTC),
        ],
    )

    result = aggregate_availability(session, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert result[0].remaining_slots == 11  # 13 − 2 예약


def test_aggregate_reserved_room_isolation() -> None:
    """한 룸의 예약이 다른 룸의 카운트에 섞이지 않는다(룸 격리 — 벌크 reader 그룹핑, AC1)."""
    room_a = _avail_room()
    room_b = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room_a, room_b],
        business_hours=[_room_bh(room_a.id, 0, 9, 22), _room_bh(room_b.id, 0, 9, 22)],
        # A에만 예약 1건 — B는 영향받지 않아야 한다.
        reservation_slots=[_res_slot(room_a.id, MON_0900_KST_UTC)],
    )

    result = aggregate_availability(session, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    by_room = {item.room_id: item.remaining_slots for item in result}
    assert by_room[room_a.id] == 12  # 13 − 1(자기 예약)
    assert by_room[room_b.id] == 13  # 타 룸 예약이 안 섞임


def test_aggregate_cancel_restores_count() -> None:
    """취소(점유 행 부재)면 차감이 사라져 카운트가 복원된다(취소=DELETE 모사 — AC1)."""
    room = _avail_room()
    # 취소된 예약은 reservation_slots에 행이 없다(_release_slots DELETE) → 차감 0.
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)], reservation_slots=[]
    )

    result = aggregate_availability(session, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert result[0].remaining_slots == 13  # 점유 행 없음 → 전 슬롯 복원


def test_aggregate_past_reserved_does_not_change_count() -> None:
    """과거 시각 예약은 카운트에 영향 없다(on_or_after=current로 제외 + 어차피 >=current 미카운트).

    now=정오면 09시 KST(과거) 예약은 reader가 on_or_after로 빼고, 설령 남아도 >=current 필터에서
    카운트되지 않는다 → 정오 기준 잔여(10)가 과거 예약 유무와 무관함을 단언한다.
    """
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        reservation_slots=[_res_slot(room.id, MON_0900_KST_UTC)],  # 09시(정오 기준 과거)
    )

    result = aggregate_availability(session, now=MONDAY_NOON_UTC)  # type: ignore[arg-type]
    assert result[0].remaining_slots == 10  # 정오 이후 10개 — 과거 예약 차감 무관


def test_aggregate_on_or_after_boundary_reserved_at_now_is_deducted() -> None:
    """on_or_after `>=` 경계(deferred L19 회수): now와 정확히 같은 시각 예약 슬롯도 차감된다.

    reader는 on_or_after=current로 `slot_start >= current` 점유만 반환한다. now=09:00 KST면 09시
    슬롯(=current)이 inclusive `>=`로 reserved 집합에 포함 → 차감 → 13→12. (`>` 였다면 미포함 13.)
    """
    room = _avail_room()
    # now = 09:00 KST(= MON_0900_KST_UTC) → 09시 슬롯이 경계(>= now → 카운트 대상)이자 예약 대상.
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        reservation_slots=[_res_slot(room.id, MON_0900_KST_UTC)],
    )

    result = aggregate_availability(session, now=MON_0900_KST_UTC)  # type: ignore[arg-type]
    assert result[0].remaining_slots == 12  # 13 − 1(경계 슬롯 inclusive 차감)


def test_search_rooms_deducts_reserved_slots() -> None:
    """search_rooms 목록 카운트도 예약을 차감한다(AC1 — aggregate 동일 패턴)."""
    room = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        reservation_slots=[_res_slot(room.id, MON_0900_KST_UTC)],
    )

    items = search_rooms(session, GANGNAM_YEOKSAM, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert len(items) == 1
    assert items[0].remaining_slots == 12  # 13 − 1 예약


def test_search_rooms_reserved_room_isolation() -> None:
    """search_rooms 카운트에서 룸 간 예약이 섞이지 않는다(벌크 reader 그룹핑 격리, AC1)."""
    room_a = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    room_b = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    session = FakeAvailabilitySession(
        rooms=[room_a, room_b],
        business_hours=[_room_bh(room_a.id, 0, 9, 22), _room_bh(room_b.id, 0, 9, 22)],
        reservation_slots=[_res_slot(room_a.id, MON_0900_KST_UTC)],
    )

    items = search_rooms(session, GANGNAM_YEOKSAM, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    by_room = {item.room_id: item.remaining_slots for item in items}
    assert by_room[room_a.id] == 12  # 자기 예약만 차감
    assert by_room[room_b.id] == 13  # 타 룸 예약 미반영


def test_geocode_non_dict_json_raises_502(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """최상위 JSON이 객체가 아니면(배열 등 손상) 502로 거부한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["unexpected", "array"])

    monkeypatch.setattr(service, "_geocode_client", _mock_geocode_client(handler))
    with pytest.raises(DomainError) as exc_info:
        geocode_address("역삼동")
    assert exc_info.value.code is ErrorCode.GEOCODING_UNAVAILABLE


# ── 룸 목록 list_active_rooms (Story 3.2 — AC1·AC2 핀 좌표 공급) ────────────────
def test_list_active_rooms_returns_map_items() -> None:
    """활성 룸 2개 → 각 {room_id, name, lat, lng}만(핀 메타 — 좌표·이름 정확, AC1).

    FakeAvailabilitySession(3.1, 읽기 전용)을 그대로 재사용한다 — list_active_rooms는
    where(is_active).all()만 하므로 Room 분기·.all() 시맨틱이 일치한다(신규 Fake 불필요).
    """
    room_a = Room(
        provider_id=uuid.uuid4(),
        name="강남룸",
        price_per_hour=12000,
        capacity=6,
        room_type="open",
        amenities=["wifi"],
        lat=37.4979,
        lng=127.0276,
        admin_dong_code="1168010100",
    )
    room_b = Room(
        provider_id=uuid.uuid4(),
        name="홍대룸",
        price_per_hour=9000,
        capacity=3,
        room_type="private",
        amenities=[],
        lat=37.5563,
        lng=126.9220,
        admin_dong_code="1144012000",
    )
    session = FakeAvailabilitySession(rooms=[room_a, room_b])

    items = list_active_rooms(session)  # type: ignore[arg-type]

    assert len(items) == 2
    by_id = {item.room_id: item for item in items}
    assert by_id[room_a.id].name == "강남룸"
    assert by_id[room_a.id].lat == pytest.approx(37.4979)
    assert by_id[room_a.id].lng == pytest.approx(127.0276)
    assert by_id[room_b.id].name == "홍대룸"
    # 핀 메타는 좌표·이름·room_id만 — 가격/부대시설 등은 RoomMapItem 필드에 아예 없다.
    assert set(by_id[room_a.id].model_dump()) == {"room_id", "name", "lat", "lng"}


def test_list_active_rooms_excludes_inactive() -> None:
    """is_active=False 룸은 목록에서 제외된다(DB where(is_active) 모사)."""
    active = _avail_room(is_active=True)
    inactive = _avail_room(is_active=False)
    session = FakeAvailabilitySession(rooms=[active, inactive])

    items = list_active_rooms(session)  # type: ignore[arg-type]

    ids = {item.room_id for item in items}
    assert active.id in ids
    assert inactive.id not in ids


def test_list_active_rooms_empty_when_none() -> None:
    """활성 룸 0개 → 빈 리스트(정상, 에러 아님)."""
    session = FakeAvailabilitySession(rooms=[])
    assert list_active_rooms(session) == []  # type: ignore[arg-type]


def test_list_active_rooms_is_read_only_no_writes() -> None:
    """목록 조회는 읽기 전용 — Room만 조회하고 쓰기(commit/add/delete)는 없다(Task 2).

    FakeAvailabilitySession은 commit/add/delete를 노출하지 않으므로, 호출 시 AttributeError로
    깨진다(여기 도달 = 쓰기 0). 조회 엔티티가 Room뿐임도 단언한다.
    """
    room = _avail_room()
    session = FakeAvailabilitySession(rooms=[room])

    list_active_rooms(session)  # type: ignore[arg-type]

    assert set(session.exec_entities) <= {Room}


# ── 단일 룸 요약 get_room_summary (Story 3.3 — AC1·AC4 바텀시트 신선 요약) ────────
def test_get_room_summary_returns_fields() -> None:
    """활성 룸 → 가격·수용·룸타입·부대시설·영업시간·좌표 정확, provider_id 등 미포함(AC1·4.2 AC4).

    FakeAvailabilitySession.get(Room, pk)로 단일 룸을 돌려주고, BusinessHours를 .all()로 조회한다.
    RoomSummary는 공개 표면 스키마로, 위치 미니 지도(Story 4.2)를 위해 lat/lng는 노출하되
    provider_id·is_active·created_at·admin_dong_code는 필드 자체로 갖지 않는다 → model_dump 키
    집합으로 노출 범위(좌표 포함·내부 필드 회피)를 단언한다.
    """
    room = Room(
        provider_id=uuid.uuid4(),
        name="강남룸",
        price_per_hour=12000,
        capacity=6,
        room_type="open",
        amenities=["wifi", "parking"],
        lat=37.4979,
        lng=127.0276,
        admin_dong_code="1168010100",
    )
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[
            _room_bh(room.id, 1, 10, 20),  # 화요일(일부러 비정렬로 넣어 정렬 확인)
            _room_bh(room.id, 0, 9, 22),  # 월요일
        ],
    )

    summary = get_room_summary(session, room.id, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert summary.room_id == room.id
    assert summary.name == "강남룸"
    assert summary.price_per_hour == 12000
    assert summary.capacity == 6
    assert summary.room_type == "open"
    assert summary.amenities == ["wifi", "parking"]
    # business_hours는 weekday 오름차순(시트 표시 안정성).
    assert [bh.weekday for bh in summary.business_hours] == [0, 1]
    assert summary.business_hours[0].open_time == time(9, 0)
    # 위치 미니 지도(4.2)용 좌표는 노출된다(저장 좌표 그대로 — RoomMapItem 선례).
    assert summary.lat == pytest.approx(37.4979)
    assert summary.lng == pytest.approx(127.0276)
    # 공개 표면 — 좌표는 노출하되 내부/소유 필드는 스키마에 아예 없다(과조회·노출 회피, 4.2 AC4).
    keys = set(summary.model_dump())
    assert keys == {
        "room_id", "name", "price_per_hour", "capacity", "room_type",
        "amenities", "business_hours", "remaining_slots", "is_closed_today",
        "lat", "lng", "address",  # address = 표시용 주소(provider 입력, 미입력 null)
    }
    assert "provider_id" not in keys
    assert "is_active" not in keys
    assert "admin_dong_code" not in keys  # 지역 코드(사람이 읽는 값 아님) 미노출 유지
    assert summary.address is None  # 이 룸은 주소 미입력 → null
    assert summary.is_closed_today is False  # 휴무 없음 → 영업일(code-review)


def test_get_room_summary_fresh_remaining_slots() -> None:
    """오늘 신선 remaining_slots가 derive_slots + >=now와 일치한다(AC4 — 핀 스냅샷 아님).

    09:00~22:00 KST 월요일 → 새벽 now면 13슬롯 전부 미래, 정오 now면 현재시각 이후만(13→10).
    이 신선값이 시트 "예약 가능" 배지의 근거다(aggregate_availability와 동일 경계 >=).
    """
    assert MONDAY.weekday() == 0
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )

    early = get_room_summary(session, room.id, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert early.remaining_slots == 13  # 전 슬롯 미래

    noon = get_room_summary(session, room.id, now=MONDAY_NOON_UTC)  # type: ignore[arg-type]
    assert noon.remaining_slots == 10  # 12:00 KST(03:00 UTC) 이후만
    assert noon.remaining_slots < early.remaining_slots  # 현재시각 이후 필터 동작


def test_get_room_summary_holiday_zero() -> None:
    """오늘이 휴무인 룸 → remaining_slots == 0(영업시간 있어도)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        holidays=[HolidayException(room_id=room.id, holiday_date=MONDAY)],
    )

    summary = get_room_summary(session, room.id, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert summary.remaining_slots == 0
    # 휴무라 remaining=0이고 is_closed_today=True여야 시트가 "오늘 휴무"로 표시한다(모순 방지).
    assert summary.is_closed_today is True


def test_get_room_summary_inactive_404() -> None:
    """is_active=False 룸 → 404 ROOM_NOT_FOUND(탐색 핀은 활성만 — 비활성/미존재 합침)."""
    room = _avail_room(is_active=False)
    session = FakeAvailabilitySession(rooms=[room])

    with pytest.raises(DomainError) as exc_info:
        get_room_summary(session, room.id, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert exc_info.value.code is ErrorCode.ROOM_NOT_FOUND
    assert exc_info.value.status_code == 404


def test_get_room_summary_missing_404() -> None:
    """미존재 room_id → 404 ROOM_NOT_FOUND(get → None)."""
    session = FakeAvailabilitySession(rooms=[])

    with pytest.raises(DomainError) as exc_info:
        get_room_summary(session, uuid.uuid4(), now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert exc_info.value.code is ErrorCode.ROOM_NOT_FOUND


def test_get_room_summary_is_read_only_no_writes() -> None:
    """요약 조회는 읽기 전용 — Room(get)·BusinessHours/HolidayException(exec)만, 쓰기 0(Task 2).

    FakeAvailabilitySession은 commit/add/delete를 노출하지 않으므로 호출 시 AttributeError로
    깨진다(여기 도달 = 쓰기 0). 조회 엔티티가 그 3종으로 한정됨도 단언한다.
    """
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )

    get_room_summary(session, room.id, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert set(session.exec_entities) <= {Room, BusinessHours, HolidayException, ReservationSlot}


def test_get_room_summary_deducts_reserved_slots() -> None:
    """단일 룸 요약 remaining_slots도 예약을 차감한다(AC1 — 단일 reader)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        reservation_slots=[
            _res_slot(room.id, MON_0900_KST_UTC),
            _res_slot(room.id, MON_1000_KST_UTC),
        ],
    )

    summary = get_room_summary(session, room.id, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert summary.remaining_slots == 11  # 13 − 2 예약


def test_get_room_summary_room_isolation_reserved() -> None:
    """타 룸의 예약이 이 룸 요약 카운트에 안 섞인다(단일 reader room_id 필터 — AC1)."""
    room = _avail_room()
    other = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room, other],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        # 다른 룸에만 예약 — 이 룸 요약은 차감 0이어야 한다.
        reservation_slots=[_res_slot(other.id, MON_0900_KST_UTC)],
    )

    summary = get_room_summary(session, room.id, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert summary.remaining_slots == 13  # 타 룸 예약 미반영


def test_get_room_summary_cancel_restores() -> None:
    """취소(점유 행 부재)면 요약 카운트가 복원된다(취소=DELETE 모사 — AC1)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)], reservation_slots=[]
    )

    summary = get_room_summary(session, room.id, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert summary.remaining_slots == 13


def test_room_remaining_slots_deducts_reserved() -> None:
    """room_remaining_slots(즐겨찾기 카운트)도 예약을 차감한다(AC1 — 단일 reader)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        reservation_slots=[_res_slot(room.id, MON_0900_KST_UTC)],
    )

    assert room_remaining_slots(session, room, now=MONDAY_EARLY_UTC) == 12  # type: ignore[arg-type]


def test_room_remaining_slots_cancel_restores() -> None:
    """취소(점유 행 부재)면 room_remaining_slots가 복원된다(AC1)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)], reservation_slots=[]
    )

    assert room_remaining_slots(session, room, now=MONDAY_EARLY_UTC) == 13  # type: ignore[arg-type]


# ── 날짜별 슬롯 조회 get_room_slots (Story 4.3 — AC1·AC2·AC3) ───────────────────
# 요일이 명확한 고정 날짜: MONDAY=2026-06-15(월=0)·TUESDAY=6/16(화=1)·WEDNESDAY=6/17(수=2).
TUESDAY = date(2026, 6, 16)
WEDNESDAY = date(2026, 6, 17)
MONDAY_LATE_UTC = datetime(2026, 6, 15, 13, 0, tzinfo=UTC)  # KST 월 22:00 — 전 슬롯 과거


def test_slots_status_available_past_split() -> None:
    """오늘(KST) 09:00~22:00, now=정오 → 정오 이전 past·이후 available(경계 >=current, AC2)."""
    assert MONDAY.weekday() == 0
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )

    # now=MONDAY_NOON_UTC=03:00 UTC=12:00 KST. 12:00 KST 슬롯=03:00 UTC == current → available.
    resp = get_room_slots(session, room.id, MONDAY, now=MONDAY_NOON_UTC)  # type: ignore[arg-type]

    assert resp.date == MONDAY
    assert len(resp.slots) == 13  # 09~21시 시작 = 13개
    past = [s for s in resp.slots if s.status == "past"]
    available = [s for s in resp.slots if s.status == "available"]
    assert len(past) == 3  # 09·10·11시 KST(00·01·02 UTC) < 03:00 UTC
    assert len(available) == 10  # 12~21시 KST(03~12 UTC) >= 03:00 UTC
    # 경계 단언: 정확히 current와 같은 슬롯(12:00 KST=03:00 UTC)은 past가 아니라 available.
    boundary = next(s for s in resp.slots if s.slot_start == MONDAY_NOON_UTC)
    assert boundary.status == "available"
    # 슬롯은 시작시각 오름차순(derive_slots 정렬 보존).
    assert resp.slots == sorted(resp.slots, key=lambda s: s.slot_start)


def test_slots_future_date_all_available() -> None:
    """미래 날짜 → 전부 available(past 0)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 1, 9, 22)]  # 화요일 영업
    )

    resp = get_room_slots(session, room.id, TUESDAY, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert len(resp.slots) == 13
    assert all(s.status == "available" for s in resp.slots)  # 전부 미래


def test_slots_holiday_empty() -> None:
    """휴무일 → slots == [](derive_slots 규칙 ①)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        holidays=[HolidayException(room_id=room.id, holiday_date=MONDAY)],
    )

    resp = get_room_slots(session, room.id, MONDAY, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert resp.slots == []


def test_slots_non_business_weekday_empty() -> None:
    """영업행 없는 요일 → [](derive_slots 규칙 ②). 행은 화요일=1, 대상은 월요일=0."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 1, 9, 22)]
    )

    resp = get_room_slots(session, room.id, MONDAY, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert resp.slots == []


def test_slots_reserved_starts_empty_no_reserved_status() -> None:
    """reserved_starts=frozenset()이라 reserved 상태 0(4.9 연결 전 동작 고정 — AC1 seam)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )

    resp = get_room_slots(session, room.id, MONDAY, now=MONDAY_NOON_UTC)  # type: ignore[arg-type]
    # 어떤 슬롯도 reserved가 아니다(예약 도메인 부재 — Story 4.9 연결 전).
    assert all(s.status in {"available", "past"} for s in resp.slots)
    assert not any(s.status == "reserved" for s in resp.slots)


def test_slots_reserved_shown_not_removed() -> None:
    """⚠️핵심(AC2): 예약 슬롯은 응답에서 **사라지지 않고** status="reserved"로 표시된다.

    derive_slots에 frozenset()(전 슬롯 유지) + _slot_status에 실제 reserved set을 주는 비대칭
    배선의 결과 — 슬롯 총수는 13 그대로이고, 예약된 09시 슬롯만 reserved, 나머지는 available.
    (만약 derive_slots에 reserved를 주면 슬롯이 소멸해 "영업 안 함"처럼 보이는 회귀가 난다.)
    """
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        reservation_slots=[_res_slot(room.id, MON_0900_KST_UTC)],
    )

    resp = get_room_slots(session, room.id, MONDAY, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert len(resp.slots) == 13  # 사라지지 않음(소멸 아님)
    reserved = [s for s in resp.slots if s.status == "reserved"]
    assert len(reserved) == 1
    assert reserved[0].slot_start == MON_0900_KST_UTC  # 그 09시 슬롯이 reserved
    assert sum(1 for s in resp.slots if s.status == "available") == 12  # 나머지는 가용


def test_slots_past_and_reserved_priority_is_reserved() -> None:
    """과거이면서 예약된 슬롯은 reserved로 표기된다(우선순위 reserved → past → available, AC2)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        # 09시 KST = 정오 기준 과거 슬롯을 예약. on_or_after 없이 조회하므로 표시엔 포함된다.
        reservation_slots=[_res_slot(room.id, MON_0900_KST_UTC)],
    )

    resp = get_room_slots(session, room.id, MONDAY, now=MONDAY_NOON_UTC)  # type: ignore[arg-type]
    nine = next(s for s in resp.slots if s.slot_start == MON_0900_KST_UTC)
    assert nine.status == "reserved"  # past가 아니라 reserved(우선순위)


def test_slots_next_available_skips_fully_booked_day() -> None:
    """next_available_date는 전부 예약된 만석 날을 건너뛴다(차감 적용 — AC2).

    월(전부 과거)→다음 빈 날 검색. 화요일은 슬롯이 1개뿐인데 그 1개가 예약돼 만석 → 화요일을
    건너뛰고 수요일이 첫 빈 날이 돼야 한다. (차감을 안 하면 화요일이 잘못 제안된다 = 회귀 가드.)
    """
    room = _avail_room()
    tue_0900_utc = datetime(2026, 6, 16, 0, 0, tzinfo=UTC)  # 화 09:00 KST 슬롯
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[
            _room_bh(room.id, 0, 9, 22),  # 월: 13슬롯(전부 과거)
            _room_bh(room.id, 1, 9, 10),  # 화: 1슬롯(09~10)
            _room_bh(room.id, 2, 9, 22),  # 수: 13슬롯
        ],
        reservation_slots=[_res_slot(room.id, tue_0900_utc)],  # 화요일 유일 슬롯 예약 → 만석
    )

    resp = get_room_slots(session, room.id, MONDAY, now=MONDAY_LATE_UTC)  # type: ignore[arg-type]
    assert all(s.status == "past" for s in resp.slots)  # 월 전부 과거
    assert resp.next_available_date == WEDNESDAY  # 화(만석) 건너뜀 → 수요일


def test_next_available_date_skips_full_day() -> None:
    """요청 날 전부 past(늦은 now)면 next_available_date=다음 영업일(빈 요일은 건너뜀, AC3)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room],
        # 월(0)·수(2)만 영업 — 화(1)는 영업행 없음(건너뛰어야 함).
        business_hours=[_room_bh(room.id, 0, 9, 22), _room_bh(room.id, 2, 9, 22)],
    )

    # now=MONDAY_LATE_UTC=22:00 KST → 월요일 슬롯 전부 past → 다음 빈 날 검색.
    resp = get_room_slots(session, room.id, MONDAY, now=MONDAY_LATE_UTC)  # type: ignore[arg-type]
    assert all(s.status == "past" for s in resp.slots)  # 월요일 전부 지난 시간
    # 화요일(6/16)=영업행 없음 → 건너뛰고 수요일(6/17)이 첫 빈 날.
    assert resp.next_available_date == WEDNESDAY


def test_next_available_date_within_horizon_only() -> None:
    """30일 내 빈 날 없으면 None(상한 단언 — 31일째 빈 날이 있어도 None, AC3·범위 결정 #2)."""
    room = _avail_room()
    # 매일 영업하되, target(월) 다음날부터 29일(6/16~7/14, 30일 창의 잔여)을 전부 휴무로 막는다.
    # 30일 창 밖(today+30=7/15)은 휴무가 아니지만 검색 상한을 넘어 도달하지 않는다 → None.
    holidays = [
        HolidayException(room_id=room.id, holiday_date=MONDAY + timedelta(days=i))
        for i in range(1, _RESERVATION_HORIZON_DAYS)  # 1..29 → 6/16~7/14
    ]
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, wd, 9, 22) for wd in range(7)],  # 매일 영업
        holidays=holidays,
    )

    resp = get_room_slots(session, room.id, MONDAY, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    # 30일 창 내 모든 다음날이 휴무 → next_available_date 없음(막다른 화면 금지 — 안내만).
    assert resp.next_available_date is None
    # 경계 확인: 창 밖 7/15는 휴무가 아니다(상한을 넘어 도달하지 않음을 데이터로 입증).
    assert (MONDAY + timedelta(days=_RESERVATION_HORIZON_DAYS)) not in {
        h.holiday_date for h in holidays
    }


def test_next_available_date_is_strictly_after_requested() -> None:
    """요청 날에 빈 슬롯이 있어도 next_available_date는 그 다음날 이후 첫 빈 날(요청 날 미포함)."""
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, wd, 9, 22) for wd in range(7)],  # 매일 영업
    )

    # now=새벽 → 월요일 자체에 가용 슬롯이 13개 있다. 그래도 다음 빈 날은 화요일(strictly after).
    resp = get_room_slots(session, room.id, MONDAY, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert any(s.status == "available" for s in resp.slots)  # 요청 날에도 빈 슬롯 존재
    assert resp.next_available_date == TUESDAY  # 그래도 다음날
    assert resp.next_available_date != MONDAY  # 요청 날 미포함


def test_get_room_slots_room_not_found() -> None:
    """미존재/비활성 룸 → DomainError(ROOM_NOT_FOUND)(get_room_summary와 공유 가드)."""
    inactive = _avail_room(is_active=False)
    session = FakeAvailabilitySession(rooms=[inactive])

    with pytest.raises(DomainError) as exc_info:
        get_room_slots(session, inactive.id, MONDAY, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert exc_info.value.code is ErrorCode.ROOM_NOT_FOUND

    with pytest.raises(DomainError) as exc_info2:
        get_room_slots(session, uuid.uuid4(), MONDAY, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert exc_info2.value.code is ErrorCode.ROOM_NOT_FOUND


def test_get_room_slots_is_read_only_no_writes() -> None:
    """슬롯 조회는 읽기 전용 — Room(get)·BusinessHours/HolidayException(exec)만, 쓰기 0(AC1).

    FakeAvailabilitySession은 commit/add/delete를 노출하지 않으므로 호출 시 AttributeError로
    깨진다(여기 도달 = 쓰기 0). next_available_date 검색이 후보 날짜마다 derive_slots만 돌리고
    DB를 재조회하지 않음도 조회 엔티티 한정으로 단언한다.
    """
    room = _avail_room()
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )

    get_room_slots(session, room.id, MONDAY, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert set(session.exec_entities) <= {Room, BusinessHours, HolidayException, ReservationSlot}


# ── 콤보 트리 list_regions (Story 3.4 — AC1 읽기 전용) ──────────────────────────
# 안정적 표준 b_code: 역삼동(강남구)·청운동(종로구). 시군구 라벨은 시도 포함.
GANGNAM_YEOKSAM = "1168010100"  # 서울특별시 강남구 역삼동
GANGNAM_SIGUNGU = "1168000000"  # 서울특별시 강남구
JONGNO_CHUNGUN = "1111010100"  # 서울특별시 종로구 청운동
JONGNO_SIGUNGU = "1111000000"  # 서울특별시 종로구


def test_list_regions_groups_by_sigungu_and_dong() -> None:
    """활성 룸을 시군구→동으로 그룹핑하고 시도 포함 라벨·room_count를 도출한다(AC1)."""
    # 강남구 역삼동 ×2, 종로구 청운동 ×1.
    r1 = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    r2 = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    r3 = _avail_room(admin_dong_code=JONGNO_CHUNGUN)
    session = FakeAvailabilitySession(rooms=[r1, r2, r3])

    groups = list_regions(session)  # type: ignore[arg-type]

    # 시군구 이름 오름차순: "서울특별시 강남구" < "서울특별시 종로구".
    assert [g.name for g in groups] == ["서울특별시 강남구", "서울특별시 종로구"]
    gangnam, jongno = groups
    assert gangnam.code == GANGNAM_SIGUNGU
    assert gangnam.room_count == 2  # 역삼동 2룸
    assert [d.name for d in gangnam.dongs] == ["역삼동"]
    assert gangnam.dongs[0].code == GANGNAM_YEOKSAM
    assert gangnam.dongs[0].room_count == 2
    assert jongno.code == JONGNO_SIGUNGU
    assert jongno.room_count == 1
    assert [d.name for d in jongno.dongs] == ["청운동"]


def test_list_regions_excludes_inactive() -> None:
    """비활성 룸은 콤보에서 제외된다(where(is_active) 모사)."""
    active = _avail_room(admin_dong_code=GANGNAM_YEOKSAM, is_active=True)
    inactive = _avail_room(admin_dong_code=JONGNO_CHUNGUN, is_active=False)
    session = FakeAvailabilitySession(rooms=[active, inactive])

    groups = list_regions(session)  # type: ignore[arg-type]

    assert [g.name for g in groups] == ["서울특별시 강남구"]  # 종로구(비활성) 미노출


def test_list_regions_empty_when_no_rooms() -> None:
    """활성 룸 0개 → 빈 리스트(정상, 에러 아님)."""
    assert list_regions(FakeAvailabilitySession(rooms=[])) == []  # type: ignore[arg-type]


def test_list_regions_unmapped_code_falls_back_to_code() -> None:
    """미매핑 b_code → 라벨이 코드 원문으로 폴백(조용한 크래시 금지 — graceful)."""
    # 9로 시작하는 가짜 코드(번들 미존재). 시군구/동 레벨 코드가 라벨이 된다.
    room = _avail_room(admin_dong_code="9999999900")
    session = FakeAvailabilitySession(rooms=[room])

    groups = list_regions(session)  # type: ignore[arg-type]

    assert len(groups) == 1
    # region_name None → 코드 원문 폴백(시군구=9999900000, 동=9999999900).
    assert groups[0].name == "9999900000"
    assert groups[0].dongs[0].name == "9999999900"


def test_list_regions_is_read_only() -> None:
    """콤보 조회는 읽기 전용 — Room만 조회하고 쓰기는 없다(commit/add/delete 미노출 → 깨짐)."""
    room = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    session = FakeAvailabilitySession(rooms=[room])

    list_regions(session)  # type: ignore[arg-type]

    assert set(session.exec_entities) <= {Room}


# ── 지역 목록 search_rooms (Story 3.4 — AC1·AC3·AC4 읽기 전용) ──────────────────
def test_search_rooms_filter_by_sigungu_returns_whole_gu() -> None:
    """시군구 코드 → 그 구의 모든 룸(동 무관). 다른 구 룸은 제외된다(AC1)."""
    gn = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    jn = _avail_room(admin_dong_code=JONGNO_CHUNGUN)
    session = FakeAvailabilitySession(
        rooms=[gn, jn],
        business_hours=[_room_bh(gn.id, 0, 9, 22), _room_bh(jn.id, 0, 9, 22)],
    )

    items = search_rooms(session, GANGNAM_SIGUNGU, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert {i.room_id for i in items} == {gn.id}  # 강남구만


def test_search_rooms_filter_by_dong_returns_only_dong() -> None:
    """동 코드 → 그 동의 룸만(같은 구 다른 동은 제외)."""
    yeoksam = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)  # 강남구 역삼동
    # 같은 강남구, 다른 동(개포동 1168010300).
    gaepo = _avail_room(admin_dong_code="1168010300")
    session = FakeAvailabilitySession(rooms=[yeoksam, gaepo])

    items = search_rooms(session, GANGNAM_YEOKSAM, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert {i.room_id for i in items} == {yeoksam.id}  # 역삼동만


def test_search_rooms_no_region_returns_all_active() -> None:
    """region_code=None → 전체 활성 룸(초기 목록)."""
    r1 = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    r2 = _avail_room(admin_dong_code=JONGNO_CHUNGUN)
    session = FakeAvailabilitySession(rooms=[r1, r2])

    items = search_rooms(session, None, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert {i.room_id for i in items} == {r1.id, r2.id}


def test_search_rooms_unmapped_code_returns_empty() -> None:
    """미매핑/미존재 region_code → 빈 리스트(200 — 에러 아님, 신규 ErrorCode 0)."""
    room = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    session = FakeAvailabilitySession(rooms=[room])

    assert search_rooms(session, "9999900000", now=MONDAY_EARLY_UTC) == []  # type: ignore[arg-type]


def test_search_rooms_excludes_inactive() -> None:
    """비활성 룸은 목록에서 제외된다(where(is_active) 모사)."""
    active = _avail_room(admin_dong_code=GANGNAM_YEOKSAM, is_active=True)
    inactive = _avail_room(admin_dong_code=GANGNAM_YEOKSAM, is_active=False)
    session = FakeAvailabilitySession(rooms=[active, inactive])

    items = search_rooms(session, GANGNAM_SIGUNGU, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert {i.room_id for i in items} == {active.id}


def test_search_rooms_fresh_remaining_slots() -> None:
    """remaining_slots가 derive_slots + >=now와 일치한다(AC4 신선 — aggregate_availability 동일)."""
    room = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )

    early = search_rooms(session, GANGNAM_SIGUNGU, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert early[0].remaining_slots == 13  # 09~22 전 슬롯 미래

    noon = search_rooms(session, GANGNAM_SIGUNGU, now=MONDAY_NOON_UTC)  # type: ignore[arg-type]
    assert noon[0].remaining_slots == 10  # 12:00 KST 이후만
    assert noon[0].remaining_slots < early[0].remaining_slots


def test_search_rooms_holiday_room_is_zero() -> None:
    """오늘 휴무인 룸 → remaining_slots == 0(영업시간 있어도)."""
    room = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    session = FakeAvailabilitySession(
        rooms=[room],
        business_hours=[_room_bh(room.id, 0, 9, 22)],
        holidays=[HolidayException(room_id=room.id, holiday_date=MONDAY)],
    )

    items = search_rooms(session, GANGNAM_SIGUNGU, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    assert items[0].remaining_slots == 0


def test_search_rooms_does_not_mix_room_business_hours() -> None:
    """룸 간 영업시간이 섞이지 않는다(room_id 그룹핑 — aggregate_availability AC4 격리 동일)."""
    a = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    b = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    session = FakeAvailabilitySession(
        rooms=[a, b],
        business_hours=[_room_bh(a.id, 0, 9, 22), _room_bh(b.id, 0, 9, 10)],
    )

    items = search_rooms(session, GANGNAM_SIGUNGU, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]
    by_room = {i.room_id: i.remaining_slots for i in items}
    assert by_room[a.id] == 13  # 자기 영업시간(09~22)
    assert by_room[b.id] == 1  # 자기 영업시간(09~10) — 섞이면 13/14


def test_search_rooms_omits_internal_fields() -> None:
    """RoomListItem은 공개 표면 필드만 — provider_id·lat/lng·admin_dong_code 미포함(AC4)."""
    room = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    session = FakeAvailabilitySession(rooms=[room])

    items = search_rooms(session, GANGNAM_SIGUNGU, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    keys = set(items[0].model_dump())
    assert keys == {
        "room_id", "name", "price_per_hour", "room_type", "amenities", "remaining_slots",
    }
    assert "provider_id" not in keys
    assert "lat" not in keys
    assert "admin_dong_code" not in keys


def test_search_rooms_is_read_only() -> None:
    """목록 조회는 읽기 전용 — Room/BusinessHours/HolidayException만, 쓰기 0."""
    room = _avail_room(admin_dong_code=GANGNAM_YEOKSAM)
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )

    search_rooms(session, GANGNAM_SIGUNGU, now=MONDAY_EARLY_UTC)  # type: ignore[arg-type]

    assert set(session.exec_entities) <= {Room, BusinessHours, HolidayException, ReservationSlot}


# ── 반경 검색 search_rooms (Story 3.5 — AC1·AC4 Haversine 읽기 전용) ────────────
# 중심 = 서울시청. 거리를 달리하는 좌표(가까운→먼). 거리 근사: 위도 1도 ≈ 111km.
RADIUS_CENTER = (37.5665, 126.9780)  # 서울시청(반경 중심)
NEAR_COORDS = (37.5665, 126.9780)  # 중심과 동일 ≈ 0km(반경 내)
MID_COORDS = (37.5800, 126.9780)  # 북쪽 ≈ 1.5km(3km 내·1km 밖)
FAR_COORDS = (37.4979, 127.0276)  # 강남역 ≈ 8.4km(3km 밖)


def test_search_rooms_radius_includes_within_excludes_outside() -> None:
    """반경 내(중심↔룸 ≤ 반경) 룸만 포함·반경 밖 제외(기본 3km, AC1①)."""
    near = _avail_room(lat=NEAR_COORDS[0], lng=NEAR_COORDS[1])
    far = _avail_room(lat=FAR_COORDS[0], lng=FAR_COORDS[1])
    session = FakeAvailabilitySession(rooms=[near, far])

    items = search_rooms(
        session,  # type: ignore[arg-type]
        center_lat=RADIUS_CENTER[0],
        center_lng=RADIUS_CENTER[1],
        radius_km=3.0,
        now=MONDAY_EARLY_UTC,
    )

    assert {i.room_id for i in items} == {near.id}  # 강남역(≈8km)은 반경 밖 제외


def test_search_rooms_radius_adjust_changes_membership() -> None:
    """radius_km 조정 시 포함 집합이 바뀐다(작은 반경=일부 제외, AC1②)."""
    near = _avail_room(lat=NEAR_COORDS[0], lng=NEAR_COORDS[1])  # 0km
    mid = _avail_room(lat=MID_COORDS[0], lng=MID_COORDS[1])  # ≈1.5km
    session = FakeAvailabilitySession(rooms=[near, mid])

    wide = search_rooms(
        session,  # type: ignore[arg-type]
        center_lat=RADIUS_CENTER[0],
        center_lng=RADIUS_CENTER[1],
        radius_km=3.0,
        now=MONDAY_EARLY_UTC,
    )
    assert {i.room_id for i in wide} == {near.id, mid.id}  # 3km=둘 다

    narrow = search_rooms(
        session,  # type: ignore[arg-type]
        center_lat=RADIUS_CENTER[0],
        center_lng=RADIUS_CENTER[1],
        radius_km=1.0,
        now=MONDAY_EARLY_UTC,
    )
    assert {i.room_id for i in narrow} == {near.id}  # 1km=mid(1.5km) 제외


def test_search_rooms_radius_default_is_3km() -> None:
    """radius_km 미지정 시 기본 3km가 적용된다(AC1②·AC4①)."""
    mid = _avail_room(lat=MID_COORDS[0], lng=MID_COORDS[1])  # ≈1.5km(3km 내)
    far = _avail_room(lat=FAR_COORDS[0], lng=FAR_COORDS[1])  # ≈8.4km(3km 밖)
    session = FakeAvailabilitySession(rooms=[mid, far])

    items = search_rooms(
        session,  # type: ignore[arg-type]
        center_lat=RADIUS_CENTER[0],
        center_lng=RADIUS_CENTER[1],
        now=MONDAY_EARLY_UTC,  # radius_km 생략 → 기본 3km
    )

    assert {i.room_id for i in items} == {mid.id}  # 3km 내만(far 제외)


def test_search_rooms_radius_sorted_by_distance_asc() -> None:
    """반경 결과는 거리 오름차순(가까운 순) 정렬된다(AC1③)."""
    near = _avail_room(lat=NEAR_COORDS[0], lng=NEAR_COORDS[1])  # 0km
    mid = _avail_room(lat=MID_COORDS[0], lng=MID_COORDS[1])  # ≈1.5km
    far = _avail_room(lat=FAR_COORDS[0], lng=FAR_COORDS[1])  # ≈8.4km
    # 입력은 의도적으로 먼 순서(정렬 단언이 입력 순서 우연 일치가 아님을 보장).
    session = FakeAvailabilitySession(rooms=[far, mid, near])

    items = search_rooms(
        session,  # type: ignore[arg-type]
        center_lat=RADIUS_CENTER[0],
        center_lng=RADIUS_CENTER[1],
        radius_km=10.0,  # 셋 다 포함
        now=MONDAY_EARLY_UTC,
    )

    assert [i.room_id for i in items] == [near.id, mid.id, far.id]  # 가까운→먼


def test_search_rooms_partial_coords_no_radius_filter() -> None:
    """중심 좌표가 하나만(부분) 있으면 반경 미적용 — 전체 활성 룸(graceful, AC4①)."""
    near = _avail_room(lat=NEAR_COORDS[0], lng=NEAR_COORDS[1])
    far = _avail_room(lat=FAR_COORDS[0], lng=FAR_COORDS[1])
    session = FakeAvailabilitySession(rooms=[near, far])

    items = search_rooms(
        session,  # type: ignore[arg-type]
        center_lat=RADIUS_CENTER[0],  # lng 없음 → 반경 미적용
        radius_km=3.0,
        now=MONDAY_EARLY_UTC,
    )

    assert {i.room_id for i in items} == {near.id, far.id}  # 반경 미적용=전체


def test_search_rooms_region_and_radius_intersection() -> None:
    """region_code + 좌표 동시 제공 시 둘 다 적용(교집합, AC4)."""
    # 강남구 + 중심 근처(포함).
    gn_near = _avail_room(
        admin_dong_code=GANGNAM_YEOKSAM, lat=NEAR_COORDS[0], lng=NEAR_COORDS[1]
    )
    # 강남구지만 반경 밖(지역 통과·반경 탈락).
    gn_far = _avail_room(
        admin_dong_code=GANGNAM_YEOKSAM, lat=FAR_COORDS[0], lng=FAR_COORDS[1]
    )
    # 중심 근처지만 종로구(반경 통과·지역 탈락).
    jn_near = _avail_room(
        admin_dong_code=JONGNO_CHUNGUN, lat=NEAR_COORDS[0], lng=NEAR_COORDS[1]
    )
    session = FakeAvailabilitySession(rooms=[gn_near, gn_far, jn_near])

    items = search_rooms(
        session,  # type: ignore[arg-type]
        GANGNAM_SIGUNGU,
        center_lat=RADIUS_CENTER[0],
        center_lng=RADIUS_CENTER[1],
        radius_km=3.0,
        now=MONDAY_EARLY_UTC,
    )

    assert {i.room_id for i in items} == {gn_near.id}  # 강남구 ∩ 반경 내


def test_search_rooms_radius_fresh_remaining_slots() -> None:
    """반경 결과의 remaining_slots도 신선 도출이 적용된다(AC4③ — 지역과 동일)."""
    room = _avail_room(lat=NEAR_COORDS[0], lng=NEAR_COORDS[1])
    session = FakeAvailabilitySession(
        rooms=[room], business_hours=[_room_bh(room.id, 0, 9, 22)]
    )

    early = search_rooms(
        session,  # type: ignore[arg-type]
        center_lat=RADIUS_CENTER[0],
        center_lng=RADIUS_CENTER[1],
        radius_km=3.0,
        now=MONDAY_EARLY_UTC,
    )
    assert early[0].remaining_slots == 13  # 전 슬롯 미래

    noon = search_rooms(
        session,  # type: ignore[arg-type]
        center_lat=RADIUS_CENTER[0],
        center_lng=RADIUS_CENTER[1],
        radius_km=3.0,
        now=MONDAY_NOON_UTC,
    )
    assert noon[0].remaining_slots == 10  # 12:00 KST 이후만
    assert noon[0].remaining_slots < early[0].remaining_slots


# ═══════════════════════════════════════════════════════════════════════════════════
# 제공자 소유 룸 조회 list_provider_rooms (Story 6.1 — 읽기 전용·소유권 축)
# ═══════════════════════════════════════════════════════════════════════════════════


class FakeProviderRoomsSession:
    """list_provider_rooms용 Fake 세션 — ``exec(select(Room).where(provider_id==X))`` 모사.

    실 SQL ``where(provider_id == X)``를 컴파일된 bind 파라미터로 충실히 재현해 **그 제공자 소유
    룸만**(``is_active`` 무관 — 소유자 뷰라 비활성 포함) 돌려준다(``FakeAvailabilitySession``의
    ``where(is_active)`` 모사와 의도적 대비). 읽기 전용이라 ``commit``/``add``/``delete``를 노출하지
    않는다 — 호출 시 ``AttributeError``로 즉시 깨져 "쓰기 없음"을 구조적으로 단언한다.
    """

    def __init__(self, rooms: list[Room] | None = None) -> None:
        self.rooms = rooms or []
        self.exec_calls = 0

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> _FakeResult:
        self.exec_calls += 1
        params = statement.compile().params
        provider_filter = params.get("provider_id_1")
        rows = [
            r
            for r in self.rooms
            if provider_filter is None or r.provider_id == provider_filter
        ]
        return _FakeResult(rows)


def _provider_room(provider_id: uuid.UUID, *, is_active: bool = True) -> Room:
    """특정 제공자 소유 룸(소유권 축 테스트용 — provider_id 명시)."""
    return Room(
        provider_id=provider_id,
        name="소유룸",
        price_per_hour=10000,
        capacity=4,
        room_type="open",
        amenities=[],
        lat=37.5,
        lng=127.0,
        admin_dong_code="1168010100",
        is_active=is_active,
    )


def test_list_provider_rooms_returns_own_only() -> None:
    """본인 소유 룸만 반환하고 타 제공자 룸은 제외한다(소유권 축 — AC3)."""
    me = uuid.uuid4()
    other = uuid.uuid4()
    mine = _provider_room(me)
    theirs = _provider_room(other)
    session = FakeProviderRoomsSession(rooms=[mine, theirs])

    result = list_provider_rooms(session, me)  # type: ignore[arg-type]

    assert result == [mine]  # 본인 1개만(타 제공자 제외)


def test_list_provider_rooms_includes_inactive() -> None:
    """비활성(운영중단) 룸도 포함한다(과거 예약을 제공자가 봐야 함 — is_active 필터 없음)."""
    me = uuid.uuid4()
    active = _provider_room(me, is_active=True)
    inactive = _provider_room(me, is_active=False)
    session = FakeProviderRoomsSession(rooms=[active, inactive])

    result = list_provider_rooms(session, me)  # type: ignore[arg-type]

    assert {r.id for r in result} == {active.id, inactive.id}  # 비활성 포함


def test_list_provider_rooms_empty_when_none_owned() -> None:
    """소유 룸이 0개면 빈 리스트(정상 — 이후 예약 조회도 빈 목록)."""
    session = FakeProviderRoomsSession(rooms=[_provider_room(uuid.uuid4())])

    assert list_provider_rooms(session, uuid.uuid4()) == []  # type: ignore[arg-type]


def test_list_provider_rooms_is_read_only() -> None:
    """list_provider_rooms는 조회만 한다(쓰기 메서드 미노출 Fake — 호출 시 깨짐으로 구조적 단언)."""
    me = uuid.uuid4()
    session = FakeProviderRoomsSession(rooms=[_provider_room(me)])

    list_provider_rooms(session, me)  # type: ignore[arg-type]

    assert session.exec_calls == 1  # select 1회
    assert not hasattr(session, "committed")  # 쓰기 인터페이스 자체가 없음(읽기 전용)
