"""react(툴콜) 그래프 배선 단위 테스트 (Story 7.5 — Task 3·6, 네트워크/실키/DB 불필요).

검증 항목(react 플럼빙 — 분기 의미 검증은 라이브 골든셋 test_golden_set.py 소유):
  (분기 a) tool_call → ToolNode가 근거 회수 → 모델 재투입 → 근거 기반 최종 답변(2-패스)
  (분기 b) 툴이 "관련 근거 없음" 반환 → 모델이 모름 답변(react 경로는 동일, 답변만 다름)
  (Task 6) react 첫 패스 빈 tool_call AIMessage는 스트림 델타에 새지 않는다(if delta: 필터)
  (Task 6) react 첫 패스 빈 tool_call AIMessage는 get_transcript 재수화에 새지 않는다

페이크 모델이 직접 tool_call을 결정한다(``bind_tools``는 self 반환 — 실 바인딩 무관). ToolNode가
실행하는 실제 ``search_service_docs``는 ``search_documents``/``_get_embedder``를 monkeypatch 해
DB·키 없이 돌린다(검색 위임 — 툴은 얇다).
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.chat_models import generate_from_stream
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from pydantic import ConfigDict, Field

from app.chatbot import service
from app.chatbot import tools as tools_mod
from app.chatbot.graph import build_graph
from app.chatbot.models import DocumentChunk
from app.rooms.schemas import RoomListItem


# ── 페이크 모델: 첫 호출=tool_call, ToolMessage 본 뒤=최종 답변 ─────────────────
class _ToolCallingFakeModel:
    """비스트리밍 react 페이크(``invoke``). 첫 호출은 tool_call(빈 content), 둘째는 답변."""

    def __init__(self, query: str, answer: str) -> None:
        self._query = query
        self._answer = answer
        self.calls: list[list[Any]] = []

    def bind_tools(self, tools: Any, **kwargs: Any) -> _ToolCallingFakeModel:
        return self  # 페이크가 자체적으로 tool_call을 결정(실 바인딩 무관)

    def invoke(self, messages: list[Any], *args: Any, **kwargs: Any) -> AIMessage:
        self.calls.append(list(messages))
        if any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content=self._answer)  # 근거 재투입 후 최종 답변
        return AIMessage(
            content="",
            tool_calls=[
                {"name": "search_service_docs", "args": {"query": self._query}, "id": "c1"}
            ],
        )


class _ToolCallingStreamingFakeModel(BaseChatModel):
    """스트리밍 react 페이크(``_stream``). 첫 패스=tool_call chunk(빈 content), 둘째=답변 토큰."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    answer_tokens: list[str] = Field(default_factory=list)
    tool_query: str = "질의"

    def bind_tools(self, tools: Any, **kwargs: Any) -> _ToolCallingStreamingFakeModel:
        return self

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        if any(isinstance(m, ToolMessage) for m in messages):
            for tok in self.answer_tokens:
                chunk = ChatGenerationChunk(message=AIMessageChunk(content=tok))
                if run_manager is not None:
                    run_manager.on_llm_new_token(tok, chunk=chunk)
                yield chunk
        else:
            # tool_call chunk — content는 비어 있다(검색 의사만). if delta: 필터에 자연 제외돼야 함.
            tc = tool_call_chunk(
                name="search_service_docs",
                args=json.dumps({"query": self.tool_query}),
                id="c1",
                index=0,
            )
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[tc]))

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return generate_from_stream(
            self._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
        )

    @property
    def _llm_type(self) -> str:
        return "toolcalling-streaming-fake"


def _chunk(source_path: str, content: str) -> DocumentChunk:
    return DocumentChunk(
        source_path=source_path,
        content_hash="h",
        chunk_index=0,
        content=content,
        embedding=[0.0],
    )


@pytest.fixture
def grounded_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """search_service_docs가 근거를 회수하도록 검색을 패치(분기 a)."""
    monkeypatch.setattr(tools_mod, "_get_embedder", lambda: object())
    monkeypatch.setattr(
        tools_mod,
        "search_documents",
        lambda *a, **k: [(_chunk("faq.md", "환불은 이용 6시간 전까지 가능합니다."), 0.2)],
    )


@pytest.fixture
def empty_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """search_service_docs가 근거를 못 찾도록 검색을 패치(분기 b)."""
    monkeypatch.setattr(tools_mod, "_get_embedder", lambda: object())
    monkeypatch.setattr(tools_mod, "search_documents", lambda *a, **k: [])


def _collect(thread_id: str, text: str, graph: Any) -> list[str]:
    async def run() -> list[str]:
        return [d async for d in service.stream_message(thread_id, text, graph=graph)]

    return asyncio.run(run())


