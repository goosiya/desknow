"""reviews 라우터 통합 테스트 (Story 5.5 — AC1·AC2·AC3·AC4 + RBAC·소유권·익명).

**DB 불필요** — ``app.dependency_overrides[get_session]``로 세션을 Fake로 교체하고,
``TestClient(app)``(모듈 레벨, lifespan 미실행 — 1.4 불변식)로 엔드포인트를 검증한다(reservations
``test_router.py`` 패턴 미러).

**이용 완료 결정성:** 라우터는 ``create_review``를 ``now`` 주입 없이 호출하므로(실 ``now_utc()``)
슬롯 시각으로 자격 경계를 고정한다 — **먼 과거**(2020) = 항상 이용 완료, **먼 미래**(2099) = 항상
미완료(종료 전).
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.db import get_session
from app.core.security import create_access_token
from app.main import app
from app.reservations.models import Reservation, ReservationStatus
from app.reviews.models import Review, ReviewReply
from app.rooms.models import Room
from tests.core.keyset_fake import apply_keyset

client = TestClient(app)

_REVIEW_PUBLIC_KEYS = {"id", "reservation_id", "room_id", "rating", "text", "created_at"}
_REVIEW_LIST_KEYS = {"id", "rating", "text", "created_at", "reply"}
_REPLY_PUBLIC_KEYS = {"id", "review_id", "text", "created_at"}
_REPLY_VIEW_KEYS = {"text", "created_at"}

# 자격 경계 고정용 슬롯 스냅샷(...Z). 과거=이용 완료, 미래=미완료(reservations 먼 날짜 패턴).
_PAST_SLOT = ["2020-01-05T05:00:00Z"]
_FUTURE_SLOT = ["2099-01-05T05:00:00Z"]


class _FakeOrig:
    """psycopg ``exc.orig``(``diag.constraint_name``) 모사 — UNIQUE 위반 선별 변환 검증용."""

    def __init__(self, constraint_name: str | None) -> None:
        self.diag = type("Diag", (), {"constraint_name": constraint_name})()


class FakeReviewSession:
    """reviews 라우터용 Fake 세션 — ``get``(소유권) + add/commit(작성) + exec(목록·답글 배치).

    ``stored``/``review``/``room``으로 ``get`` 소유권·존재 분기를(예약 후기 작성=Reservation, 답글
    작성=Review+Room), ``raise_on_commit``으로 중복(UNIQUE→409) 변환을, ``reviews``/``replies``로
    공개 목록·답글 배치 조회를 제어한다(``exec``는 select 엔티티로 후기/답글을 구분).
    """

    def __init__(
        self,
        *,
        stored: Reservation | None = None,
        review: Review | None = None,
        room: Room | None = None,
        reviews: list[Review] | None = None,
        replies: list[ReviewReply] | None = None,
        raise_on_commit: bool = False,
        commit_violation: str | None = None,
    ) -> None:
        self.stored = stored
        self.review = review
        self.room = room
        self.reviews = reviews or []
        self.replies = replies or []
        self.raise_on_commit = raise_on_commit
        self.commit_violation = commit_violation
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False
        self.refreshed = 0

    def get(self, model: Any, pk: Any) -> Any:
        # 타입+id로 매칭 — 예약(create_review)·후기/룸(create_reply) get 경로를 모두 모사한다.
        for obj in (self.stored, self.review, self.room):
            if obj is not None and type(obj) is model and obj.id == pk:
                return obj
        return None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        if self.raise_on_commit:
            raise IntegrityError("stmt", {}, _FakeOrig(self.commit_violation))  # type: ignore[arg-type]
        self.committed = True

    def refresh(self, obj: Any) -> None:
        self.refreshed += 1

    def rollback(self) -> None:
        self.rolled_back = True

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        # select 엔티티로 후기 목록(Review) vs 답글 배치(ReviewReply)를 구분한다.
        descriptions = getattr(statement, "column_descriptions", None)
        entity = descriptions[0]["entity"] if descriptions else None
        rows: list[Any] = self.replies if entity is ReviewReply else self.reviews
        # 페이징 select(limit 있음 = list_room_reviews_page)는 실제 DB와 동일하게 keyset 정렬·커서
        # 필터·절단한다(F 무한스크롤). 답글 배치(IN·limit 없음) 경로는 무가공.
        if entity is Review and getattr(statement, "_limit", None) is not None:
            rows = apply_keyset(statement, rows)
        return type("R", (), {"all": lambda self_: list(rows)})()  # type: ignore[misc]


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


def _reservation(
    *,
    booker_id: uuid.UUID,
    room_id: uuid.UUID | None = None,
    status: ReservationStatus = ReservationStatus.CONFIRMED,
    slot_starts: list[str] | None = None,
) -> Reservation:
    return Reservation(
        id=uuid.uuid4(),
        booker_id=booker_id,
        room_id=room_id or uuid.uuid4(),
        status=status,
        slot_starts=slot_starts if slot_starts is not None else _PAST_SLOT,
    )


def _room(*, provider_id: uuid.UUID, is_active: bool = True) -> Room:
    return Room(
        id=uuid.uuid4(),
        provider_id=provider_id,
        name="테스트룸",
        price_per_hour=10000,
        capacity=4,
        room_type="open",
        amenities=[],
        lat=37.5,
        lng=127.0,
        admin_dong_code="1111010100",
        is_active=is_active,
    )


def _review_row(
    *, room_id: uuid.UUID, rating: int = 4, text: str = "좋아요"
) -> Review:
    return Review(
        id=uuid.uuid4(),
        reservation_id=uuid.uuid4(),
        room_id=room_id,
        booker_id=uuid.uuid4(),
        rating=rating,
        text=text,
    )


def _post_url(reservation_id: Any) -> str:
    return f"/api/v1/reservations/{reservation_id}/reviews"


def _list_url(room_id: Any) -> str:
    return f"/api/v1/rooms/{room_id}/reviews"


def _reply_url(review_id: Any) -> str:
    return f"/api/v1/reviews/{review_id}/reply"


# ── 작성 성공 (AC1) ──────────────────────────────────────────────────────────
def test_create_review_booker_returns_201(auth_env: None) -> None:
    """booker 본인 이용 완료 예약 → 201 + ReviewPublic(별점·텍스트·작성일 ...Z)."""
    booker_id = uuid.uuid4()
    room_id = uuid.uuid4()
    reservation = _reservation(booker_id=booker_id, room_id=room_id)
    session = FakeReviewSession(stored=reservation)
    with _override_session(session):
        resp = client.post(
            _post_url(reservation.id),
            json={"rating": 4, "text": "조용하고 좋았어요"},
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == _REVIEW_PUBLIC_KEYS
    assert body["rating"] == 4
    assert body["text"] == "조용하고 좋았어요"
    assert body["room_id"] == str(room_id)  # 예약에서 도출
    assert body["created_at"].endswith("Z")
    assert session.committed is True


def test_create_review_strips_whitespace(auth_env: None) -> None:
    """텍스트 앞뒤 공백은 trim되어 저장된다(스키마 정규화)."""
    booker_id = uuid.uuid4()
    reservation = _reservation(booker_id=booker_id)
    session = FakeReviewSession(stored=reservation)
    with _override_session(session):
        resp = client.post(
            _post_url(reservation.id),
            json={"rating": 5, "text": "  좋아요  "},
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["text"] == "좋아요"


# ── 자격 거부 (AC2) ──────────────────────────────────────────────────────────
def test_create_review_not_completed_returns_409(auth_env: None) -> None:
    """미완료(미래 슬롯) 예약 → 409 RESERVATION_NOT_COMPLETED."""
    booker_id = uuid.uuid4()
    reservation = _reservation(booker_id=booker_id, slot_starts=_FUTURE_SLOT)
    session = FakeReviewSession(stored=reservation)
    with _override_session(session):
        resp = client.post(
            _post_url(reservation.id),
            json={"rating": 4, "text": "좋아요"},
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "RESERVATION_NOT_COMPLETED"
    assert session.committed is False


def test_create_review_cancelled_returns_409(auth_env: None) -> None:
    """취소된 예약(과거여도) → 409 RESERVATION_NOT_COMPLETED(상태 위반)."""
    booker_id = uuid.uuid4()
    reservation = _reservation(
        booker_id=booker_id, status=ReservationStatus.CANCELLED, slot_starts=_PAST_SLOT
    )
    session = FakeReviewSession(stored=reservation)
    with _override_session(session):
        resp = client.post(
            _post_url(reservation.id),
            json={"rating": 4, "text": "좋아요"},
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "RESERVATION_NOT_COMPLETED"


def test_create_review_duplicate_returns_409(auth_env: None) -> None:
    """이미 후기 작성된 예약(UNIQUE 위반) → 409 REVIEW_ALREADY_EXISTS·rollback."""
    booker_id = uuid.uuid4()
    reservation = _reservation(booker_id=booker_id)
    session = FakeReviewSession(
        stored=reservation,
        raise_on_commit=True,
        commit_violation="uq_reviews_reservation",
    )
    with _override_session(session):
        resp = client.post(
            _post_url(reservation.id),
            json={"rating": 4, "text": "좋아요"},
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "REVIEW_ALREADY_EXISTS"
    assert session.rolled_back is True


# ── 소유권 (AC3) ─────────────────────────────────────────────────────────────
def test_create_review_other_owner_returns_404(auth_env: None) -> None:
    """타인 예약 작성 시도 → 404 RESERVATION_NOT_FOUND(403 아님 — 존재 누설 금지)."""
    reservation = _reservation(booker_id=uuid.uuid4())  # 소유자는 다른 사람
    session = FakeReviewSession(stored=reservation)
    with _override_session(session):
        resp = client.post(
            _post_url(reservation.id),
            json={"rating": 4, "text": "좋아요"},
            headers={"Authorization": f"Bearer {create_access_token(uuid.uuid4(), 'booker')}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RESERVATION_NOT_FOUND"
    assert session.committed is False


def test_create_review_unknown_reservation_returns_404(auth_env: None) -> None:
    """미존재 예약 id → 404 RESERVATION_NOT_FOUND."""
    session = FakeReviewSession(stored=None)  # get → None
    with _override_session(session):
        resp = client.post(
            _post_url(uuid.uuid4()),
            json={"rating": 4, "text": "좋아요"},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RESERVATION_NOT_FOUND"


# ── RBAC (AC3) ───────────────────────────────────────────────────────────────
def test_create_review_provider_returns_403(auth_env: None) -> None:
    """provider 토큰 → 403 FORBIDDEN_ROLE(작성은 booker 전용)."""
    session = FakeReviewSession(stored=None)
    with _override_session(session):
        resp = client.post(
            _post_url(uuid.uuid4()),
            json={"rating": 4, "text": "좋아요"},
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_create_review_admin_returns_403(auth_env: None) -> None:
    """admin 토큰도 → 403(booker만 통과)."""
    session = FakeReviewSession(stored=None)
    with _override_session(session):
        resp = client.post(
            _post_url(uuid.uuid4()),
            json={"rating": 4, "text": "좋아요"},
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_create_review_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401 UNAUTHENTICATED."""
    session = FakeReviewSession(stored=None)
    with _override_session(session):
        resp = client.post(
            _post_url(uuid.uuid4()), json={"rating": 4, "text": "좋아요"}
        )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


