"""챗봇 라우터 요청/응답 스키마 (Story 7.3).

device_id는 ``derive_thread_id``가 thread_id 합성에 쓰므로 형식을 1차 검증한다(서비스
``validate_device_id``가 동형 방어 — defense in depth). 위반은 Pydantic→1.5 핸들러가 422
``VALIDATION_ERROR``로 단일화한다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# device_id 허용 형식(서비스 ``_DEVICE_ID_RE``와 동일): UUID 또는 opaque 토큰, 8~128자.
DEVICE_ID_PATTERN = r"^[A-Za-z0-9_-]{8,128}$"

# 사용자 메시지 상한(과길이 입력·토큰 남용 방어). 1자 미만 거부.
_MESSAGE_MAX_LENGTH = 4000


class SendMessageRequest(BaseModel):
    """``POST /chatbot/messages``·``/stream`` 본문 — 메시지 + 디바이스 식별자 + (선택) 현재 좌표."""

    message: str = Field(min_length=1, max_length=_MESSAGE_MAX_LENGTH)
    device_id: str = Field(pattern=DEVICE_ID_PATTERN)
    # 사용자 현재 좌표(선택) — 위치 권한 허용 시 클라가 동봉한다. 챗봇 "내 주변" 반경 검색에 쓰이며
    # **둘 다 있을 때만** 적용(부분 좌표=미적용). LLM엔 노출되지 않고 그래프 config로 툴에 주입된다.
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class SendMessageResponse(BaseModel):
    """``POST /chatbot/messages`` 응답 — 봇 전체 응답(비스트리밍) + 도출된 thread_id."""

    reply: str
    thread_id: str


class ChatMessage(BaseModel):
    """대화 한 줄(재수화 표시용). role=user|assistant."""

    role: str
    content: str


class TranscriptResponse(BaseModel):
    """``GET /chatbot/messages`` 응답 — 현재 thread의 메시지 이력(재수화)."""

    messages: list[ChatMessage]
