"""chatbot 라우터: 비스트리밍 멀티턴 대화 + 세션 재수화/초기화 (Story 7.3).

``main.py``가 ``api_router``(``/api/v1``) 아래에 포함하므로 최종 경로는:

- ``POST /api/v1/chatbot/messages`` — 메시지 전송 → 봇 전체 응답(비스트리밍). 같은
  thread_id로 연속 전송 시 이전 맥락 유지(checkpointer 누적, AC3).
- ``GET /api/v1/chatbot/messages?device_id=...`` — 현재 thread 메시지 이력 재수화(AC4).
- ``DELETE /api/v1/chatbot/session?device_id=...`` — thread checkpointer 상태 폐기(204·멱등, AC5).
- ``POST /api/v1/chatbot/stream`` — 메시지 전송 → 봇 응답을 **SSE 토큰 스트리밍**(Story 7.4). 각
  토큰은 ``data: {"delta": "..."}``(JSON 인코딩 — ``\n``·공백·``[DONE]`` 오염 차단), 정상 종료는
  ``event: done``, LLM 업스트림 실패는 ``event: error``로 **인밴드** 전달(스트림 시작 후 HTTP
  상태 불가 — 함정 #2). 미인증 401은 스트림 시작 **전** dependency라 정상 HTTP 401.

**규약:**

- **인증 = ``get_current_principal``**(로그인만·역할 무관, notifications 미러). 미인증=401.
  ``thread_id = user_id:device_id``로 도출 → 앞에 인증 user_id 고정이라 cross-user 접근 불가.
- **DB 세션 불요**: 상태는 MemorySaver(인메모리)라 ``Depends(get_session)``를 쓰지 않는다(타
  라우터와 다른 정상 차이 — architecture L160). raw ``HTTPException`` 금지(``DomainError``만).
- **device_id 전달**: POST=body 필드, GET/DELETE=query param(@hey-api SDK 친화·Pydantic 검증).
- **SSE ``/stream``은 만들지 않는다**(7.4 소유) — 본 스토리는 ``invoke`` 비스트리밍만.
- **operationId(1.9):** ``{tag}_{name}`` = ``chatbot_send_message``·``chatbot_get_transcript``·
  ``chatbot_reset_session`` → SDK ``chatbotSendMessage``·``...GetTranscript``·``...ResetSession``.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, Response, status
from sse_starlette import EventSourceResponse

from app.chatbot import service
from app.chatbot.schemas import (
    DEVICE_ID_PATTERN,
    ChatMessage,
    SendMessageRequest,
    SendMessageResponse,
    TranscriptResponse,
)
from app.core.errors import DomainError, ErrorResponse
from app.core.security import AuthPrincipal, get_current_principal

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

# GET/DELETE 공용 device_id 쿼리(필수·형식 검증). 모듈 싱글톤으로 1회 생성(rooms ``_date_query``
# 선례 — 인자 기본값 함수 호출 B008 회피).
_device_id_query = Query(pattern=DEVICE_ID_PATTERN)


def _coords_from_body(body: SendMessageRequest) -> tuple[float, float] | None:
    """요청 본문의 lat/lng를 좌표 튜플로 변환한다(둘 다 있을 때만 — 부분 좌표=미적용 graceful).

    챗봇 "내 주변" 반경 검색용. None이면 서비스→그래프 config에 ``user_coords=None``으로 흘러
    툴이 위치 미보유로 판단한다(LLM엔 노출되지 않음).
    """
    if body.lat is not None and body.lng is not None:
        return (body.lat, body.lng)
    return None


@router.post(
    "/messages",
    response_model=SendMessageResponse,
    responses={
        401: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
def send_message(
    body: SendMessageRequest,
    principal: AuthPrincipal = Depends(get_current_principal),
) -> SendMessageResponse:
    """메시지를 보내고 봇의 전체 응답을 반환한다 → 200(로그인 필요, AC3).

    같은 ``thread_id``(=``user_id:device_id``)로 연속 전송 시 이전 맥락이 유지된다(checkpointer
    자동 누적·멀티턴). LLM 업스트림 실패는 502 ``LLM_PROVIDER_UNAVAILABLE``. 미인증은 401.
    """
    thread_id = service.derive_thread_id(principal.user_id, body.device_id)
    reply = service.send_message(thread_id, body.message, coords=_coords_from_body(body))
    return SendMessageResponse(reply=reply, thread_id=thread_id)


@router.post(
    "/stream",
    responses={401: {"model": ErrorResponse}},
)
async def stream_message(
    body: SendMessageRequest,
    principal: AuthPrincipal = Depends(get_current_principal),
) -> EventSourceResponse:
    """메시지를 보내고 봇 응답을 **SSE 토큰 스트리밍**한다 → 200 ``text/event-stream``(AC1·AC2).

    미인증 401은 스트림 시작 **전** dependency(``get_current_principal``)라 정상 HTTP 401이다.
    스트림이 시작되면 200 헤더가 이미 송신되므로(함정 #2), LLM 업스트림 실패를 ``raise``로 전파하지
    않고 ``event: error`` 프레임으로 **인밴드** 전달한다 → 클라가 graceful degrade(AC4).
    각 토큰은 ``data: {"delta": "..."}``(JSON — ``\\n``·공백·``[DONE]`` 섞여도 프레임 무손상,
    deferred L129 회수), 정상 종료는 ``event: done``. 같은 ``thread_id``로 재스트림 시 7.3
    checkpointer가 맥락을 누적한다.
    """
    thread_id = service.derive_thread_id(principal.user_id, body.device_id)
    coords = _coords_from_body(body)

    async def event_gen() -> AsyncIterator[dict[str, str]]:
        # 스트림 시작 후 발생 에러는 절대 raise로 전파하지 않는다(200 헤더 송신됨) — DomainError만
        # 좁혀 잡아 인밴드 event:error로 전달한다(그 외 예외=코드 버그는 그대로 전파해 위장 안 함).
        try:
            async for delta in service.stream_message(thread_id, body.message, coords=coords):
                yield {"data": json.dumps({"delta": delta}, ensure_ascii=False)}
            yield {"event": "done", "data": "{}"}
        except DomainError as exc:  # 업스트림 LLM 실패(LLM_PROVIDER_UNAVAILABLE) 인밴드 전달
            yield {
                "event": "error",
                "data": json.dumps(
                    {"code": exc.code.value, "message": exc.message}, ensure_ascii=False
                ),
            }

    return EventSourceResponse(event_gen(), media_type="text/event-stream")


@router.get(
    "/messages",
    response_model=TranscriptResponse,
    responses={401: {"model": ErrorResponse}},
)
def get_transcript(
    device_id: str = _device_id_query,
    principal: AuthPrincipal = Depends(get_current_principal),
) -> TranscriptResponse:
    """현재 thread의 메시지 이력을 반환한다 → 200(재수화용, AC4). 빈 thread=[]. 미인증 401."""
    thread_id = service.derive_thread_id(principal.user_id, device_id)
    messages = service.get_transcript(thread_id)
    return TranscriptResponse(
        messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages]
    )


@router.delete(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse}},
)
def reset_session(
    device_id: str = _device_id_query,
    principal: AuthPrincipal = Depends(get_current_principal),
) -> Response:
    """해당 thread의 대화 상태를 폐기한다 → 204(로그아웃 초기화·멱등, AC5). 미인증 401."""
    thread_id = service.derive_thread_id(principal.user_id, device_id)
    service.reset_session(thread_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