# ── (분기 a) 근거 회수 후 근거 기반 답변(2-패스 react) ───────────────────────
def test_branch_a_grounded_answer(auth_env: None, grounded_tool: None) -> None:
    fake = _ToolCallingFakeModel("환불 규정", "환불은 6시간 전까지 가능해요")
    graph = build_graph(model=fake)  # type: ignore[arg-type]

    reply = service.send_message("u1:device-aaaa-1111", "환불 규정 알려줘", graph=graph)

    assert reply == "환불은 6시간 전까지 가능해요"
    # 2-패스: 첫 호출(tool_call) + 둘째 호출(근거 재투입 후 답변).
    assert len(fake.calls) == 2
    # 둘째 호출 메시지에 ToolNode가 회수한 근거(ToolMessage)가 포함된다.
    tool_msgs = [m for m in fake.calls[1] if isinstance(m, ToolMessage)]
    assert tool_msgs and "환불은 이용 6시간 전까지 가능합니다." in tool_msgs[0].content


# ── (분기 b) 근거 없음 → 모름 경로(react 동일, 답변만 다름) ──────────────────
def test_branch_b_unknown_no_grounding(auth_env: None, empty_tool: None) -> None:
    fake = _ToolCallingFakeModel("미지의 질문", "그건 확인이 안 돼요.")
    graph = build_graph(model=fake)  # type: ignore[arg-type]

    reply = service.send_message("u1:device-aaaa-1111", "지구 인구 알려줘", graph=graph)

    assert reply == "그건 확인이 안 돼요."
    # 툴은 "관련 근거를 찾지 못했어요." 신호를 모델에 돌려준다(환각 유도 금지).
    tool_msgs = [m for m in fake.calls[1] if isinstance(m, ToolMessage)]
    assert tool_msgs and tool_msgs[0].content == tools_mod.NO_RELEVANT_DOCS


# ── (Task 6) react 첫 패스 빈 tool_call 청크는 스트림 델타에 새지 않는다 ──────
def test_stream_skips_empty_toolcall_chunk(auth_env: None, grounded_tool: None) -> None:
    fake = _ToolCallingStreamingFakeModel(
        answer_tokens=["환불은 ", "6시간 ", "전까지 ", "가능해요"], tool_query="환불 규정"
    )
    graph = build_graph(model=fake)  # type: ignore[arg-type]

    deltas = _collect("u1:device-aaaa-1111", "환불 규정 알려줘", graph)

    # 첫 패스 tool_call(빈 content)은 제외되고, 최종 답변 토큰만 흐른다(합=완성 답변).
    assert "" not in deltas
    assert "".join(deltas) == "환불은 6시간 전까지 가능해요"
    assert len(deltas) == 4


# ── (Task 6) react 첫 패스 빈 tool_call AIMessage는 transcript에 새지 않는다 ──
def test_transcript_excludes_empty_toolcall_message(
    auth_env: None, grounded_tool: None
) -> None:
    fake = _ToolCallingFakeModel("환불 규정", "환불은 6시간 전까지 가능해요")
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    thread_id = "u1:device-aaaa-1111"

    service.send_message(thread_id, "환불 규정 알려줘", graph=graph)
    transcript = service.get_transcript(thread_id, graph=graph)

    # 빈 tool_call AIMessage·ToolMessage는 제외 — user + 최종 assistant만 남는다.
    assert transcript == [
        {"role": "user", "content": "환불 규정 알려줘"},
        {"role": "assistant", "content": "환불은 6시간 전까지 가능해요"},
    ]


# ── (Story 7.6) 예약검색 툴이 같은 react 그래프에서 호출·회수·재투입된다 ──────
class _ReservationToolFakeModel:
    """예약검색 react 페이크. 첫 호출=search_available_rooms tool_call, ToolMessage 후=답변."""

    def __init__(self, region: str, answer: str) -> None:
        self._region = region
        self._answer = answer
        self.calls: list[list[Any]] = []

    def bind_tools(self, tools: Any, **kwargs: Any) -> _ReservationToolFakeModel:
        return self

    def invoke(self, messages: list[Any], *args: Any, **kwargs: Any) -> AIMessage:
        self.calls.append(list(messages))
        if any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content=self._answer)
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "search_available_rooms",
                    "args": {"region": self._region},
                    "id": "r1",
                }
            ],
        )


