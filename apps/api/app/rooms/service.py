"""rooms 도메인 서비스: 슬롯 도출 순수 함수 (Story 2.1).

슬롯은 **물리 테이블이 아니라 도출**된다(architecture.md §Cross-Component L360-362):

    슬롯 = (요일별 영업시간 − 휴무일 − 이미 예약)

고정 1시간 단위이며, 영업시간은 같은 날 내(자정 넘김 없음 — ``ck_business_hours_hours_order``
가 DB에서 강제)라 슬롯 소속 날짜가 모호하지 않다.

**이 함수는 순수 함수다** — DB에 접근하지 않고 모든 입력을 인자로 받는다(import 시점 부작용
0). 소비처가 ORM 조회 결과(``business_hours``·``holiday_dates``·``reserved_starts``)를 주입한다.
이로써 단위 테스트가 라이브 DB 없이 실제 입력→출력을 직접 단언할 수 있다(Fake 불필요).

**시간 규약(AC3, core/time):** ``open_time``/``close_time``은 ROOM_TZ **벽시계** 시각이고,
반환되는 ``slot_start``는 **UTC 인스턴트**(tz-aware)다. 벽시계→UTC 변환은 이 함수가 담당한다
(09:00 KST = 00:00 UTC, −9h). KST(Asia/Seoul)는 DST가 없어 ``combine`` + ``astimezone``이
결정적이다(멀티-tz DST gap/fold 경계 처리는 1.5 defer — 멀티-tz 도입 시).

소비처(후속): Story 3.1(가용성 집계 = "오늘 남은 빈 슬롯 수"), Story 4.9(예약 차감 연결).
이 함수가 그 단일 출처다.

**쓰기 경로(Story 2.2):** ``create_room``(provider 공간 등록)·``geocode_address``(카카오
주소 검색 백엔드 프록시)를 추가한다. 라우터/RBAC는 ``router.py``가, 검증은 ``schemas.py``가
담당하고, 이 모듈은 도메인 로직(선검사·원자 삽입·제약명 선별 변환·업스트림 호출)만 진다.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Collection, Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.core.config import get_settings
from app.core.db import violated_constraint
from app.core.errors import DomainError, ErrorCode
from app.core.pagination import decode_offset, offset_next_cursor
from app.core.time import ROOM_TZ, now_utc, to_tz, today_in_tz
from app.reservations.service import (
    confirmed_slot_starts,
    confirmed_slot_starts_by_room,
)
from app.rooms.geo import haversine_km
from app.rooms.models import BusinessHours, HolidayException, Room
from app.rooms.regions import leaf_name, level_codes, region_name
from app.rooms.schemas import (
    BusinessHoursPublic,
    GeocodeResult,
    ProviderRoomDetail,
    Region,
    RegionGroup,
    RoomAvailability,
    RoomCreateRequest,
    RoomListItem,
    RoomMapItem,
    RoomSlot,
    RoomSlotsResponse,
    RoomSummary,
    RoomUpdateRequest,
    SlotStatus,
)

_SLOT_LENGTH = timedelta(hours=1)  # 고정 1시간 단위(AC2)
_DEFAULT_RADIUS_KM = 3.0  # 반경 검색 기본 반경(Story 3.5 — radius_km 미지정 시)
# 예약 가능 기간 상한(Story 4.3 범위 결정 #2) — 오늘 포함 ~ 오늘+29일(=30일 창). 달력 선택
# 가능 범위·next_available_date forward 검색 상한을 이 값으로 고정한다(무제한 미래 검색 금지).
_RESERVATION_HORIZON_DAYS = 30

# ── 카카오 지오코딩(AC2 — NFR-6: REST 키는 백엔드 전용) ─────────────────────────
_KAKAO_ADDRESS_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/address.json"
_GEOCODE_TIMEOUT_SECONDS = 10.0  # httpx 타임아웃 — 초과 시 502 GEOCODING_UNAVAILABLE


def derive_slots(
    business_hours: Iterable[BusinessHours],
    holiday_dates: Collection[date],
    target_date: date,
    reserved_starts: Collection[datetime] = frozenset(),
    tz: ZoneInfo = ROOM_TZ,
) -> list[datetime]:
    """한 룸의 ``target_date`` 가용 슬롯 시작시각(UTC)을 오름차순으로 도출한다.

    Args:
        business_hours: 그 룸의 요일별 영업시간 행들(``weekday``·``open_time``·``close_time``).
            ``target_date``의 요일에 해당하는 행만 사용한다.
        holiday_dates: 그 룸의 휴무 날짜 집합(ROOM_TZ 기준 ``date``).
        target_date: 슬롯을 도출할 날짜(ROOM_TZ 기준).
        reserved_starts: 이미 예약된 ``slot_start``(UTC) 집합 — 이 시작시각은 제외한다.
            Story 2.1에서 호출부는 빈 집합을 전달하고(예약 도메인 부재), 실제 예약 차감은
            reservations가 생기는 Story 4.9에서 연결한다.
        tz: 룸 소재지 타임존(벽시계 해석 기준). 기본 ROOM_TZ=Asia/Seoul.

    Returns:
        오름차순 tz-aware **UTC** ``slot_start`` 리스트. 휴무·미영업 요일·전부 예약 시 ``[]``.

    Raises:
        ValueError: ``target_date``/``holiday_dates`` 항목이 순수 ``date``가 아니거나
            (``datetime`` 금지), ``reserved_starts`` 항목이 naive(tz 없음)일 때.
            core/time ``_require_aware`` fail-fast 철학과 일관 — **조용한 무시 금지**.

    규칙:
        ① ``target_date``가 휴무면 ``[]``.
        ② 그 요일 영업행이 없으면(미영업) ``[]``.
        ③ ``open_time``부터 1시간 간격으로, ``walltime + 1h <= close_time``인 동안 슬롯 생성
           (부분 잔여 시간 < 1h은 제외 = 고정 1시간 단위).
        ④ 각 슬롯의 벽시계 ``(target_date, time)``를 ROOM_TZ로 aware 생성 후 ``.astimezone(UTC)``.
        ⑤ ``reserved_starts``에 있는 ``slot_start``는 제외한다.
    """
    # ⓪ 입력 계약 fail-fast(core/time의 _require_aware 철학과 일관 — 조용한 무시 금지):
    #   · ``datetime``은 ``date``의 하위형이라 isinstance(x, date)를 통과하지만, 휴무 집합
    #     멤버십(``date == datetime``은 **항상 False**)·요일 판정이 어긋나 휴무/요일이
    #     조용히 빗나간다 → date 자리에 들어온 datetime을 명시 거부한다.
    #   · ``reserved_starts``의 naive datetime은 aware UTC 슬롯과 결코 같지 않아(차감 실패)
    #     이미 예약된 슬롯이 "가용"으로 남는다 → naive를 명시 거부한다.
    if isinstance(target_date, datetime):
        raise ValueError("target_date는 date여야 합니다 (datetime 금지 — 날짜 경계가 모호).")
    for holiday in holiday_dates:
        if isinstance(holiday, datetime):
            raise ValueError("holiday_dates 항목은 date여야 합니다 (datetime 금지).")
    for reserved_start in reserved_starts:
        if reserved_start.tzinfo is None or reserved_start.utcoffset() is None:
            raise ValueError(
                "reserved_starts 항목은 tz-aware여야 합니다 (naive datetime 금지) — "
                "예약 slot_start는 UTC로 저장·전달됩니다."
            )

    # ① 휴무일 → 영업시간과 무관하게 슬롯 0.
    if target_date in holiday_dates:
        return []

    # ② 대상 날짜의 요일(월=0~일=6)에 해당하는 영업행만 사용한다.
    #    DB는 uq_business_hours_room_id_weekday로 룸·요일당 1행을 보장하지만, 함수는
    #    방어적으로 매칭되는 모든 행을 처리한다(중복 시 set으로 합쳐 결정적 결과 유지).
    weekday = target_date.weekday()
    reserved = set(reserved_starts)
    starts: set[datetime] = set()

    for bh in business_hours:
        if bh.weekday != weekday:
            continue
        # ③ open_time부터 1시간 스텝. 벽시계 naive로 스텝 계산 후 tz를 부착(KST=DST 없음).
        wall = datetime.combine(target_date, bh.open_time)
        close_wall = datetime.combine(target_date, bh.close_time)
        while wall + _SLOT_LENGTH <= close_wall:
            # ④ 벽시계(ROOM_TZ) → UTC 인스턴트. replace(tzinfo=tz)는 벽시계 해석(변환 아님),
            #    이어서 astimezone(UTC)로 실제 UTC 순간을 얻는다.
            slot_utc = wall.replace(tzinfo=tz).astimezone(UTC)
            starts.add(slot_utc)
            wall += _SLOT_LENGTH

    # ⑤ 예약 차감 + 오름차순 정렬.
    return sorted(starts - reserved)


def aggregate_availability(
    session: Session, *, now: datetime | None = None
) -> list[RoomAvailability]:
    """활성 룸별 "오늘(ROOM_TZ) 현재시각 이후 남은 빈 슬롯 수"를 1회 집계한다(AC1·AC2·AC4).

    핀 색(FR-5)을 **서버 집계값**으로 결정하기 위한 읽기 전용 집계다 — 클라이언트가 핀마다
    슬롯을 재계산하지 않도록(architecture.md L362 금지 안티패턴, NFR-2) 서버가 한 번에 센다.
    슬롯 도출은 ``derive_slots``(단일 출처)를 그대로 재사용하며 여기서 재구현하지 않는다.

    Args:
        session: DB 세션(읽기 전용 — ``commit``/``add``/``delete`` 호출 0).
        now: 기준 현재시각(tz-aware UTC). 테스트 결정성을 위해 주입받으며, 미지정 시
            ``now_utc()``(core/time 단일 출처)를 쓴다. ``datetime.now()`` 직접 호출 금지.

    Returns:
        활성 룸마다 ``RoomAvailability(room_id, remaining_slots)``. 활성 룸이 0개면 ``[]``
        (정상 200 — 에러 아님). 메타데이터(좌표/가격 등)는 싣지 않는다(AC3).

    집계 규칙:
        ① **대상 = 활성 룸만**(``is_active=True``) — 비활성 룸은 핀에서 제외(E8 전제).
        ② **"오늘"=ROOM_TZ 기준 날짜**(``today_in_tz`` — UTC 로컬 날짜로 판정 금지, NFR-1).
        ③ 영업시간·휴무를 **벌크 조회 후 room_id별 그룹핑**(N+1 회피) — 각 룸 호출에 **그 룸의
           행만** 넘긴다(AC4 — derive_slots가 room_id를 안 보므로 섞으면 합쳐진다, 회고 회수).
        ④ ``reserved_starts=frozenset()`` 명시 전달(AC2 — reservations 부재, **Story 4.9 예약
           차감 연결 지점**). ⑤ ``slot_start >= now``인 슬롯만 카운트("오늘 현재시각 이후 남은").
    """
    # ② "오늘"은 ROOM_TZ 기준 — now(aware UTC)를 단일 진입점으로 고정한다.
    current = now if now is not None else now_utc()
    target_date = today_in_tz(ROOM_TZ, now=current)

    # ① 활성 룸만 — ``Room.is_active == True``는 ruff E712(불리언 비교)에 걸리므로 col(...).is_().
    active_rooms = list(
        session.exec(select(Room).where(col(Room.is_active).is_(True))).all()
    )
    if not active_rooms:
        return []  # 활성 룸 0개 = 정상 빈 리스트(200)
    active_room_ids = [room.id for room in active_rooms]

    # ③ 영업시간 벌크 조회 후 room_id별 그룹핑(N+1 회피 + AC4 룸 격리의 회수 지점).
    hours_by_room: dict[uuid.UUID, list[BusinessHours]] = defaultdict(list)
    hours_rows = session.exec(
        select(BusinessHours).where(col(BusinessHours.room_id).in_(active_room_ids))
    ).all()
    for hours_row in hours_rows:
        hours_by_room[hours_row.room_id].append(hours_row)

    # 휴무도 동일하게 벌크 조회 후 room_id별 date 집합으로 그룹핑.
    holidays_by_room: dict[uuid.UUID, set[date]] = defaultdict(set)
    holiday_rows = session.exec(
        select(HolidayException).where(
            col(HolidayException.room_id).in_(active_room_ids)
        )
    ).all()
    for holiday_row in holiday_rows:
        holidays_by_room[holiday_row.room_id].add(holiday_row.holiday_date)

    # Story 4.9: 활성 점유 슬롯을 벌크 1회 조회 후 room_id별 그룹핑(N+1 회피 — 영업시간/휴무 벌크
    # 패턴과 동형). reservation_slots SQL을 직접 만지지 않고 reservations.service reader를 경유한다
    # (도메인 경계 — architecture.md L354). on_or_after=current로 과거 점유를 빼 집합 크기를
    # 미래로 제한한다(아래 >= current 카운트라 동작 보존 — Dev Notes "on_or_after 최적화").
    reserved_by_room = confirmed_slot_starts_by_room(
        session, active_room_ids, on_or_after=current
    )

    results: list[RoomAvailability] = []
    for room in active_rooms:
        # AC4 핵심: 각 룸 호출에 **그 룸의 영업시간/휴무 행만** 넘긴다(섞으면 슬롯이 합쳐짐).
        # 그룹에 없는 룸은 빈 입력 → derive_slots가 [] → remaining_slots=0.
        slots = derive_slots(
            hours_by_room.get(room.id, []),
            holidays_by_room.get(room.id, set()),
            target_date,
            # Story 4.9: 그 룸의 활성 점유를 차감(영업시간 − 휴무 − 예약). 점유 0건 룸은
            # frozenset() 폴백 → 차감 없음. derive_slots가 starts − reserved로 제거하므로
            # remaining_slots는 "예약된 슬롯을 뺀 남은 빈 슬롯 수"가 된다(AC1).
            reserved_starts=reserved_by_room.get(room.id, frozenset()),
        )
        # "오늘 현재시각 이후 남은" — 도출값(aware UTC)과 now(aware UTC)를 직접 비교한다.
        # is_within_hours/hours_until은 윈도우 판정용(1.5 float 경계 defer)이라 쓰지 않는다.
        # 경계는 >=(now에 시작하는 슬롯 포함)로 고정한다.
        remaining = sum(1 for slot_start in slots if slot_start >= current)
        results.append(
            RoomAvailability(room_id=room.id, remaining_slots=remaining)
        )
    return results


def list_active_rooms(session: Session) -> list[RoomMapItem]:
    """활성 룸의 핀 메타(``{room_id, name, lat, lng}``)를 반환한다(읽기 전용, AC1).

    첫 진입 지도 핀 좌표 공급(FR-4) — ``aggregate_availability``가 좌표를 의도적으로 빼고
    ``{room_id, remaining_slots}``만 돌려주므로(3.1 AC3), 좌표·이름은 이 탐색/목록
    엔드포인트가 책임진다. 프론트가 두 응답을 ``room_id``로 인메모리 조인한다.

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).

    Returns:
        활성 룸마다 ``RoomMapItem(room_id, name, lat, lng)``. 활성 룸이 0개면 ``[]``
        (정상 200 — 에러 아님). 상세 메타(가격/영업시간/부대시설/provider_id 등)는 싣지
        않는다(과조회 방지 + 공개 엔드포인트 provider_id 노출 회피, AC1 — 상세는 3.3 소유).

    범위 = **전체 활성 룸**(필터 없음). bbox/반경/지역 필터·페이지네이션은 3.4·3.5
    소유(KTH 3.1 결정 #2: 초기 전체 활성 룸, bbox 최적화는 3.5 보류 → 클라가 화면 범위
    핀만 골라 색칠). 공개·무제한 스캔의 페이지네이션/레이트리밋 부재는 availability와 동일
    계열의 deferred(Dev Notes).
    """
    # 활성 룸만 — ``Room.is_active == True``는 ruff E712(불리언 비교)에 걸리므로 col(...).is_().
    rooms = session.exec(
        select(Room).where(col(Room.is_active).is_(True))
    ).all()
    # Room.id를 room_id로 명시 매핑(from_attributes 자동 매핑에 의존하지 않음 — 키 이름 변환).
    return [
        RoomMapItem(room_id=room.id, name=room.name, lat=room.lat, lng=room.lng)
        for room in rooms
    ]


def _get_active_room_or_404(session: Session, room_id: uuid.UUID) -> Room:
    """단일 룸을 조회하되 미존재 **또는** 비활성이면 404 ``ROOM_NOT_FOUND``로 합친다.

    ``get_room_summary``(3.3)·``get_room_slots``(4.3)가 공유하는 단일 룸 404 가드다 — 활성 룸만
    공개 표면 대상이므로 미존재/비활성을 동일 404로 합친다(``update_room`` 미존재/비-소유 합침
    선례). ``ROOM_NOT_FOUND``는 2.3에서 이미 정의됨(신규 ErrorCode 0). 읽기 전용(``session.get``만).
    """
    room = session.get(Room, room_id)
    if room is None or not room.is_active:
        raise DomainError(
            ErrorCode.ROOM_NOT_FOUND,
            "해당 공간을 찾을 수 없습니다.",
        )  # 404
    return room


def get_my_room(session: Session, provider_id: uuid.UUID) -> ProviderRoomDetail:
    """provider 본인 룸 상세를 폼 prefill 형태로 반환한다(``GET /rooms/mine``).

    제공자당 1개(``uq_rooms_provider_id``)라 ``provider_id``로 0..1개를 조회한다. 없으면 404
    ``ROOM_NOT_FOUND``(아직 등록 안 함 → 폼은 생성 모드로 분기). 활성 여부와 무관하게 본인 룸을
    돌려준다(비활성 캐스케이드된 본인 룸도 수정 화면에서 보이게 — 소유자 표면). 영업시간은
    weekday 오름차순으로 함께 싣는다(수정 폼 prefill).
    """
    room = session.exec(
        select(Room).where(Room.provider_id == provider_id)
    ).first()
    if room is None:
        raise DomainError(ErrorCode.ROOM_NOT_FOUND, "등록된 공간이 없습니다.")  # 404
    hours = list(
        session.exec(
            select(BusinessHours).where(BusinessHours.room_id == room.id)
        ).all()
    )
    sorted_hours = sorted(hours, key=lambda bh: bh.weekday)
    return ProviderRoomDetail(
        room_id=room.id,
        name=room.name,
        price_per_hour=room.price_per_hour,
        capacity=room.capacity,
        room_type=room.room_type,
        amenities=list(room.amenities),
        lat=room.lat,
        lng=room.lng,
        admin_dong_code=room.admin_dong_code,
        address=room.address,
        business_hours=[
            BusinessHoursPublic(
                weekday=bh.weekday, open_time=bh.open_time, close_time=bh.close_time
            )
            for bh in sorted_hours
        ],
    )


def get_room_summary(
    session: Session, room_id: uuid.UUID, *, now: datetime | None = None
) -> RoomSummary:
    """단일 룸의 바텀시트 요약(가격·수용·룸형태·부대시설·영업시간 + 신선 잔여 슬롯)을 반환한다.

    바텀시트 단일 룸 신선 요약(Story 3.3, AC1·AC4) — 공개·``provider_id`` 미노출. 핀 탭 시점의
    동결 스냅샷이 아니라, ``remaining_slots``를 ``derive_slots``(2.1) 재사용으로 **이 조회 시점에
    신선 계산**한다(3.2 stale 배지 회수). 4.2 상세 화면이 이 요약을 후기/예약 UI로 확장한다.

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).
        room_id: 조회 대상 룸 PK.
        now: 기준 현재시각(tz-aware UTC). 테스트 결정성을 위해 주입받으며, 미지정 시
            ``now_utc()``를 쓴다(``datetime.now()`` 직접 호출 금지 — 1.5/3.1 패턴).

    Returns:
        ``RoomSummary`` — ``business_hours``는 ``weekday`` 오름차순. ``is_closed_today``는
        오늘(ROOM_TZ)이 휴무인지(시트 "오늘 휴무" 표시·배지-영업행 모순 방지). ``lat``/``lng``는
        상세 위치 미니 지도용 좌표(Story 4.2 신규 노출). ``address``는 표시용 주소(provider 입력,
        미입력 null)로 노출. provider_id·is_active·admin_dong_code는 미노출(내부/소유 필드).

    Raises:
        DomainError: 미존재 **또는** 비활성 룸이면 404 ``ROOM_NOT_FOUND``. 탐색 핀은 활성 룸만
            띄우므로 미존재/비활성을 동일 404로 합친다(``update_room``의 미존재/비-소유 합침 선례).
    """
    # 미존재/비활성을 동일 404로 합친다(활성 룸만 탐색 대상 — 공유 헬퍼, get_room_slots와 재사용).
    room = _get_active_room_or_404(session, room_id)

    # 오늘 신선 remaining_slots — aggregate_availability의 단일 룸 판(슬롯 로직 중복 금지).
    current = now if now is not None else now_utc()
    target_date = today_in_tz(ROOM_TZ, now=current)
    business_hours = list(
        session.exec(
            select(BusinessHours).where(BusinessHours.room_id == room_id)
        ).all()
    )
    holiday_rows = session.exec(
        select(HolidayException).where(HolidayException.room_id == room_id)
    ).all()
    holiday_dates = {row.holiday_date for row in holiday_rows}
    # Story 4.9: 이 룸의 활성 점유를 차감(단일 룸 reader — get_room_slots/room_remaining_slots와
    # 동일). on_or_after=current로 과거 점유 제외(아래 >= current 카운트라 동작 보존).
    reserved = confirmed_slot_starts(session, room_id, on_or_after=current)
    # derive_slots(2.1) 재사용 — starts − reserved로 예약된 슬롯을 뺀 남은 빈 슬롯만 남는다(AC1).
    slots = derive_slots(
        business_hours, holiday_dates, target_date, reserved_starts=reserved
    )
    # aggregate_availability와 동일 경계 >= current 직접 비교(is_within_hours 회피 = 1.5 defer).
    remaining = sum(1 for slot_start in slots if slot_start >= current)
    # 오늘 휴무 여부(code-review). 휴무면 remaining 0이라 배지는 "마감"인데 클라의 weekday 영업행은
    # 남아 모순 → 서버가 휴무를 신호해 시트가 "오늘 휴무"로 표시하게 한다.
    is_closed_today = target_date in holiday_dates

    # weekday 오름차순 매핑(시트 표시 안정). Room.id → room_id 명시(from_attributes 미사용).
    sorted_hours = sorted(business_hours, key=lambda bh: bh.weekday)
    return RoomSummary(
        room_id=room.id,
        name=room.name,
        price_per_hour=room.price_per_hour,
        capacity=room.capacity,
        room_type=room.room_type,
        amenities=list(room.amenities),
        business_hours=[
            BusinessHoursPublic(
                weekday=bh.weekday, open_time=bh.open_time, close_time=bh.close_time
            )
            for bh in sorted_hours
        ],
        remaining_slots=remaining,
        is_closed_today=is_closed_today,
        # 위치 미니 지도(Story 4.2) — 저장 좌표를 그대로 노출(RoomMapItem 명시 매핑 선례).
        lat=room.lat,
        lng=room.lng,
        address=room.address,
    )


def room_remaining_slots(
    session: Session, room: Room, *, now: datetime | None = None
) -> int:
    """단일 룸의 "오늘(ROOM_TZ) 현재시각 이후 남은 빈 슬롯 수"를 신선 집계한다(읽기 전용).

    ``get_room_summary``의 슬롯 집계 로직을 **재사용 가능한 단위**로 노출한다 — favorites(3.7)가
    즐겨찾기 행마다 신선 ``remaining_slots``를 채울 때 이 함수를 호출한다(슬롯 로직 중복 금지 +
    도메인 경계 준수: favorites는 ``BusinessHours``/``HolidayException`` SQL을 직접 만지지 않고
    rooms 도메인의 이 함수를 경유한다, architecture.md L354). ``derive_slots``(2.1) 재사용,
    ``reserved_starts=frozenset()``은 Story 4.9 예약 차감 지점(3.1/3.3 동일).

    Args:
        session: DB 세션(**읽기 전용**). room: 슬롯을 셀 룸(호출처가 이미 보유).
        now: 기준 현재시각(tz-aware UTC). 미지정 시 ``now_utc()``(직접 ``datetime.now()`` 금지).
    """
    current = now if now is not None else now_utc()
    target_date = today_in_tz(ROOM_TZ, now=current)
    business_hours = list(
        session.exec(
            select(BusinessHours).where(BusinessHours.room_id == room.id)
        ).all()
    )
    holiday_rows = session.exec(
        select(HolidayException).where(HolidayException.room_id == room.id)
    ).all()
    holiday_dates = {row.holiday_date for row in holiday_rows}
    # Story 4.9: 이 룸의 활성 점유를 차감(단일 룸 reader — get_room_summary 동일). 즐겨찾기
    # 행마다 신선 잔여를 채울 때도 예약을 뺀 남은 빈 슬롯 수가 된다(AC1).
    reserved = confirmed_slot_starts(session, room.id, on_or_after=current)
    slots = derive_slots(
        business_hours, holiday_dates, target_date, reserved_starts=reserved
    )
    return sum(1 for slot_start in slots if slot_start >= current)


def get_room_slots(
    session: Session,
    room_id: uuid.UUID,
    target_date: date,
    *,
    now: datetime | None = None,
) -> RoomSlotsResponse:
    """단일 룸의 ``target_date`` 1시간 슬롯을 상태별로 + 다음 빈 날짜를 반환한다(읽기 전용, AC1).

    ``GET /rooms/{room_id}/slots?date=``의 데이터다 — ``get_room_summary``(3.3)가 **오늘** 슬롯의
    **카운트**(``remaining_slots``)만 주는 데 비해, 이 함수는 **임의 ``target_date``**의 **슬롯
    리스트 + 슬롯별 상태**(``available``/``past``/``reserved``)와 **다음 빈 날짜**를 준다. 같은
    ``derive_slots``(2.1)·같은 404 가드(``_get_active_room_or_404``)·같은 ``>= current`` 경계를
    쓰되 카운트 대신 슬롯별 ``status``를 매핑한다(슬롯 도출 로직 재구현 0 — 단일 출처).

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).
        room_id: 조회 대상 룸 PK. target_date: 슬롯을 도출할 날짜(ROOM_TZ 기준).
        now: 기준 현재시각(tz-aware UTC). 테스트 결정성을 위해 주입받으며, 미지정 시
            ``now_utc()``를 쓴다(``datetime.now()`` 직접 호출 금지 — 1.5/3.1/3.3 패턴).

    Returns:
        ``RoomSlotsResponse(date, slots, next_available_date)``. ``slots``는 그날 1시간 슬롯을
        시작시각 오름차순으로 상태와 함께 싣는다(휴무·미영업 요일 → 빈 리스트, 에러 아님).
        ``next_available_date``는 ``target_date`` **다음날부터** 30일 상한 내 첫 "가용 슬롯 ≥ 1개"
        날(없으면 ``None``).

    Raises:
        DomainError: 미존재/비활성 룸이면 404 ``ROOM_NOT_FOUND``(``get_room_summary`` 동일 가드).

    상태 매핑 우선순위(``reserved`` → ``past`` → ``available``): ``reserved``를 먼저 판정해야
    4.9 예약 차감 연결 후 "예약+과거" 슬롯이 일관 표기된다. 현재 ``reserved_starts=frozenset()``
    이라 ``reserved`` 상태는 미발생한다(**Story 4.9 예약 차감 연결 지점** — 3.1·3.3 동일 seam).
    """
    # 미존재/비활성 → 404(get_room_summary와 공유 헬퍼). 읽기 전용 — 쓰기 호출 0.
    _get_active_room_or_404(session, room_id)

    current = now if now is not None else now_utc()
    # 영업시간·휴무 1회 조회 — next_available_date 검색이 후보 날짜마다 재사용한다(루프 내 DB 0).
    # 단일 룸이라 room_id 그룹핑 불요(3.1 AC4 회수는 다중 룸 집계 한정).
    business_hours = list(
        session.exec(
            select(BusinessHours).where(BusinessHours.room_id == room_id)
        ).all()
    )
    holiday_rows = session.exec(
        select(HolidayException).where(HolidayException.room_id == room_id)
    ).all()
    holiday_dates = {row.holiday_date for row in holiday_rows}

    # Story 4.9: 이 룸의 활성 점유 슬롯 집합(단일 룸 reader). on_or_after는 **주지 않는다** —
    # 표시는 임의 target_date(미래/과거)의 슬롯을 다루므로 과거 점유도 reserved로 표기해야
    # 일관된다(카운트 4곳과 달리 "남은 수"가 아니라 "상태 표시"). instant 매칭이라 타 날짜
    # 슬롯과 우연 일치 불가(UTC 정시 인스턴트).
    reserved = confirmed_slot_starts(session, room_id)

    # ① ⚠️ 핵심 비대칭(Dev Notes "최대 함정"): 표시용 슬롯 리스트는 derive_slots에 frozenset()을
    #    줘 **전 슬롯을 유지**한다(예약 슬롯이 사라지지 않게). 예약 여부는 _slot_status에 **실제
    #    reserved set**을 줘 status="reserved"로 표기한다(취소선·비활성). derive_slots에 reserved를
    #    주면 starts − reserved로 **소멸**해 "원래 영업 안 함"처럼 보이는 회귀가 난다(AC2).
    starts = derive_slots(
        business_hours, holiday_dates, target_date, reserved_starts=frozenset()
    )
    slots = [
        RoomSlot(slot_start=slot_start, status=_slot_status(slot_start, current, reserved))
        for slot_start in starts
    ]

    # ② 다음 빈 날짜 검색 — 같은 룸 데이터를 in-memory로 반복(DB 재조회 0). target_date 다음날부터
    #    오늘+29일(30일 상한, 범위 결정 #2)까지. 무제한 미래 검색 금지.
    #    ⚠️ 표시와 달리 next_available은 **만석 날을 건너뛰어야** 하므로 reserved를 **차감**한다
    #    (후보 날짜의 예약 슬롯이 빠져 "가용 ≥1" 판정이 정확 — AC2).
    next_available = _next_available_date(
        business_hours, holiday_dates, target_date, current, reserved
    )
    return RoomSlotsResponse(
        date=target_date, slots=slots, next_available_date=next_available
    )


def _slot_status(
    slot_start: datetime, current: datetime, reserved: Collection[datetime]
) -> SlotStatus:
    """단일 슬롯의 상태를 매핑한다(``reserved`` → ``past`` → ``available`` 우선순위, AC2).

    경계는 ``slot_start >= current``를 ``available``로 본다(3.1·3.3 ``>= current`` 직접 인스턴트
    비교와 동일 — ``is_within_hours``/``hours_until`` 회피, 1.5 float 경계 defer 우회). ``reserved``
    를 먼저 판정해 4.9 연결 후 "예약+과거" 슬롯이 일관 표기되게 한다(현재 ``reserved`` 빈 집합).
    """
    if slot_start in reserved:
        return "reserved"  # 현재 미발생(reserved_starts=frozenset()) — Story 4.9 연결 지점
    if slot_start < current:
        return "past"  # 룸 타임존 기준 현재시각 이전(지난 시간)
    return "available"  # slot_start >= current + 미예약 → 선택 가능


def _next_available_date(
    business_hours: list[BusinessHours],
    holiday_dates: Collection[date],
    target_date: date,
    current: datetime,
    reserved: Collection[datetime] = frozenset(),
) -> date | None:
    """``target_date`` **다음날부터** 30일 상한 내 첫 "가용 슬롯 ≥ 1개" 날을 찾는다(AC3).

    같은 ``business_hours``/``holiday_dates``를 재사용해 후보 날짜마다 ``derive_slots``만 재호출
    한다(DB 재조회 0). 검색 상한 = ``today(ROOM_TZ) + 29일``(30일 창, 범위 결정 #2 — 무제한 미래
    검색 금지). "가용"은 ``slot_start >= current``인 슬롯(미래 날짜는 전부 가용). 없으면 ``None``.

    **Story 4.9:** ``reserved``(이 룸의 활성 점유 slot_start 집합 — 전 날짜 포함)를 후보 날짜마다
    ``derive_slots``에 차감해, 전부 예약된 만석 날을 "가용"으로 잘못 제안하지 않는다(AC2). reserved
    는 전 날짜를 담지만 instant 매칭이라 각 후보 날짜의 슬롯에만 적용된다(타 날짜와 우연 일치 불가).
    """
    today = today_in_tz(ROOM_TZ, now=current)
    # 상한 = 오늘 포함 30일 창의 마지막 날(today + 29일). target_date가 과거라 다음날이 오늘
    # 이전이어도 후보는 그 다음날부터 돌되, 상한은 오늘 기준이라 30일 창을 넘지 않는다.
    horizon_last = today + timedelta(days=_RESERVATION_HORIZON_DAYS - 1)
    # 하한 클램프(code-review P1 — 공개 무인증 엔드포인트 DoS 방어): 후보 시작은 요청 날 다음날과
    # "오늘" 중 늦은 쪽. target_date가 먼 과거여도(예: ?date=0001-01-01) 루프가 과거 수만~수십만
    # 일을 순회하지 않게 today로 끌어올린다. 과거 날은 slot_start >= current가 어차피 0이라 결과
    # 불변(동작 보존) — 단지 의미 없는 과거 순회를 제거해 반복 횟수를 30일 창 이하로 고정한다.
    candidate = max(target_date + timedelta(days=1), today)  # 요청 날 제외 + 과거 하한 클램프
    while candidate <= horizon_last:
        candidate_slots = derive_slots(
            business_hours, holiday_dates, candidate, reserved_starts=reserved
        )
        if any(slot_start >= current for slot_start in candidate_slots):
            return candidate
        candidate += timedelta(days=1)
    return None


def list_regions(session: Session) -> list[RegionGroup]:
    """활성 룸이 있는 시/군/구→동/읍/면 트리(콤보 옵션)를 반환한다(읽기 전용, AC1).

    ``GET /rooms/regions``의 데이터다 — 지역 콤보(1차 시군구·2차 동)를 채운다. 보유 활성
    룸의 ``admin_dong_code``(b_code)를 ``level_codes``로 시군구·동 레벨로 환산해 그룹핑하고,
    ``region_name``으로 라벨링한다(미매핑=코드 원문 폴백 — graceful, 회고 ⑤). **룸이 있는 시군구·
    동만** 제시한다(빈 지역 미노출, AC1). 표시 안정을 위해 시군구·동 이름 오름차순 정렬한다.

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).

    Returns:
        ``RegionGroup``(시군구) 리스트. 각 그룹은 시도 포함 라벨·``room_count``·룸이 있는
        ``dongs``를 갖는다. 활성 룸이 0개면 ``[]``(정상 200 — 에러 아님).

    지역명 출처 = 백엔드 번들 지역 정적 참조(``regions.py``) — 모델·2.2·마이그레이션 무변경
    (KTH 결정 #1). 비활성 룸은 ``where(is_active)``로 제외한다.
    """
    # 활성 룸만 — Room.is_active == True 는 ruff E712(불리언 비교)라 col(...).is_().
    rooms = session.exec(select(Room).where(col(Room.is_active).is_(True))).all()

    # 시군구 코드 → (동 코드 → 룸 수). dict 삽입 순서가 아니라 이름으로 최종 정렬한다.
    dong_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for room in rooms:
        _sido, sigungu_code, dong_code = level_codes(room.admin_dong_code)
        dong_counts[sigungu_code][dong_code] += 1

    groups: list[RegionGroup] = []
    for sigungu_code, dongs in dong_counts.items():
        dong_items = [
            Region(
                code=dong_code,
                # 동 짧은 라벨(말단 토큰). 미매핑이면 코드 원문 폴백(조용한 크래시 금지 — 회고 ⑤).
                name=_dong_label(dong_code),
                room_count=count,
            )
            for dong_code, count in dongs.items()
        ]
        dong_items.sort(key=lambda r: r.name)  # 동 이름 오름차순(표시 안정)
        # 시군구 라벨 = 시도 포함 전체명(미매핑=코드 원문 폴백).
        sigungu_full = region_name(sigungu_code)
        groups.append(
            RegionGroup(
                code=sigungu_code,
                name=sigungu_full if sigungu_full else sigungu_code,
                dongs=dong_items,
                room_count=sum(dongs.values()),
            )
        )
    groups.sort(key=lambda g: g.name)  # 시군구 이름 오름차순(표시 안정)
    return groups


def _dong_label(dong_code: str) -> str:
    """동/읍/면 코드의 짧은 라벨(말단 토큰). 미매핑이면 코드 원문 폴백(graceful)."""
    full = region_name(dong_code)
    return leaf_name(full) if full else dong_code


def search_rooms(
    session: Session,
    region_code: str | None = None,
    *,
    center_lat: float | None = None,
    center_lng: float | None = None,
    radius_km: float | None = None,
    now: datetime | None = None,
) -> list[RoomListItem]:
    """활성 룸 목록을 (지역/반경 필터해) 신선 잔여 슬롯과 함께 반환한다(읽기 전용, AC1·AC4).

    ``GET /rooms/search``의 데이터다 — 목록 행(이름·가격·룸형태·부대시설 + 예약 가능 배지용
    신선 ``remaining_slots``). UJ-1의 가격·시설 비교를 한 응답으로 충족한다. 두 검색방식을
    지원한다: ``region_code``(지역, 3.4) · ``center_lat``/``center_lng``/``radius_km``(반경, 3.5).

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).
        region_code: 시군구 또는 동/읍/면 레벨 지역 코드. 주어지면 룸의 시도/시군구/동 레벨
            코드 중 하나와 **동등 매칭**으로 필터한다(시군구 코드=그 구 전체·동 코드=그 동만).
            ``None``이면 지역 필터 없음. **미매핑/미존재 코드는 빈 리스트(200) — 에러 아님**
            (신규 ErrorCode 0, 회고 ⑤ graceful).
        center_lat: 반경 중심 위도(도). ``center_lng``와 **둘 다** 주어질 때만 반경 필터가
            적용된다(부분 좌표=반경 미적용 graceful — 에러 아님).
        center_lng: 반경 중심 경도(도).
        radius_km: 반경(km). 반경 필터 적용 시 미지정이면 기본 ``3.0``(``_DEFAULT_RADIUS_KM``).
        now: 기준 현재시각(tz-aware UTC). 테스트 결정성을 위해 주입받으며, 미지정 시
            ``now_utc()``(core/time 단일 출처)를 쓴다. ``datetime.now()`` 직접 호출 금지.

    Returns:
        ``RoomListItem`` 리스트. 각 행의 ``remaining_slots``는 ``aggregate_availability``(3.1)와
        동일 패턴 — 영업시간/휴무 벌크 조회 후 ``room_id``별 그룹핑(N+1 회피) + ``derive_slots``
        재사용 + ``>= now`` 카운트다. ``reserved_starts=frozenset()``은 **Story 4.9 예약 차감
        지점**(3.1/3.3 동일). 매칭 룸 0개면 ``[]``.

    **반경 필터(Haversine — Story 3.5):** ``center_lat``·``center_lng``가 둘 다 있을 때만 적용한다.
    각 룸까지의 ``haversine_km`` 거리가 유효 반경 이하인 룸만 통과시키고, 결과를 **거리 오름차순
    (가까운 순)** 으로 정렬한다(AC1③ — 거리는 필터 계산값을 재사용해 룸별 1회). ``region_code``와
    좌표가 함께 오면 **둘 다 적용(교집합)** 한다. 거리 숫자는 응답에 싣지 않는다(``RoomListItem``
    무변경 — 범위 결정 #4).

    **필터 위치(MVP):** 활성 룸을 조회한 뒤 지역 ``level_codes`` 동등 매칭·반경 거리 계산을
    **Python에서** 수행한다(제공자당 1룸 규모에서 충분·테스트 명확). SQL ``LIKE`` prefix·PostGIS
    공간쿼리 최적화는 bbox 계열의 deferred다(Dev Notes — 데이터 증가 시점).
    """
    current = now if now is not None else now_utc()
    target_date = today_in_tz(ROOM_TZ, now=current)

    # 활성 룸만 — col(...).is_()로 E712 회피(aggregate_availability 선례).
    active_rooms = list(
        session.exec(select(Room).where(col(Room.is_active).is_(True))).all()
    )
    # ① 지역 필터(Python) — region_code가 룸의 시도/시군구/동 레벨 코드 중 하나와 일치하면 통과.
    # 미매핑/미존재 코드는 어떤 룸과도 일치하지 않아 빈 리스트가 된다(에러 아님 — graceful).
    if region_code is not None:
        rooms = [
            room
            for room in active_rooms
            if region_code in level_codes(room.admin_dong_code)
        ]
    else:
        rooms = active_rooms

    # ② 반경 필터(Haversine) — 중심 좌표가 **둘 다** 있을 때만 적용(부분 좌표=미적용 graceful).
    # region_code와 동시 제공 시 ①의 결과에 추가로 적용 → 교집합. 거리는 정렬에 재사용한다.
    if center_lat is not None and center_lng is not None:
        effective_radius = radius_km if radius_km is not None else _DEFAULT_RADIUS_KM
        within: list[tuple[float, Room]] = []
        for room in rooms:
            distance = haversine_km(center_lat, center_lng, room.lat, room.lng)
            if distance <= effective_radius:
                within.append((distance, room))
        # ③ 거리 오름차순 정렬(가까운 순 — AC1③). list.sort는 안정 정렬(동일 거리=입력 순서 유지).
        within.sort(key=lambda pair: pair[0])
        rooms = [room for _distance, room in within]

    if not rooms:
        return []

    # 영업시간/휴무 벌크 조회 후 room_id별 그룹핑(N+1 회피 — aggregate_availability와 동일 패턴).
    room_ids = [room.id for room in rooms]
    hours_by_room: dict[uuid.UUID, list[BusinessHours]] = defaultdict(list)
    for hours_row in session.exec(
        select(BusinessHours).where(col(BusinessHours.room_id).in_(room_ids))
    ).all():
        hours_by_room[hours_row.room_id].append(hours_row)
    holidays_by_room: dict[uuid.UUID, set[date]] = defaultdict(set)
    for holiday_row in session.exec(
        select(HolidayException).where(col(HolidayException.room_id).in_(room_ids))
    ).all():
        holidays_by_room[holiday_row.room_id].add(holiday_row.holiday_date)

    # Story 4.9: 필터된 룸들의 활성 점유를 벌크 1회 조회 후 per-room 차감(aggregate_availability
    # 동일 패턴 — N+1 회피 + 도메인 경계 reader 경유). on_or_after=current로 과거 점유 제외.
    reserved_by_room = confirmed_slot_starts_by_room(
        session, room_ids, on_or_after=current
    )

    items: list[RoomListItem] = []
    for room in rooms:
        # 각 룸에 그 룸의 행만 넘긴다(섞이면 슬롯 합쳐짐 — aggregate_availability AC4 격리와 동일).
        slots = derive_slots(
            hours_by_room.get(room.id, []),
            holidays_by_room.get(room.id, set()),
            target_date,
            # Story 4.9: 그 룸의 활성 점유 차감(3.1/aggregate_availability 동일 — AC1 목록 카운트).
            reserved_starts=reserved_by_room.get(room.id, frozenset()),
        )
        remaining = sum(1 for slot_start in slots if slot_start >= current)
        items.append(
            RoomListItem(
                room_id=room.id,
                name=room.name,
                price_per_hour=room.price_per_hour,
                room_type=room.room_type,
                amenities=list(room.amenities),
                remaining_slots=remaining,
            )
        )
    return items


def search_rooms_page(
    session: Session,
    region_code: str | None = None,
    *,
    center_lat: float | None = None,
    center_lng: float | None = None,
    radius_km: float | None = None,
    limit: int,
    cursor: str | None = None,
    now: datetime | None = None,
) -> tuple[list[RoomListItem], str | None]:
    """``search_rooms``의 **offset 페이징판**(F — 탐색 목록 무한스크롤).

    검색은 거리/지역 **계산 정렬**이라 시간 keyset이 부적합하다 → "몇 개까지 봤는지"(offset)를
    담는 불투명 커서를 쓴다([[pagination]] offset 절). 전체 결과를 ``search_rooms``로 한 번 계산한
    뒤(필터·거리 정렬·신선 슬롯 — 단일 출처 재사용, 챗봇 툴과 동일 함수) ``[offset:offset+limit]``
    로 잘라 페이지를 만들고, 끝이 아니면 다음 offset 토큰을 낸다. MVP 규모(제공자당 1룸)에서 전체
    계산 후 슬라이스는 충분하다(SQL LIMIT 푸시다운은 region/거리 Python 필터를 SQL로 내릴 때의
    deferred — ``search_rooms`` Dev Notes). 손상/음수 offset 커서는 422(``decode_offset``).

    Args:
        session: DB 세션(**읽기 전용**).
        region_code: 지역 코드(``search_rooms`` 동일 의미).
        center_lat / center_lng / radius_km: 반경 필터(``search_rooms`` 동일 의미).
        limit: 한 페이지 크기(라우터가 검증).
        cursor: 이전 페이지의 ``next_cursor``(없으면 offset 0).
        now: 기준 현재시각(테스트 결정성). 미지정 시 ``now_utc()``.

    Returns:
        ``(이번 페이지 RoomListItem 리스트, next_cursor)`` — 마지막 페이지면 next_cursor=``None``.
    """
    offset = decode_offset(cursor)  # 손상/음수 커서는 여기서 422
    full = search_rooms(
        session,
        region_code,
        center_lat=center_lat,
        center_lng=center_lng,
        radius_km=radius_km,
        now=now,
    )
    total = len(full)
    page = full[offset : offset + limit]
    return page, offset_next_cursor(offset, limit, total)


def available_room_ids_at(
    session: Session,
    room_ids: list[uuid.UUID],
    target_date: date,
    start_hour: int | None = None,
    *,
    now: datetime | None = None,
) -> set[uuid.UUID]:
    """``target_date``에 (``start_hour``가 있으면 그 KST 시각에) 예약 가능한 슬롯이 있는 룸
    ``id`` 집합을 **벌크로** 반환한다(읽기 전용, Story 7.6 — 챗봇 시간필터 N+1 회피).

    ``get_room_slots``를 룸마다 호출하면 룸별 영업시간/휴무/예약 조회 + 표시·**버려지는 30일
    ``next_available_date`` 루프**까지 반복돼 룸 수 비례 N+1이 된다(리뷰 patch). 이 reader는
    ``search_rooms``와 동형으로 영업시간·휴무·활성 점유를 ``room_ids``에 대해 **각 1회 벌크
    조회**한 뒤 룸별 ``derive_slots``로 그날 슬롯을 도출해 가용 슬롯 존재 여부만 판정한다(슬롯
    리스트·다음 빈 날짜는 산출하지 않음 — 챗봇 후보 추림엔 "있다/없다"만 필요).

    "가용"의 정의는 ``get_room_slots``/``_slot_status``의 ``available``과 동일하다 —
    ``slot_start >= now``(과거 아님) **그리고** 미예약. ``start_hour``가 오면 슬롯 시작시각을
    ROOM_TZ(KST) 벽시계로 환산해 그 시(hour)와 일치하는 가용 슬롯이 있어야 한다(``to_tz`` 단일
    출처 — 시각 산술 함정 회피). 도메인 경계: 예약 차감은 ``confirmed_slot_starts_by_room``
    (4.9 seam) 경유 — raw SQL 미접근.

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).
        room_ids: 가용 판정 대상 룸들. **빈 입력이면 ``set()``**(쿼리 미발행).
        target_date: 슬롯을 도출할 날짜(ROOM_TZ 기준).
        start_hour: 0~23(KST). 주어지면 그 시각에 시작하는 가용 슬롯이 있는 룸만 통과.
        now: 기준 현재시각(tz-aware UTC). 미지정 시 ``now_utc()``(테스트 결정성용 주입).

    Returns:
        조건을 만족하는 룸 ``id``의 ``set``. 만족 룸이 없으면 빈 ``set``.
    """
    if not room_ids:
        return set()  # 빈 입력 → 쿼리 미발행

    current = now if now is not None else now_utc()

    # 영업시간/휴무 벌크 조회 후 room_id별 그룹핑(N+1 회피 — search_rooms 동일 패턴).
    hours_by_room: dict[uuid.UUID, list[BusinessHours]] = defaultdict(list)
    for hours_row in session.exec(
        select(BusinessHours).where(col(BusinessHours.room_id).in_(room_ids))
    ).all():
        hours_by_room[hours_row.room_id].append(hours_row)
    holidays_by_room: dict[uuid.UUID, set[date]] = defaultdict(set)
    for holiday_row in session.exec(
        select(HolidayException).where(col(HolidayException.room_id).in_(room_ids))
    ).all():
        holidays_by_room[holiday_row.room_id].add(holiday_row.holiday_date)
    # 활성 점유 벌크 1회(on_or_after 미지정 — get_room_slots와 동일하게 임의 날짜의 점유도
    # reserved로 정확 판정. 과거 슬롯은 아래 `>= current`로 별도 제외). instant 매칭이라 타 날짜
    # 슬롯과 우연 일치 불가.
    reserved_by_room = confirmed_slot_starts_by_room(session, room_ids)

    available: set[uuid.UUID] = set()
    for room_id in room_ids:
        # 표시용과 동일 비대칭: derive_slots엔 frozenset()을 줘 전 슬롯을 유지하고(예약 슬롯이
        # 사라지지 않게), reserved/past는 아래 판정에서 제외한다(get_room_slots 핵심 비대칭).
        starts = derive_slots(
            hours_by_room.get(room_id, []),
            holidays_by_room.get(room_id, set()),
            target_date,
            reserved_starts=frozenset(),
        )
        reserved: Collection[datetime] = reserved_by_room.get(room_id, frozenset())
        for slot_start in starts:
            if slot_start < current or slot_start in reserved:
                continue  # past 또는 reserved → available 아님
            if start_hour is not None and to_tz(slot_start, ROOM_TZ).hour != start_hour:
                continue  # 요청 시각과 불일치
            available.add(room_id)
            break  # 한 곳이라도 가용이면 충분(있다/없다만 필요)
    return available


def list_provider_rooms(
    session: Session, provider_id: uuid.UUID
) -> list[Room]:
    """제공자가 소유한 룸 전체를 반환한다(읽기 전용, Story 6.1 — 제공자 예약현황 합성용).

    ``Room.provider_id == provider_id`` 소유 룸을 **상태 무관**(비활성 포함)으로 낸다 —
    운영중단(``is_active=False``)된 룸의 과거 예약도 제공자가 봐야 하므로 ``is_active`` 필터를
    두지 않는다(``list_rooms``의 공개 탐색 ``where(is_active)``와 의도적 대비 — 여긴 소유자 뷰).
    MVP는 제공자당 1개(``uq_rooms_provider_id``)지만 **다중 룸 대비** 리스트로 반환한다(향후
    제약 완화 시 무영향).

    ``create_room``의 제공자당 1개 선검사(``service.py`` ``select(Room).where(provider_id==...)``
    ``.first()``)가 같은 소유권 축을 쓰나, 그건 **존재 여부**(first) 판정이고 이 함수는 **소유 룸
    전체**(예약 합성용)를 낸다 — 의도가 달라 별도 함수로 둔다. 룸 소유권 조회는 **rooms.service가
    소유**하고(reservations 도메인이 rooms를 import하면 4.9 ``rooms.service → reservations.service``
    역방향과 순환), reservations 라우터(조합 계층)가 이 결과로 예약을 조회·합성한다(Story 6.1).

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).
        provider_id: 소유 룸을 조회할 제공자(``users.id`` = 인증 principal).

    Returns:
        소유 룸 리스트(비활성 포함). 소유 룸이 없으면 ``[]``(정상 빈 목록).
    """
    statement = select(Room).where(col(Room.provider_id) == provider_id)
    return list(session.exec(statement).all())


def create_room(
    session: Session, provider_id: uuid.UUID, data: RoomCreateRequest
) -> Room:
    """검증된 등록 요청으로 ``rooms`` + ``business_hours``를 단일 트랜잭션에 생성한다(AC1·AC4).

    ① **제공자당 1개 선검사**: 이미 룸을 보유한 제공자면 409 ``ROOM_LIMIT_REACHED``(친절한
       메시지). ② ``Room`` + ``BusinessHours[]``를 한 트랜잭션에 ``add`` 후 ``commit``한다 —
       룸만 생기고 영업시간이 누락되는 부분 저장을 막는다(원자). ③ ``session.refresh`` 후 반환.

    **P2 — IntegrityError 선별 변환(회고 회수):** 선검사와 DB UNIQUE는 이중 방어다. 경합으로
    ``uq_rooms_provider_id``가 위반되면 ``violated_constraint``로 제약명을 식별해
    ``ROOM_LIMIT_REACHED``로 변환하고, **무관한 위반은 그대로 re-raise**한다(과대캐치 금지).
    """
    existing = session.exec(
        select(Room).where(Room.provider_id == provider_id)
    ).first()
    if existing is not None:
        raise DomainError(
            ErrorCode.ROOM_LIMIT_REACHED,
            "제공자당 공간은 1개만 등록할 수 있습니다.",
        )  # 409

    room = Room(
        provider_id=provider_id,
        name=data.name,
        price_per_hour=data.price_per_hour,
        capacity=data.capacity,
        room_type=data.room_type,
        amenities=list(data.amenities),
        lat=data.lat,
        lng=data.lng,
        admin_dong_code=data.admin_dong_code,
        address=data.address,
    )
    session.add(room)
    # room.id는 default_factory=uuid4라 commit 전 이미 존재하지만, ORM에 FK가 선언돼 있어도
    # psycopg3 + 실 Postgres에서는 flush INSERT 순서가 보장되지 않아 business_hours(자식)가
    # rooms(부모)보다 먼저 INSERT되면 fk_business_hours_room_id_rooms 위반(500)이 난다.
    # → room을 먼저 flush해 같은 트랜잭션 안에서 rooms 행을 확정한 뒤 자식을 add한다(commit 아님 —
    #   이후 BH 실패 시 전체 롤백되어 원자성 유지). (E2E 발견 — 유닛테스트가 실 FK 미경유로 잠복)
    session.flush()
    for bh in data.business_hours:
        session.add(
            BusinessHours(
                room_id=room.id,
                weekday=bh.weekday,
                open_time=bh.open_time,
                close_time=bh.close_time,
            )
        )
    try:
        session.commit()
    except IntegrityError as exc:  # 경합: 선검사 통과 후 동시 삽입 → UNIQUE 위반
        session.rollback()
        if violated_constraint(exc) == "uq_rooms_provider_id":
            raise DomainError(
                ErrorCode.ROOM_LIMIT_REACHED,
                "제공자당 공간은 1개만 등록할 수 있습니다.",
            ) from exc
        raise  # 무관한 제약 위반은 오변환 금지 — 그대로 전파(P2)
    session.refresh(room)
    return room


# Room ORM 스칼라 컬럼이 아닌 요청 필드(별도 처리). ``business_hours``는 전체 교체로 별도 처리하므로
# setattr 루프에서 제외한다. (``address``는 provider 웹 표면 구축으로 실제 컬럼이 됐으므로 일반
# setattr 경로로 저장된다 — 더는 제외하지 않는다.)
_NON_ROOM_COLUMN_FIELDS = frozenset({"business_hours"})


def update_room(
    session: Session,
    provider_id: uuid.UUID,
    room_id: uuid.UUID,
    data: RoomUpdateRequest,
) -> Room:
    """본인 소유 공간을 부분 수정한다(룸 필드 + 영업시간 전체 교체, 단일 트랜잭션, AC1·AC2·AC4).

    ① **소유권/존재 검사(AC4 — 백엔드 최종 강제)**: ``session.get``으로 룸을 찾되, 미존재
       **또는** 비-소유(``room.provider_id != provider_id``)면 **동일 404 ``ROOM_NOT_FOUND``**로
       합친다(타 provider의 room_id 존재 여부 미노출 + 제공자당 1개라 "내 공간이 아니면 곧 없는
       것" — KTH 확정). ② **부분 적용**: ``model_dump(exclude_unset=True)``로 요청에 실제로 온
       필드만 ``setattr``(PATCH 시맨틱 — 미제공 필드는 기존값 유지). ③ **영업시간 전체 교체(제공
       시)**: 기존 ``BusinessHours`` 행 삭제 후 신규 삽입 — 같은 트랜잭션(원자). ④ ``commit`` 후
       ``refresh``하고 반환한다.

    **AC2 독립성(구조적 불변식 — FR-22):** 이 함수는 ``rooms``·``business_hours``만 변경하고
    **reservations를 절대 조회/삭제/재계산하지 않는다**(넣을 테이블도 없다 — E4). 슬롯은
    ``derive_slots``가 매번 현재 ``business_hours``로 도출하고, 확정 예약(E4)은 행에
    ``slot_start``(UTC)를 **보유**하므로 영업시간 축소가 과거 예약을 소급 무효화하지 않는다
    (architecture.md L149-150). E4가 reservations를 추가해도 이 불변식 덕에 독립이 자동 유지된다.

    **P2 — IntegrityError 선별 변환(회고 일관):** ``provider_id``는 수정 불가(불변)라
    ``uq_rooms_provider_id`` 위반 경로가 없고, 영업시간 중복은 Pydantic
    ``_reject_duplicate_weekday``가 1차 차단한다. 즉 **변환 대상 위반이 없다** → 포괄 캐치로
    오변환하지 않고(과대캐치 금지) rollback 후 그대로 re-raise 한다.
    """
    # ① 소유권/존재 — 미존재와 비-소유를 동일 404로 합친다(AC4 백엔드 최종 강제, KTH 확정).
    room = session.get(Room, room_id)
    if room is None or room.provider_id != provider_id:
        raise DomainError(
            ErrorCode.ROOM_NOT_FOUND,
            "해당 공간을 찾을 수 없습니다.",
        )  # 404 — 미존재/비-소유 동일 처리(타인 room_id 존재 여부 미노출)

    # ② 부분 적용 — 요청에 실제로 온 필드만(PATCH 시맨틱). business_hours만 별도(전체 교체)로 제외.
    provided = data.model_dump(exclude_unset=True)
    replace_hours = "business_hours" in provided
    for field, value in provided.items():
        if field in _NON_ROOM_COLUMN_FIELDS:
            continue  # business_hours=별도 교체, address=Room 컬럼 아님(저장 안 함)
        setattr(room, field, value)

    # ③ 영업시간 전체 교체(키가 제공된 경우만 — 미제공=불변).
    if replace_hours:
        assert data.business_hours is not None  # replace_hours ⇒ 키 제공 ⇒ min_length=1 보장
        existing_hours = session.exec(
            select(BusinessHours).where(BusinessHours.room_id == room_id)
        ).all()
        for old_row in existing_hours:
            session.delete(old_row)
        # ⚠️ flush로 DELETE를 INSERT보다 먼저 emit한다. SQLAlchemy 기본 flush 순서는 같은
        #    테이블의 INSERT를 DELETE보다 앞세우므로, 같은 weekday를 교체하면 신규 INSERT가
        #    아직 살아있는 기존 행과 uq_business_hours_room_id_weekday로 충돌한다 → 같은
        #    트랜잭션 안에서 DELETE를 선행 flush해 충돌을 차단한다(commit 아님 — 원자성 유지).
        session.flush()
        for bh in data.business_hours:
            session.add(
                BusinessHours(
                    room_id=room.id,
                    weekday=bh.weekday,
                    open_time=bh.open_time,
                    close_time=bh.close_time,
                )
            )

    # ④ 원자 커밋 — 룸 필드 변경 + 영업시간 삭제/삽입을 하나의 commit으로 묶는다.
    try:
        session.commit()
    except IntegrityError:
        # provider_id 불변 + 영업시간 중복 Pydantic 선차단 → 변환 대상 없음(P2). 무관 위반을
        # 단일 도메인 에러로 오변환하지 않고(과대캐치 금지) rollback 후 그대로 전파한다.
        session.rollback()
        raise
    session.refresh(room)
    return room


def _parse_kakao_documents(payload: dict[str, Any]) -> list[GeocodeResult]:
    """카카오 주소검색 응답(JSON)을 ``GeocodeResult`` 리스트로 매핑한다(AC2).

    **카카오 좌표 규약: ``x``=경도(lng)·``y``=위도(lat)**(혼동 주의). 지역 코드는
    ``address.b_code``(지역 10자리)를 우선하고 ``road_address.b_code``로 폴백한다(Dev Notes
    결정: ``admin_dong_code`` = 지역 ``b_code``). 좌표가 없거나 손상된 항목은 후보에서 제외하고,
    코드 부재 시 빈 문자열로 표시한다. 결과 0건은 정상(빈 리스트 + 200 — 에러 아님).
    """
    results: list[GeocodeResult] = []
    # documents 키가 존재+null이면 .get(..., []) 기본값이 적용되지 않아 None이 반환된다
    # (`for doc in None` → TypeError). 또 dict/문자열 등 비-리스트면 조용한 오작동이 되므로
    # 명시적으로 리스트가 아니면 빈 후보로 취급한다(code-review patch — 손상 응답 방어).
    documents = payload.get("documents")
    if not isinstance(documents, list):
        return results
    for doc in documents:
        if not isinstance(doc, dict):
            continue  # 손상 항목(비-객체)은 후보 제외
        try:
            lat = float(doc["y"])  # 카카오 y = 위도
            lng = float(doc["x"])  # 카카오 x = 경도
        except (KeyError, TypeError, ValueError):
            continue  # 좌표 없는/손상 항목은 후보 제외
        address_obj = doc.get("address") or {}
        road_obj = doc.get("road_address") or {}
        b_code = address_obj.get("b_code") or road_obj.get("b_code") or ""  # 지역 코드
        address_name = (
            doc.get("address_name") or address_obj.get("address_name") or ""
        )
        results.append(
            GeocodeResult(
                address=address_name, lat=lat, lng=lng, admin_dong_code=b_code
            )
        )
    return results


def _geocode_client() -> httpx.Client:
    """지오코딩용 httpx 동기 클라이언트(타임아웃 10s).

    테스트는 이 함수를 monkeypatch해 ``httpx.MockTransport``를 주입한다 — 라이브 카카오
    호출 없이 결정적으로 검증한다(회고 A2). 별도 함수로 분리해 주입 지점을 명확히 한다.
    """
    return httpx.Client(timeout=_GEOCODE_TIMEOUT_SECONDS)


def geocode_address(query: str) -> list[GeocodeResult]:
    """카카오 주소검색으로 주소 후보(좌표 + 지역 코드)를 조회한다(AC2 — 백엔드 프록시).

    ``KAKAO_REST_API_KEY``는 **백엔드 전용**(NFR-6)이라 프론트가 직접 호출하지 않고 이
    프록시를 경유한다. 키는 **함수 내부에서 지연 로드**한다(import 시점 부작용 금지 — 1.8
    security 패턴). 카카오 비-200(키 무효·한도 초과 등)·타임아웃·연결 실패는 모두 502
    ``GEOCODING_UNAVAILABLE``로 변환한다. 결과 0건은 에러가 아니라 빈 리스트(200)다.
    """
    key = get_settings().KAKAO_REST_API_KEY  # 함수 내부 지연 로드(백엔드 전용 키)
    try:
        with _geocode_client() as client:
            resp = client.get(
                _KAKAO_ADDRESS_SEARCH_URL,
                params={"query": query},
                headers={"Authorization": f"KakaoAK {key}"},
            )
    except httpx.HTTPError as exc:  # 타임아웃·연결 실패 등 전송 계층 오류
        raise DomainError(
            ErrorCode.GEOCODING_UNAVAILABLE,
            "주소 검색 서비스에 연결할 수 없습니다 (네트워크 또는 타임아웃).",
        ) from exc
    if resp.status_code != 200:  # 키 무효·한도 초과 등 업스트림 실패
        raise DomainError(
            ErrorCode.GEOCODING_UNAVAILABLE,
            f"주소 검색에 실패했습니다 (카카오 응답 {resp.status_code}).",
        )
    try:
        payload = resp.json()  # 200이라도 본문이 비-JSON(점검 HTML 등)이면 JSONDecodeError
    except ValueError as exc:  # json.JSONDecodeError는 ValueError 하위 — httpx.HTTPError 밖
        raise DomainError(
            ErrorCode.GEOCODING_UNAVAILABLE,
            "주소 검색 응답을 해석할 수 없습니다 (카카오 응답 형식 오류).",
        ) from exc
    if not isinstance(payload, dict):  # 최상위가 객체가 아니면 손상 응답 → 502
        raise DomainError(
            ErrorCode.GEOCODING_UNAVAILABLE,
            "주소 검색 응답 형식이 올바르지 않습니다.",
        )
    return _parse_kakao_documents(payload)
