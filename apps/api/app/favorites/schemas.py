"""favorites 요청/응답 스키마: ``FavoriteCreateRequest`` · ``FavoriteRoomItem`` (Story 3.7).

**규약(아키텍처 §Format/Process L256-296):**

- **와이어는 snake_case 유지**(L286, camelCase 변환 레이어 금지). ``favorited_at``은
  ``isoformat_utc``로 ``...Z`` 직렬화한다(L263 — ``RoomPublic`` 패턴).
- **⚠️ 인증(비공개) 표면이므로 ``is_active`` 노출 OK.** 공개 표면인 ``RoomListItem``/
  ``RoomSummary``는 ``is_active``를 의도적으로 제외했으나, 즐겨찾기는 **로그인 전용** +
  AC3가 '비활성' 라벨/진입 차단을 요구하므로 ``is_active``를 **반드시 포함**한다.
  ``RoomListItem``을 재사용하지 않고 전용 ``FavoriteRoomItem``을 둔다.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_serializer

from app.core.time import isoformat_utc


class FavoriteCreateRequest(BaseModel):
    """즐겨찾기 추가 요청(POST 본문). 토글의 '추가' 방향 — 룸 PK만 받는다."""

    room_id: uuid.UUID


class FavoriteRoomItem(BaseModel):
    """즐겨찾기 목록 한 행 — 룸 메타 + 신선 잔여 슬롯 + 활성 여부 (AC2·AC3).

    ``GET /favorites``(목록)·``POST /favorites``(추가 후) 응답 항목이다. 룸 비교용 가격·룸형태·
    부대시설 + 예약 가능 배지용 ``remaining_slots``(서버 ``derive_slots`` 재사용 신선값)에 더해,
    **``is_active``**(AC3 비활성 라벨·진입 차단 판정)와 **``favorited_at``**(목록 정렬 = 최근 추가
    순)을 싣는다. ``provider_id``·좌표·``admin_dong_code``는 싣지 않는다(불필요·내부 필드).

    **키 이름 = ``room_id``**(``RoomMapItem``/``RoomSummary``/``RoomListItem``과 동일) — 시트·핀과
    일관. 서비스에서 명시 생성한다(``from_attributes`` 미사용 — 키 변환·remaining_slots 합성).
    """

    room_id: uuid.UUID
    name: str
    price_per_hour: int  # 시간당 금액(원)
    room_type: str  # RoomType 값(open/private — 자유 문자열)
    amenities: list[str]  # 부대시설 코드 리스트("기타" 포함)
    remaining_slots: int  # 오늘(ROOM_TZ) 현재시각 이후 신선 잔여 슬롯(비활성 룸은 0)
    is_active: bool  # AC3 — 비활성 룸 '비활성' 라벨 + 상세 진입 차단 판정(인증 표면이라 노출 OK)
    favorited_at: datetime  # 즐겨찾기 추가 시각(목록 최근순 정렬 — ...Z 직렬화)

    @field_serializer("favorited_at")
    def _ser_favorited_at(self, value: datetime) -> str:
        return isoformat_utc(value)  # 와이어 규약 ...Z(architecture.md L263)
