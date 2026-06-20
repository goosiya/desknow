"""favorites 도메인 서비스: 즐겨찾기 추가/제거/조회 (Story 3.7, AC1·AC2·AC3).

**토글 멱등성(견고성):** ``add_favorite``는 중복 add 시 기존 행을 반환하고, ``remove_favorite``는
없는 행 delete 시에도 에러 없이 통과한다 — 옵티미스틱 토글(프론트)이 네트워크 재시도·중복
클릭에도 일관되게 수렴하도록 DB 멱등성으로 받친다(``uq_favorites_user_id_room_id``가 근거).

**도메인 경계(architecture.md L354):** favorites는 자기 ``Favorite`` 테이블만 직접 쓴다. 룸 슬롯
집계는 rooms 도메인의 ``room_remaining_slots``를 **호출**하고(슬롯 SQL/로직 재구현 금지),
``Room`` 메타(이름·가격·is_active)는 PK ``session.get``으로 읽는다(읽기 전용 참조).

**에러:** 신규 ErrorCode 0 — 미존재 룸 추가는 기존 ``ROOM_NOT_FOUND``(404), 미인증은 라우터
의존성(``get_current_principal``)이 ``UNAUTHENTICATED``(401)로 막는다.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.core.db import violated_constraint
from app.core.errors import DomainError, ErrorCode
from app.core.pagination import keyset_page, keyset_predicate
from app.core.time import now_utc
from app.favorites.models import Favorite
from app.favorites.schemas import FavoriteRoomItem
from app.rooms.models import Room
from app.rooms.service import room_remaining_slots


def add_favorite(session: Session, user_id: uuid.UUID, room_id: uuid.UUID) -> Favorite:
    """사용자의 즐겨찾기에 룸을 추가한다(멱등 — 토글의 '추가' 방향, AC1).

    ① 룸 존재 확인(없으면 404 ``ROOM_NOT_FOUND``). ② ``Favorite`` add+commit. ③ 경합/중복으로
    ``uq_favorites_user_id_room_id``가 위반되면(이미 즐겨찾기) rollback 후 **기존 행을 조회 반환**
    (멱등) — ``create_room``의 ``violated_constraint`` 선별 변환 패턴. 무관한 제약 위반은
    오변환 없이 그대로 re-raise(과대캐치 금지, 회고 P2).
    """
    room = session.get(Room, room_id)
    if room is None:
        raise DomainError(
            ErrorCode.ROOM_NOT_FOUND, "해당 공간을 찾을 수 없습니다."
        )  # 404

    favorite = Favorite(user_id=user_id, room_id=room_id)
    session.add(favorite)
    try:
        session.commit()
    except IntegrityError as exc:  # 경합·중복: 이미 즐겨찾기된 (user, room)
        session.rollback()
        if violated_constraint(exc) == "uq_favorites_user_id_room_id":
            existing = session.exec(
                select(Favorite).where(
                    Favorite.user_id == user_id, Favorite.room_id == room_id
                )
            ).first()
            if existing is not None:
                return existing  # 멱등 — 기존 행 반환
        raise  # 무관한 제약 위반은 그대로 전파(P2)
    session.refresh(favorite)
    return favorite


def remove_favorite(
    session: Session, user_id: uuid.UUID, room_id: uuid.UUID
) -> None:
    """사용자의 즐겨찾기에서 룸을 제거한다(멱등 — 없는 행 delete도 무에러, AC1).

    행이 없어도 에러 없이 통과한다(토글 견고성). 동일 (user, room)은 uq로 1행이지만,
    방어적으로 매칭되는 모든 행을 삭제한다.
    """
    rows = session.exec(
        select(Favorite).where(
            Favorite.user_id == user_id, Favorite.room_id == room_id
        )
    ).all()
    for row in rows:
        session.delete(row)
    session.commit()  # 행이 없으면 no-op commit(멱등)


def build_favorite_item(
    session: Session, favorite: Favorite, *, now: datetime | None = None
) -> FavoriteRoomItem:
    """``Favorite`` 한 건을 룸 메타 + 신선 잔여 슬롯 + 활성여부 응답 항목으로 만든다(AC2·AC3).

    룸 메타(이름·가격·룸형태·부대시설·is_active)는 PK ``session.get``으로 읽고, 슬롯은 rooms
    도메인의 ``room_remaining_slots``로 신선 집계한다. **비활성 룸은 슬롯 0**(AC3 — 표시는
    '비활성' 라벨이 우선하며, 비활성 룸에 예약 가능 배지를 띄우지 않는다). ``favorited_at``은
    ``favorite.created_at``(추가 시각)을 별칭으로 노출한다(목록 최근순 정렬용).
    """
    current = now if now is not None else now_utc()
    room = session.get(Room, favorite.room_id)
    if room is None:
        # FK(ondelete RESTRICT) 보장상 즐겨찾기가 가리키는 룸은 항상 존재한다(룸 하드삭제 없음).
        # 도달 불가지만 타입 안전·방어를 위해 404로 막는다.
        raise DomainError(ErrorCode.ROOM_NOT_FOUND, "해당 공간을 찾을 수 없습니다.")
    # 비활성 룸은 슬롯 0(AC3) — 활성 룸만 신선 집계한다.
    remaining = room_remaining_slots(session, room, now=current) if room.is_active else 0
    return FavoriteRoomItem(
        room_id=room.id,
        name=room.name,
        price_per_hour=room.price_per_hour,
        room_type=room.room_type,
        amenities=list(room.amenities),
        remaining_slots=remaining,
        is_active=room.is_active,
        favorited_at=favorite.created_at,
    )


def list_favorites(
    session: Session, user_id: uuid.UUID, *, now: datetime | None = None
) -> list[FavoriteRoomItem]:
    """사용자의 즐겨찾기 목록을 최근 추가순으로 반환한다(읽기 전용, AC2·AC3).

    favorites ⨝ rooms를 ``created_at`` 내림차순(최근 추가 먼저)으로 구성한다. **비활성 룸도
    포함**한다(AC3 — ``is_active`` 필터 금지, 행에서 '비활성' 라벨로 안내). 각 행의 신선
    ``remaining_slots``는 ``build_favorite_item``이 rooms 도메인 집계로 채운다. 즐겨찾기가 없으면
    ``[]``(정상 200).
    """
    current = now if now is not None else now_utc()
    favorites = session.exec(
        select(Favorite)
        .where(Favorite.user_id == user_id)
        .order_by(col(Favorite.created_at).desc())  # 최근 추가 먼저
    ).all()
    return [build_favorite_item(session, fav, now=current) for fav in favorites]


def list_favorites_page(
    session: Session,
    user_id: uuid.UUID,
    *,
    limit: int,
    cursor: str | None = None,
    now: datetime | None = None,
) -> tuple[list[FavoriteRoomItem], str | None]:
    """``list_favorites``의 **커서 페이징판**(F — 즐겨찾기 무한스크롤).

    ``Favorite`` 행을 ``(created_at, id)`` keyset(정렬 ``created_at desc, id desc``)으로 한
    페이지 조회하고, 각 행을 ``build_favorite_item``으로 신선 합성한다(슬롯 집계는 페이지 행만 —
    전체 합성보다 가볍다). 다음 토큰은 **Favorite 행**의 ``(created_at, id)``로 만든다
    (``FavoriteRoomItem``엔 id가 없어 행에서 직접 뽑는다 — keyset_page에 행 리스트를 넘긴 뒤 items로
    매핑). 손상 커서는 422.

    Args:
        session: DB 세션(**읽기 전용**).
        user_id: 조회 대상 사용자(``users.id`` = 인증 principal).
        limit: 한 페이지 크기(라우터가 검증).
        cursor: 이전 페이지의 ``next_cursor``(없으면 첫 페이지).
        now: 기준 현재시각(테스트 결정성). 미지정 시 ``now_utc()``.

    Returns:
        ``(이번 페이지 FavoriteRoomItem 리스트, next_cursor)`` — 마지막이면 next_cursor=``None``.
    """
    current = now if now is not None else now_utc()
    predicate = keyset_predicate(col(Favorite.created_at), col(Favorite.id), cursor)
    statement = select(Favorite).where(Favorite.user_id == user_id)
    if predicate is not None:
        statement = statement.where(predicate)
    statement = statement.order_by(
        col(Favorite.created_at).desc(), col(Favorite.id).desc()
    ).limit(limit + 1)
    rows = list(session.exec(statement).all())
    # next_cursor는 **Favorite 행**의 (created_at, id) 기준(item에는 id가 없음) → keyset_page에 행을
    # 넘겨 페이지 경계·토큰을 계산한 뒤, 잘린 페이지 행만 item으로 합성한다.
    page_rows, next_cursor = keyset_page(
        rows, limit, created=lambda r: r.created_at, ident=lambda r: r.id
    )
    items = [build_favorite_item(session, fav, now=current) for fav in page_rows]
    return items, next_cursor
