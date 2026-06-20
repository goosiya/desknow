"""reviews 요청/응답 스키마: Create·Public·ListItem (Story 5.5).

후기 작성 쓰기 경로의 본문 검증과 응답 직렬화를 분리한다(4.5 ``reservations/schemas.py`` 미러).
``reservation_id``는 **경로 파라미터**(``/reservations/{reservation_id}/reviews``)라 본문 스키마에
두지 않는다(reservations 선례).

**규약(아키텍처 §Format/Process L256-296):**

- **검증은 백엔드가 신뢰 경계**(L277). 별점 범위 밖·텍스트 0자/501자+는 모두 Pydantic 검증으로
  ``RequestValidationError``가 되며, 1.5 ``validation_exception_handler``가 **422 +
  ``{detail:{code:"VALIDATION_ERROR", message}}``** 로 단일화한다(AC2). → service의 ``ValueError``가
  500으로 새지 않게 **스키마에서 선차단**한다(반복 함정 #1).
- **와이어는 snake_case 유지**(L286). datetime은 ``isoformat_utc``로 ``...Z`` 직렬화한다(L263).
- **작성자 익명(KTH 결정 1):** ``ReviewListItem``(룸 상세 공개 노출)은 별점·텍스트·작성일만 싣고
  ``booker_id`` 등 작성자 식별 필드를 **포함하지 않는다**(users엔 email만 — 프라이버시 누수 방지).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.core.time import isoformat_utc
from app.reviews.models import (
    REVIEW_RATING_MAX,
    REVIEW_RATING_MIN,
    REVIEW_TEXT_MAX_LENGTH,
)


class ReviewCreateRequest(BaseModel):
    """후기 작성 요청(POST 본문) — 별점 1~5 + 텍스트 1~500자(AC1·AC2).

    별점 범위 밖·텍스트 길이 위반은 Pydantic이 **선차단**해 422로 되돌린다 — service가 별점/길이를
    재검증하다 ``ValueError``를 500으로 흘리지 않도록 라우터 도달 전에 막는다(반복 함정 #1).
    텍스트는 **필수**(KTH 결정 2 — 빈 후기 금지): ``min_length=1`` + 공백만 방어(strip 후 재검증).

    ``reservation_id``는 **경로 파라미터**(중첩 라우트)라 본문에 두지 않는다. ``booker_id``는 인증
    principal에서 도출하므로 본문에 없다(클라가 작성자를 지정할 수 없음 — RBAC).
    """

    rating: int = Field(ge=REVIEW_RATING_MIN, le=REVIEW_RATING_MAX)  # 1~5 정수(범위 밖=422)
    text: str = Field(min_length=1, max_length=REVIEW_TEXT_MAX_LENGTH)  # 필수 1~500자

    @field_validator("text")
    @classmethod
    def _strip_and_require_nonblank(cls, value: str) -> str:
        """텍스트 앞뒤 공백을 제거하고, 공백만 입력(strip 후 빈 문자열)을 422로 거부한다.

        ``min_length=1``은 원문 길이만 보므로 ``"   "``(공백 3칸)이 통과한다 — 빈 후기 금지(KTH
        결정 2)의 빈틈을 ``strip()`` 후 재검증으로 막는다. 정규화된(trim된) 텍스트를 저장한다.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("후기 내용을 입력해 주세요 (공백만으로는 작성할 수 없어요).")
        return stripped


class ReviewPublic(BaseModel):
    """후기 작성 성공 응답(생성된 후기 리소스, AC1).

    생성된 ``Review``의 식별·별점·텍스트·작성시각 + 귀속(room_id·reservation_id)을 싣는다.
    작성 주체 본인 응답이라 식별 필드를 노출해도 무방하나, 일관성을 위해 별점/텍스트/시각/귀속만
    싣는다(``booker_id`` 미노출). datetime은 ``...Z``(``isoformat_utc`` — reservations 선례).
    """

    id: uuid.UUID
    reservation_id: uuid.UUID
    room_id: uuid.UUID
    rating: int  # 1~5
    text: str
    created_at: datetime  # 작성 시각(...Z 직렬화)

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)