# ── 입력 형식 422 (AC2 — 스키마 선차단) ───────────────────────────────────────
def test_create_review_rating_out_of_range_returns_422(auth_env: None) -> None:
    """별점 범위 밖(6) → 422 VALIDATION_ERROR(ge=1·le=5 선차단)."""
    booker_id = uuid.uuid4()
    reservation = _reservation(booker_id=booker_id)
    session = FakeReviewSession(stored=reservation)
    with _override_session(session):
        resp = client.post(
            _post_url(reservation.id),
            json={"rating": 6, "text": "좋아요"},
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_create_review_text_too_long_returns_422(auth_env: None) -> None:
    """텍스트 501자 → 422 VALIDATION_ERROR(max_length=500 선차단)."""
    booker_id = uuid.uuid4()
    reservation = _reservation(booker_id=booker_id)
    session = FakeReviewSession(stored=reservation)
    with _override_session(session):
        resp = client.post(
            _post_url(reservation.id),
            json={"rating": 4, "text": "가" * 501},
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_create_review_blank_text_returns_422(auth_env: None) -> None:
    """공백만 텍스트 → 422 VALIDATION_ERROR(strip 후 빈 문자열 거부 — 빈 후기 금지)."""
    booker_id = uuid.uuid4()
    reservation = _reservation(booker_id=booker_id)
    session = FakeReviewSession(stored=reservation)
    with _override_session(session):
        resp = client.post(
            _post_url(reservation.id),
            json={"rating": 4, "text": "   "},
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_create_review_empty_text_returns_422(auth_env: None) -> None:
    """빈 텍스트(0자) → 422 VALIDATION_ERROR(min_length=1)."""
    booker_id = uuid.uuid4()
    reservation = _reservation(booker_id=booker_id)
    session = FakeReviewSession(stored=reservation)
    with _override_session(session):
        resp = client.post(
            _post_url(reservation.id),
            json={"rating": 4, "text": ""},
            headers={"Authorization": f"Bearer {create_access_token(booker_id, 'booker')}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


# ── 공개 후기 목록 (AC4 — 무인증·익명) ────────────────────────────────────────
def _review(*, room_id: uuid.UUID, rating: int, text: str, created_at: datetime) -> Review:
    return Review(
        id=uuid.uuid4(),
        reservation_id=uuid.uuid4(),
        room_id=room_id,
        booker_id=uuid.uuid4(),
        rating=rating,
        text=text,
        created_at=created_at,
    )


def test_list_room_reviews_public_returns_anonymous(auth_env: None) -> None:
    """무인증 GET → 200 + ReviewListItem(별점·텍스트·작성일만 — 작성자 식별 필드 미노출, 익명)."""
    room_id = uuid.uuid4()
    review = _review(
        room_id=room_id,
        rating=5,
        text="최고예요",
        created_at=datetime(2026, 6, 17, 0, tzinfo=UTC),
    )
    session = FakeReviewSession(reviews=[review])
    with _override_session(session):
        resp = client.get(_list_url(room_id))  # 인증 헤더 없음
    assert resp.status_code == 200, resp.text
    body = resp.json()["items"]
    assert len(body) == 1
    item = body[0]
    assert set(item) == _REVIEW_LIST_KEYS  # booker_id·reservation_id·room_id 미노출(익명)
    assert "booker_id" not in item
    assert item["rating"] == 5
    assert item["text"] == "최고예요"
    assert item["created_at"].endswith("Z")


def test_list_room_reviews_empty_returns_200(auth_env: None) -> None:
    """후기 0건 → 빈 리스트(정상 200 — 막다른 화면 금지는 FE 빈 상태 카피)."""
    session = FakeReviewSession(reviews=[])
    with _override_session(session):
        resp = client.get(_list_url(uuid.uuid4()))
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["next_cursor"] is None


def test_list_room_reviews_synthesizes_reply(auth_env: None) -> None:
    """공개 GET — 답글 있는 후기=reply 채워짐(text·작성일 only·익명)·없는 후기=reply null(5.6)."""
    room_id = uuid.uuid4()
    with_reply = _review_row(room_id=room_id, text="좋아요")
    without_reply = _review_row(room_id=room_id, text="조용해요")
    reply = ReviewReply(
        id=uuid.uuid4(),
        review_id=with_reply.id,
        provider_id=uuid.uuid4(),
        text="감사합니다",
        created_at=datetime(2026, 6, 18, 0, tzinfo=UTC),
    )
    session = FakeReviewSession(reviews=[with_reply, without_reply], replies=[reply])
    with _override_session(session):
        resp = client.get(_list_url(room_id))  # 무인증
    assert resp.status_code == 200, resp.text
    body = {item["id"]: item for item in resp.json()["items"]}
    # 답글 있는 후기 — reply 중첩(text·작성일만, provider 식별 미노출=익명).
    replied = body[str(with_reply.id)]
    assert set(replied) == _REVIEW_LIST_KEYS
    assert replied["reply"] is not None
    assert set(replied["reply"]) == _REPLY_VIEW_KEYS  # provider_id·id 미노출
    assert replied["reply"]["text"] == "감사합니다"
    assert replied["reply"]["created_at"].endswith("Z")
    # 답글 없는 후기 — reply null.
    assert body[str(without_reply.id)]["reply"] is None


# ── 제공자 답글 작성 (5.6 AC1·AC2·AC3·AC4) ────────────────────────────────────
def test_create_reply_provider_owner_returns_201(auth_env: None) -> None:
    """provider 본인 룸 후기 → 201 + ReviewReplyPublic(review_id 귀속·작성일 ...Z·익명)."""
    provider_id = uuid.uuid4()
    room = _room(provider_id=provider_id)
    review = _review_row(room_id=room.id)
    session = FakeReviewSession(review=review, room=room)
    with _override_session(session):
        resp = client.post(
            _reply_url(review.id),
            json={"text": "이용해 주셔서 감사합니다"},
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == _REPLY_PUBLIC_KEYS
    assert body["review_id"] == str(review.id)
    assert body["text"] == "이용해 주셔서 감사합니다"
    assert body["created_at"].endswith("Z")
    assert "provider_id" not in body
    assert session.committed is True


def test_create_reply_strips_whitespace(auth_env: None) -> None:
    """답글 텍스트 앞뒤 공백은 trim되어 저장된다(스키마 정규화)."""
    provider_id = uuid.uuid4()
    room = _room(provider_id=provider_id)
    review = _review_row(room_id=room.id)
    session = FakeReviewSession(review=review, room=room)
    with _override_session(session):
        resp = client.post(
            _reply_url(review.id),
            json={"text": "  감사합니다  "},
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["text"] == "감사합니다"


def test_create_reply_inactive_own_room_allowed(auth_env: None) -> None:
    """비활성 룸이라도 본인 룸이면 답글 허용(자기 데이터 — is_active 게이트 없음, AC4)."""
    provider_id = uuid.uuid4()
    room = _room(provider_id=provider_id, is_active=False)
    review = _review_row(room_id=room.id)
    session = FakeReviewSession(review=review, room=room)
    with _override_session(session):
        resp = client.post(
            _reply_url(review.id),
            json={"text": "감사합니다"},
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 201, resp.text


def test_create_reply_unknown_review_returns_404(auth_env: None) -> None:
    """미존재 후기 id → 404 REVIEW_NOT_FOUND."""
    session = FakeReviewSession(review=None, room=None)  # get(Review) → None
    with _override_session(session):
        resp = client.post(
            _reply_url(uuid.uuid4()),
            json={"text": "감사합니다"},
            headers={"Authorization": f"Bearer {_provider_token()}"},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "REVIEW_NOT_FOUND"
    assert session.committed is False


def test_create_reply_other_provider_room_returns_403(auth_env: None) -> None:
    """타 제공자 룸 후기 답글 시도 → 403 REVIEW_REPLY_FORBIDDEN(소유권 차단 — 404 아님, AC2)."""
    owner_id = uuid.uuid4()
    room = _room(provider_id=owner_id)  # 소유자는 다른 제공자
    review = _review_row(room_id=room.id)
    session = FakeReviewSession(review=review, room=room)
    with _override_session(session):
        resp = client.post(
            _reply_url(review.id),
            json={"text": "감사합니다"},
            headers={"Authorization": f"Bearer {create_access_token(uuid.uuid4(), 'provider')}"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "REVIEW_REPLY_FORBIDDEN"
    assert session.committed is False


def test_create_reply_duplicate_returns_409(auth_env: None) -> None:
    """이미 답글 달린 후기(UNIQUE 위반) → 409 REVIEW_REPLY_ALREADY_EXISTS·rollback."""
    provider_id = uuid.uuid4()
    room = _room(provider_id=provider_id)
    review = _review_row(room_id=room.id)
    session = FakeReviewSession(
        review=review,
        room=room,
        raise_on_commit=True,
        commit_violation="uq_review_replies_review",
    )
    with _override_session(session):
        resp = client.post(
            _reply_url(review.id),
            json={"text": "감사합니다"},
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "REVIEW_REPLY_ALREADY_EXISTS"
    assert session.rolled_back is True


def test_create_reply_booker_returns_403(auth_env: None) -> None:
    """booker 토큰 → 403 FORBIDDEN_ROLE(답글은 provider 전용)."""
    session = FakeReviewSession()
    with _override_session(session):
        resp = client.post(
            _reply_url(uuid.uuid4()),
            json={"text": "감사합니다"},
            headers={"Authorization": f"Bearer {_booker_token()}"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_create_reply_admin_returns_403(auth_env: None) -> None:
    """admin 토큰도 → 403 FORBIDDEN_ROLE(provider만 통과)."""
    session = FakeReviewSession()
    with _override_session(session):
        resp = client.post(
            _reply_url(uuid.uuid4()),
            json={"text": "감사합니다"},
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORBIDDEN_ROLE"


def test_create_reply_no_token_returns_401(auth_env: None) -> None:
    """무토큰 → 401 UNAUTHENTICATED."""
    session = FakeReviewSession()
    with _override_session(session):
        resp = client.post(_reply_url(uuid.uuid4()), json={"text": "감사합니다"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_create_reply_empty_text_returns_422(auth_env: None) -> None:
    """빈 텍스트(0자) → 422 VALIDATION_ERROR(min_length=1 선차단)."""
    provider_id = uuid.uuid4()
    room = _room(provider_id=provider_id)
    review = _review_row(room_id=room.id)
    session = FakeReviewSession(review=review, room=room)
    with _override_session(session):
        resp = client.post(
            _reply_url(review.id),
            json={"text": ""},
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_create_reply_blank_text_returns_422(auth_env: None) -> None:
    """공백만 텍스트 → 422 VALIDATION_ERROR(strip 후 빈 문자열 거부)."""
    provider_id = uuid.uuid4()
    room = _room(provider_id=provider_id)
    review = _review_row(room_id=room.id)
    session = FakeReviewSession(review=review, room=room)
    with _override_session(session):
        resp = client.post(
            _reply_url(review.id),
            json={"text": "   "},
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_create_reply_text_too_long_returns_422(auth_env: None) -> None:
    """텍스트 501자 → 422 VALIDATION_ERROR(max_length=500 선차단)."""
    provider_id = uuid.uuid4()
    room = _room(provider_id=provider_id)
    review = _review_row(room_id=room.id)
    session = FakeReviewSession(review=review, room=room)
    with _override_session(session):
        resp = client.post(
            _reply_url(review.id),
            json={"text": "가" * 501},
            headers={"Authorization": f"Bearer {create_access_token(provider_id, 'provider')}"},
        )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"


# ═══════════════════════════════════════════════════════════════════════════════════
# 커서 페이징 (F — 룸 상세 후기 무한스크롤): keyset 페이지 경계·전수 일치·손상 커서 422
# ═══════════════════════════════════════════════════════════════════════════════════


def _seed_room_reviews(room_id: uuid.UUID, count: int) -> list[Review]:
    """한 룸의 후기 count건을 created_at 내림차순(최신=인덱스 0)으로 시드한다.

    created_at은 1시간 간격으로 분리해 keyset (created_at desc, id desc) 경계를 결정적으로 만든다.
    """
    base = datetime(2026, 6, 17, tzinfo=UTC)
    return [
        _review(
            room_id=room_id,
            rating=4,
            text=f"후기{i}",
            created_at=base - timedelta(hours=i),
        )
        for i in range(count)
    ]


def test_list_room_reviews_pagination_walks_all_pages(auth_env: None) -> None:
    """limit=2로 5건 페이징 → 첫 페이지 2건+next_cursor, 전 페이지 합집합이 전체와 순서까지 일치."""
    room_id = uuid.uuid4()
    seeded = _seed_room_reviews(room_id, 5)
    session = FakeReviewSession(reviews=list(seeded))

    def _get(cursor: str | None):
        params = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        with _override_session(session):
            return client.get(_list_url(room_id), params=params)  # 무인증(공개)

    first = _get(None).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    collected: list[dict] = []
    cursor: str | None = None
    while True:
        body = _get(cursor).json()
        collected.extend(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    ids = [item["id"] for item in collected]
    assert ids == [str(r.id) for r in seeded]  # created_at desc 전수 일치(순서 포함)
    assert len(ids) == len(set(ids)) == 5  # 중복 없음


def test_list_room_reviews_pagination_last_page_cursor_none(auth_env: None) -> None:
    """항목 수가 limit의 배수면 마지막 페이지에서도 next_cursor None."""
    room_id = uuid.uuid4()
    seeded = _seed_room_reviews(room_id, 4)  # limit=2 → 딱 2페이지
    session = FakeReviewSession(reviews=list(seeded))
    with _override_session(session):
        first = client.get(_list_url(room_id), params={"limit": 2}).json()
    assert first["next_cursor"] is not None
    with _override_session(session):
        second = client.get(
            _list_url(room_id), params={"limit": 2, "cursor": first["next_cursor"]}
        ).json()
    assert len(second["items"]) == 2
    assert second["next_cursor"] is None


def test_list_room_reviews_invalid_cursor_returns_422(auth_env: None) -> None:
    """손상 커서 → 422 VALIDATION_ERROR(조용한 1페이지 폴백 금지)."""
    session = FakeReviewSession(reviews=[])
    with _override_session(session):
        resp = client.get(_list_url(uuid.uuid4()), params={"cursor": "!!!invalid"})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"
