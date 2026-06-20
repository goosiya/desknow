"""챗봇 세션 서비스 — thread 도출·전송·재수화·초기화 (Story 7.3, AC3·AC4·AC5).

세션 모델: ``thread_id = f"{user_id}:{device_id}"``. user_id는 JWT(신뢰), device_id는 클라
생성 식별자(웹 localStorage 영속). "사용자×디바이스" 단위를 충족하면서 **인증 스키마 무변경**
(refresh_tokens·JWT 클레임 손대지 않음)이다.

- ``derive_thread_id``: device_id를 **검증**해 thread_id 오염을 막는다(함정 #3). user_id는 JWT
  도출이라 신뢰 — thread_id 앞에 인증된 user_id를 고정하므로 cross-user 접근은 불가능하다.
- ``send_message``: 그래프를 ``invoke``해 전체 응답을 한 번에 반환한다(비스트리밍). checkpointer가
  이전 메시지를 자동 로드·누적한다(멀티턴). LLM 업스트림 실패는 7.1 ``normalize_llm_error``로
  ``DomainError(LLM_PROVIDER_UNAVAILABLE, 502)``로 정규화한다(신규 ErrorCode 없음).
- ``get_transcript``: 현재 thread의 메시지 이력을 ``{role, content}`` 리스트로 재수화(빈 thread=[]).
- ``reset_session``: 해당 thread의 checkpointer 상태를 폐기(멱등 — 없는 thread도 no-op).
"""
from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any, cast

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    RemoveMessage,
)
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.chatbot.graph import get_graph
from app.chatbot.llm import get_provider_spec, normalize_llm_error
from app.core.config import get_settings
from app.core.errors import DomainError, ErrorCode

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from langchain_core.messages import BaseMessage
    from langchain_core.runnables import RunnableConfig
    from langgraph.graph.state import CompiledStateGraph

    # 컴파일된 챗봇 그래프 별칭(graph.py와 동형 — 4개 제네릭 구체화 불요).
    ChatGraph = CompiledStateGraph[Any, Any, Any, Any]

# device_id 허용 형식: UUID 또는 opaque 토큰(영숫자·하이픈·언더스코어, 8~128자). 빈값/과길이/
# 제어문자/구분자(``:``) 거부 → thread_id 합성 오염을 차단한다(함정 #3). user_id 부분은 JWT 도출
# UUID라 신뢰 — 검증 대상은 외부 입력 device_id뿐이다.
_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

# react 툴콜 루프 상한(super-step 수). 정상 단일툴 RAG는 START→call_model→tools→call_model→END
# (≈3 step)이라 넉넉하고, 모델이 툴콜을 무한 반복하면 GraphRecursionError로 조기 차단한다 — 미설정
# 시 기본 25까지 돌며 raw 500 + 실패 turn 롤백 우회(고아 HumanMessage) 위험(리뷰 D2). 7.6/7.7이
# 멀티툴(예약검색·거절)을 더하면 필요 시 상향한다.
_RECURSION_LIMIT = 8


def validate_device_id(device_id: str) -> str:
    """device_id 형식을 검증한다(통과 시 그대로 반환). 위반은 422 ``VALIDATION_ERROR``.

    라우터 스키마(Pydantic)가 1차 검증하지만, 서비스가 독립 호출돼도 thread_id가 오염되지 않도록
    여기서도 방어한다(defense in depth — 함정 #3).
    """
    if not _DEVICE_ID_RE.fullmatch(device_id):
        raise DomainError(
            ErrorCode.VALIDATION_ERROR, "유효하지 않은 디바이스 식별자입니다."
        )
    return device_id


def derive_thread_id(user_id: uuid.UUID, device_id: str) -> str:
    """``user_id:device_id`` thread_id를 도출한다(device_id는 검증 후 합성)."""
    return f"{user_id}:{validate_device_id(device_id)}"


def _content_to_str(content: object) -> str:
    """메시지 content를 문자열로 강제한다(텍스트 LLM은 str, 멀티모달 list 방어)."""
    return content if isinstance(content, str) else str(content)


