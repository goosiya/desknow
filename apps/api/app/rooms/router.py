"""rooms 라우터: 공간 등록 + 주소 검색 + 가용성 집계 + 룸 목록(Story 2.2·3.1·3.2).

``main.py``가 ``api_router``(``/api/v1``) 아래에 포함하므로 최종 경로는
``/api/v1/rooms`` (POST 등록 / GET 목록) · ``/api/v1/rooms/geocode`` (GET 주소검색) ·
``/api/v1/rooms/availability`` (GET 가용성 집계 — 공개)가 된다.

**규약:**

- **RBAC 최종 강제(1.8, §Boundaries L351):** 쓰기/주소검색 엔드포인트(create/update/geocode)는
  ``Depends(require_role("provider"))``. booker/admin은 403 ``FORBIDDEN_ROLE``, 미인증은 401
  ``UNAUTHENTICATED``. **단 가용성 집계(``/availability``)와 룸 목록(``GET ""``)은 공개**다 —
  탐색 첫 화면 핀(FR-4/5)은 비로그인 접근(PRD §FR-2: 인증 *필요* 기능만 로그인 유도). 따라서
  이 둘은 인증 의존성·401/403 계약이 없다.
- **상태코드:** 등록=201(생성), geocode·availability=200(조회). 검증 실패는 Pydantic→1.5
  핸들러가 422. 제공자당 1개 초과=409 ``ROOM_LIMIT_REACHED``, 카카오 업스트림 실패=502
  ``GEOCODING_UNAVAILABLE``. 가용성 집계는 입력(쿼리 파라미터)·외부 호출이 없어 신규 에러코드가
  없다(활성 룸 0개=빈 리스트 200).
- **``responses={...: ErrorResponse}``** 로 OpenAPI에 에러 계약을 노출한다(1.9 SDK가
  ``detail.code`` 타입을 생성하도록).
- **operationId(1.9):** 라우트 함수명은 도메인 내 유일(``create_room``·``geocode_address``·
  ``aggregate_availability``·``list_rooms``·``list_regions``·``search_rooms``) → ``{tag}_{name}`` =
  ``rooms_create_room``·``rooms_geocode_address``·``rooms_aggregate_availability``·
  ``rooms_list_rooms``·``rooms_list_regions``·``rooms_search_rooms``.
- **라우팅 순서 가드(2.3 — 동적 라우트 추가됨, 3.3 GET /{room_id}·3.4 /regions·/search 포함):**
  정적 경로 ``/geocode``·``/availability``·``GET ""``(컬렉션)·``/regions``·``/search``는 동적
  ``/{room_id}``(UUID 변환)보다 **반드시 먼저 선언**돼야 한다(미선언 시 "geocode"/"regions"/
  "search" 등이 room_id로 잡혀 422). Story 2.3가 ``PATCH /{room_id}``(공간 수정)를, 3.3이
  ``GET /{room_id}``(바텀시트 요약)를 추가하며 이 순서를 발효시켰고, 3.4가 정적 ``/regions``·
  ``/search``를 추가했다 — 정적 라우트들을 동적 ``/{room_id}`` 그룹 **앞에** 배치한다. 이 순서를
  깨지 말 것(회귀 테스트로 고정). 4.3 ``GET /{room_id}/slots``(날짜별 슬롯)는 **2-세그먼트**라
  1-세그먼트 정적/동적 라우트와 매칭 충돌이 없어(경로 깊이 다름) 동적 ``/{room_id}`` 그룹
  근처에 두며 정적 라우트 뒤여도 무방하다.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.db import get_session
from app.core.errors import ErrorResponse
from app.core.pagination import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, CursorPage
from app.core.security import AuthPrincipal, require_role
from app.rooms import service
from app.rooms.models import Room
from app.rooms.schemas import (
    GeocodeResult,
    ProviderRoomDetail,
    RegionGroup,
    RoomAvailability,
    RoomCreateRequest,
    RoomListItem,
    RoomMapItem,
    RoomPublic,
    RoomSlotsResponse,
    RoomSummary,
    RoomUpdateRequest,
)

router = APIRouter(prefix="/rooms", tags=["rooms"])

# RBAC 의존성을 모듈레벨 싱글톤으로 고정한다(provider 전용 — AC5). ``require_role(...)``는
# 의존성 팩토리라 호출 결과(checker)를 한 번만 만들어 재사용한다. 인자 기본값에서 직접
# ``require_role("provider")``를 호출하면 ruff B008(기본값 함수 호출)에 걸리므로,
# B008 권장대로 싱글톤을 ``Depends``에 전달한다(extend-immutable-calls엔 fastapi.Depends만 등록).
_require_provider = require_role("provider")

# 필수 ``date`` 쿼리 파라미터(Story 4.3 슬롯 조회). ``room_id`` 경로 파라미터 뒤에 오는 Query는
# 인자 기본값에서 직접 호출 시 ruff B008에 걸리므로(``_require_provider``와 동일 회피), 모듈레벨
# 싱글톤으로 한 번만 만들어 재사용한다. ``Query(...)``=필수(누락 시 422 — Pydantic→1.5 핸들러).
_date_query = Query(...)


@router.get(
    "/geocode",
    response_model=list[GeocodeResult],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def geocode_address(
    query: str = Query(min_length=1),
    _principal: AuthPrincipal = Depends(_require_provider),
) -> list[GeocodeResult]:
    """주소를 검색해 좌표·지역 코드 후보를 반환한다 → 200(provider 전용, AC2).

    카카오 REST 키는 백엔드 전용(NFR-6)이라 이 프록시를 경유한다. 업스트림 실패는 502.
    결과 0건은 정상(빈 리스트). 정적 경로라 향후 ``/{room_id}``보다 먼저 선언한다.
    """
    return service.geocode_address(query)


@router.post(
    "",
    response_model=RoomPublic,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def create_room(
    data: RoomCreateRequest,
    principal: AuthPrincipal = Depends(_require_provider),
    session: Session = Depends(get_session),
) -> Room:
    """공간을 등록한다 → 201 + RoomPublic(provider 전용, AC1·AC5).

    인증된 provider의 ``user_id``를 ``provider_id``로 ``create_room`` 호출. 제공자당 1개
    초과는 409, 자정 넘김 영업시간 등 검증 실패는 422(Pydantic→1.5 핸들러).
    """
    return service.create_room(session, principal.user_id, data)


@router.get("/availability", response_model=list[RoomAvailability])
def aggregate_availability(
    session: Session = Depends(get_session),
) -> list[RoomAvailability]:
    """활성 룸별 오늘 잔여 빈 슬롯 수를 반환한다 → 200(공개, AC1·AC3).

    핀 색 결정용 집계(FR-5·NFR-2) — 서버가 1회 계산해 ``list[RoomAvailability]``(각
    ``{room_id, remaining_slots}``)를 돌려준다. **인증 없음**(탐색 첫 화면 핀은 비로그인 —
    PRD §FR-2). ``now`` 미주입 → ``now_utc()`` 기준. 정적 경로라 ``/{room_id}``보다 먼저 선언한다.
    """
    return service.aggregate_availability(session)


@router.get("", response_model=list[RoomMapItem])
def list_rooms(session: Session = Depends(get_session)) -> list[RoomMapItem]:
    """활성 룸의 핀 메타(``{room_id, name, lat, lng}``)를 반환한다 → 200(공개, AC1·AC2).

    첫 진입 지도 핀 좌표 공급(FR-4). **인증 없음**(탐색 첫 화면 핀은 비로그인 — PRD §FR-2,
    ``/availability``와 동일 근거). 가용성(핀 색)은 ``/availability``, 룸 상세는 바텀시트
    (Story 3.3)가 책임진다 — 이 응답은 핀 좌표·이름만 싣는다(과조회 방지). 컬렉션 루트
    ``GET ""``는 ``POST ""``(등록·메서드 다름)·``GET /{room_id}``(동적·경로 세그먼트 다름)와
    충돌하지 않으나, 일관성을 위해 정적 그룹 근처·``PATCH /{room_id}`` 앞에 선언한다.
    operationId = ``rooms_list_rooms``(1.9 규약, 도메인 내 유일).
    """
    return service.list_active_rooms(session)


@router.get(
    "/mine",
    response_model=ProviderRoomDetail,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_my_room(
    principal: AuthPrincipal = Depends(_require_provider),
    session: Session = Depends(get_session),
) -> ProviderRoomDetail:
    """provider 본인 룸 상세를 반환한다 → 200(provider 전용 — 등록/수정 폼 prefill).

    인증된 provider의 ``user_id``로 본인 룸(0..1)을 조회한다. 없으면 404 ``ROOM_NOT_FOUND``
    (등록 안 함 → 폼 생성 모드). 정적 경로라 동적 ``/{room_id}``보다 **먼저** 선언한다(미선언 시
    "mine"이 room_id로 잡혀 422). booker/admin은 403, 미인증 401(``_require_provider``).
    """
    return service.get_my_room(session, principal.user_id)


@router.get("/regions", response_model=list[RegionGroup])
def list_regions(session: Session = Depends(get_session)) -> list[RegionGroup]:
    """활성 룸이 있는 시/군/구→동/읍/면 콤보 트리를 반환한다 → 200(공개, AC1).

    지역 콤보(1차 시군구·2차 동) 데이터 공급. 보유 룸의 지역 b_code를 백엔드 번들 참조에
    조인해 라벨·필터 목록을 구성한다(룸이 있는 지역만). **인증 없음**(탐색은 비로그인 —
    PRD §FR-2, ``/availability``·``GET ""``와 동일 근거). 정적 경로라 동적 ``/{room_id}``보다
    **먼저 선언**한다(미선언 시 "regions"가 room_id로 잡혀 422). operationId =
    ``rooms_list_regions``(1.9, 도메인 유일).
    """
    return service.list_regions(session)


@router.get(
    "/search",
    response_model=CursorPage[RoomListItem],
    responses={422: {"model": ErrorResponse}},
)
def search_rooms(
    region_code: str | None = Query(default=None),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=3.0, gt=0, le=50),
    limit: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    cursor: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> CursorPage[RoomListItem]:
    """선택 지역/반경(또는 전체)의 활성 룸을 신선 슬롯과 함께 **한 페이지** 반환 → 200(공개·AC1·AC4 + F).

    목록 행(이름·가격·룸형태·부대시설 + 예약 가능 배지용 신선 ``remaining_slots``). 두 검색방식:

    - **지역(3.4):** ``region_code`` 미지정=지역 필터 없음, 지정=시군구/동 레벨 코드로 필터.
    - **반경(3.5):** ``lat``·``lng``가 **둘 다** 있을 때만 반경 필터 적용(부분 좌표=미적용).
      ``radius_km`` 미지정 시 기본 3km, 결과는 가까운 순 정렬. ``region_code``와 동시=교집합.

    **페이징(F):** 거리/지역 계산 정렬이라 **offset 커서**(``CursorPage`` 봉투 — ``items`` +
    ``next_cursor``). ``limit``(기본 20·최대 100)·``cursor``는 쿼리, 손상/음수 커서는 422.
    **미매핑/미존재 region_code=빈 페이지 200**(에러 계약 없음 — graceful). 범위 밖 파라미터
    (``lat∉[-90,90]``·``lng∉[-180,180]``·``radius_km≤0`` 또는 50 초과)=**422**(Query 검증→1.5).
    **인증 없음**(탐색은 비로그인 — PRD §FR-2). 정적 경로라 ``/{room_id}``보다 **먼저 선언**한다.
    operationId = ``rooms_search_rooms``(1.9, 도메인 유일).
    """
    items, next_cursor = service.search_rooms_page(
        session,
        region_code,
        center_lat=lat,
        center_lng=lng,
        radius_km=radius_km,
        limit=limit,
        cursor=cursor,
    )
    return CursorPage(items=items, next_cursor=next_cursor)


# ⚠️ 동적 ``/{room_id}``는 정적 ``/geocode``·``/availability``·``GET ""``·``/regions``·
#    ``/search``(위)보다 **뒤에** 선언한다
# (라우팅 순서 가드 — 모듈 docstring 참조). 위로 올리면 ``GET /rooms/availability``가
# room_id="availability" UUID 변환 422가 된다. GET·PATCH 둘 다 동적 그룹이라 함께 둔다.
@router.get(
    "/{room_id}",
    response_model=RoomSummary,
    responses={404: {"model": ErrorResponse}},
)
def get_room(
    room_id: uuid.UUID, session: Session = Depends(get_session)
) -> RoomSummary:
    """단일 룸 신선 요약(바텀시트, Story 3.3) → 200(공개, AC1·AC4).

    가격·수용·룸형태·부대시설·영업시간 + ``derive_slots`` 재사용한 **신선 ``remaining_slots``**.
    **인증 없음**(탐색 첫 화면 핀 탭 — PRD §FR-2, ``/availability``·``GET ""``와 동일 근거).
    미존재/비활성=404 ``ROOM_NOT_FOUND``. ``provider_id`` 미노출(공개·과조회 방지). 동적 라우트라
    정적 경로 뒤·``PATCH /{room_id}`` 근처 선언. operationId = ``rooms_get_room``(1.9, 도메인 유일).
    4.2 상세 화면이 이 엔드포인트를 후기/예약 UI로 확장한다.
    """
    return service.get_room_summary(session, room_id)


@router.get(
    "/{room_id}/slots",
    response_model=RoomSlotsResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_room_slots(
    room_id: uuid.UUID,
    date: date = _date_query,
    session: Session = Depends(get_session),
) -> RoomSlotsResponse:
    """활성 룸의 ``date``(ROOM_TZ) 1시간 슬롯을 상태별로 + 다음 빈 날짜를 반환한다 → 200(공개, AC1).

    그날 1시간 슬롯을 상태별(``available`` 가용/``past`` 지난 시간/``reserved`` 예약됨)로,
    그리고 그날 다음부터 30일 내 첫 빈 날(``next_available_date``)을 함께 싣는다. ``derive_slots``
    (2.1) 재사용 — ``reserved`` 상태는 **Story 4.9 예약 차감 연결 전까지 미발생**. **인증 없음**
    (상세·슬롯은 비로그인 — PRD §FR-2, ``GET /{room_id}``와 동일 근거). 미존재/비활성=404
    ``ROOM_NOT_FOUND``. ``date`` 누락/오형식=422(Query 파싱→1.5 핸들러).

    **라우팅 순서:** ``/{room_id}/slots``는 2-세그먼트라 정적 ``/geocode``·``/availability``·
    ``/regions``·``/search``·``GET ""`` 및 1-세그먼트 동적 ``/{room_id}``와 충돌하지 않는다(경로
    깊이 다름) — 동적 ``/{room_id}`` 그룹 근처에 둔다. operationId = ``rooms_get_room_slots``(1.9,
    도메인 유일) → SDK ``roomsGetRoomSlots``.
    """
    return service.get_room_slots(session, room_id, date)


@router.patch(
    "/{room_id}",
    response_model=RoomPublic,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def update_room(
    room_id: uuid.UUID,
    data: RoomUpdateRequest,
    principal: AuthPrincipal = Depends(_require_provider),
    session: Session = Depends(get_session),
) -> Room:
    """본인 소유 공간을 부분 수정한다 → 200 + RoomPublic(provider 전용, AC1·AC4·AC5).

    ``model_dump(exclude_unset=True)`` 부분 수정(PATCH 시맨틱) — 미제공 필드는 불변,
    ``business_hours`` 제공 시 전체 교체. 소유권은 **서비스에서 최종 강제**(타인/미존재
    room_id는 404 ``ROOM_NOT_FOUND``로 합침). 자정 넘김·범위 밖 값 등 검증 실패는 422.
    operationId = ``rooms_update_room``(1.9 규약, 도메인 내 유일).
    """
    return service.update_room(session, principal.user_id, room_id, data)
