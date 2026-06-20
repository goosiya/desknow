"""reviews 도메인 서비스: 이용 완료 자격 판정·후기 생성·룸 목록·has_review 합성 (Story 5.5).

후기 도메인의 **데이터 계층 프리미티브**를 소유한다(라우터는 소유권 가드·조합만). reservations
도메인(4.x)의 서비스 패턴(원자 INSERT·제약명 선별 변환·now 주입 시간 판정)을 미러한다.

**도메인 경계(architecture.md L354 · 반복 함정 #3):** 이 모듈은 ``reviews`` 테이블만 **쓴다**.
이용 완료 판정에 필요한 ``Reservation``(status·slot_starts·room_id)은 **인자로 받는다**
(``reservations.models`` 타입 import는 허용 — service↔service 순환 금지). ``has_review`` 합성은
reservations.router(조합 계층)가 ``reservation_ids_with_review``를 호출하는 **단방향**이다
(reservations.router → reviews.service. 역방향 import 0 — list_reservations 룸 메타 합성 선례 동형).

**이용 완료 진실 경계(AC1 · [[availability-freshness-policy]]):** 후기 작성 자격은 작성 확정
시점에 서버가 재판정한다 — ``status == "confirmed"`` 그리고 ``max(slot_starts) + 1시간(슬롯
길이) < now_utc()``. 슬롯 길이 1h는 reservations 내재 규약(별도 duration 필드 없음 —
``derive_slots`` 1h 격자). 시간 판정은 ``app.core.time``(``now_utc`` 단일 진입점) 재사용.

**중복 차단(AC2 · 반복 함정 #2):** 예약당 1회는 ``uq_reviews_reservation``가 진실의 원천이다.
INSERT IntegrityError를 try/except + rollback → 409 ``REVIEW_ALREADY_EXISTS``로 변환한다(favorites
``add_favorite`` 선례). 무관한 제약 위반은 오변환 없이 re-raise(과대캐치 금지 — 회고 P2).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.core.db import violated_constraint
from app.core.errors import DomainError, ErrorCode
from app.core.pagination import keyset_page, keyset_predicate
from app.core.time import now_utc
from app.reservations.models import Reservation, ReservationStatus
from app.reviews.models import Review, ReviewReply

# 슬롯 길이(reservations 내재 규약 — derive_slots 1h 격자). 마지막 슬롯 시작 + 1h = 예약 종료 시각.
_SLOT_DURATION = timedelta(hours=1)

# 중복 후기 시 REVIEW_ALREADY_EXISTS로 변환할 제약명(다른 위반은 re-raise — P2 과대캐치 금지).
_RESERVATION_UNIQUE_CONSTRAINT = "uq_reviews_reservation"

# 중복 답글 시 REVIEW_REPLY_ALREADY_EXISTS로 변환할 제약명(다른 위반은 re-raise — P2, 5.6).
_REVIEW_REPLY_UNIQUE_CONSTRAINT = "uq_review_replies_review"


def _latest_slot_end(slot_starts: list[str]) -> datetime | None:
    """예약 슬롯 스냅샷(ISO ``...Z``)에서 **예약 종료 시각**(max 시작 + 1h, UTC aware)을 낸다.

    슬롯이 없거나(빈 리스트) 어느 항목이라도 파싱 실패/naive(손상)면 ``None``을 반환한다 — 손상이
    후기 작성/판정을 500으로 죽이지 않게 방어한다(reservations ``earliest_slot_start`` 안전 파서
    정신, 반복 함정 #4). ``Reservation.slot_starts``는 ``isoformat_utc``가 낸 ``...Z`` 문자열이라
    정상 경로에선 항상 tz-aware로 파싱된다.
    """
    if not slot_starts:
        return None
    latest: datetime | None = None
    for raw in slot_starts:
        try:
            # isoformat_utc는 ...Z를 내므로 fromisoformat용으로 +00:00로 환원해 tz-aware 파싱.
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None  # 손상 항목 — 판정 불가(방어적으로 미완료 취급)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None  # naive(손상) — 시각 비교 불가
        if latest is None or parsed > latest:
            latest = parsed
    return latest + _SLOT_DURATION if latest is not None else None


def is_reservation_completed(
    reservation: Reservation, *, now: datetime | None = None
) -> bool:
    """예약이 **이용 완료**(후기 작성 자격)인지 판정한다(AC1 — 서버 진실 경계).

    이용 완료 = ``status == "confirmed"`` **그리고** 마지막 슬롯 종료(``max(slot_starts) + 1h``)가
    현재시각 이전. 취소/거절(종료 상태)·미완료(아직 종료 전)·슬롯 0건/손상은 모두 ``False``.

    Args:
        reservation: 판정 대상 예약(소유권·존재 검증은 라우터가 선차단).
        now: 현재시각(테스트 결정성 — ``core/time`` now 주입 철학). 미지정 시 ``now_utc()``.

    Returns:
        후기 작성 자격이 있으면 ``True``, 아니면 ``False``.
    """
    if reservation.status != ReservationStatus.CONFIRMED:
        return False  # 취소/거절 = 자격 없음(상태 위반)
    end = _latest_slot_end(list(reservation.slot_starts))
    if end is None:
        return False  # 슬롯 0건/손상 = 판정 불가(미완료 취급)
    current = now if now is not None else now_utc()
    return end < current  # 마지막 슬롯 종료가 지났으면 이용 완료


def create_review(
    session: Session,
    *,
    reservation: Reservation,
    booker_id: uuid.UUID,
    rating: int,
    text: str,
    now: datetime | None = None,
) -> Review:
    """이용 완료 예약에 후기 1건을 생성한다(자격 게이트 → INSERT → 중복 변환, AC1·AC2).

    ① 자격 게이트: ``is_reservation_completed``가 아니면(취소/거절/미완료/슬롯손상) 409
    ``RESERVATION_NOT_COMPLETED``. ② INSERT: ``Review``(room_id=예약의 룸) add+commit. ③ 경합/중복
    으로 ``uq_reviews_reservation`` 위반(이미 작성) → rollback 후 409 ``REVIEW_ALREADY_EXISTS``로
    변환(favorites ``add_favorite`` 선례). 무관한 위반은 오변환 없이 re-raise(과대캐치 금지, P2).

    별점 범위·텍스트 길이는 ``ReviewCreateRequest``가 선차단(422)하므로 여기선 재검증하지 않는다
    (service ValueError 500 누출 방지 — 반복 함정 #1). DB CHECK(``ck_reviews_rating``)가 백스톱.

    Args:
        session: DB 세션.
        reservation: 후기 대상 예약(소유권 검증·룸 도출 원천 — 라우터가 선조회·소유권 가드).
        booker_id: 작성자(``users.id`` = 인증 principal, == reservation.booker_id).
        rating: 별점(1~5 — 스키마 선검증).
        text: 후기 텍스트(1~500자·trim됨 — 스키마 선검증).
        now: 현재시각(테스트 결정성). 미지정 시 ``now_utc()``.

    Returns:
        생성된 ``Review``(``refresh`` 완료).

    Raises:
        DomainError: 이용 완료 전/불가 → 409 ``RESERVATION_NOT_COMPLETED``. 이미 작성됨 → 409
            ``REVIEW_ALREADY_EXISTS``.
    """
    # ① 자격 게이트 — 취소/거절/미완료/슬롯손상은 후기 작성 불가(서버 권위 최종 강제, AC2).
    if not is_reservation_completed(reservation, now=now):
        raise DomainError(
            ErrorCode.RESERVATION_NOT_COMPLETED,
            "이용 완료된 예약만 후기를 쓸 수 있어요.",
        )  # 409

    # ② INSERT — room_id는 예약에서 도출(경로에 room_id 불요 — 예약이 룸을 안다).
    review = Review(
        reservation_id=reservation.id,
        room_id=reservation.room_id,
        booker_id=booker_id,
        rating=rating,
        text=text,
    )
    session.add(review)
    try:
        session.commit()
    except IntegrityError as exc:  # 경합·중복: 이미 후기 작성된 예약
        session.rollback()
        if violated_constraint(exc) == _RESERVATION_UNIQUE_CONSTRAINT:
            raise DomainError(
                ErrorCode.REVIEW_ALREADY_EXISTS,
                "이미 후기를 작성한 예약이에요.",
            ) from exc  # 409
        raise  # 무관한 제약 위반(FK 등)은 오변환 금지 — 그대로 전파(P2)
    session.refresh(review)
    return review


def list_room_reviews(session: Session, room_id: uuid.UUID) -> list[Review]:
    """한 룸의 후기를 최신순(``created_at`` 내림차순)으로 반환한다(읽기 전용, AC4).

    룸 미존재/비활성 여부는 판정하지 않는다 — 라우터/호출처가 정책을 정한다(빈 목록 또는 404).
    후기가 없으면 ``[]``(정상 빈 목록 — 막다른 화면 금지는 FE가 빈 상태 카피로 처리).
    ``idx_reviews_room_id`` 백킹.

    Args:
        session: DB 세션(**읽기 전용** — ``commit``/``add``/``delete`` 호출 0).
        room_id: 조회 대상 룸(``rooms.id``).

    Returns:
        룸 후기 리스트(``created_at`` desc). 없으면 ``[]``.
    """
    statement = (
        select(Review)
        .where(col(Review.room_id) == room_id)
        .order_by(col(Review.created_at).desc())  # 최신 먼저
    )
    return list(session.exec(statement).all())


def list_room_reviews_page(
    session: Session,
    room_id: uuid.UUID,
    *,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[Review], str | None]:
    """``list_room_reviews``의 **커서 페이징판**(F — 룸 상세 후기 무한스크롤).

    한 룸의 후기를 ``(created_at, id)`` keyset(정렬 ``created_at desc, id desc``)으로 한 페이지
    조회한다. 답글 배치 합성(``replies_by_review_ids``)·``ReviewListItem`` 매핑은 호출처(라우터)가
    페이지 행에 대해 수행한다(전체판과 동일 조합 책임). 손상 커서는 422.

    Args:
        session: DB 세션(**읽기 전용**).
        room_id: 조회 대상 룸(``rooms.id``).
        limit: 한 페이지 크기(라우터가 검증).
        cursor: 이전 페이지의 ``next_cursor``(없으면 첫 페이지).

    Returns:
        ``(이번 페이지 Review 리스트, next_cursor)`` — 마지막 페이지면 next_cursor=``None``.
    """
    predicate = keyset_predicate(col(Review.created_at), col(Review.id), cursor)
    statement = select(Review).where(col(Review.room_id) == room_id)
    if predicate is not None:
        statement = statement.where(predicate)
    statement = statement.order_by(
        col(Review.created_at).desc(), col(Review.id).desc()
    ).limit(limit + 1)
    rows = list(session.exec(statement).all())
    return keyset_page(
        rows, limit, created=lambda r: r.created_at, ident=lambda r: r.id
    )


def create_reply(
    session: Session,
    *,
    review: Review,
    provider_id: uuid.UUID,
    text: str,
    now: datetime | None = None,
) -> ReviewReply:
    """후기 1건에 제공자 답글을 생성한다(INSERT → 중복 변환, Story 5.6 AC1·AC3).

    ① INSERT: ``ReviewReply``(review_id=후기, provider_id=작성자) add+commit. ② 경합/중복으로
    ``uq_review_replies_review`` 위반(이미 답글) → rollback 후 409 ``REVIEW_REPLY_ALREADY_EXISTS``로
    변환(``create_review``의 UNIQUE→409 선례 미러). 무관한 위반은 오변환 없이 re-raise(과대캐치
    금지, P2).

    **자격·소유권은 라우터가 선차단한다**(service는 검증된 ``review`` 객체를 받는다 — 도메인 경계:
    소유권 판정용 ``Room`` 조회는 라우터(조합 계층)가 하고 service는 ``Room``을 만지지 않는다, 반복
    함정 #3). 텍스트 길이/공백은 ``ReviewReplyCreateRequest``가 선차단(422)하므로 여기선 재검증하지
    않는다(service ValueError 500 누출 방지 — 반복 함정 #1).

    Args:
        session: DB 세션.
        review: 답글 대상 후기(존재·소유권 검증은 라우터가 선조회·선차단).
        provider_id: 답글 작성자(``users.id`` = 인증 principal = 룸 provider).
        text: 답글 텍스트(1~500자·trim됨 — 스키마 선검증).
        now: 작성 시각(테스트 결정성 — 미지정 시 모델 ``default_factory=now_utc``).

    Returns:
        생성된 ``ReviewReply``(``refresh`` 완료).

    Raises:
        DomainError: 이미 답글이 달린 후기 → 409 ``REVIEW_REPLY_ALREADY_EXISTS``.
    """
    # review_id=review.id로 INSERT(답글은 후기에 종속 — room_id 불요). created_at은 now 주입 시
    # 그 값을, 아니면 모델 default_factory(now_utc)를 쓴다(create_review가 now를 자격 판정에만
    # 쓰는 것과 달리, 답글엔 자격 게이트가 없어 now는 작성 시각 결정성에만 쓰인다).
    reply = ReviewReply(review_id=review.id, provider_id=provider_id, text=text)
    if now is not None:
        reply.created_at = now
    session.add(reply)
    try:
        session.commit()
    except IntegrityError as exc:  # 경합·중복: 이미 답글이 달린 후기
        session.rollback()
        if violated_constraint(exc) == _REVIEW_REPLY_UNIQUE_CONSTRAINT:
            raise DomainError(
                ErrorCode.REVIEW_REPLY_ALREADY_EXISTS,
                "이미 답글을 작성한 후기예요.",
            ) from exc  # 409
        raise  # 무관한 제약 위반(FK 등)은 오변환 금지 — 그대로 전파(P2)
    session.refresh(reply)
    return reply


def replies_by_review_ids(
    session: Session, review_ids: set[uuid.UUID]
) -> dict[uuid.UUID, ReviewReply]:
    """주어진 후기 id 집합의 답글을 **단일 쿼리**로 조회해 ``{review_id: ReviewReply}`` 맵을 낸다.

    룸 상세 후기 목록(``GET /rooms/{id}/reviews``)에 답글을 합성할 때 N+1을 막는 배치 조회다
    (``reservation_ids_with_review`` 배치 정신 미러). 후기당 답글은 ``uq_review_replies_review``로
    최대 1건이라 맵 값은 단일 ``ReviewReply``. 답글 없는 후기는 맵에서 빠진다(합성 측이 None 처리).

    Args:
        session: DB 세션(**읽기 전용**).
        review_ids: 답글을 조회할 후기 id 집합. 빈 집합이면 빈 맵(쿼리 미발행).

    Returns:
        ``{review_id: ReviewReply}``. 답글이 있는 후기만 키로 포함. 없으면 빈 맵.
    """
    if not review_ids:
        return {}  # 빈 입력 — 불필요한 IN () 쿼리 회피
    statement = select(ReviewReply).where(col(ReviewReply.review_id).in_(review_ids))
    return {reply.review_id: reply for reply in session.exec(statement).all()}


def reviews_by_booker(
    session: Session, booker_id: uuid.UUID
) -> dict[uuid.UUID, Review]:
    """예약자 본인이 작성한 후기를 ``{reservation_id: Review}`` 맵으로 반환한다(읽기 전용).

    예약현황(``GET /reservations``)에서 본인이 쓴 후기 **내용(별점·텍스트·작성일)** + 사장님 답글을
    함께 보여주기 위한 단일 조회다(``reservation_ids_with_review``의 풍부판 — 존재 여부뿐 아니라
    실체를 돌려준다). 예약당 후기는 ``uq_reviews_reservation``으로 최대 1건이라 맵 값은 단일
    ``Review``. 답글은 호출처(라우터)가 ``replies_by_review_ids``로 배치 합성한다(N+1 금지).
    본인 후기라 익명 제약 무관(공개 ``list_room_reviews``의 작성자 비노출과 다른 표면).

    Args:
        session: DB 세션(**읽기 전용**).
        booker_id: 조회 대상 예약자(``users.id`` = 인증 principal).

    Returns:
        ``{reservation_id: Review}``. 작성한 후기가 없으면 빈 맵.
    """
    statement = select(Review).where(col(Review.booker_id) == booker_id)
    return {review.reservation_id: review for review in session.exec(statement).all()}


def reservation_ids_with_review(
    session: Session, booker_id: uuid.UUID
) -> set[uuid.UUID]:
    """예약자 본인 예약 중 **후기가 존재하는** reservation_id 집합을 반환한다(읽기 전용, AC5).

    예약현황(``GET /reservations``)의 ``has_review`` 합성용 — reservations.router가 이 **단일
    쿼리**(N+1 금지)로 집합을 구해 각 항목 ``has_review = reservation.id in ids``를 합성한다.
    reviews.service → reservations 역import 0(라우터=조합 계층 단방향, 반복 함정 #3).

    Args:
        session: DB 세션(**읽기 전용**).
        booker_id: 조회 대상 예약자(``users.id`` = 인증 principal).

    Returns:
        후기가 존재하는 예약 id 집합. 없으면 빈 집합.
    """
    statement = select(Review.reservation_id).where(
        col(Review.booker_id) == booker_id
    )
    return set(session.exec(statement).all())
