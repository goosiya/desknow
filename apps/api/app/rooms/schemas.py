"""rooms 요청/응답 스키마: 공간 등록·주소 검색 (Story 2.2).

요청 검증(룸 형태·부대시설·영업시간·좌표/금액/인원 범위)과 응답 직렬화(``...Z`` 시각)를
분리한다. 1.7 ``auth/schemas.py`` 패턴을 미러한다.

**규약(아키텍처 §Format/Process L256-296):**

- **검증은 백엔드가 신뢰 경계**(L277). 형식·범위·enum 위반은 모두 Pydantic 검증으로
  ``RequestValidationError``가 되며, 1.5 ``validation_exception_handler``가 자동으로
  **422 + ``{detail:{code:"VALIDATION_ERROR", message}}``** 로 단일화한다(AC1·AC3).
  → 422용 별도 핸들러/에러코드를 작성하지 않는다.
- **enum은 Pydantic ``Literal``로 1차 차단**(1.7 ``role`` 패턴 = P3). 최종 강제는 DB CHECK.
- **와이어는 snake_case 유지**(L286, camelCase 변환 레이어 금지). ``created_at``은
  ``isoformat_utc``로 ``...Z`` 직렬화한다(L263).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.core.time import isoformat_utc

# ``RoomSlotsResponse.date`` 필드가 동명 타입을 가리므로(아래), 타입 참조용 별칭을 둔다.
_Date = date

# 부대시설 어휘(AC1: 주차·빔프로젝터/TV·커피머신·화이트보드·wifi·기타). 미지정 코드는 422.
AmenityCode = Literal["parking", "projector_tv", "coffee", "whiteboard", "wifi", "etc"]

# 룸 형태(AC1: 개방형/독립룸). RoomType enum과 동일 값 — Pydantic 1차 차단(P3).
RoomTypeLiteral = Literal["open", "private"]


class BusinessHoursInput(BaseModel):
    """요일별 영업시간 입력(같은 날 내 — 자정 넘김 거부, AC3).

    ``open_time``/``close_time``은 ROOM_TZ 벽시계 시각(``"HH:MM:SS"`` ↔ ``datetime.time``).
    ``close_time > open_time``을 강제해 자정 넘김(22:00~02:00)·역전을 422로 거부한다 —
    DB CHECK ``ck_business_hours_hours_order``의 친절한 상위 레이어(defense-in-depth, AC3).
    """

    weekday: int = Field(ge=0, le=6)  # 0=월 ... 6=일 (date.weekday() 규약)
    open_time: time
    close_time: time

    @model_validator(mode="after")
    def _enforce_same_day(self) -> BusinessHoursInput:
        """자정 넘김·역전 거부: close_time은 open_time보다 늦어야 한다(AC3)."""
        if self.close_time <= self.open_time:
            raise ValueError(
                "영업 종료 시각은 시작 시각보다 늦어야 합니다 "
                "(같은 날 내 — 자정을 넘기는 시간은 등록할 수 없습니다)."
            )
        return self


class RoomCreateRequest(BaseModel):
    """공간 등록 요청(provider 전용 쓰기, AC1).

    범위·enum 위반은 Pydantic 검증 → 1.5 핸들러가 422로 단일화(P3 1차 차단 + 2.1 defer 회수).
    좌표(``lat``/``lng``)·``admin_dong_code``는 클라이언트가 ``GET /rooms/geocode`` 결과에서
    선택해 실어 보낸다(MVP client-trusted — 인증된 provider + DB CHECK 방어, Dev Notes 참조).
    """

    name: str = Field(min_length=1, max_length=200)
    price_per_hour: int = Field(ge=0)  # 시간당 금액(원) — 음수 거부(2.1 defer 회수)
    capacity: int = Field(ge=1)  # 수용 인원 — 1 이상
    room_type: RoomTypeLiteral  # 개방형/독립룸(P3 1차 차단)
    amenities: list[AmenityCode] = Field(default_factory=list)  # 다중선택(미지정 코드 422)
    lat: float = Field(ge=-90, le=90)  # 위도 범위(2.1 defer 회수)
    lng: float = Field(ge=-180, le=180)  # 경도 범위
    admin_dong_code: str = Field(min_length=1, max_length=20)  # 지역 코드(b_code)
    business_hours: list[BusinessHoursInput] = Field(min_length=1)  # 최소 1행(없으면 슬롯 0)
    address: str | None = Field(default=None, max_length=300)  # 표시용 선택

    @model_validator(mode="after")
    def _dedupe_amenities(self) -> RoomCreateRequest:
        """부대시설 중복을 제거한다(순서 보존). 와이어에 중복이 와도 저장은 고유 집합."""
        seen: set[str] = set()
        deduped: list[AmenityCode] = []
        for code in self.amenities:
            if code not in seen:
                seen.add(code)
                deduped.append(code)
        self.amenities = deduped
        return self

    @model_validator(mode="after")
    def _reject_duplicate_weekday(self) -> RoomCreateRequest:
        """요일별 영업시간은 weekday당 1행만 허용한다(친절한 422 — code-review patch).

        DB ``uq_business_hours_room_id_weekday``(2.1)와 이중 방어다. 이 검증이 없으면
        같은 weekday 2행이 Pydantic을 통과해 ``create_room`` commit에서 UNIQUE 위반
        ``IntegrityError``가 되고, ``create_room``은 ``uq_rooms_provider_id``만 선별 변환하므로
        무관 위반으로 re-raise → 미처리 500이 된다(사용자 입력 오류가 500화). amenities와 달리
        조용한 dedupe가 아니라 명시 거부한다 — 서로 다른 영업시간을 가진 중복 weekday는
        사용자 의도가 모호하므로(어느 행을 살릴지) 422로 되돌려준다.
        """
        weekdays = [bh.weekday for bh in self.business_hours]
        if len(weekdays) != len(set(weekdays)):
            raise ValueError(
                "요일별 영업시간은 같은 요일을 중복해 등록할 수 없습니다 "
                "(weekday당 1행)."
            )
        return self


class RoomUpdateRequest(BaseModel):
    """공간 수정 요청(provider 전용 쓰기·부분 수정 PATCH 시맨틱, Story 2.3 AC1·AC5).

    **모든 필드가 Optional**(기본 ``None``)이며, ``RoomCreateRequest``와 **동일한 ``Field``
    제약**(범위·``Literal``·max_length)을 Optional 위에 그대로 부여한다. ``id``·``provider_id``·
    ``created_at``·``is_active``는 **수정 불가**라 요청 스키마에 포함하지 않는다
    (불변 필드·is_active=E8).

    **PATCH 시맨틱(핵심 함정):** 서비스가 ``model_dump(exclude_unset=True)``로 **요청에 실제로
    온 필드만** 골라 적용한다 — "필드 미제공"과 "명시적 null"을 구분한다. ``business_hours``가
    키 자체로 없으면 영업시간 **불변**, 키가 있으면 **전체 교체**(``update_room``). 따라서 검증기는
    "제공된 필드"에만 작동해야 한다 → ``amenities``/``business_hours``가 ``None``이면 건너뛴다
    (미제공 = 검증 대상 아님). PUT 시맨틱(미제공 필드를 None으로 덮어쓰기)으로 착각 금지.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    price_per_hour: int | None = Field(default=None, ge=0)  # 음수 거부
    capacity: int | None = Field(default=None, ge=1)  # 1 이상
    room_type: RoomTypeLiteral | None = None  # 개방형/독립룸(P3 1차 차단)
    amenities: list[AmenityCode] | None = None  # 다중선택(미지정 코드 422). None=미제공
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    admin_dong_code: str | None = Field(default=None, min_length=1, max_length=20)
    # None=영업시간 미제공(불변). 제공 시 min_length=1(빈 배열 거부 — 0행=휴무/비활성은 범위 밖).
    business_hours: list[BusinessHoursInput] | None = Field(default=None, min_length=1)
    address: str | None = Field(default=None, max_length=300)  # 표시용 선택

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> RoomUpdateRequest:
        """명시적 ``null`` 입력을 422로 거부한다(미처리 500 방지 — code-review patch).

        PATCH 시맨틱상 **필드 미제공 = 불변**이며, 어떤 필드도 ``null``을 정당한 값으로 받지
        않는다(리스트 비우기는 ``[]``, 스칼라 불변은 미제공으로 표현). 그러나 모든 필드가
        ``X | None``이라 명시적 ``null``이 Pydantic을 통과하고, ``model_dump(exclude_unset=True)``
        는 *미제공*만 제외하고 *명시 null*은 포함시키므로 ``update_room``의
        ``setattr(room, field, None)``에 도달한다 → NOT NULL 스칼라·JSONB ``amenities``는 commit
        ``IntegrityError``, ``business_hours``는 교체 분기 가드에서 각각 **미처리 500**이 된다
        (인증 provider의 입력 오류가 500화 — AC5 "검증 422 단일화" 위반). ``model_fields_set``으로
        **명시 제공된 필드 중 값이 ``None``인 것만** 골라 거부해(미제공은 통과 → 불변 유지),
        422 ``VALIDATION_ERROR``로 단일화한다. ``business_hours``/``amenities``의 None-스킵 검증기
        (아래)는 *미제공*(불변) 케이스를 위한 것으로 이 가드와 역할이 다르다.
        """
        null_fields = sorted(
            name for name in self.model_fields_set if getattr(self, name) is None
        )
        if null_fields:
            raise ValueError(
                "다음 필드는 null로 설정할 수 없습니다(미제공으로 두면 기존값이 유지됩니다): "
                f"{', '.join(null_fields)}."
            )
        return self

    @model_validator(mode="after")
    def _dedupe_amenities(self) -> RoomUpdateRequest:
        """부대시설 중복 제거(순서 보존). **미제공(None)이면 건너뛴다**(검증 대상 아님)."""
        if self.amenities is None:
            return self
        seen: set[str] = set()
        deduped: list[AmenityCode] = []
        for code in self.amenities:
            if code not in seen:
                seen.add(code)
                deduped.append(code)
        self.amenities = deduped
        return self

    @model_validator(mode="after")
    def _reject_duplicate_weekday(self) -> RoomUpdateRequest:
        """영업시간 제공 시 weekday당 1행만 허용한다(친절한 422). **미제공(None)이면 건너뛴다**.

        ``RoomCreateRequest._reject_duplicate_weekday``와 동일 의도 — DB
        ``uq_business_hours_room_id_weekday``(2.1)와 이중 방어다. 이 검증이 없으면 중복 weekday가
        ``update_room`` 영업시간 교체 commit에서 UNIQUE 위반이 되어 미처리 500이 된다(사용자
        입력 오류가 500화). 어느 행을 살릴지 모호하므로 dedupe 대신 명시 거부한다.
        """
        if self.business_hours is None:
            return self
        weekdays = [bh.weekday for bh in self.business_hours]
        if len(weekdays) != len(set(weekdays)):
            raise ValueError(
                "요일별 영업시간은 같은 요일을 중복해 등록할 수 없습니다 "
                "(weekday당 1행)."
            )
        return self


