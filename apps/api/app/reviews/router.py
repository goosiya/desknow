"""reviews 라우터: 후기 작성(booker 인증·소유권) + 룸 상세 후기 목록(공개 무인증) (Story 5.5).

``main.py``가 ``api_router``(``/api/v1``) 아래에 포함하므로 최종 경로는
``POST /api/v1/reservations/{reservation_id}/reviews``(작성 — booker, reservations me_router 동형
top-level)와 ``GET /api/v1/rooms/{room_id}/reviews``(룸 상세 목록 — 공개)다. reviews.service
프리미티브(자격 판정·생성·목록)를 소비하고, 소유권 가드·조합만 라우터가 진다.

**작성(AC1·AC2·AC3):** booker 본인 이용 완료 예약만. 소유권 가드(미존재·비소유=404
``RESERVATION_NOT_FOUND``, 누설 금지 — reservations cancel 미러) → 자격·중복은 service(미완료=409
``RESERVATION_NOT_COMPLETED``, 중복=409 ``REVIEW_ALREADY_EXISTS``). room_id는 예약에서 도출(경로
불요). 입력 형식(별점 범위·텍스트 길이)은 ``ReviewCreateRequest``가 선차단(422).

**조회(AC3·AC4):** 룸 상세는 공개 표면(``GET /rooms/{id}`` 동일 근거 — PRD §FR-2)이라 **무인증**.
미존재/비활성 룸도 후기 목록은 빈/기존 노출(상세 404와 분리 — 후기는 공개 데이터, 존재 누설 무관).

**규약:**

- **RBAC 최종 강제(1.8):** 작성은 booker 행위라 ``Depends(_require_booker)``(모듈레벨 싱글톤 —
  ruff B008 회피, reservations 선례). provider/admin=403 ``FORBIDDEN_ROLE``, 미인증=401
  ``UNAUTHENTICATED``. 조회는 의존성 없음(공개).
- **operationId(1.9):** ``{tag}_{name}`` — ``reviews_create_review`` → SDK ``reviewsCreateReview``,
  ``reviews_list_room_reviews`` → ``reviewsListRoomReviews``.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.db import get_session
from app.core.errors import DomainError, ErrorCode, ErrorResponse
from app.core.pagination import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, CursorPage
from app.core.security import AuthPrincipal, require_role
from app.reservations.models import Reservation
from app.reviews import service
from app.reviews.models import Review
from app.reviews.schemas import (
    ReviewCreateRequest,
    ReviewListItem,
    ReviewPublic,
    ReviewReplyCreateRequest,
    ReviewReplyPublic,
    ReviewReplyView,
)
from app.rooms.models import Room  # 소유권 판정용 조회(라우터=조합 계층 — service↔service 아님)

# 후기 작성은 예약 종속(특정 예약에 다는 행위)이라 reservations me_router와 동형 top-level 라우터에
# 둔다(``POST /reservations/{reservation_id}/reviews``). tags=["reviews"]라 operationId는 reviews_*.
me_router = APIRouter(prefix="/reservations", tags=["reviews"])

# 룸 상세 후기 목록은 룸 결합 공개 표면(``GET /rooms/{room_id}/reviews``)이라 별도 public 라우터.
router = APIRouter(prefix="/rooms", tags=["reviews"])

# 제공자 답글 작성은 후기 종속(특정 후기에 다는 행위)이라 후기 결합 top-level 라우터에 둔다
# (``POST /reviews/{review_id}/reply``, 5.6). tags=["reviews"]라 operationId는 reviews_*.
reply_router = APIRouter(prefix="/reviews", tags=["reviews"])

# RBAC 의존성을 모듈레벨 싱글톤으로 고정한다(booker 전용 — 작성은 예약자 행위). 인자 기본값에서
# 직접 require_role 호출 시 ruff B008에 걸리므로 싱글톤을 Depends에 전달한다(reservations 선례).
_require_booker = require_role("booker")

# 답글 작성은 provider 행위라 별도 싱글톤(provider 전용 — rooms 라우터 _require_provider 선례 미러).
_require_provider = require_role("provider")


@me_router.post(
    "/{reservation_id}/reviews",
    response_model=ReviewPublic,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def create_review(
    reservation_id: uuid.UUID,
    data: ReviewCreateRequest,
    principal: AuthPrincipal = Depends(_require_booker),
    session: Session = Depends(get_session),
) -> ReviewPublic:
    """이용 완료한 본인 예약에 별점+텍스트 후기를 작성한다 → 201 + ReviewPublic(booker, AC1~AC3).

    ① **소유권 가드(AC3):** ``session.get(Reservation, id)`` → 미존재이거나 ``booker_id``가
    요청자가 아니면 **404 ``RESERVATION_NOT_FOUND``**. 타인 예약을 403이 아니라 404로 막아 **존재
    여부를 누설하지 않는다**(reservations cancel 패턴 미러). 미인증=401·provider/admin=403은
    ``_require_booker``. ② **자격·중복은 service:** 이용 완료 아님(취소/거절/미완료) → 409
    ``RESERVATION_NOT_COMPLETED``, 이미 작성 → 409 ``REVIEW_ALREADY_EXISTS``. 입력 형식(별점 범위·
    텍스트 길이)은 ``ReviewCreateRequest``가 선차단(422). room_id는 예약에서 도출한다(경로 불요).
    """
    # ① 소유권 가드 — 미존재·비소유를 동일 404로 합쳐 타인 예약 존재를 누설하지 않는다.
    reservation = session.get(Reservation, reservation_id)
    if reservation is None or reservation.booker_id != principal.user_id:
        raise DomainError(ErrorCode.RESERVATION_NOT_FOUND, "예약을 찾을 수 없습니다.")

    # ② 자격(이용 완료)·중복(예약당 1회)은 service가 강제 — 미완료/중복은 DomainError(409)로 던지고
    #    전역 핸들러가 표준 스키마로 변환(라우터 추가 try 불요).
    review = service.create_review(
        session,
        reservation=reservation,
        booker_id=principal.user_id,
        rating=data.rating,
        text=data.text,
    )
    return ReviewPublic(
        id=review.id,
        reservation_id=review.reservation_id,
        room_id=review.room_id,
        rating=review.rating,
        text=review.text,
        created_at=review.created_at,
    )


@router.get(
    "/{room_id}/reviews",
    response_model=CursorPage[ReviewListItem],
    responses={422: {"model": ErrorResponse}},
)
def list_room_reviews(
    room_id: uuid.UUID,
    session: Session = Depends(get_session),
    limit: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    cursor: str | None = Query(default=None),
) -> CursorPage[ReviewListItem]:
    """룸 상세의 후기를 최신순 **한 페이지**로 반환한다 → 200(공개·무인증, AC4 + F 페이징).

    룸 상세는 공개 표면(``GET /rooms/{id}`` 동일 근거 — PRD §FR-2)이라 **인증 없음**. 각 후기는
    **별점·텍스트·작성일만**(작성자 식별 미노출 — KTH 결정 1 익명). ``created_at`` keyset 페이징
    (``CursorPage`` 봉투). ``limit``(기본 20·최대 100)·``cursor``는 쿼리, 손상 커서는 422. 후기가
    없으면 ``items=[]``·``next_cursor=None``(정상 200 — 막다른 화면 금지는 FE 빈 상태 카피).
    미존재/비활성 룸도 빈/기존 목록을 낸다(후기는 공개 데이터, 상세 404와 분리).
    """
    reviews, next_cursor = service.list_room_reviews_page(
        session, room_id, limit=limit, cursor=cursor
    )
    # 답글을 단일 배치 쿼리로 합성한다(N+1 금지 — reservation_ids_with_review 배치 정신). 후기당
    # 답글은 최대 1건(uq_review_replies_review). 답글 있는 후기만 reply 채우고 없으면 None(5.6).
    replies = service.replies_by_review_ids(session, {review.id for review in reviews})
    items = [
        ReviewListItem(
            id=review.id,
            rating=review.rating,
            text=review.text,
            created_at=review.created_at,
            reply=(
                ReviewReplyView(text=reply.text, created_at=reply.created_at)
                if (reply := replies.get(review.id)) is not None
                else None
            ),
        )
        for review in reviews
    ]
    return CursorPage(items=items, next_cursor=next_cursor)


@reply_router.post(
    "/{review_id}/reply",
    response_model=ReviewReplyPublic,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def create_reply(
    review_id: uuid.UUID,
    data: ReviewReplyCreateRequest,
    principal: AuthPrincipal = Depends(_require_provider),
    session: Session = Depends(get_session),
) -> ReviewReplyPublic:
    """제공자가 자기 룸 후기에 답글을 단다 → 201 + ReviewReplyPublic(provider, 5.6 AC1·AC2·AC3·AC4).

    ① **후기 존재(AC2):** ``session.get(Review, id)`` → 미존재면 **404 ``REVIEW_NOT_FOUND``**.
    ② **소유권(AC2):** 후기의 룸(``session.get(Room, review.room_id)``)이 요청자 소유가 아니면
    **403 ``REVIEW_REPLY_FORBIDDEN``** — 후기·룸은 공개 데이터라 존재 누설이 무관하고 epic AC가
    명시 403을 요구한다(booker 도메인의 404 비노설과 의도적 분기). 라우터=조합 계층이 ``Room``을
    조회한다(reviews.service는 ``Room``을 만지지 않음 — 순환 금지, 반복 함정 #3). ③ **중복은
    service:** 이미 답글이 달린 후기 → 409 ``REVIEW_REPLY_ALREADY_EXISTS``. 미인증=401·
    booker/admin=403 ``FORBIDDEN_ROLE``은 ``_require_provider``. 텍스트 형식은
    ``ReviewReplyCreateRequest`` 선차단(422). room_id는 후기에서 도출(경로 불요). 비활성
    룸이라도 본인 룸이면 허용(자기 데이터).
    """
    # ① 후기 존재 — 미존재면 404(후기·룸은 공개 데이터라 누설 무관, booker 404 비노설과 다름).
    review = session.get(Review, review_id)
    if review is None:
        raise DomainError(ErrorCode.REVIEW_NOT_FOUND, "후기를 찾을 수 없습니다.")

    # ② 소유권 가드 — 후기의 룸 provider가 요청자가 아니면 403(epic AC 명시 소유권 차단). 룸
    #    조회는 라우터(조합 계층)가 한다 — service↔rooms.service 순환 금지(Room 타입 import만).
    room = session.get(Room, review.room_id)
    if room is None or room.provider_id != principal.user_id:
        raise DomainError(
            ErrorCode.REVIEW_REPLY_FORBIDDEN,
            "본인 룸의 후기에만 답글을 달 수 있어요.",
        )

    # ③ 중복(후기당 1회)은 service가 강제 — 중복은 DomainError(409)로 던지고 전역 핸들러가 변환.
    reply = service.create_reply(
        session,
        review=review,
        provider_id=principal.user_id,
        text=data.text,
    )
    return ReviewReplyPublic(
        id=reply.id,
        review_id=reply.review_id,
        text=reply.text,
        created_at=reply.created_at,
    )
