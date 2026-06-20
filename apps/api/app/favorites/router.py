"""favorites 라우터: 즐겨찾기 추가/제거/조회 (Story 3.7, AC1·AC2·AC4·AC5).

``main.py``가 ``api_router``(``/api/v1``) 아래에 포함하므로 최종 경로는
``/api/v1/favorites`` (POST 추가 / GET 목록) · ``/api/v1/favorites/{room_id}`` (DELETE 제거)다.

**규약:**

- **인증 의존성 = ``get_current_principal``**(로그인만 요구·역할 무관, ``security.py:180``) —
  ``require_role`` **아님**. 로그인한 provider/admin도 즐겨찾기할 수 있어야 한다(403 회피).
  미인증은 401 ``UNAUTHENTICATED``(``get_current_principal``이 막음). ``principal.user_id``로 식별.
- **상태코드:** add=201(생성·멱등 재추가도 201), delete=204(멱등), list=200. 미존재 룸 추가는 404
  ``ROOM_NOT_FOUND``. 신규 ErrorCode 0(기존 코드 재사용).
- **``responses={...: ErrorResponse}``** 로 OpenAPI에 에러 계약을 노출한다(1.9 SDK가 ``detail.code``
  타입을 생성하도록). 검증 실패(잘못된 room_id 형식)는 Pydantic→1.5 핸들러가 422.
- **operationId(1.9):** ``{tag}_{name}`` = ``favorites_add_favorite``·``favorites_remove_favorite``·
  ``favorites_list_favorites``.
- **AC5 인증 배선:** 웹 SDK가 ``credentials:"include"``로 httpOnly 쿠키를 동봉하고, 백엔드는
  ``get_current_principal``이 쿠키/헤더에서 토큰을 추출한다(``auth/me``와 동일 메커니즘).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlmodel import Session

from app.core.db import get_session
from app.core.errors import ErrorResponse
from app.core.pagination import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, CursorPage
from app.core.security import AuthPrincipal, get_current_principal
from app.favorites import service
from app.favorites.schemas import FavoriteCreateRequest, FavoriteRoomItem

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.post(
    "",
    response_model=FavoriteRoomItem,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def add_favorite(
    data: FavoriteCreateRequest,
    principal: AuthPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> FavoriteRoomItem:
    """즐겨찾기에 룸을 추가한다 → 201 + FavoriteRoomItem(로그인 필요, AC1·AC4·AC5).

    멱등 — 이미 즐겨찾기된 룸이면 기존 행 기준으로 201을 돌려준다(토글 견고성). 미존재 룸은
    404 ``ROOM_NOT_FOUND``, 미인증은 401 ``UNAUTHENTICATED``.
    """
    favorite = service.add_favorite(session, principal.user_id, data.room_id)
    return service.build_favorite_item(session, favorite)


@router.get(
    "",
    response_model=CursorPage[FavoriteRoomItem],
    responses={
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def list_favorites(
    principal: AuthPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
    limit: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    cursor: str | None = Query(default=None),
) -> CursorPage[FavoriteRoomItem]:
    """현재 사용자의 즐겨찾기를 최근순 **한 페이지**로 반환한다 → 200(로그인 필요, AC2·AC3·AC5 + F).

    비활성 룸도 포함하며(AC3 — 행에서 '비활성' 라벨), 각 행에 신선 ``remaining_slots``를 싣는다.
    ``created_at`` keyset 페이징(``CursorPage`` 봉투). ``limit``(기본 20·최대 100)·``cursor``는 쿼리,
    손상 커서는 422. 미인증은 401. 즐겨찾기가 없으면 ``items=[]``·``next_cursor=None``(정상 200).
    """
    items, next_cursor = service.list_favorites_page(
        session, principal.user_id, limit=limit, cursor=cursor
    )
    return CursorPage(items=items, next_cursor=next_cursor)


@router.delete(
    "/{room_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse}},
)
def remove_favorite(
    room_id: uuid.UUID,
    principal: AuthPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> Response:
    """즐겨찾기에서 룸을 제거한다 → 204(로그인 필요·멱등, AC1·AC5).

    없는 행을 제거해도 204(멱등 — 토글 견고성). 미인증은 401.
    """
    service.remove_favorite(session, principal.user_id, room_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
