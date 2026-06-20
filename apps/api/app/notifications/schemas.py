"""notifications 응답 스키마: ``NotificationItem`` (Story 5.1).

``GET /notifications``(본인 미확인 통지 목록) 응답 항목이다. 통지 식별·종류·사유 + 대상 예약
식별 + 대상 룸 이름(라우터 합성) + 생성시각을 싣는다. dismiss는 본문 없는 ``POST .../dismiss``
(204)라 요청/응답 스키마가 없다(경로 파라미터만).

**규약(아키텍처 §Format/Process L256-296):**

- **와이어는 snake_case 유지**(L286, camelCase 변환 레이어 금지). ``created_at``은 ``isoformat_utc``
  로 ``...Z`` 직렬화한다(L263 — ``RoomPublic``·``FavoriteRoomItem`` 선례).
- **``room_name``은 라우터가 ``session.get(Room)``로 합성**한다(service rooms import 금지·순환
  회피, 4.8 ``ReservationListItem`` 선례). 룸 누락/손상은 ``None`` 폴백(막다른 화면 금지).
- **카피는 프론트가 type/reason으로 생성**한다(generic — 5.2/5.3이 정밀화). 스키마는 표시 재료
  (type·reason·room_name)만 싣고 완성 문장은 싣지 않는다.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_serializer

from app.core.time import isoformat_utc


class NotificationItem(BaseModel):
    """미확인 통지 목록 한 행 — 배너 표시 재료(AC3·AC4).

    프론트 ``NotificationBanner``가 ``type``·``reason``·``room_name``·``slot_start``로 카피를
    만든다(status_change → "○○ 예약이 거절됐어요." / reservation_reminder → "○○ 예약이 곧
    다가와요. {KST 시각}…"). ``reservation_id``는 추적·dismiss 라우팅용. ``provider_id``·내부
    식별자는 노출하지 않는다(``FavoriteRoomItem`` 정신).

    **두 종류의 비대칭(Story 5.2·5.3):** ``status_change``는 DB 행이라 ``id``·``created_at``이
    있고, ``reservation_reminder``는 **도출**(행 없음)이라 ``id``=None·``created_at``=None이다.
    ``slot_start``는 **양쪽 모두** 라우터가 ``earliest_slot_start``로 합성한다(reminder=윈도 판정
    대상인 가장 이른 슬롯 / **status_change=원래 점유 슬롯[0] — 4.8 immutable 스냅샷·표시용**,
    Story 5.3이 None→값으로 채움). FE는 ``id`` 유무·``type``으로 dismiss 경로를 분기한다
    (reminder=reservation_id 키 / status_change=id 키). 손상/누락 slot_starts는 ``None`` 폴백.
    """

    id: uuid.UUID | None  # status_change=notification_id / reservation_reminder=None(도출)
    type: str  # NotificationType 값(reservation_reminder/status_change — 카피·dismiss 분기)
    reservation_id: uuid.UUID  # 대상 예약(추적·리마인드 dismiss 키)
    reason: str | None  # status_change 사유('rejected'|'cancelled') — reminder=None
    room_name: str | None  # 라우터가 session.get(Room)으로 합성(룸 누락 시 None 폴백)
    slot_start: datetime | None  # 가장 이른 슬롯(...Z) — reminder=윈도/status_change=원래 슬롯(5.3)
    created_at: datetime | None  # status_change=행 생성 시각(...Z) / reservation_reminder=None

    @field_serializer("slot_start", "created_at")
    def _ser_optional_dt(self, value: datetime | None) -> str | None:
        # 두 종류 비대칭으로 None일 수 있다 → None-safe(...Z는 값 있을 때만, architecture.md L263).
        return isoformat_utc(value) if value is not None else None