def test_branch_reservation_search_react(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 예약검색 툴이 의존하는 service reader/지역해석을 패치(DB·키 0). ToolNode가 실제 툴을 실행한다.
    room_id = uuid.uuid4()
    monkeypatch.setattr(tools_mod, "resolve_region", lambda name: "1168000000")
    monkeypatch.setattr(
        tools_mod,
        "search_rooms",
        lambda *a, **k: [
            RoomListItem(
                room_id=room_id,
                name="강남 스터디룸",
                price_per_hour=12000,
                room_type="private",
                amenities=["화이트보드"],
                remaining_slots=3,
            )
        ],
    )
    fake = _ReservationToolFakeModel("강남", "강남 스터디룸을 추천해요")
    graph = build_graph(model=fake)  # type: ignore[arg-type]

    reply = service.send_message("u1:device-aaaa-1111", "강남 빈 방 추천해줘", graph=graph)

    assert reply == "강남 스터디룸을 추천해요"
    # 2-패스: tool_call → ToolNode 회수 → 재투입 후 답변.
    assert len(fake.calls) == 2
    tool_msgs = [m for m in fake.calls[1] if isinstance(m, ToolMessage)]
    # ToolMessage에 후보 이름·상세 링크가 그라운딩 컨텍스트로 실린다.
    assert tool_msgs
    assert "강남 스터디룸" in tool_msgs[0].content
    assert f"/rooms/{room_id}" in tool_msgs[0].content


# ── (Story 7.7) 범위 밖 거절 — 툴콜 없는 최종 AIMessage → 곧장 END(툴 미경유) ──
_REJECT_COPY = "그건 제가 도와드리기 어려운 주제예요. 스터디룸 찾기나 예약은 얼마든지 도와드릴게요!"


class _NoToolFakeModel:
    """거절(범위 밖) 페이크. tool_call 없는 최종 AIMessage를 한 번 반환한다(``bind_tools``→self).

    잡담·서비스 무관 질문에 모델이 어떤 툴도 부르지 않는 "평범한 대화" 경로 그 자체 —
    ``tools_condition``이 마지막 AIMessage의 tool_calls 부재를 보고 곧장 END로 라우팅하므로
    ToolNode는 도달되지 않고, 모델은 **정확히 1회**만 호출된다(거절은 새 코드 경로가 아님).
    """

    def __init__(self, answer: str) -> None:
        self._answer = answer
        self.calls: list[list[Any]] = []

    def bind_tools(self, tools: Any, **kwargs: Any) -> _NoToolFakeModel:
        return self  # 바인딩돼도 페이크는 tool_call을 내지 않는다(거절 경로).

    def invoke(self, messages: list[Any], *args: Any, **kwargs: Any) -> AIMessage:
        self.calls.append(list(messages))
        return AIMessage(content=self._answer)  # tool_calls 없음 → tools_condition이 END


def test_branch_c_out_of_scope_reject_no_tool(auth_env: None) -> None:
    fake = _NoToolFakeModel(_REJECT_COPY)
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    thread_id = "u1:device-aaaa-1111"

    reply = service.send_message(thread_id, "오늘 서울 날씨 어때?", graph=graph)

    # 거절 카피가 그대로 반환된다(평문 텍스트 — 기존 채팅 렌더링으로 흐름).
    assert reply == _REJECT_COPY
    # 모델이 정확히 1회 호출됨 = ToolMessage 미생성, tools_condition이 곧장 END(툴 미경유).
    assert len(fake.calls) == 1
    assert not any(isinstance(m, ToolMessage) for call in fake.calls for m in call)
    # 거절은 정상 turn — 입력 롤백/중복 누적과 무관하게 transcript가 정상 적재된다.
    transcript = service.get_transcript(thread_id, graph=graph)
    assert transcript == [
        {"role": "user", "content": "오늘 서울 날씨 어때?"},
        {"role": "assistant", "content": _REJECT_COPY},
    ]


# ── (Story 8.4) ToolNode handle_tool_errors 정책 — 툴 내부 예외를 통제된 메시지로 치환 ──
def test_tool_error_replaced_with_controlled_message(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """툴 내부 예외(임베더 생성 실패 등)가 에러 원문이 아니라 통제된 메시지로 모델에 재투입된다.

    7.5 deferred L29 회수(Story 8.4): 기본 handle_tool_errors=True는 예외 문자열을 그대로
    ToolMessage로 재투입해 모델이 그라운딩 근거로 오인할 수 있다. 명시 정책으로 내부 사유를 숨기고
    "도구 오류"임을 알리는 고정 메시지로 치환한다. 페이크 툴이 raise하는 시나리오로 검증한다.
    """
    from app.chatbot.graph import _TOOL_ERROR_MESSAGE

    # 툴이 _get_embedder()에서 내부 예외를 던지게 한다(DB/키 오류 모사 — 내부 사유 포함).
    def _boom() -> object:
        raise RuntimeError("OPENAI_API_KEY 누락(내부 사유 — 모델/사용자에 노출 금지)")

    monkeypatch.setattr(tools_mod, "_get_embedder", _boom)
    fake = _ToolCallingFakeModel("환불 규정", "잠시 후 다시 시도해 주세요")
    graph = build_graph(model=fake)  # type: ignore[arg-type]

    reply = service.send_message("u1:device-aaaa-1111", "환불 규정 알려줘", graph=graph)

    assert reply == "잠시 후 다시 시도해 주세요"
    # 2-패스: tool_call → ToolNode가 예외를 통제된 메시지로 치환 → 재투입 후 답변.
    assert len(fake.calls) == 2
    tool_msgs = [m for m in fake.calls[1] if isinstance(m, ToolMessage)]
    assert tool_msgs
    # 에러 원문(내부 사유)이 아니라 통제된 고정 메시지가 재투입된다.
    assert tool_msgs[0].content == _TOOL_ERROR_MESSAGE
    assert "OPENAI_API_KEY" not in tool_msgs[0].content  # 내부 사유 미노출(NFR-6)
