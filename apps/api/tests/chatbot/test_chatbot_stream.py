"""챗봇 스트리밍 서비스 단위 테스트 (Story 7.4 — AC1·AC2·AC4, 네트워크/실키 불필요).

검증 항목:
  (AC1·AC2) 다중 델타 방출 — astream(messages)이 토큰 chunk를 여러 개 순서대로 yield(합=완성 응답)
  (AC1)     멀티턴 맥락 — 같은 thread 재스트림 시 2번째 노드 호출이 1번째 메시지 포함(checkpointer)
  (AC2)     스트림 완료 후 get_transcript가 양 turn 일관 보존(완성 AI 메시지 영속)
  (AC4)     실패 turn 롤백 — 첫 토큰 전/스트림 중 native 예외 → 502 정규화 + 입력 메시지 미잔존
  (AC4·L129) 프레이밍 견고성 토대 — 델타에 \n·공백·[DONE]이 섞여도 서비스는 그대로 통과(재조립용)

``pytest-asyncio`` 없이 ``asyncio.run``으로 async 제너레이터를 구동한다(신규 테스트 의존성 회피).
페이크 모델은 ``_stream``을 구현해 langgraph messages 모드가 토큰 chunk를 캡처하게 한다(착수 전
스파이크로 sync ``invoke`` 노드에서도 ``_stream`` 토큰이 방출됨을 실증).
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.chat_models import generate_from_stream
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from pydantic import ConfigDict, Field

from app.chatbot import service
from app.chatbot.graph import build_graph
from app.chatbot.llm import get_provider_spec
from app.core.errors import DomainError, ErrorCode


class _StreamingFakeModel(BaseChatModel):
    """``_stream``으로 토큰을 방출하는 페이크(astream messages 모드 토큰 캡처용).

    ``turns``는 호출(turn)별 델타 리스트다 — n번째 노드 호출은 ``turns[n]``(범위 초과 시 마지막)을
    토큰 단위로 흘린다. ``recorded``는 각 호출이 받은 메시지 열을 기록(멀티턴 누적 실증). ``exc``+
    ``fail_at``으로 native 예외 주입(fail_at=0=첫 토큰 전, n=n개 방출 후, len 이상=정상 방출 후).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    turns: list[list[str]] = Field(default_factory=list)
    recorded: list[list[BaseMessage]] = Field(default_factory=list)
    exc: BaseException | None = None
    fail_at: int = -1

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        self.recorded.append(list(messages))
        idx = len(self.recorded) - 1
        deltas = self.turns[idx] if idx < len(self.turns) else self.turns[-1]
        for i, delta in enumerate(deltas):
            if self.exc is not None and self.fail_at == i:
                raise self.exc
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=delta))
            if run_manager is not None:
                run_manager.on_llm_new_token(delta, chunk=chunk)
            yield chunk
        if self.exc is not None and self.fail_at >= len(deltas):
            raise self.exc

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        # 노드는 sync ``model.invoke``를 호출 → _generate가 _stream을 모아 완성 메시지로(콜백 토큰
        # 발화는 _stream이 담당 — langgraph messages 모드가 이를 캡처). 7.3 그래프 무변경 전제.
        return generate_from_stream(
            self._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
        )

    @property
    def _llm_type(self) -> str:
        return "streaming-fake"


def _human_texts(messages: list[BaseMessage]) -> list[str]:
    from langchain_core.messages import HumanMessage

    return [m.content for m in messages if isinstance(m, HumanMessage)]  # type: ignore[misc]


def _collect(thread_id: str, text: str, graph: Any) -> list[str]:
    """async 스트림을 동기적으로 소비해 델타 리스트를 반환(asyncio.run)."""

    async def run() -> list[str]:
        return [d async for d in service.stream_message(thread_id, text, graph=graph)]

    return asyncio.run(run())


# ── (AC1·AC2) 다중 델타 방출 ─────────────────────────────────────────────────
def test_streams_multiple_deltas(auth_env: None) -> None:
    fake = _StreamingFakeModel(turns=[["환불은 ", "24시간 ", "전까지 ", "가능해요"]])
    graph = build_graph(model=fake)  # type: ignore[arg-type]

    deltas = _collect("u1:device-aaaa-1111", "환불 규정?", graph)

    assert len(deltas) > 1  # 토큰 단위(단일 chunk 아님)
    assert "".join(deltas) == "환불은 24시간 전까지 가능해요"  # 합=완성 응답