def send_message(
    thread_id: str,
    user_text: str,
    *,
    coords: tuple[float, float] | None = None,
    graph: ChatGraph | None = None,
    provider: str | None = None,
) -> str:
    """사용자 메시지를 보내고 봇의 전체 응답(비스트리밍)을 반환한다(AC3).

    같은 ``thread_id``로 연속 호출하면 checkpointer가 이전 메시지를 자동 로드·누적한다(멀티턴).
    LLM 업스트림 네이티브 예외만 좁혀 잡아(``native_exceptions``) ``normalize_llm_error``로
    정규화한다 — 그 외 예외(코드 버그 등)는 502로 위장하지 않고 그대로 전파한다.

    ★실패 turn 롤백(AC4 무결성): LangGraph는 ``call_model`` 노드 실패 **전에** 입력 HumanMessage를
    체크포인트에 영속한다. 정규화 전에 이 turn 입력을 명시 id로 thread에서 제거하지 않으면, 같은
    텍스트 재전송(retry) 시 user 메시지가 thread에 두 번 쌓여 재수화 transcript가 중복된다.
    """
    g = graph if graph is not None else get_graph()
    provider_name = provider if provider is not None else get_settings().LLM_PROVIDER
    # 네이티브 예외 튜플을 미리 해석(미등록 프로바이더면 여기서 LLMConfigurationError — 설정 문제).
    native_exceptions = get_provider_spec(provider_name).native_exceptions
    config: RunnableConfig = {
        # user_coords: 챗봇 "내 주변" 반경 검색용 사용자 좌표(없으면 None) — 툴이 config에서 읽는다.
        "configurable": {"thread_id": thread_id, "user_coords": coords},
        "recursion_limit": _RECURSION_LIMIT,  # react 툴콜 폭주 조기 차단(리뷰 D2)
    }
    # 입력에 명시 id를 부여 — 노드 실패 시 이 turn 입력만 정확히 롤백하기 위함(아래 except).
    message_id = str(uuid.uuid4())
    try:
        result = g.invoke(
            {"messages": [HumanMessage(content=user_text, id=message_id)]}, config
        )
    except native_exceptions as exc:  # LLM 업스트림 실패만 좁혀 정규화(7.1 규약)
        # 실패한 turn의 입력 HumanMessage를 thread에서 제거 — 재전송 시 중복 누적 차단(AC4 무결성).
        # checkpointer가 없는(비영속) 그래프면 남을 상태도 없으므로 롤백은 best-effort다.
        try:
            g.update_state(config, {"messages": [RemoveMessage(id=message_id)]})
        except Exception:  # noqa: BLE001 — 롤백 실패가 정규화 에러를 가리지 않게 흡수
            pass
        raise normalize_llm_error(exc, provider_name) from exc
    messages: list[BaseMessage] = result["messages"]
    # 마지막 AI 메시지 content 반환(노드가 방금 append한 응답).
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return _content_to_str(message.content)
    return ""