class RoomPublic(BaseModel):
    """공간 등록 성공 응답(룸 리소스). ``created_at``은 ``...Z``(1.7 ``UserPublic`` 패턴)."""

    model_config = ConfigDict(from_attributes=True)  # Room ORM 객체 → 응답 직렬화

    id: uuid.UUID
    provider_id: uuid.UUID
    name: str
    price_per_hour: int
    capacity: int
    room_type: str
    amenities: list[str]
    lat: float
    lng: float
    admin_dong_code: str
    is_active: bool
    created_at: datetime

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)


class GeocodeResult(BaseModel):
    """주소 검색(지오코딩) 결과 항목(AC2).

    카카오 주소검색 ``documents[]`` 한 항목의 매핑 결과다 — ``lat=y``·``lng=x``(카카오는
    x=경도·y=위도), ``admin_dong_code``는 지역 ``b_code``(Dev Notes 결정). 프론트가 후보
    중 하나를 선택해 ``RoomCreateRequest``의 ``lat``/``lng``/``admin_dong_code``로 실어 보낸다.
    """

    address: str
    lat: float
    lng: float
    admin_dong_code: str


class RoomMapItem(BaseModel):
    """룸 핀 렌더용 최소 메타 — 첫 진입 지도 좌표 공급 (Story 3.2, AC1·AC2).

    각 항목은 한 활성 룸의 **핀을 찍는 데 필요한 최소 정보**(좌표·이름)다. 프론트가 이
    목록을 ``GET /rooms/availability``(``RoomAvailability``)와 ``room_id``로 인메모리
    조인해 핀 좌표(이 응답)에 가용성 색(저쪽 응답)을 입힌다.

    **이 네 필드만** 둔다 — 가격·영업시간·부대시설·수용·주소·``provider_id``·
    ``created_at``은 **싣지 않는다**. 상세는 바텀시트(Story 3.3)의 신선 단일 조회 책임이고,
    공개 엔드포인트라 ``provider_id`` 노출을 피하며, 과조회를 막는다(L155 신선도 정책).

    **키 이름 = ``room_id``**(``RoomAvailability.room_id``와 동일) → 두 공개 GET을
    ``room_id``로 조인하기 위함이다. ``Room.id``를 ``room_id``로 노출하므로
    ``from_attributes`` 자동 매핑에 의존하지 않고 서비스에서 명시 생성한다
    (``RoomMapItem(room_id=r.id, ...)`` — ``RoomAvailability`` 명시 생성 선례).

    **와이어 규약:** snake_case 그대로(``room_id``·``name``·``lat``·``lng``). 시각 필드가
    없어 ``field_serializer``가 불필요하다.
    """

    room_id: uuid.UUID
    name: str
    lat: float
    lng: float