# ── (AC1) 멀티턴 맥락 + (AC2) transcript 일관 보존 ───────────────────────────
def test_multi_turn_context_retained_streaming(auth_env: None) -> None:
    fake = _StreamingFakeModel(turns=[["첫 ", "응답"], ["둘째 ", "응답"]])
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    thread_id = "u1:device-aaaa-1111"

    reply1 = "".join(_collect(thread_id, "환불 규정 알려줘", graph))
    reply2 = "".join(_collect(thread_id, "그럼 취소는?", graph))

    assert reply1 == "첫 응답"
    assert reply2 == "둘째 응답"
    # 2번째 노드 호출이 1번째 사용자 메시지를 포함해야 한다(checkpointer 누적 — 함정 #1 회귀 고정).
    assert _human_texts(fake.recorded[0]) == ["환불 규정 알려줘"]
    assert _human_texts(fake.recorded[1]) == ["환불 규정 알려줘", "그럼 취소는?"]
    # 스트림 완료 후 transcript가 양 turn을 일관 보존(완성 AI 메시지 영속).
    transcript = service.get_transcript(thread_id, graph=graph)
    assert transcript == [
        {"role": "user", "content": "환불 규정 알려줘"},
        {"role": "assistant", "content": "첫 응답"},
        {"role": "user", "content": "그럼 취소는?"},
        {"role": "assistant", "content": "둘째 응답"},
    ]


# ── (AC4) 실패 turn 롤백 — 첫 토큰 전 실패(TTFT 실패) ────────────────────────
def test_failed_turn_before_first_token_rolled_back(auth_env: None) -> None:
    native_exc_cls = get_provider_spec("openai").native_exceptions[0]
    fake = _StreamingFakeModel(
        turns=[["never", " emitted"]], exc=native_exc_cls("boom api_key=sk-LEAK"), fail_at=0
    )
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    thread_id = "u1:device-aaaa-1111"

    with pytest.raises(DomainError) as exc_info:
        _collect(thread_id, "환불 규정 알려줘", graph)
    assert exc_info.value.code == ErrorCode.LLM_PROVIDER_UNAVAILABLE
    assert exc_info.value.status_code == 502
    assert "sk-LEAK" not in exc_info.value.message  # 비밀 미노출

    # 실패 turn 입력이 롤백돼 thread에 잔존하지 않는다(재전송 중복 차단 토대).
    transcript = service.get_transcript(thread_id, graph=graph)
    assert transcript == []


# ── (AC4) 실패 turn 롤백 — 스트림 도중 실패(부분 토큰 후) ────────────────────
def test_failed_turn_mid_stream_rolled_back(auth_env: None) -> None:
    native_exc_cls = get_provider_spec("openai").native_exceptions[0]
    fake = _StreamingFakeModel(
        turns=[["부분 ", "토큰 ", "그다음"]], exc=native_exc_cls("mid boom"), fail_at=2
    )
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    thread_id = "u1:device-aaaa-1111"

    received: list[str] = []

    async def run() -> None:
        async for d in service.stream_message(thread_id, "질문", graph=graph):
            received.append(d)

    with pytest.raises(DomainError):
        asyncio.run(run())

    # 실패 전 일부 델타는 수신됐다(스트림 도중 실패).
    assert received == ["부분 ", "토큰 "]
    # 실패 turn 입력은 롤백(부분 응답 turn은 thread에 영속되지 않음).
    assert service.get_transcript(thread_id, graph=graph) == []


# ── (AC4) 실패→재전송 시 user 메시지 중복 없음(메모 회수 — 회귀 고정) ────────
def test_no_duplicate_user_message_after_retry(auth_env: None) -> None:
    native_exc_cls = get_provider_spec("openai").native_exceptions[0]
    # 1번째 turn=첫 토큰 전 실패, 2번째 turn=정상 응답(재전송 성공 시뮬).
    fake = _StreamingFakeModel(
        turns=[["x"], ["이제 ", "답했어요"]], exc=native_exc_cls("boom"), fail_at=0
    )
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    thread_id = "u1:device-aaaa-1111"

    with pytest.raises(DomainError):  # 1차 — 실패
        _collect(thread_id, "환불 규정 알려줘", graph)

    # exc를 끄고 2차 재전송이 정상 방출되게 한다.
    fake.exc = None
    reply = "".join(_collect(thread_id, "환불 규정 알려줘", graph))
    assert reply == "이제 답했어요"

    transcript = service.get_transcript(thread_id, graph=graph)
    users = [m for m in transcript if m["role"] == "user"]
    assert len(users) == 1  # 실패 turn 입력 롤백 → 중복 누적 없음
    assert users[0]["content"] == "환불 규정 알려줘"


# ── (AC4·L129) 프레이밍 견고성 토대 — 오염 토큰도 서비스가 그대로 통과 ───────
def test_deltas_with_special_chars_pass_through(auth_env: None) -> None:
    # 토큰에 개행·공백·리터럴 [DONE]이 섞여도 서비스는 손실 없이 그대로 yield(SSE JSON 인코딩 전).
    payload = ["줄1\n줄2", "  ", "[DONE]", " 끝"]
    fake = _StreamingFakeModel(turns=[payload])
    graph = build_graph(model=fake)  # type: ignore[arg-type]

    deltas = _collect("u1:device-aaaa-1111", "질문", graph)

    assert "".join(deltas) == "줄1\n줄2  [DONE] 끝"