class ReviewReplyCreateRequest(BaseModel):
    """제공자 답글 작성 요청(POST 본문) — 텍스트 1~500자(Story 5.6 AC1·AC2).

    텍스트 길이/공백 위반은 Pydantic이 **선차단**해 422로 되돌린다 — service가 길이를 재검증하다
    ``ValueError``를 500으로 흘리지 않도록 라우터 도달 전에 막는다(반복 함정 #1 —
    ``ReviewCreateRequest`` 미러). ``review_id``는 **경로 파라미터**라 본문에 없다.
    ``provider_id``는 인증 principal에서 도출하므로 본문에 없다(클라가 작성자 지정 불가 — RBAC).
    """

    text: str = Field(min_length=1, max_length=REVIEW_TEXT_MAX_LENGTH)  # 필수 1~500자

    @field_validator("text")
    @classmethod
    def _strip_and_require_nonblank(cls, value: str) -> str:
        """텍스트 앞뒤 공백을 제거하고, 공백만 입력(strip 후 빈 문자열)을 422로 거부한다.

        ``min_length=1``은 원문 길이만 보므로 ``"   "``(공백)가 통과한다 — 빈 답글 금지의 빈틈을
        ``strip()`` 후 재검증으로 막는다(``ReviewCreateRequest`` 미러). 정규화된 텍스트를 저장한다.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("답글 내용을 입력해 주세요 (공백만으로는 작성할 수 없어요).")
        return stripped


class ReviewReplyPublic(BaseModel):
    """답글 작성 성공 응답(생성된 답글 리소스, Story 5.6 AC1).

    생성된 ``ReviewReply``의 식별·귀속(review_id)·텍스트·작성시각을 싣는다. provider 본인 응답이라
    식별 노출이 무방하나 일관성을 위해 ``provider_id``는 싣지 않는다. datetime ``...Z``.
    """

    id: uuid.UUID
    review_id: uuid.UUID
    text: str
    created_at: datetime  # 작성 시각(...Z 직렬화)

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)


class ReviewReplyView(BaseModel):
    """룸 상세 후기에 중첩되는 제공자 답글 공개 노출 — 텍스트·작성일 **only**(Story 5.6 AC5, 익명).

    ``GET /rooms/{room_id}/reviews`` 응답의 각 후기에 ``reply``로 중첩된다(공개·무인증). **제공자
    식별 필드를 포함하지 않는다**(KTH 결정 5 — users엔 email만, 공개 노출에 식별 누수 금지). FE
    라벨은 "제공자 답글" 고정. datetime ``...Z``.
    """

    text: str
    created_at: datetime  # 답글 작성 시각(...Z 직렬화)

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)


class ReviewListItem(BaseModel):
    """룸 상세 후기 한 행 — 별점·텍스트·작성일 + 선택적 제공자 답글(Story 5.5 AC4 · 5.6 AC5, 익명).

    ``GET /rooms/{room_id}/reviews``(공개·무인증) 응답 항목이다. **작성자 식별 필드를 포함하지
    않는다**(KTH 결정 1 — users엔 email만 있어 표시 이름 부재, 공개 룸 상세에 email 노출 =
    프라이버시 누수). ``id``는 React key·답글 연결용(작성자 식별 아님). 5.6: ``reply``는 후기에
    제공자 답글이 있으면 ``ReviewReplyView``(익명), 없으면 ``None``(기존 직렬화 불변).
    datetime ``...Z``.
    """

    id: uuid.UUID  # review_id(React key·답글 연결용 — 작성자 식별 아님)
    rating: int  # 1~5(별 시각화 + 숫자 텍스트 — a11y)
    text: str
    created_at: datetime  # 작성 시각(...Z 직렬화 — 최신순 정렬·표시)
    reply: ReviewReplyView | None = None  # 제공자 답글(있으면 중첩, 없으면 None — 5.6 AC5)

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)
