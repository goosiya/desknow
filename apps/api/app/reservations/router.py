"""reservations 라우터: 즉시 예약 확정(4.5) + 예약 취소(4.7) + 본인 예약현황 목록(4.8).

``main.py``가 ``api_router``(``/api/v1``) 아래에 포함하므로 최종 경로는
``POST /api/v1/rooms/{room_id}/reservations``(생성, 4.5)와
``POST /api/v1/rooms/{room_id}/reservations/{reservation_id}/cancel``(취소, 4.7 — 상태 전이
액션 동사·DELETE 아님)다(중첩 — architecture.md L243). **본인 예약현황 목록**은 룸 비결합이라
별도 top-level 라우터(``me_router``, ``GET /api/v1/reservations`` — 4.8)에 둔다(favorites
``/favorites`` 동형). 4.1 프리미티브(``create_reservation``
all-or-nothing 점유·SLOT_CONFLICT 변환 / ``cancel_reservation`` status flip+슬롯 재활성)를
소비하고, 확정 시점에 ``rooms.service``의 슬롯 도출을 **재사용**해 신선 재검증한다(슬롯 SQL
직접 접근 금지 — 도메인 경계 architecture.md L354·L362).

**취소(4.7):** booker 본인 확정 예약만 취소한다. 소유권 가드(미존재·비소유=404
``RESERVATION_NOT_FOUND``, 누설 금지) + 6h 윈도우 게이트(``< 6시간`` → 409
``CANCEL_WINDOW_PASSED``, ``service.cancel_reservation_for_booker``에 위임) + 종료 상태 멱등.
취소 = 행 삭제가 아니라 status flip(히스토리 잔존)이라 ``POST …/cancel`` 액션 동사를 쓴다.

**규약:**

- **RBAC 최종 강제(1.8, §Boundaries L351 — 범위 결정 #1):** 예약 생성은 booker 행위라
  ``Depends(require_role("booker"))``. provider/admin은 403 ``FORBIDDEN_ROLE``, 미인증은 401
  ``UNAUTHENTICATED``(favorites의 역할무관 ``get_current_principal``과 달리 **역할 제약**).
  ``require_role("booker")``는 모듈레벨 싱글톤(``_require_booker``)으로 고정한다(ruff B008 회피 —
  rooms ``_require_provider`` 선례).
- **결제 없음(FR-14):** 결제·금액 차감 단계 없음. 확정 = 슬롯 점유 행 생성이 전부.
- **신선 재검증(범위 결정 #2, [[availability-freshness-policy]]):** 요청 슬롯이 **확정 시점에
  실제 빈 슬롯**인지 ``rooms.service.get_room_slots``(4.3 — ``derive_slots`` 재사용) 경유로
  재확인한다. 요청 ``slot_starts ⊆ 가용 집합``이 아니면(stale·과거·영업시간외·휴무) 409
  ``SLOT_CONFLICT``. **이미 예약된 슬롯**은 ``uq_reservation_slots_room_slot`` UNIQUE가 INSERT 시
  최종 차단(4.1 변환 → 409). 룸 미존재/비활성은 ``get_room_slots``의 404 ``ROOM_NOT_FOUND`` 가드가
  처리한다(공유 헬퍼 ``_get_active_room_or_404``).
- **입력 형식(422):** 빈 배열·naive datetime·중복·교차일은 ``ReservationCreateRequest``가
  Pydantic 검증으로 선차단 → 1.5 핸들러가 422 ``VALIDATION_ERROR``. service ``ValueError``가
  500으로 새지 않는다(반복 함정 #6).
- **신규 ErrorCode 0:** SLOT_CONFLICT·ROOM_NOT_FOUND·FORBIDDEN_ROLE·UNAUTHENTICATED·
  VALIDATION_ERROR 전부 기존(core/errors).
- **operationId(1.9):** 함수명 ``create_reservation`` → ``{tag}_{name}`` =
  ``reservations_create_reservation`` → SDK ``reservationsCreateReservation``.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.db import get_session
from app.core.errors import DomainError, ErrorCode, ErrorResponse
from app.core.pagination import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    CursorPage,
)
from app.core.security import AuthPrincipal, require_role
from app.core.time import ROOM_TZ, to_tz
from app.reservations import service
from app.reservations.models import Reservation
from app.reservations.schemas import (
    ProviderReservationItem,
    ReservationCreateRequest,
    ReservationListItem,
    ReservationPublic,
    booker_display_label,
)
from app.reviews import service as reviews_service
from app.reviews.schemas import ReviewListItem, ReviewReplyView
from app.rooms import service as rooms_service
from app.rooms.models import Room

router = APIRouter(prefix="/rooms/{room_id}/reservations", tags=["reservations"])

# 본인 예약 목록은 **룸 비결합 top-level**(여러 룸에 걸친 내 예약)이라 중첩 라우터와 별도로 둔다
# (favorites ``/favorites``와 동형). 같은 tags=["reservations"]라 operationId는 reservations_*
# 규약을 따른다(``GET /api/v1/reservations`` → ``reservations_list_reservations`` →
# reservationsListReservations).
me_router = APIRouter(prefix="/reservations", tags=["reservations"])

# 제공자 예약현황(Story 6.1)도 **여러 룸에 걸친** 조회라 중첩 라우터와 별도 top-level 인스턴스로
# 둔다(me_router ``/reservations``와 동형 — 단 provider 네임스페이스). 같은 tags=["reservations"]라
# operationId는 reservations_* 규약(``GET /api/v1/provider/reservations`` →
# ``reservations_list_provider_reservations`` → reservationsListProviderReservations).
provider_router = APIRouter(prefix="/provider/reservations", tags=["reservations"])

# RBAC 의존성을 모듈레벨 싱글톤으로 고정한다(booker 전용 — 범위 결정 #1). 인자 기본값에서 직접
# ``require_role("booker")``를 호출하면 ruff B008(기본값 함수 호출)에 걸리므로, B008 권장대로
# 싱글톤을 ``Depends``에 전달한다(rooms ``_require_provider`` 선례, extend-immutable-calls=Depends).
_require_booker = require_role("booker")

# 제공자 예약현황(Story 6.1)은 provider 행위라 provider 전용 싱글톤(rooms ``_require_provider``·본
# 모듈 ``_require_booker`` 동형 — B008 회피). booker/admin=403, 미인증=401.
_require_provider = require_role("provider")


@router.post(
    "",
    response_model=ReservationPublic,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def create_reservation(
    room_id: uuid.UUID,
    data: ReservationCreateRequest,
    principal: AuthPrincipal = Depends(_require_booker),
    session: Session = Depends(get_session),
) -> ReservationPublic:
    """선택한 빈 연속 슬롯을 결제 없이 즉시 확정한다 → 201 + ReservationPublic(booker, AC1·AC2).

    ① 신선 재검증: 요청 슬롯의 ROOM_TZ 날짜에 대해 ``get_room_slots``(4.3 — ``derive_slots`` 재사용)
    로 가용 슬롯 집합을 구하고 ``요청 ⊆ 가용``을 확인한다(룸 미존재/비활성은 그 호출의 404 가드).
    위반(stale·과거·영업시간외·휴무)은 409 ``SLOT_CONFLICT``. ② 확정: 4.1 ``create_reservation``으로
    예약 단위 1건 + 슬롯 점유 행을 단일 트랜잭션 all-or-nothing 생성(이미 점유된 슬롯은 UNIQUE가
    최종 차단 → 409). 입력 형식 위반(빈/naive/중복/교차일)은 스키마가 선차단(422).
    """
    # ① 신선 재검증 — 요청 슬롯이 확정 시점에 실제 빈 슬롯인지 rooms.service 경유로 재확인한다.
    #    스키마가 "같은 ROOM_TZ 날짜"를 보장하므로 첫 슬롯의 날짜 하나만 도출하면 충분하다.
    #    get_room_slots가 미존재/비활성 룸을 404 ROOM_NOT_FOUND로 막는다(공유 404 가드 재사용).
    target_date = to_tz(data.slot_starts[0], ROOM_TZ).date()
    slots_response = rooms_service.get_room_slots(session, room_id, target_date)
    # 가용 슬롯 집합 — aware UTC 인스턴트끼리 비교(set은 인스턴트 기준 멤버십). available만 통과.
    available = {
        slot.slot_start for slot in slots_response.slots if slot.status == "available"
    }
    if not set(data.slot_starts) <= available:
        # stale 선택·과거·영업시간외·휴무 = "지금 잡을 수 없는 슬롯" → SLOT_CONFLICT(409) 단일화
        # ([[availability-freshness-policy]] 확정 시 409 차단). 특화 카피·인접 재표시는 4.6.
        raise DomainError(
            ErrorCode.SLOT_CONFLICT,
            "선택한 시간을 지금 예약할 수 없습니다. 시간표를 다시 확인해 주세요.",
        )

    # ② 확정 — 4.1 프리미티브 소비(재구현 금지). 이미 점유된 슬롯은 UNIQUE가 INSERT 시 최종 차단
    #    → create_reservation이 DomainError(SLOT_CONFLICT)를 던지고 전역 핸들러가 409로 변환한다
    #    (라우터 추가 try 불요). 신선 재검증과 UNIQUE가 이중 방어(검증=과거/시간외/휴무).
    reservation = service.create_reservation(
        session,
        booker_id=principal.user_id,
        room_id=room_id,
        slot_starts=data.slot_starts,
    )
    # 점유 행 slot_start는 요청값과 동일(create_reservation이 그대로 INSERT) → 요청값을 응답에 싣음.
    return ReservationPublic(
        id=reservation.id,
        room_id=reservation.room_id,
        booker_id=reservation.booker_id,
        status=reservation.status,
        created_at=reservation.created_at,
        slot_starts=list(data.slot_starts),
    )


@router.post(
    "/{reservation_id}/cancel",
    response_model=ReservationPublic,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def cancel_reservation(
    room_id: uuid.UUID,
    reservation_id: uuid.UUID,
    principal: AuthPrincipal = Depends(_require_booker),
    session: Session = Depends(get_session),
) -> ReservationPublic:
    """예약자 본인 확정 예약을 취소한다 → 200 + ReservationPublic(status cancelled, AC1~AC4).

    분기 순서(중요):

    ① **소유권 가드(AC4):** ``session.get(Reservation, id)`` → 미존재이거나 ``booker_id``가
    요청자가 아니거나 경로 ``room_id``와 불일치면 **404 ``RESERVATION_NOT_FOUND``**. 타인 예약을
    403이 아니라 404로 막아 **타인 예약 존재 여부를 누설하지 않는다**(2.3 ``ROOM_NOT_FOUND`` 패턴
    미러 — 미존재와 비-소유를 동일 404로 합침). 미인증=401·provider/admin=403은 ``_require_booker``.

    ② **게이트 + 취소:** ``service.cancel_reservation_for_booker``가 종료 상태면 즉시 멱등 반환,
    아니면 6h 윈도우(``< 6시간`` → 409 ``CANCEL_WINDOW_PASSED``)를 강제한 뒤 4.1
    ``cancel_reservation``(status flip + 슬롯 DELETE 단일 트랜잭션)을 호출한다. 6h 게이트는
    **service에 위임**한다.

    성공·멱등 모두 **200**(생성만 201). 취소 후 점유 슬롯은 비워졌으므로 ``slot_starts=[]``로
    직렬화한다(이미 종료 상태인 멱등 경로도 슬롯이 0건이라 동일). 에러코드·숫자 상태는 화면에
    노출하지 않는다(고정 한국어 ``message``만 — UX-DR10, FE 분기는 4.8 ``detail.code``).
    """
    # ① 소유권 가드 — 미존재·비소유·경로 불일치를 동일 404로 합쳐 타인 예약 존재를 누설하지 않는다.
    reservation = session.get(Reservation, reservation_id)
    if (
        reservation is None
        or reservation.booker_id != principal.user_id
        or reservation.room_id != room_id
    ):
        raise DomainError(ErrorCode.RESERVATION_NOT_FOUND, "예약을 찾을 수 없습니다.")

    # ② 게이트 + 취소 — 종료 상태 멱등 → 6h 게이트 → 4.1 cancel_reservation(재구현 금지). 윈도우
    #    경과면 DomainError(CANCEL_WINDOW_PASSED, 409)를 던져 전역 핸들러가 표준 스키마로 변환.
    updated = service.cancel_reservation_for_booker(session, reservation)

    # 취소 후 점유 슬롯은 0건(슬롯 DELETE=재활성) → 빈 리스트. 멱등(이미 종료 상태) 경로도 동일.
    return ReservationPublic(
        id=updated.id,
        room_id=updated.room_id,
        booker_id=updated.booker_id,
        status=updated.status,
        created_at=updated.created_at,
        slot_starts=[],
    )


@me_router.get(
    "",
    response_model=CursorPage[ReservationListItem],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def list_reservations(
    principal: AuthPrincipal = Depends(_require_booker),
    session: Session = Depends(get_session),
    limit: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    cursor: str | None = Query(default=None),
) -> CursorPage[ReservationListItem]:
    """예약자 본인의 예약을 최근순 **한 페이지**로 반환한다 → 200(booker, AC1·AC2·AC4 + F 페이징).

    본인(``booker_id == principal.user_id``) 예약만 상태 무관(confirmed/cancelled/rejected)으로
    ``created_at`` 내림차순 keyset 페이징한다(``CursorPage`` 봉투 — ``items`` + ``next_cursor``;
    다가오는/지난 분류·6h 취소 가능 판정은 FE가 ``slot_starts`` 스냅샷으로 계산 — 4.7 범위 결정 #3).
    ``limit``(기본 20·최대 100)·``cursor``(이전 페이지 토큰)는 쿼리. 손상 커서는 422. 미인증=401,
    provider/admin=403(``_require_booker``). 예약이 없으면 ``items=[]``·``next_cursor=None``(정상 200).

    **룸 이름·is_active 합성은 라우터에서**(``session.get(Room, …)``): reservations.service가
    rooms를 import하면 4.9 ``rooms.service → reservations.service``(차감) 역방향과 **순환 import**가
    되므로, service는 ``reservations`` 테이블만 만지고 룸 메타 합성은 조합 계층인 라우터가
    한다(``rooms.models`` import는 router 한정 = service↔service 순환 아님 — favorites
    ``build_favorite_item`` 선례). 슬롯 시간은 ``Reservation.slot_starts`` **스냅샷**(취소/거절
    후에도 잔존 — 범위 결정 #1)을 싣는다.

    **``has_review`` 합성(Story 5.5 — 후기 작성 게이팅):** ``reviews.service``의
    ``reservation_ids_with_review``를 **단일 호출**(N+1 금지)해 본인 후기 존재 예약 집합을 구하고
    각 항목에 ``has_review = reservation.id in ids``를 싣는다. reservations.router →
    reviews.service **단방향**(라우터=조합 계층, room_name 합성과 동형 — service↔service 순환 아님:
    reviews.service는 reservations를 import하지 않는다).
    """
    reservations, next_cursor = service.list_booker_reservations_page(
        session, principal.user_id, limit=limit, cursor=cursor
    )
    # 본인 후기를 {reservation_id: Review}로 단일 조회(N+1 금지). 존재 여부(has_review)뿐 아니라
    # 내용(별점·텍스트·작성일)까지 행에 싣는다 → 예약현황에서 "후기 완료"가 아니라 실제 후기를 표시.
    reviews_by_resv = reviews_service.reviews_by_booker(session, principal.user_id)
    # 그 후기들의 사장님 답글도 단일 배치 조회로 합성(N+1 금지 — 후기당 답글 최대 1건).
    replies_by_review = reviews_service.replies_by_review_ids(
        session, {review.id for review in reviews_by_resv.values()}
    )
    items: list[ReservationListItem] = []
    for reservation in reservations:
        # 룸 메타(이름·활성여부)를 PK 조회로 합성. FK(ondelete RESTRICT)상 룸은 하드삭제되지 않아
        # 항상 존재하지만, 도달 불가 경로를 타입 안전하게 막기 위해 None이면 이름 폴백한다(404 대신
        # 목록 1행 누락 회피 — 비활성 룸의 예약도 이름·히스토리를 표시해야 하므로, 룸 부재 시에도
        # 행 자체는 시간 스냅샷으로 표시 가능하게 둔다).
        room = session.get(Room, reservation.room_id)
        # 본인 후기(있으면) → 답글까지 중첩한 ReviewListItem 합성. 없으면 None(has_review=False).
        my_review = reviews_by_resv.get(reservation.id)
        review_item = None
        if my_review is not None:
            reply = replies_by_review.get(my_review.id)
            review_item = ReviewListItem(
                id=my_review.id,
                rating=my_review.rating,
                text=my_review.text,
                created_at=my_review.created_at,
                reply=(
                    ReviewReplyView(text=reply.text, created_at=reply.created_at)
                    if reply is not None
                    else None
                ),
            )
        items.append(
            ReservationListItem(
                id=reservation.id,
                room_id=reservation.room_id,
                room_name=room.name if room is not None else "알 수 없는 공간",
                status=reservation.status,
                slot_starts=list(reservation.slot_starts),
                created_at=reservation.created_at,
                is_active=room.is_active if room is not None else False,
                has_review=my_review is not None,  # 5.5 후기 작성 게이팅(review 존재와 정합)
                review=review_item,  # 본인 후기 내용 + 사장님 답글(없으면 None)
            )
        )
    return CursorPage(items=items, next_cursor=next_cursor)


@provider_router.get(
    "",
    response_model=CursorPage[ProviderReservationItem],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def list_provider_reservations(
    principal: AuthPrincipal = Depends(_require_provider),
    session: Session = Depends(get_session),
    limit: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    cursor: str | None = Query(default=None),
) -> CursorPage[ProviderReservationItem]:
    """제공자 소유 룸의 예약을 최근순 **한 페이지**로 반환한다 → 200(provider, AC1·AC2·AC3 + F).

    ``list_reservations``(예약자 본인 목록, 4.8)의 **거울상** — 소유권 축이 ``booker_id``(본인) →
    ``Room.provider_id``(소유 룸)이고, 예약자 식별정보를 **익명 라벨**로 가린다(FR-23 Privacy).
    본인 소유 룸이 없거나 예약이 없으면 빈 리스트(정상 200). 미인증=401,
    booker/admin=403(``_require_provider``).

    **합성(도메인 경계 — architecture.md L354·4.9 순환 회피):**

    ① ``rooms_service.list_provider_rooms``로 소유 룸을 가져온다(``Room.provider_id`` 필터 — 타
    제공자 룸의 예약은 구조적으로 노출 불가, AC3). 그 결과로 **이름 맵**(``{room.id: room.name}``)을
    만든다(룸 0개면 이후 빈 목록). ② ``service.list_reservations_for_rooms``로 그 룸들의 예약을
    상태 무관·``created_at`` desc로 조회한다(reservations.service는 ``room_ids``만 받고 rooms를
    import하지 않는다). ③ 각 예약을 ``ProviderReservationItem``으로 매핑 — ``room_name``은 이름
    맵에서(행마다 ``session.get(Room)`` 재조회 금지 = N+1 회피, 소유 룸은 이미 메모리에),
    ``booker_label``은 ``booker_display_label(reservation.booker_id)``로 해시 파생한다.
    **``booker_id``는 응답에 싣지 않는다**(AC2 — 이메일·raw UUID 비노출).

    슬롯 시간은 ``Reservation.slot_starts`` **스냅샷**(취소/거절 후에도 잔존)을 싣는다.
    다가오는/지난 분류·정렬은 소비처가 ``slot_starts``로 계산한다(서버 flat — 4.8 범위 결정 #3, 소비
    UI는 provider 웹 표면 후속). **읽기 전용**(상태 전이·슬롯 변경 0 — cancel↔reject race는 6.2).
    """
    rooms = rooms_service.list_provider_rooms(session, principal.user_id)
    # 룸 이름 맵 — 행마다 session.get(Room) 재조회 대신 소유 룸 결과로 1회 합성(N+1 회피). 소유 룸은
    # MVP 1개·최대 소수라 메모리 맵으로 충분(list_reservations의 행별 get(Room)과 의도적 대비 —
    # 거기선 룸이 본인 예약마다 다양하지만, 여긴 소유 룸 전체를 이미 가져왔으므로).
    room_names = {room.id: room.name for room in rooms}
    reservations, next_cursor = service.list_reservations_for_rooms_page(
        session, list(room_names), limit=limit, cursor=cursor
    )
    items = [
        ProviderReservationItem(
            id=reservation.id,
            room_id=reservation.room_id,
            # 예약의 room_id는 항상 소유 룸 집합에 속한다(list_reservations_for_rooms가 그 룸들만
            # 조회) → 이름 맵에 반드시 존재. 도달 불가 경로를 타입 안전하게 막기 위해 폴백을 둔다.
            room_name=room_names.get(reservation.room_id, "알 수 없는 공간"),
            booker_label=booker_display_label(reservation.booker_id),  # 익명 라벨(AC2)
            status=reservation.status,
            slot_starts=list(reservation.slot_starts),
            created_at=reservation.created_at,
        )
        for reservation in reservations
    ]
    return CursorPage(items=items, next_cursor=next_cursor)


@provider_router.post(
    "/{reservation_id}/reject",
    response_model=ReservationPublic,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def reject_reservation(
    reservation_id: uuid.UUID,
    principal: AuthPrincipal = Depends(_require_provider),
    session: Session = Depends(get_session),
) -> ReservationPublic:
    """제공자 본인 소유 룸의 확정 예약을 시작 전까지 거절한다 → 200 + ReservationPublic(AC1~AC5).

    6.1 읽기 위의 첫 쓰기(거절) 슬라이스. 분기 순서(중요):

    ① **소유권 가드(AC5 — 404로 누설 금지):** ``session.get(Reservation, id)`` + 그 예약의 룸을
    ``session.get(Room, reservation.room_id)``로 조회해 **본인 소유 룸(`Room.provider_id ==
    principal.user_id`)** 인지 확인한다. 미존재 예약·**타 제공자 룸의 예약**·룸 부재는 **동일 404
    ``RESERVATION_NOT_FOUND``**(403 아님 — 타인 예약 존재 누설 금지, 4.7 cancel 미러). 룸 소유권은
    라우터가 판정한다(reservations.service는 rooms import 금지 — 4.9 순환 회피, 라우터=조합 계층).

    ② **게이트 + 거절(+ 통지 원자):** ``service.reject_reservation_for_provider``가 종료 상태면 즉시
    멱등 반환, 아니면 시작 전 게이트(``earliest <= now`` → 409 ``REJECT_WINDOW_PASSED``)를 강제한 뒤
    ``reject_reservation``(status flip + 슬롯 DELETE + **예약자 ``status_change``/reason=
    ``'rejected'`` 통지가 동일 트랜잭션**)을 호출한다. ``now`` 미주입=실시간(``now_utc``). 게이트는
    service에 위임한다.

    **★통지 원자화(Story 8.3 — deferred L42 회수):** 거절 통지 생성은 이제 **service가 winner
    판정 시 전이 commit과 한 트랜잭션**에서 한다(이전엔 라우터가 거절 *후* 별도 트랜잭션으로
    ``create_notification``을 호출해, 통지 실패 시 거절은 영속인데 재시도가 "이미 종료"로 통지를
    건너뛰어 영구 손실 위험이 있었다). 라우터의 ``was_confirmed`` 사전 캡처·통지 호출은 제거됐다 —
    통지 결정은 service의 ``rowcount`` winner 판정으로 일원화(race 정확성·retry-safe 둘 다 충족).
    거절 통지가 **생성되는 사실은 6.2와 불변**(배선만 router→service 이동·원자화). 예약자 web 배너
    표시는 5.3이 이미 구축(web 신규 0).

    성공·멱등 모두 **200**(생성만 201). 거절 후 점유 슬롯은 비워졌으므로 ``slot_starts=[]``로
    직렬화한다(이미 종료 상태인 멱등 경로도 슬롯 0건이라 동일 — cancel 엔드포인트 미러). 에러코드·
    숫자 상태는 화면에 노출하지 않는다(고정 한국어 ``message``만 — UX-DR10, FE 분기는 detail.code).
    """
    # ① 소유권 가드 — 미존재·타 제공자 룸·룸 부재를 동일 404로 합쳐 타인 예약 존재를 누설 안 함.
    #    룸 소유권은 라우터가 session.get(Room)으로 판정한다(reservations.service는 rooms import 0).
    reservation = session.get(Reservation, reservation_id)
    room = (
        session.get(Room, reservation.room_id) if reservation is not None else None
    )
    if reservation is None or room is None or room.provider_id != principal.user_id:
        raise DomainError(ErrorCode.RESERVATION_NOT_FOUND, "예약을 찾을 수 없습니다.")

    # ② 게이트 + 거절(+ 통지 원자) — 종료 상태 멱등 → 시작 전 게이트 → reject_reservation(재구현
    #    금지·winner면 status flip + 슬롯 DELETE + reason='rejected' 통지를 단일 commit으로 원자화).
    #    시작 후면 DomainError(REJECT_WINDOW_PASSED, 409)를 전역 핸들러가 표준 스키마로 변환한다.
    #    통지 결정은 service의 rowcount winner 판정이 한다(라우터 was_confirmed 사전 캡처 제거 —
    #    deferred L42 회수: 통지가 전이와 한 트랜잭션이라 통지 실패 시 거절도 롤백·재시도가 재수행).
    updated = service.reject_reservation_for_provider(session, reservation)

    # 거절 후 점유 슬롯은 0건(슬롯 DELETE=재활성) → 빈 리스트. 멱등(이미 종료 상태) 경로도 동일.
    return ReservationPublic(
        id=updated.id,
        room_id=updated.room_id,
        booker_id=updated.booker_id,
        status=updated.status,
        created_at=updated.created_at,
        slot_starts=[],
    )
