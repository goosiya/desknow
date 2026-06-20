"""reviews 도메인 ORM 모델: ``Review`` (Story 5.5).

이용 완료한 예약에 남기는 별점+텍스트 후기 1건을 정의한다. reservations 도메인(4.1)의
모델·제약명 규약을 **참조 선례로 미러**한다(명시 단축명·≤63자·CHECK/UNIQUE 패턴). 본 모듈은
``reviews`` 테이블만 정의하고, 자격 판정(이용 완료)·생성·목록 로직은 ``service.py``가 진다.

**핵심 불변식(FR-20):**

- **예약당 1회 = ``uq_reviews_reservation``**(``reservation_id`` UNIQUE). 중복 후기 차단의
  **진실의 원천**이다 — 서비스가 INSERT 시 IntegrityError를 잡아 409
  ``REVIEW_ALREADY_EXISTS``로 변환한다(favorites ``add_favorite`` 멱등 선례 미러).
- **별점 1~5 = ``ck_reviews_rating``**(DB CHECK). Pydantic ``Field(ge=1, le=5)``가 쓰기 경로에서
  선차단하고(422), DB CHECK가 최종 강제한다(defense-in-depth — reservations ``status`` CHECK 정신).

**규약(아키텍처 §Naming Patterns / §Data-Architecture · reservations/models.py 미러):**

- 단일 제약(PK/FK/INDEX)은 1.4 ``NAMING_CONVENTION``(``app/core/db.py:28``)이 자동 부여한다
  (PK ``pk_reviews``, FK ``fk_reviews_*``, INDEX ``idx_reviews_room_id``). 단일컬럼 UNIQUE·CHECK는
  reservations 선례대로 **명시 단축명**을 부여한다(63바이트 절단 회귀 방지 — 회고 P1):
  ``uq_reviews_reservation``(예약당 1회) · CHECK는 ``ck_%(table)s_%(name)s`` 규약이 접두하므로
  name엔 **접미사만**(``"rating"`` → ``ck_reviews_rating``, 이중접두 회피 — 2.1 함정).
- **FK ondelete:** ``reservation_id``·``room_id``·``booker_id`` 모두 **RESTRICT(미지정)** — 후기는
  보존 데이터이고(작성 후 불변·수정/삭제 미제공), 예약/룸/유저 하드삭제 경로가 없다(운영중단=
  is_active 비활성 E8). reservations의 ``booker_id``/``room_id`` RESTRICT 선례 따름.
- ``created_at`` = ``*_at`` 규약상 UTC ``timestamptz``(``core/time.now_utc`` 단일 출처).

**작성자 익명(KTH 결정 1):** ``booker_id``는 소유권 가드·has_review 합성용으로 보유하되, 룸 상세
공개 응답(``ReviewListItem``)엔 노출하지 않는다(users엔 email만 있어 표시 이름 부재 — 프라이버시).

스키마는 Alembic이 단독 소유한다(``SQLModel.metadata.create_all`` 금지 — 1.4 규약).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Uuid,
)
from sqlmodel import Field, SQLModel

from app.core.time import now_utc

# 후기 텍스트 최대 길이(FR-20 — 별점+텍스트 500자). Pydantic 스키마(선차단)와 DB VARCHAR(최종)
# 양쪽에 같은 상한을 둔다(defense-in-depth). 최소 1자(빈 후기 금지)는 스키마가 강제한다.
REVIEW_TEXT_MAX_LENGTH = 500

# 별점 범위(FR-20 — 1~5 정수). DB CHECK·Pydantic Field(ge/le) 단일 출처.
REVIEW_RATING_MIN = 1
REVIEW_RATING_MAX = 5


class Review(SQLModel, table=True):
    """후기 한 건(이용 완료 예약의 별점+텍스트 — 1행/예약, FR-20).

    제약명은 1.4 규약 자동: PK ``pk_reviews``, FK ``fk_reviews_reservation_id_reservations``(38자
    ≤63 ✓)·``fk_reviews_room_id_rooms``·``fk_reviews_booker_id_users``, INDEX
    ``idx_reviews_room_id``.
    단일컬럼 UNIQUE·CHECK만 명시 단축명 ``uq_reviews_reservation``·``ck_reviews_rating``(아래).

    ``reservation_id``·``room_id``·``booker_id``는 **ondelete 미지정(RESTRICT)** — 후기는 보존
    데이터이고 예약/룸/유저 하드삭제 경로가 없다. ``room_id``는 룸 상세 후기 목록 조회용으로
    ``index=True``(``idx_reviews_room_id``) + denormalized(예약 조인 없이 룸 후기 조회).
    """

    __tablename__ = "reviews"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    reservation_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # 예약은 하드삭제 안 함(취소=status flip) → ondelete 미지정(RESTRICT, 후기 보존).
            ForeignKey("reservations.id"),
            nullable=False,
            # UNIQUE는 __table_args__에서 명시 단축명으로(예약당 1회 — 중복 후기의 진실의 원천).
        ),
    )
    room_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # rooms 하드삭제 안 함 → ondelete 미지정(RESTRICT). denormalized(룸 상세 후기 조회).
            ForeignKey("rooms.id"),
            nullable=False,
            index=True,  # idx_reviews_room_id — 룸 상세 후기 목록(GET /rooms/{id}/reviews) 조회
        ),
    )
    booker_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # users 하드삭제 안 함(운영중단=is_active 비활성 E8) → ondelete 미지정(RESTRICT).
            ForeignKey("users.id"),
            nullable=False,
        ),
    )
    # 별점(1~5 정수). 값 검증은 DB CHECK(ck_reviews_rating) + 쓰기 경로 Pydantic Field(ge/le).
    rating: int = Field(nullable=False)
    # 후기 텍스트(필수 1~500자 — KTH 결정 2). max_length로 DB VARCHAR(500) 강제(defense-in-depth).
    # 최소 1자·공백만 입력 방어는 ReviewCreateRequest 스키마가 선차단한다(빈 후기 금지).
    text: str = Field(max_length=REVIEW_TEXT_MAX_LENGTH, nullable=False)
    created_at: datetime = Field(
        default_factory=now_utc,  # core/time 단일 출처(datetime.now() 직접 호출 금지)
        sa_column=Column(DateTime(timezone=True), nullable=False),  # *_at = UTC timestamptz
    )

    __table_args__ = (
        # 예약당 1회 — 단일컬럼 UNIQUE 명시 단축명(회고 P1). 중복 후기 차단의 진실의 원천(FR-20):
        # 서비스가 INSERT IntegrityError를 잡아 409 REVIEW_ALREADY_EXISTS로 변환한다.
        UniqueConstraint("reservation_id", name="uq_reviews_reservation"),
        # 별점 1~5 CHECK — 명시 단축명(회고 P1). ck 규약 ck_%(table)s_%(name)s가 접두하므로
        # name엔 **접미사만** 준다(2.1 이중접두 함정 — 전체명을 주면 ck_reviews_ck_reviews_rating).
        # → 최종명: ck_reviews_rating.
        CheckConstraint(
            f"rating >= {REVIEW_RATING_MIN} AND rating <= {REVIEW_RATING_MAX}",
            name="rating",
        ),
    )


class ReviewReply(SQLModel, table=True):
    """후기 1건에 대한 제공자 답글(1행/후기 — FR-21, Story 5.6).

    5.5가 깐 ``reviews`` 위에 "제공자 답글" 한 겹을 얹는다. 룸 provider가 자기 룸 후기에 답글 1건을
    달고, 룸 상세 후기 목록에 후기와 연결되어 익명("제공자 답글" 라벨)으로 노출된다.

    제약명은 1.4 규약 자동: PK ``pk_review_replies``, FK ``fk_review_replies_review_id_reviews``·
    ``fk_review_replies_provider_id_users``, 단일컬럼 UNIQUE만 명시 단축명
    ``uq_review_replies_review``(아래). **CHECK 없음**(별점 없음 — op.f() 이중접두 함정 비해당).

    **핵심 불변식(FR-21):**

    - **후기당 답글 1회 = ``uq_review_replies_review``**(``review_id`` UNIQUE). 중복 답글 차단의
      **진실의 원천**이다 — 서비스가 INSERT IntegrityError를 잡아 409
      ``REVIEW_REPLY_ALREADY_EXISTS``로 변환한다(``Review``의 ``uq_reviews_reservation`` 선례 미러).
    - **작성 후 불변**(수정/삭제 미제공 — reviews 불변 정책 일관).

    **FK ondelete:** ``review_id``·``provider_id`` 모두 **RESTRICT(미지정)** — 답글은 보존
    데이터이고 후기/유저 하드삭제 경로가 없다(``Review`` FK 정책 일관).

    **익명(KTH 결정 5):** ``provider_id``는 소유권 귀속용으로 보유하되, 룸 상세 공개 응답
    (``ReviewReplyView``)엔 노출하지 않는다(users엔 email만 — 5.5 작성자 익명 동일 근거).

    스키마는 Alembic이 단독 소유한다(``SQLModel.metadata.create_all`` 금지 — 1.4 규약).
    """

    __tablename__ = "review_replies"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    review_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # 후기는 하드삭제 안 함(불변) → ondelete 미지정(RESTRICT, 답글 보존).
            ForeignKey("reviews.id"),
            nullable=False,
            # UNIQUE는 __table_args__에서 명시 단축명으로(후기당 1회 — 중복 답글의 진실의 원천).
        ),
    )
    provider_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # users 하드삭제 안 함(운영중단=is_active 비활성 E8) → ondelete 미지정(RESTRICT).
            ForeignKey("users.id"),
            nullable=False,
        ),
    )
    # 답글 텍스트(필수 1~500자 — 후기 본문 상한 재사용). max_length로 DB VARCHAR(500) 강제
    # (defense-in-depth). 최소 1자·공백만 입력 방어는 ReviewReplyCreateRequest 스키마가 선차단한다.
    text: str = Field(max_length=REVIEW_TEXT_MAX_LENGTH, nullable=False)
    created_at: datetime = Field(
        default_factory=now_utc,  # core/time 단일 출처(datetime.now() 직접 호출 금지)
        sa_column=Column(DateTime(timezone=True), nullable=False),  # *_at = UTC timestamptz
    )

    __table_args__ = (
        # 후기당 1회 — 단일컬럼 UNIQUE 명시 단축명(회고 P1). 중복 답글 차단의 진실의 원천(FR-21):
        # 서비스가 INSERT IntegrityError를 잡아 409 REVIEW_REPLY_ALREADY_EXISTS로 변환한다.
        UniqueConstraint("review_id", name="uq_review_replies_review"),
    )
