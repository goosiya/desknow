"""reservations 요청/응답 스키마: ``ReservationCreateRequest`` · ``ReservationPublic`` (Story 4.5).

즉시 예약(결제 없음) 쓰기 경로의 본문 검증과 응답 직렬화를 분리한다. 2.2 ``rooms/schemas.py``·
3.7 ``favorites/schemas.py`` 패턴을 미러한다. ``room_id``는 **경로 파라미터**(중첩 라우트
``/rooms/{room_id}/reservations``)라 본문 스키마에 두지 않는다.

**규약(아키텍처 §Format/Process L256-296):**

- **검증은 백엔드가 신뢰 경계**(L277). 형식 위반(빈 배열·naive datetime·중복·교차일)은 모두
  Pydantic 검증으로 ``RequestValidationError``가 되며, 1.5 ``validation_exception_handler``가
  **422 + ``{detail:{code:"VALIDATION_ERROR", message}}``** 로 단일화한다(AC2). → service의
  ``ValueError``(빈/naive/중복)가 500으로 새지 않게 **스키마에서 선차단**한다(반복 함정 #6).
- **와이어는 snake_case 유지**(L286, camelCase 변환 레이어 금지). datetime은 ``isoformat_utc``로
  ``...Z`` 직렬화한다(L263 — ``RoomPublic.created_at``·``RoomSlot.slot_start`` 선례).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_serializer, model_validator

from app.core.time import ROOM_TZ, isoformat_utc, to_tz
from app.reviews.schemas import ReviewListItem  # 본인 후기 노출(예약현황 — 5.5/5.6 답글 포함)


def booker_display_label(booker_id: uuid.UUID) -> str:
    """예약자 식별자에서 **결정적·비가역 익명 라벨**을 파생한다(Story 6.1 — FR-23 Privacy).

    제공자 예약현황은 예약자 식별정보를 노출하면 안 되지만(이메일·연락처·raw UUID 비노출 — FR-23),
    제공자가 **동일 예약자의 여러 예약을 구분·집계**할 수 있어야 한다("표시 이름" 문구 충족).
    ``User`` 모델엔 표시명 컬럼이 없고(``email``이 유일 식별 필드인데 FR-23이 노출 금지) reviews가
    익명인 것과 동일 제약이므로, ``booker_id``에서 **결정적**(같은 예약자=같은 라벨)·**비가역**
    (이메일/UUID 복원 불가) 해시 파생한 라벨만 노출한다. 진짜 표시명(users ``display_name`` 컬럼)은
    가입·마이그레이션·SDK 동반이 선행돼야 하는 별도 미니에픽이라 defer(5.5 작성자 표시명과 동근).

    **왜 prefix가 아니라 hash인가:** ``str(booker_id)[:6]``처럼 UUID 일부를 자르면 raw UUID
    바이트가 누출된다("raw UUID 미노출" 위반). ``sha256`` 파생은 UUID 어떤 부분도 노출하지 않으면서
    결정적·안정적이다. 6자 hex(16.7M 공간) 충돌은 MVP 규모(제공자당 소수 예약자)에서 무시 가능하고,
    충돌해도 표시 라벨일 뿐 데이터 영향 0이다(정밀 표시명 도입 시 자연 해소).

    Args:
        booker_id: 예약자 식별자(``users.id``).

    Returns:
        ``"예약자 #" + sha256(str(booker_id))[:6]`` 형식의 안정 익명 라벨(예: ``"예약자 #a3f9c1"``).
    """
    digest = hashlib.sha256(str(booker_id).encode()).hexdigest()[:6]
    return f"예약자 #{digest}"


class ReservationCreateRequest(BaseModel):
    """즉시 예약 요청(POST 본문) — 점유할 연속 슬롯 시작시각들(AC1·AC2).

    ``slot_starts``는 UTC aware datetime 리스트다(4.4가 추출한 서버 UTC ISO 그대로). 본문 검증으로
    빈 배열·naive datetime·중복·교차일(서로 다른 ROOM_TZ 날짜)을 **선차단**해 422로 되돌린다 —
    service ``create_reservation``의 ``ValueError`` fail-fast(빈/naive/중복)가 미처리 500으로 새지
    않도록 라우터 도달 전에 막는다(반복 함정 #6). 연속성 판정은 4.4 UI(클라)가 이미 끝냈고, 서버는
    확정 시점에 ``derive_slots`` 재사용으로 **가용 슬롯 집합 멤버십**만 재검증한다(라우터, AC2).

    ``room_id``는 **경로 파라미터**(중첩 라우트)라 본문에 두지 않는다. ``booker_id``는 인증
    principal에서 도출하므로 본문에 없다(클라가 예약자를 지정할 수 없음 — RBAC).
    """

    slot_starts: list[datetime] = Field(min_length=1)  # 최소 1개(빈 배열=422)

    @model_validator(mode="after")
    def _validate_slot_starts(self) -> ReservationCreateRequest:
        """슬롯 시작시각이 tz-aware·중복 없음·같은 ROOM_TZ 날짜인지 검증한다(위반 시 422).

        - **naive 거부:** naive datetime은 ``derive_slots``가 내는 aware UTC 슬롯과 결코 같지 않아
          신선 재검증이 항상 실패한다 → 경계에서 즉시 422로 막는다(``_require_aware`` 철학).
        - **중복 거부:** 같은 슬롯 2개는 ``uq_reservation_slots_room_slot`` 자기충돌로 신규인데도
          ``SLOT_CONFLICT``(409 "이미 예약됨")로 오변환된다 → 입력 계약 위반(422)으로 분리한다
          (service의 동일 ValueError 선차단).
        - **교차일 거부:** 서로 다른 ROOM_TZ 날짜의 슬롯을 한 예약에 섞으면 신선 재검증이 단일
          날짜(``get_room_slots``) 도출과 어긋난다 → 같은 ROOM_TZ 날짜만 허용한다(범위 결정 #2).
        """
        for slot_start in self.slot_starts:
            if slot_start.tzinfo is None or slot_start.utcoffset() is None:
                raise ValueError(
                    "slot_starts 항목은 tz-aware여야 합니다 (naive datetime 금지) — "
                    "슬롯 시작시각은 UTC로 전달됩니다."
                )
        # aware datetime은 동일 인스턴트면 동일 해시/동치라 set이 인스턴트 기준으로 중복을 합친다.
        if len(set(self.slot_starts)) != len(self.slot_starts):
            raise ValueError("slot_starts에 중복된 슬롯이 있습니다 (각 슬롯은 한 번만 예약 가능).")
        # 모든 슬롯이 같은 ROOM_TZ 날짜인지 — 신선 재검증이 단일 날짜 도출(get_room_slots)을 쓰므로
        # 교차일 입력을 422로 거부한다(라우터가 첫 슬롯의 날짜만 보고 검증하는 전제를 보장).
        room_dates = {to_tz(slot_start, ROOM_TZ).date() for slot_start in self.slot_starts}
        if len(room_dates) > 1:
            raise ValueError(
                "slot_starts는 모두 같은 날짜여야 합니다 (다른 날의 슬롯은 함께 예약 불가)."
            )
        return self


class ReservationPublic(BaseModel):
    """즉시 예약 성공 응답(예약 리소스, AC1).

    생성된 ``Reservation``(상태머신 단위)의 식별·상태·생성시각 + 점유한 ``slot_starts``를 싣는다.
    datetime은 ``...Z``(``RoomPublic``·``RoomSlot`` 선례 — ``isoformat_utc``). ``provider_id`` 등
    내부 필드는 노출하지 않는다(예약자 본인 표면이라 ``booker_id``는 노출 — 응답 주체 확인용).
    """

    id: uuid.UUID
    room_id: uuid.UUID
    booker_id: uuid.UUID
    status: str  # ReservationStatus 값(confirmed — 자유 문자열 저장, 4.1)
    created_at: datetime  # 예약 생성 시각(...Z 직렬화)
    slot_starts: list[datetime]  # 점유한 슬롯 시작시각(UTC aware — ...Z 직렬화)

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)

    @field_serializer("slot_starts")
    def _ser_slot_starts(self, value: list[datetime]) -> list[str]:
        return [isoformat_utc(slot_start) for slot_start in value]  # 항목별 ...Z


class ProviderReservationItem(BaseModel):
    """제공자 예약현황 목록 한 행 — 예약 메타 + 룸 이름 + 예약자 익명 라벨 (Story 6.1, AC1·AC2).

    ``GET /provider/reservations``(제공자 소유 룸 예약 목록) 응답 항목이다.
    ``ReservationListItem``(예약자 본인 표면, 4.8)의 **거울상**으로, 예약 식별·상태·생성시각 +
    **시간 스냅샷**(``slot_starts`` — 취소/거절 후에도 잔존하는 표시 전용 히스토리) + 룸 이름을
    싣되, 예약자는 **안정 익명 라벨**(``booker_label``)만 노출한다.

    **프라이버시(AC2·FR-23 — ★핵심):** ``booker_id``·``email``·연락처·좌표 등 **식별/내부 필드를
    스키마에 두지 않는다**. ``booker_label``은 ``booker_id``에서 결정적·비가역 해시 파생
    (``booker_display_label`` — ``sha256(str(booker_id))[:6]``)이라 같은 예약자=같은 라벨(제공자가
    동일 예약자 구분·집계 가능)이고, 이메일/raw UUID는 복원 불가하다(``ReservationPublic``·
    ``ReservationListItem``의 "필요한 것만 노출" 정신).

    - **``room_name``은 라우터가 합성**한다(``list_provider_rooms`` 결과로 만든 이름 맵에서 — 4.9
      순환 회피로 reservations.service rooms import 금지, ``ReservationListItem`` 선례). 본인 표면이
      아니라 제공자 소유자 뷰라 ``is_active``·``has_review``는 싣지 않는다(소비 UI 후속).
    - **``slot_starts``는 스냅샷**(``Reservation.slot_starts`` ISO ``...Z`` 문자열)을
      ``list[datetime]``로 받아 ``...Z`` 재직렬화한다(``ReservationListItem`` 미러).
      취소/거절 예약도 점유 행은 DELETE됐어도 이 스냅샷으로 날짜·시간을 표시한다.
    """

    id: uuid.UUID  # reservation_id
    room_id: uuid.UUID
    room_name: str  # 라우터가 list_provider_rooms 결과 이름 맵으로 합성(service rooms import 금지)
    booker_label: str  # 예약자 안정 익명 라벨(해시 파생 — 이메일·raw UUID 비노출, AC2)
    status: str  # ReservationStatus 값(confirmed/cancelled/rejected — 자유 문자열)
    slot_starts: list[datetime]  # 점유 슬롯 시작시각 스냅샷(UTC aware — ...Z 직렬화·취소 후 잔존)
    created_at: datetime  # 예약 생성 시각(...Z 직렬화 — 목록 정렬·표시)

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)

    @field_serializer("slot_starts")
    def _ser_slot_starts(self, value: list[datetime]) -> list[str]:
        return [isoformat_utc(slot_start) for slot_start in value]  # 항목별 ...Z


class ReservationListItem(BaseModel):
    """예약현황 목록 한 행 — 예약 메타 + 룸 이름 + 슬롯 시간 스냅샷 (Story 4.8, AC1·AC2·AC4).

    ``GET /reservations``(본인 예약 목록) 응답 항목이다. 예약 식별·상태·생성시각 + **시간 스냅샷**
    (``slot_starts`` — 취소/거절 후에도 잔존하는 표시 전용 히스토리, 범위 결정 #1) + 룸 이름·활성
    여부를 싣는다. ``provider_id``·좌표 등 내부 필드는 노출하지 않는다(``ReservationPublic`` 정신).

    - **``room_name``·``is_active``는 라우터가 ``session.get(Room, …)``로 합성**한다(4.9 순환 회피로
      reservations.service rooms import 금지, ``FavoriteRoomItem`` 선례). ``is_active``는 비활성 룸
      상세 Link 차단 판정용(인증 표면이라 노출 OK — ``FavoriteRoomItem`` 선례).
    - **``slot_starts``는 스냅샷**(``Reservation.slot_starts`` ISO ``...Z`` 문자열)을
      ``list[datetime]``로 받아 ``...Z`` 재직렬화한다(``ReservationPublic._ser_slot_starts`` 미러 —
      와이어 규약 정규화).
      cancellable/6h은 **FE가 ``slot_starts``로 계산**(4.7 범위 결정 #3 — 서버는 cancellable 필드를
      노출하지 않고, 취소 엔드포인트가 6h 경계를 timedelta로 최종 강제).
    """

    id: uuid.UUID  # reservation_id
    room_id: uuid.UUID
    room_name: str  # 라우터가 session.get(Room)으로 합성(service rooms import 금지)
    status: str  # ReservationStatus 값(confirmed/cancelled/rejected — 자유 문자열)
    slot_starts: list[datetime]  # 점유 슬롯 시작시각 스냅샷(UTC aware — ...Z 직렬화·취소 후 잔존)
    created_at: datetime  # 예약 생성 시각(...Z 직렬화 — 목록 정렬·표시)
    is_active: bool  # 룸 활성 여부(비활성 룸 상세 Link 차단 판정 — 인증 표면이라 노출 OK)
    has_review: bool  # 예약별 후기 작성 여부(Story 5.5 — 예약현황 후기 작성 게이팅·죽은 버튼 0).
    # 라우터가 reviews.service로 단일 쿼리 합성(N+1 금지·room_name 옆).
    # ★본인이 작성한 후기(별점·텍스트·작성일 + 사장님 답글) — 작성한 예약에만 채워지고 아니면 None.
    #   예약현황에서 "후기 완료"만 보여주던 것을 실제 후기 내용+답글까지 보이도록
    #   추가(KTH 2026-06-19).
    #   has_review와 정합(review is not None ⟺ has_review). 본인 표면이라 익명 제약 무관(자기 후기).
    review: ReviewListItem | None = None

    @field_serializer("created_at")
    def _ser_created_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)

    @field_serializer("slot_starts")
    def _ser_slot_starts(self, value: list[datetime]) -> list[str]:
        return [isoformat_utc(slot_start) for slot_start in value]  # 항목별 ...Z