class RoomAvailability(BaseModel):
    """룸별 가용성 집계값 — 핀 색(FR-5) 결정용 (Story 3.1, AC1·AC3).

    각 항목은 한 활성 룸의 "**오늘(ROOM_TZ=KST) 현재시각 이후** 남은 빈 슬롯 수"다. 서버가
    ``aggregate_availability``에서 **1회** 집계하므로 클라이언트가 핀마다 슬롯을 N회 재계산하지
    않는다(architecture.md L362 금지 안티패턴 회피, NFR-2 성능).

    **이 두 필드만** 둔다(AC3 — 집계값만). 좌표·가격·이름 등 룸 메타데이터는 싣지 않는다 —
    그건 탐색/목록/바텀시트 엔드포인트(Story 3.2·3.3·3.4·3.5)의 책임이며, 클라이언트가
    ``room_id``로 조인한다. 가용성에 메타를 합치면 책임이 섞인다.

    **핀 색 분기:** ``remaining_slots >= 1`` → 예약 가능(초록), ``0`` → 마감(회색). 이 ``>= 1``
    판정은 **자명한 클라이언트 분기**일 뿐, architecture.md L362가 금지하는 "슬롯 N회 재계산"이
    아니다(슬롯 계산은 서버가 1회 끝냈다).

    **와이어 규약:** snake_case 그대로(``room_id``·``remaining_slots``, camelCase 변환 금지 —
    architecture.md L240·L286). 시각 필드가 없어 ``field_serializer``가 불필요하다.
    """

    room_id: uuid.UUID
    remaining_slots: int


