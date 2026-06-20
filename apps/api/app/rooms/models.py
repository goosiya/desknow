"""rooms 도메인 ORM 모델: ``Room`` · ``BusinessHours`` · ``HolidayException`` (Story 2.1).

스터디룸(공간)과 그 **요일별 영업시간**·**휴무 예외 날짜**를 정의한다. 이 세 테이블이
슬롯 도출(``app.rooms.service.derive_slots``)의 입력 원천이다 — 슬롯은 물리 테이블이
아니라 (영업시간 − 휴무 − 예약)으로 **도출**된다(architecture.md §Cross-Component L360-362).

**규약(아키텍처 §Naming Patterns L228-241 / §Data-Architecture L141-153):**

- **테이블 복수 snake_case**(``rooms``·``business_hours``·``holiday_exceptions``).
  단순 제약(PK/FK/INDEX/단일 UNIQUE)은 1.4 ``NAMING_CONVENTION``(``app/core/db.py:28``)이
  자동 부여한다. **복합 제약(2~N컬럼 UNIQUE·CHECK)은 명시 단축명**을 부여한다(아래 정책).
- **시각/날짜의 두 종류를 엄격히 구분한다(핵심):**
  - ``business_hours.open_time``/``close_time`` = **로컬 벽시계 시각**(KST 09:00 등),
    타임존 없는 ``sa.Time``. ``holiday_date`` = **ROOM_TZ 기준 날짜**, ``sa.Date``.
  - 도출된 ``slot_start``(service.py)만이 **UTC 인스턴트**(tz-aware datetime)다.
    벽시계→UTC 변환은 슬롯 도출이 담당한다(09:00 KST = 00:00 UTC, −9h).
  - ``created_at`` = ``*_at`` 규약상 UTC ``timestamptz``(1.7/1.8과 동일, ``now_utc``).
- **``room_type``은 ``role``(1.7)과 동일하게 자유 문자열로 저장**한다. ``RoomType`` enum은
  코드 측 참조값일 뿐이며, DB CHECK·Pydantic ``Literal`` 검증은 쓰기 경로가 생기는
  Story 2.2로 명시 편성됐다(deferred 회수 라우팅 P3). ``amenities``는 다중선택+"기타"라
  코드값 리스트를 JSONB 배열로 저장한다.

**복합 제약 명시 단축명 의무 정책 (Epic 1 회고 P1 — 출처 1.4 defer):**
PostgreSQL 식별자는 **63바이트** 한계가 있다. 네이밍 규약이 자동 생성하는 이름이 길어지면
조용히 절단되어 ① autogenerate가 모델↔DB 제약명 불일치를 매번 감지하거나 ② 서로 다른
제약이 같은 절단명으로 충돌할 수 있다. 따라서 **3~4컬럼 복합 UNIQUE/CHECK 제약은 반드시
``name=`` 명시 단축명을 부여**하고, 그 길이가 ≤63임을 테스트로 회귀 검증한다
(``tests/rooms/test_models.py``). 단일 컬럼 제약은 규약 자동 생성으로 충분하다.

스키마는 Alembic이 단독 소유한다(``SQLModel.metadata.create_all`` 금지 — 1.4 규약).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.core.time import now_utc


class RoomType(StrEnum):
    """스터디룸 형태(코드 측 참조값). ``room_type`` 컬럼은 ``role``(1.7)과 동일하게
    자유 문자열로 저장하며, 값 검증(Pydantic ``Literal``·DB CHECK)은 쓰기 경로가
    생기는 Story 2.2에서 ``role``과 함께 회수한다(P3)."""

    OPEN = "open"  # 오픈형(공용)
    PRIVATE = "private"  # 프라이빗(독립)


class Room(SQLModel, table=True):
    """스터디룸(공간). 제공자(provider)가 등록하는 예약 가능한 단위.

    ``provider_id`` FK는 완전한 데이터 모델을 위해 **지금 정의**한다(나중에 NOT NULL FK를
    ALTER로 추가하는 부담 회피). 단 MVP "제공자당 1개"(``UNIQUE(provider_id)``)는 Story 2.2의
    비즈니스 규칙이라 여기서 추가하지 않는다. ``provider_id``는 **ondelete 미지정**
    (NO ACTION/RESTRICT) — 룸은 종속 폐기 데이터가 아니다(룸 삭제 없음, 운영중단=계정 비활성 E8).

    제약명은 1.4 규약 자동: PK ``pk_rooms``, FK ``fk_rooms_provider_id_users``,
    INDEX ``idx_rooms_provider_id``.

    **쓰기 경로(Story 2.2)가 추가한 ``__table_args__``:**

    - **``uq_rooms_provider_id``**(복합 아닌 단일 컬럼이나 비즈니스 규칙이라 명시 UNIQUE):
      MVP "제공자당 1개" 제약(AC4)을 DB에서 최종 강제한다. 서비스 선검사(친절한 409
      ``ROOM_LIMIT_REACHED``)와 이중 방어 — 경합 시 ``IntegrityError``를 제약명 식별 후
      선별 변환한다(P2). uq 규약은 명시 ``name``을 그대로 최종명으로 쓴다.
    - **값 범위 CHECK 5종**(P3 동반 회수 — 2.1 code-review defer): ``room_type`` enum,
      ``price_per_hour >= 0``, ``capacity >= 1``, ``lat``/``lng`` 좌표 범위. 1차 차단은
      Pydantic ``Literal``/``Field`` 범위(``schemas.py``), 최종 강제는 DB CHECK
      (시드·비-API 쓰기 경로 대비 defense-in-depth). ck 규약이 ``ck_%(table)s_%(name)s``로
      접두하므로 ``name``엔 **접미사만** 준다(2.1 이중접두 함정 — ``business_hours`` 선례).
      → 최종명: ``ck_rooms_room_type`` 등.
    """

    __tablename__ = "rooms"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    provider_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            # 룸은 폐기 종속 데이터가 아니므로 CASCADE 아님(ondelete 미지정 = RESTRICT/NO ACTION).
            ForeignKey("users.id"),
            nullable=False,
            index=True,  # idx_rooms_provider_id — 제공자별 룸 조회
        ),
    )
    name: str = Field(max_length=200)
    price_per_hour: int  # 시간당 금액(원, 정수)
    capacity: int  # 수용 인원
    room_type: str  # RoomType 값(자유 문자열 저장 — 검증은 Pydantic Literal + DB CHECK, 2.2)
    # 다중선택 부대시설 코드 리스트("기타" 포함). JSONB 배열. list 타입은 명시 sa_column 필요.
    amenities: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    lat: float  # 위도(좌표 저장 — 반경 검색 E3)
    lng: float  # 경도
    admin_dong_code: str = Field(max_length=20)  # 지역 코드(콤보 목록 E3, 좌표와 이중 저장)
    # 표시용 주소(지도 검색 결과의 address_name). idea.md L36 provider 스터디룸 설정 항목 —
    # provider 웹 표면 구축으로 저장/노출한다(이전엔 요청만 받고 미저장이었음). 선택(nullable).
    address: str | None = Field(default=None, max_length=300)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=now_utc,  # core/time 단일 출처(datetime.now() 직접 호출 금지)
        sa_column=Column(DateTime(timezone=True), nullable=False),  # *_at = UTC timestamptz
    )

    __table_args__ = (
        # 제공자당 1개(AC4) — uq 규약은 명시 name을 그대로 최종명으로 사용한다.
        UniqueConstraint("provider_id", name="uq_rooms_provider_id"),
        # 값 범위 CHECK(P3 + 2.1 defer 회수). ck 규약이 접두하므로 name엔 접미사만.
        # → ck_rooms_room_type / ck_rooms_price_per_hour_nonneg / ck_rooms_capacity_positive /
        #   ck_rooms_lat_range / ck_rooms_lng_range.
        CheckConstraint("room_type IN ('open', 'private')", name="room_type"),
        CheckConstraint("price_per_hour >= 0", name="price_per_hour_nonneg"),
        CheckConstraint("capacity >= 1", name="capacity_positive"),
        CheckConstraint("lat >= -90 AND lat <= 90", name="lat_range"),
        CheckConstraint("lng >= -180 AND lng <= 180", name="lng_range"),
    )


class BusinessHours(SQLModel, table=True):
    """룸의 **요일별 영업시간**(같은 날 내 시작/종료 — 자정 넘김 없음).

    ``open_time``/``close_time``은 **로컬 벽시계 시각**(``sa.Time``, tz 없음 = ROOM_TZ 기준).
    슬롯 도출이 (날짜 + 벽시계 time, KST) → UTC 변환을 담당한다. ``weekday``는 월=0~일=6
    (Python ``date.weekday()`` 규약).

    ``__table_args__``의 복합 UNIQUE·CHECK는 **명시 단축명**(회고 P1 정책). CHECK 2종은
    AC2의 "weekday 0~6"·"같은 날 내(자정 넘김 없음)"를 **DB 레벨에서 강제**한다
    (``close_time > open_time``이면 자정 미교차). 2.2의 친절한 422 거부는 그 위 Pydantic
    레이어(defense-in-depth).
    """

    __tablename__ = "business_hours"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    room_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            ForeignKey("rooms.id", ondelete="CASCADE"),  # 룸 종속 데이터 → CASCADE
            nullable=False,
            index=True,  # idx_business_hours_room_id — 룸별 영업시간 조회
        ),
    )
    weekday: int  # 0=월 ... 6=일 (date.weekday() 규약)
    open_time: time = Field(sa_column=Column(Time, nullable=False))  # 벽시계(ROOM_TZ)
    close_time: time = Field(sa_column=Column(Time, nullable=False))  # 벽시계(ROOM_TZ)

    __table_args__ = (
        # 복합 UNIQUE(2컬럼) — 명시 단축명(회고 P1). 룸·요일당 영업시간 1행.
        # uq 규약은 %(column_0_N_name)s 기반이라 명시 name이 그대로 최종명이 된다.
        UniqueConstraint("room_id", "weekday", name="uq_business_hours_room_id_weekday"),
        # CHECK — 명시 단축명(회고 P1). weekday 범위 + 같은 날 내(자정 넘김 없음) 강제.
        # ck 규약은 ck_%(table_name)s_%(constraint_name)s 라, name에는 **접미사만** 준다
        # (전체명을 주면 ck_business_hours_ck_business_hours_weekday 식 이중접두가 됨).
        # → 최종명: ck_business_hours_weekday / ck_business_hours_hours_order.
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="weekday"),
        CheckConstraint("close_time > open_time", name="hours_order"),
    )


class HolidayException(SQLModel, table=True):
    """룸의 **휴무 예외 날짜**(ROOM_TZ 기준 날짜). 해당 날짜는 영업시간과 무관하게 슬롯 0.

    ``holiday_date``는 **ROOM_TZ 기준 날짜**(``sa.Date``, tz 없음). 슬롯 도출은
    ``target_date``가 이 집합에 있으면 ``[]``를 반환한다.

    ``__table_args__``의 복합 UNIQUE는 **명시 단축명**(회고 P1) — 룸·날짜당 1행(중복 휴무 차단).
    """

    __tablename__ = "holiday_exceptions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    room_id: uuid.UUID = Field(
        sa_column=Column(
            Uuid(),
            ForeignKey("rooms.id", ondelete="CASCADE"),  # 룸 종속 데이터 → CASCADE
            nullable=False,
            index=True,  # idx_holiday_exceptions_room_id
        ),
    )
    holiday_date: date = Field(sa_column=Column(Date, nullable=False))  # ROOM_TZ 기준 날짜

    __table_args__ = (
        # 복합 UNIQUE(2컬럼) — 명시 단축명(회고 P1). 룸·날짜당 휴무 1행.
        UniqueConstraint(
            "room_id", "holiday_date", name="uq_holiday_exceptions_room_id_holiday_date"
        ),
    )