async def stream_message(
    thread_id: str,
    user_text: str,
    *,
    coords: tuple[float, float] | None = None,
    graph: ChatGraph | None = None,
    provider: str | None = None,
) -> AsyncIterator[str]:
    """사용자 메시지를 보내고 봇 응답을 **토큰 단위로 스트리밍**한다(AC1·AC2, Story 7.4).

    7.3 ``send_message``(비스트리밍 ``invoke``)와 동일한 그래프·thread·롤백 규약을 공유하되,
    ``g.astream(..., stream_mode="messages")``로 노드 내부 LLM 토큰을 델타 단위로 소비한다.
    LangGraph messages 모드는 모델이 스트리밍(``_stream``/``_astream``)을 지원하면 sync ``invoke``
    노드에서도 토큰 chunk를 콜백으로 캡처한다(착수 전 스파이크로 실증 — graph.py 무변경).

    필터: ``metadata["langgraph_node"] == "call_model"`` & ``isinstance(chunk, AIMessageChunk)``.
    비스트리밍 모델이 방출하는 완성 메시지는 플레인 ``AIMessage``라 자연 제외된다(``AIMessageChunk``
    는 ``AIMessage`` 하위클래스 — 반드시 chunk 타입으로 좁혀야 한다). 빈 델타는 건너뛴다.

    ★실패 turn 롤백(AC4 무결성 — [[langgraph-failed-turn-input-rollback]] 스트리밍 경로 회수):
    LangGraph는 ``call_model`` 노드 실행 **전에** 입력 HumanMessage를 체크포인트에 영속하므로,
    첫 토큰 전 실패든 스트림 도중 실패든 정규화 전에 명시 id로 이 turn 입력을 제거하지 않으면 같은
    텍스트 재전송 시 user 메시지가 중복 누적된다(``send_message``와 동형 — async ``aupdate_state``).
    """
    g = graph if graph is not None else get_graph()
    provider_name = provider if provider is not None else get_settings().LLM_PROVIDER
    # 네이티브 예외 튜플을 미리 해석(미등록 프로바이더면 여기서 LLMConfigurationError — 설정 문제).
    native_exceptions = get_provider_spec(provider_name).native_exceptions
    config: RunnableConfig = {
        # user_coords: 챗봇 "내 주변" 반경 검색용 사용자 좌표(없으면 None) — 툴이 config에서 읽는다.
        "configurable": {"thread_id": thread_id, "user_coords": coords},
        "recursion_limit": _RECURSION_LIMIT,  # react 툴콜 폭주 조기 차단(리뷰 D2)
    }
    # 입력에 명시 id를 부여 — 노드 실패 시 이 turn 입력만 정확히 롤백하기 위함(아래 except).
    message_id = str(uuid.uuid4())
    try:
        async for chunk, raw_metadata in g.astream(
            {"messages": [HumanMessage(content=user_text, id=message_id)]},
            config,
            stream_mode="messages",
        ):
            # astream(messages) 항목은 (chunk, metadata) 튜플 — 동적 표면이라 cast로 좁힌다.
            metadata = cast("dict[str, Any]", raw_metadata)
            # call_model 노드의 LLM 토큰 chunk만 통과(타 노드·완성 AIMessage·tool 메시지 제외).
            if metadata.get("langgraph_node") != "call_model":
                continue
            if not isinstance(chunk, AIMessageChunk):
                continue
            delta = _content_to_str(chunk.content)
            if delta:  # 빈 델타(메타데이터-only chunk 등) skip
                yield delta
    except native_exceptions as exc:  # LLM 업스트림 실패만 좁혀 정규화(7.1 규약)
        # 실패한 turn의 입력 HumanMessage를 thread에서 제거 — 재전송 시 중복 누적 차단(AC4 무결성).
        # checkpointer가 없는(비영속) 그래프면 남을 상태도 없으므로 롤백은 best-effort다.
        try:
            await g.aupdate_state(config, {"messages": [RemoveMessage(id=message_id)]})
        except Exception:  # noqa: BLE001 — 롤백 실패가 정규화 에러를 가리지 않게 흡수
            pass
        raise normalize_llm_error(exc, provider_name) from exc


def get_transcript(
    thread_id: str, *, graph: ChatGraph | None = None
) -> list[dict[str, str]]:
    """현재 thread의 메시지 이력을 ``{role, content}`` 리스트로 반환한다(재수화용, AC4).

    빈 thread는 ``[]``. system/tool 메시지는 표시 대상이 아니라 건너뛴다(user/assistant만).
    """
    g = graph if graph is not None else get_graph()
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    snapshot = g.get_state(config)
    messages: list[BaseMessage] = snapshot.values.get("messages", []) if snapshot.values else []
    transcript: list[dict[str, str]] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            # ★react 첫 패스 tool_call AIMessage는 content가 비어 있다(검색 의사만 담은 중간
            # 메시지). 이를 ``{"role":"assistant","content":""}``로 재수화 transcript에 새지 않게
            # **빈 content만** 기준으로 제외한다(7.5 Task 6 회귀 가드). tool_calls 보유 자체로는
            # 거르지 않는다 — 멀티 LLM(7.1) 중 일부는 한 메시지에 답변 content와 tool_calls를 함께
            # 방출하므로, 그 경우 사용자-노출 답변이 transcript에서 누락되면 안 된다(리뷰 P2).
            if not _content_to_str(message.content).strip():
                continue
            role = "assistant"
        else:
            continue  # system/tool 등은 표시 transcript에서 제외
        transcript.append({"role": role, "content": _content_to_str(message.content)})
    return transcript


def reset_session(thread_id: str, *, graph: ChatGraph | None = None) -> None:
    """해당 thread의 checkpointer 상태를 폐기한다(로그아웃 초기화, AC5). 멱등(없는 thread=no-op).

    ``delete_thread``는 컴파일된 그래프가 아니라 checkpointer(MemorySaver)에 있다. checkpointer가
    없는(비영속) 그래프면 폐기할 상태도 없으므로 no-op.
    """
    g = graph if graph is not None else get_graph()
    checkpointer = g.checkpointer
    # checkpointer는 bool | BaseCheckpointSaver(컴파일 옵션에 따라). 실 saver일 때만 폐기한다.
    if isinstance(checkpointer, BaseCheckpointSaver):
        checkpointer.delete_thread(thread_id)