class BusinessHoursPublic(BaseModel):
    """바텀시트 표시용 요일별 영업시간(공개 요약, Story 3.3).

    ``open_time``/``close_time``은 ROOM_TZ 벽시계 시각이며, Pydantic이 ``datetime.time``을
    ``"HH:MM:SS"`` 문자열로 직렬화한다(snake_case 그대로). 시트가 오늘 요일 행을 골라
    ``"09:00–22:00"``로 포맷한다(슬롯 도출 아님 — 단순 표시). ``weekday``는 월=0~일=6
    (``date.weekday()`` 규약)이며, ``BusinessHoursInput``과 동일 형상의 **응답 전용** 스키마다.
    """

    weekday: int  # 0=월 ... 6=일 (date.weekday() 규약)
    open_time: time  # 벽시계(ROOM_TZ) — "HH:MM:SS" 직렬화
    close_time: time  # 벽시계(ROOM_TZ)


class RoomSummary(BaseModel):
    """바텀시트 단일 룸 신선 요약 — 1차/2차 정보 + 신선 잔여 슬롯 (Story 3.3, AC1·AC4).

    핀(3.2)·목록 항목(3.4)이 탭한 룸의 **신선 요약**이다. ``GET /rooms/{room_id}``가 단일 룸
    조회로 가격·수용·룸 형태·부대시설·영업시간 + ``derive_slots``(2.1) 재사용한 **오늘 신선
    ``remaining_slots``**를 함께 싣는다. 이로써 시트의 "예약 가능 여부"가 핀 탭 시점의 동결
    스냅샷이 아니라 신선값이 된다(3.2 stale 배지 회수).

    **위치 미니 지도(Story 4.2)를 위해 ``lat``/``lng``를 노출한다** — 공개 스터디룸 좌표는 지도
    표시가 곧 제품 목적이라 공개해도 안전하다(``RoomMapItem``이 이미 좌표를 공개 노출하는 선례).
    반면 **``provider_id``·``is_active``·``created_at``·``admin_dong_code``는 여전히 싣지 않는다**
    (내부/소유 필드·지역 코드는 사람이 읽는 값 아님 — 노출 회피).
    ``RoomPublic``(provider_id·is_active 노출)을 재사용하지 않는 **공개 표면 전용** 스키마다.
    ``address``(표시용 주소)는 provider 웹 표면 구축으로 ``Room`` 컬럼이 되어 노출한다 — 바텀시트·
    상세에서 사람이 읽는 주소를 보여준다(좌표는 지도용, 주소는 텍스트용). 미입력이면 ``null``.
    4.2 상세 화면이 이 엔드포인트를 후기/평점·예약 UI로 **확장**한다(중복 아님).

    **키 이름 = ``room_id``**(``RoomMapItem``/``RoomAvailability``와 동일). ``Room.id``를
    ``room_id``로 노출하므로 서비스에서 명시 생성한다(``from_attributes`` 미사용 — 키 변환).
    **와이어 규약:** snake_case 그대로(camelCase 변환 금지). 시각 필드(``...Z``)가 없어
    ``field_serializer``가 불필요하다(``open_time``/``close_time``은 ``BusinessHoursPublic`` 처리).
    """

    room_id: uuid.UUID
    name: str
    price_per_hour: int  # 시간당 금액(원)
    capacity: int  # 수용 인원
    room_type: str  # RoomType 값(open/private — 자유 문자열 저장)
    amenities: list[str]  # 부대시설 코드 리스트("기타" 포함)
    business_hours: list[BusinessHoursPublic]  # 요일별 영업시간(weekday 오름차순)
    remaining_slots: int  # 오늘(ROOM_TZ) 현재시각 이후 신선 잔여 슬롯(derive_slots 재사용)
    # 오늘(ROOM_TZ)이 휴무(HolidayException)인지. true면 영업행이 있어도 시트가 "오늘 휴무"로 표시해
    # 휴무 마감과 '예약 꽉 차 마감'을 구분한다(영업시간 줄이 "마감" 배지와 모순 방지, code-review).
    is_closed_today: bool
    lat: float  # 위도 — 상세 위치 미니 지도(Story 4.2, RoomMapItem 좌표 공개 노출 선례)
    lng: float  # 경도 — 상세 위치 미니 지도(저장 좌표만 사용 · 지오코딩 호출 없음)
    address: str | None  # 표시용 주소(provider 입력 — 미입력이면 null)


