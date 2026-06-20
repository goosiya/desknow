"""reviews 서비스 단위 테스트 (Story 5.5 — AC1·AC2 자격 판정·생성·중복 변환).

DB 불필요 — **Fake 세션**으로 이용 완료 자격 판정(``is_reservation_completed`` 경계)과
``create_review``의 게이트·중복 변환을 실증한다(4.1 ``FakeSession`` 패턴 미러). 라이브 DB 왕복
(실 UNIQUE·CHECK)은 라이브 마이그레이션 + 통합 경로가 담당한다.

**결정성:** 고정 ISO ``...Z`` slot_starts + ``now`` 주입(reservations 먼 미래/과거 날짜 패턴).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import DomainError, ErrorCode
from app.reservations.models import Reservation, ReservationStatus
from app.reviews.models import Review, ReviewReply
from app.reviews.service import (
    create_reply,
    create_review,
    is_reservation_completed,
    replies_by_review_ids,
    reservation_ids_with_review,
)


class _FakeOrig:
    """psycopg ``exc.orig``(``diag.constraint_name``) 모사 — 제약명 선별 변환 검증용."""

    def __init__(self, constraint_name: str | None) -> None:
        self.diag = type("Diag", (), {"constraint_name": constraint_name})()


def _integrity_error(constraint_name: str | None) -> IntegrityError:
    """``violated_constraint``가 읽는 ``orig.diag.constraint_name``을 단 실제 IntegrityError 대역.

    service의 ``except IntegrityError``가 실제 타입으로만 잡으므로(반복 함정 방어), reservations
    test_router 선례대로 실제 ``IntegrityError(stmt, params, orig)``를 구성한다.
    """
    return IntegrityError("stmt", {}, _FakeOrig(constraint_name))  # type: ignore[arg-type]


class FakeSession:
    """add/commit/refresh/rollback 호출을 기록하고 commit 시 선택적으로 IntegrityError를 던진다.

    ``create_review``의 INSERT 성공/중복 변환/롤백 분기를 라이브 DB 없이 실증한다(reservations
    create 테스트 패턴). ``exec``는 ``reservation_ids_with_review``의 ``.all()`` 경로만 모사한다.
    """

    def __init__(
        self,
        *,
        commit_error: IntegrityError | None = None,
        exec_rows: list[Any] | None = None,
    ) -> None:
        self.commit_error = commit_error
        self.exec_rows = exec_rows or []
        self.added: list[Any] = []
        self.committed = False
        self.refreshed = 0
        self.rolled_back = False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True

    def refresh(self, obj: Any) -> None:
        self.refreshed += 1

    def rollback(self) -> None:
        self.rolled_back = True

    def exec(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        return type("R", (), {"all": lambda self_: list(self.exec_rows)})()  # type: ignore[misc]


def _reservation(
    *,
    status: ReservationStatus,
    slot_starts: list[str],
    booker_id: uuid.UUID | None = None,
    room_id: uuid.UUID | None = None,
) -> Reservation:
    return Reservation(
        id=uuid.uuid4(),
        booker_id=booker_id or uuid.uuid4(),
        room_id=room_id or uuid.uuid4(),
        status=status,
        slot_starts=slot_starts,
    )


# 고정 시각 — 슬롯 종료(05:00 시작 +1h = 06:00 UTC) 경계 판정 결정성.
_AFTER_END = datetime(2026, 6, 17, 7, 0, tzinfo=UTC)  # 06:00 종료 이후 → 이용 완료
_BEFORE_END = datetime(2026, 6, 17, 5, 30, tzinfo=UTC)  # 06:00 종료 이전 → 미완료


# ── is_reservation_completed 경계 (AC1) ───────────────────────────────────────
def test_completed_confirmed_after_last_slot_end() -> None:
    """confirmed + 마지막 슬롯 종료(max+1h) 경과 → True(이용 완료)."""
    res = _reservation(
        status=ReservationStatus.CONFIRMED, slot_starts=["2026-06-17T05:00:00Z"]
    )
    assert is_reservation_completed(res, now=_AFTER_END) is True


def test_not_completed_before_last_slot_end() -> None:
    """confirmed지만 종료 전(종료 30분 전) → False(아직 미완료)."""
    res = _reservation(
        status=ReservationStatus.CONFIRMED, slot_starts=["2026-06-17T05:00:00Z"]
    )
    assert is_reservation_completed(res, now=_BEFORE_END) is False


def test_multi_slot_uses_latest_slot_end() -> None:
    """다중 슬롯은 **가장 늦은** 슬롯 종료(max+1h)로 판정한다(05·06시작 → 07:00 종료)."""
    res = _reservation(
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2026-06-17T05:00:00Z", "2026-06-17T06:00:00Z"],
    )
    # 06:00 시작 슬롯의 종료=07:00. now=07:00은 종료 '이전'이 아니므로(end < now False) 미완료.
    assert is_reservation_completed(res, now=datetime(2026, 6, 17, 7, 0, tzinfo=UTC)) is False
    # 07:01이면 마지막 슬롯도 종료 경과 → 이용 완료.
    assert is_reservation_completed(res, now=datetime(2026, 6, 17, 7, 1, tzinfo=UTC)) is True


@pytest.mark.parametrize(
    "status", [ReservationStatus.CANCELLED, ReservationStatus.REJECTED]
)
def test_terminal_status_never_completed(status: ReservationStatus) -> None:
    """취소/거절(종료 상태)은 시각 무관 항상 False(자격 없음)."""
    res = _reservation(status=status, slot_starts=["2026-06-17T05:00:00Z"])
    assert is_reservation_completed(res, now=_AFTER_END) is False


def test_empty_slot_starts_not_completed() -> None:
    """슬롯 스냅샷 0건 → False(판정 불가·미완료 취급, 손상 방어)."""
    res = _reservation(status=ReservationStatus.CONFIRMED, slot_starts=[])
    assert is_reservation_completed(res, now=_AFTER_END) is False


# ── create_review (AC1·AC2) ──────────────────────────────────────────────────
def test_create_review_success() -> None:
    """이용 완료 예약 → Review INSERT·commit·예약의 room_id 도출."""
    booker_id = uuid.uuid4()
    room_id = uuid.uuid4()
    res = _reservation(
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2026-06-17T05:00:00Z"],
        booker_id=booker_id,
        room_id=room_id,
    )
    session = FakeSession()
    review = create_review(
        session, reservation=res, booker_id=booker_id, rating=4, text="좋아요", now=_AFTER_END
    )
    assert session.committed is True
    assert session.refreshed == 1
    assert isinstance(review, Review)
    assert review.rating == 4
    assert review.text == "좋아요"
    assert review.room_id == room_id  # 예약에서 도출
    assert review.reservation_id == res.id


def test_create_review_not_completed_raises_409() -> None:
    """미완료(종료 전) 예약 작성 → 409 RESERVATION_NOT_COMPLETED·INSERT 미진입."""
    booker_id = uuid.uuid4()
    res = _reservation(
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2026-06-17T05:00:00Z"],
        booker_id=booker_id,
    )
    session = FakeSession()
    with pytest.raises(DomainError) as exc:
        create_review(
            session, reservation=res, booker_id=booker_id, rating=5, text="음", now=_BEFORE_END
        )
    assert exc.value.code == ErrorCode.RESERVATION_NOT_COMPLETED
    assert exc.value.status_code == 409
    assert session.added == []  # 자격 게이트에서 차단 — INSERT 미진입
    assert session.committed is False


@pytest.mark.parametrize(
    "status", [ReservationStatus.CANCELLED, ReservationStatus.REJECTED]
)
def test_create_review_terminal_status_raises_409(status: ReservationStatus) -> None:
    """취소/거절 예약 작성 → 409 RESERVATION_NOT_COMPLETED(자격 없음)."""
    booker_id = uuid.uuid4()
    res = _reservation(
        status=status, slot_starts=["2026-06-17T05:00:00Z"], booker_id=booker_id
    )
    session = FakeSession()
    with pytest.raises(DomainError) as exc:
        create_review(
            session, reservation=res, booker_id=booker_id, rating=5, text="음", now=_AFTER_END
        )
    assert exc.value.code == ErrorCode.RESERVATION_NOT_COMPLETED


def test_create_review_duplicate_raises_409() -> None:
    """UNIQUE(uq_reviews_reservation) 위반 → 409 REVIEW_ALREADY_EXISTS·rollback(중복 후기)."""
    booker_id = uuid.uuid4()
    res = _reservation(
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2026-06-17T05:00:00Z"],
        booker_id=booker_id,
    )
    session = FakeSession(
        commit_error=_integrity_error("uq_reviews_reservation")
    )
    with pytest.raises(DomainError) as exc:
        create_review(
            session, reservation=res, booker_id=booker_id, rating=5, text="좋음", now=_AFTER_END
        )
    assert exc.value.code == ErrorCode.REVIEW_ALREADY_EXISTS
    assert exc.value.status_code == 409
    assert session.rolled_back is True


def test_create_review_unrelated_integrity_error_reraised() -> None:
    """무관한 제약 위반(FK 등)은 오변환 없이 그대로 전파한다(P2 과대캐치 금지)."""
    booker_id = uuid.uuid4()
    res = _reservation(
        status=ReservationStatus.CONFIRMED,
        slot_starts=["2026-06-17T05:00:00Z"],
        booker_id=booker_id,
    )
    session = FakeSession(
        commit_error=_integrity_error("fk_reviews_room_id_rooms")
    )
    with pytest.raises(IntegrityError):  # DomainError 아님 — 원본 전파
        create_review(
            session, reservation=res, booker_id=booker_id, rating=5, text="좋음", now=_AFTER_END
        )
    assert session.rolled_back is True


def test_reservation_ids_with_review_returns_set() -> None:
    """본인 예약 중 후기 존재하는 reservation_id 집합을 반환한다(has_review 합성용)."""
    rid1, rid2 = uuid.uuid4(), uuid.uuid4()
    session = FakeSession(exec_rows=[rid1, rid2])
    result = reservation_ids_with_review(session, uuid.uuid4())
    assert result == {rid1, rid2}


# ── create_reply (5.6 AC1·AC3) ───────────────────────────────────────────────
def _review(*, room_id: uuid.UUID | None = None) -> Review:
    return Review(
        id=uuid.uuid4(),
        reservation_id=uuid.uuid4(),
        room_id=room_id or uuid.uuid4(),
        booker_id=uuid.uuid4(),
        rating=4,
        text="좋아요",
    )


def test_create_reply_success() -> None:
    """후기에 답글 → ReviewReply INSERT·commit·refresh·review_id 귀속·now 주입."""
    provider_id = uuid.uuid4()
    review = _review()
    session = FakeSession()
    reply = create_reply(
        session, review=review, provider_id=provider_id, text="감사합니다", now=_AFTER_END
    )
    assert session.committed is True
    assert session.refreshed == 1
    assert isinstance(reply, ReviewReply)
    assert reply.review_id == review.id  # 후기에 종속(room_id 불요)
    assert reply.provider_id == provider_id
    assert reply.text == "감사합니다"
    assert reply.created_at == _AFTER_END  # now 주입(결정성)


def test_create_reply_duplicate_raises_409() -> None:
    """UNIQUE(uq_review_replies_review) 위반 → 409 REVIEW_REPLY_ALREADY_EXISTS·rollback."""
    review = _review()
    session = FakeSession(
        commit_error=_integrity_error("uq_review_replies_review")
    )
    with pytest.raises(DomainError) as exc:
        create_reply(session, review=review, provider_id=uuid.uuid4(), text="중복")
    assert exc.value.code == ErrorCode.REVIEW_REPLY_ALREADY_EXISTS
    assert exc.value.status_code == 409
    assert session.rolled_back is True


def test_create_reply_unrelated_integrity_error_reraised() -> None:
    """무관한 제약 위반(FK 등)은 오변환 없이 그대로 전파한다(P2 과대캐치 금지)."""
    review = _review()
    session = FakeSession(
        commit_error=_integrity_error("fk_review_replies_provider_id_users")
    )
    with pytest.raises(IntegrityError):  # DomainError 아님 — 원본 전파
        create_reply(session, review=review, provider_id=uuid.uuid4(), text="음")
    assert session.rolled_back is True


def test_replies_by_review_ids_batch_maps_only_present() -> None:
    """주어진 후기 id 집합 중 답글 있는 것만 {review_id: ReviewReply} 맵에 담는다(배치·N+1 금지)."""
    rid_with = uuid.uuid4()
    reply = ReviewReply(
        id=uuid.uuid4(), review_id=rid_with, provider_id=uuid.uuid4(), text="답글"
    )
    # 답글 있는 후기(rid_with) + 답글 없는 후기(rid_without) 혼재 — 쿼리는 있는 것만 반환.
    session = FakeSession(exec_rows=[reply])
    result = replies_by_review_ids(session, {rid_with, uuid.uuid4()})
    assert set(result) == {rid_with}  # 답글 없는 후기는 맵에서 빠짐
    assert result[rid_with] is reply


def test_replies_by_review_ids_empty_input_returns_empty() -> None:
    """빈 후기 id 집합 → 빈 맵(쿼리 미발행)."""
    session = FakeSession(exec_rows=[])
    assert replies_by_review_ids(session, set()) == {}