class ProviderRoomDetail(BaseModel):
    """provider 본인 룸 전체 상세 — 등록/수정 폼 prefill용 (``GET /rooms/mine``).

    소유자 전용 표면이라 공개 요약과 달리 **수정에 필요한 모든 필드**(좌표·지역·주소·영업시간)를
    싣는다. provider 웹 표면 구축(idea.md L36 스터디룸 설정/수정)의 폼이 이 응답으로 현재 값을
    미리 채운다. 룸이 없으면 라우터가 404 ``ROOM_NOT_FOUND``(= 아직 등록 안 함 → 폼은 생성 모드).
    """

    room_id: uuid.UUID
    name: str
    price_per_hour: int
    capacity: int
    room_type: str
    amenities: list[str]
    lat: float
    lng: float
    admin_dong_code: str
    address: str | None
    business_hours: list[BusinessHoursPublic]  # weekday 오름차순


class Region(BaseModel):
    """지역 콤보의 동/읍/면 옵션 한 항목 (Story 3.4, AC1).

    ``code``는 동/읍/면 레벨 지역 코드(``XXXXXXXX00``), ``name``은 짧은 동 라벨
    (``"역삼동"`` — 시군구는 ``RegionGroup``이 들고 있어 동은 말단만 표시). ``room_count``는
    그 동에 있는 활성 룸 수(콤보 옵션에 개수 힌트). **룸이 있는 동만** 제시한다(빈 지역 미노출).
    """

    code: str  # 동/읍/면 레벨 지역 코드(10자리, 트레일링 0)
    name: str  # 동/읍/면 짧은 라벨(미매핑 시 코드 원문 폴백)
    room_count: int  # 이 동의 활성 룸 수


class RegionGroup(BaseModel):
    """지역 콤보의 시/군/구 그룹 (Story 3.4, AC1).

    ``GET /rooms/regions`` 응답의 한 항목 = 룸이 있는 한 시/군/구다. ``name``은 **시도명을
    포함**해 동명 시군구 모호성을 없앤다(``"서울특별시 강남구"``). ``dongs``는 그 시군구에서
    **룸이 있는 동/읍/면**만(빈 동 미노출). ``room_count``는 시군구 전체 활성 룸 수. 와이어는
    snake_case 그대로(시각 필드 없어 ``field_serializer`` 불필요).
    """

    code: str  # 시군구 레벨 지역 코드(10자리, 트레일링 0)
    name: str  # 시도 포함 시군구 라벨(미매핑 시 코드 원문 폴백)
    dongs: list[Region]  # 룸이 있는 동/읍/면(이름 오름차순)
    room_count: int  # 이 시군구의 활성 룸 수(동 합)


class RoomListItem(BaseModel):
    """지역 목록 한 행 — 이름·가격·룸형태·부대시설 + 신선 잔여 슬롯 (Story 3.4, AC1·AC4).

    ``GET /rooms/search?region_code=`` 응답의 한 항목이다. UJ-1의 "가격·시설 비교"를 위해
    리스트 행에 가격·룸형태·부대시설을 싣고, 예약 가능 배지를 위해 **오늘(ROOM_TZ) 신선
    ``remaining_slots``**(서버가 ``derive_slots`` 재사용으로 1회 집계)를 함께 싣는다.

    **공개 엔드포인트라 ``provider_id``·``is_active``·``lat``/``lng``·``admin_dong_code``·
    ``created_at``은 싣지 않는다**(내부/소유 필드 노출 회피 + 과조회 방지 — ``RoomSummary``/
    ``RoomMapItem`` 선례). ``RoomPublic``(provider_id·is_active 노출)을 재사용하지 않는 **공개
    표면 전용** 스키마다. 상세(영업시간·수용 등)는 행 탭이 여는 ``RoomSummary``(3.3)가 책임진다.

    **키 이름 = ``room_id``**(``RoomMapItem``/``RoomSummary``와 동일 — 시트 재사용 시 일관).
    ``Room.id``를 ``room_id``로 노출하므로 서비스에서 명시 생성한다(``from_attributes`` 미사용).
    와이어는 snake_case 그대로(시각 필드 없어 ``field_serializer`` 불필요).
    """

    room_id: uuid.UUID
    name: str
    price_per_hour: int  # 시간당 금액(원)
    room_type: str  # RoomType 값(open/private — 자유 문자열)
    amenities: list[str]  # 부대시설 코드 리스트("기타" 포함)
    remaining_slots: int  # 오늘(ROOM_TZ) 현재시각 이후 신선 잔여 슬롯(derive_slots 재사용)


# 슬롯 도메인 3상태(Story 4.3 — 날짜별 슬롯 가용성 표시). 와이어 snake_case 그대로.
#   · available  = 예약 가능(룸 타임존 현재시각 이후 + 미예약)
#   · past       = 룸 타임존 기준 현재시각 이전(지난 시간 — 선택 불가)
#   · reserved   = 이미 예약된 slot_start(점유). **Story 4.9 예약 차감 연결 전까지 미발생**
#                  (호출부가 reserved_starts=frozenset()을 넘겨 reserved 슬롯이 나오지 않는다).
SlotStatus = Literal["available", "past", "reserved"]


class RoomSlot(BaseModel):
    """그날 1시간 슬롯 하나 — 시작시각(UTC) + 상태 (Story 4.3, AC1·AC2).

    ``GET /rooms/{room_id}/slots`` 응답 ``slots[]``의 한 항목이다. ``slot_start``는
    ``derive_slots``(2.1)가 도출한 **UTC 인스턴트**(tz-aware)이며, ``...Z`` 와이어 규약으로
    직렬화한다(``RoomPublic.created_at`` 선례 — ``isoformat_utc``). 클라이언트는 이 UTC를
    Asia/Seoul 벽시계("14:00")로 **표시만** 한다(슬롯 재계산 금지 — architecture.md L362).

    ``status``는 ``available``(선택 가능)/``past``(지난 시간)/``reserved``(예약됨)의 3상태다.
    ``reserved``는 **Story 4.9 예약 차감 연결 전까지 미발생**한다(호출부가
    ``reserved_starts=frozenset()``을 전달 — 3.1·3.3 동일 seam). 가격·이름 등 룸 메타는 싣지
    않는다(슬롯 단위 — 메타는 ``RoomSummary`` 책임).
    """

    slot_start: datetime  # UTC 인스턴트(tz-aware) — ...Z 직렬화
    status: SlotStatus  # available/past/reserved(reserved는 4.9 전까지 미발생)

    @field_serializer("slot_start")
    def _ser_slot_start(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263 — RoomPublic 선례)


class RoomSlotsResponse(BaseModel):
    """날짜별 슬롯 목록 + 다음 빈 날짜 (Story 4.3, AC1·AC3).

    ``GET /rooms/{room_id}/slots?date=YYYY-MM-DD`` 응답이다 — 요청 ``date``(ROOM_TZ)의 1시간
    슬롯을 상태별로(``slots``) + 그날 빈 슬롯이 없을 때 안내할 **다음 빈 날짜**
    (``next_available_date``)를 함께 싣는다.

    - ``date`` = 요청 날짜 echo(ROOM_TZ 기준 ``date`` — 클라가 어느 날 응답인지 확인).
    - ``slots`` = 그날 1시간 슬롯 상태별 리스트(휴무·미영업 요일 → 빈 리스트, 에러 아님).
    - ``next_available_date`` = 요청 날 **다음날부터** 30일 상한 내 첫 "가용 슬롯 ≥ 1개" 날
      (ROOM_TZ 기준 ``date``). 30일 내 빈 날이 없으면 ``null``(막다른 화면 금지 — 안내만).

    가격·이름·좌표 등 룸 메타는 싣지 않는다(슬롯·다음빈날만 — 메타는 ``RoomSummary``가 별도 제공,
    클라가 ``useRoomSummary``와 조인). 와이어 snake_case 그대로
    (``slot_start``·``next_available_date``).
    """

    # 필드명 ``date``가 동명 타입 ``date``를 가려 그대로 쓰면 타입 해석이 깨진다(mypy valid-type).
    # 모듈레벨 별칭 ``_Date``로 타입을 가리켜 와이어 필드명은 ``date``로 유지한다.
    date: _Date  # 요청 날짜 echo(ROOM_TZ 기준)
    slots: list[RoomSlot]  # 그날 1시간 슬롯 상태별(휴무·미영업=빈 리스트)
    next_available_date: _Date | None  # 다음날~30일 내 첫 빈 날(없으면 null)
