"""챗봇 세션 서비스 단위 테스트 (Story 7.3 — AC3·AC4·AC5, 네트워크/실키 불필요).

검증 항목:
  (AC3) device_id 검증(빈/과길이/제어문자/구분자 거부) + thread_id 도출
  (AC3) 멀티턴 맥락 유지 — 같은 thread_id 2회 전송 시 2번째 invoke가 1번째 메시지를 포함(누적 실증)
  (AC4) thread 격리 — 다른 thread_id는 독립 이력
  (AC4) get_transcript 재수화(user/assistant role) — 빈 thread는 []
  (AC5) reset_session 후 transcript [](초기화 실증·멱등)
  (AC3) LLM 업스트림 예외 → LLM_PROVIDER_UNAVAILABLE(502) 정규화

페이크 모델은 ``.invoke``만 구현하는 덕타이핑 스파이로, 그래프 노드가 본 메시지 열을 기록한다
(7.2 store 주입 정신 — 네트워크/실키 없이 누적·격리를 실증).
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.chatbot import service
from app.chatbot.graph import build_graph
from app.chatbot.llm import get_provider_spec
from app.core.errors import DomainError, ErrorCode


class _RecordingFakeModel:
    """그래프 노드가 ``invoke``한 메시지 열을 기록하는 스파이(누적·격리 실증용)."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = iter(replies)
        self.calls: list[list[Any]] = []

    def invoke(self, messages: list[Any], *args: Any, **kwargs: Any) -> AIMessage:
        self.calls.append(list(messages))
        return AIMessage(content=next(self._replies))


class _RaisingFakeModel:
    """invoke 시 프로바이더 네이티브 예외를 던지는 페이크(에러 정규화 실증)."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def invoke(self, messages: list[Any], *args: Any, **kwargs: Any) -> AIMessage:
        raise self._exc


class _FlakyFakeModel:
    """첫 invoke는 네이티브 예외, 이후는 정상 응답(전송 실패→재전송 시뮬)."""

    def __init__(self, exc: BaseException, reply: str) -> None:
        self._exc = exc
        self._reply = reply
        self.calls = 0

    def invoke(self, messages: list[Any], *args: Any, **kwargs: Any) -> AIMessage:
        self.calls += 1
        if self.calls == 1:
            raise self._exc
        return AIMessage(content=self._reply)


def _human_texts(messages: list[Any]) -> list[str]:
    """메시지 열에서 HumanMessage content만 추출(누적 검증 보조)."""
    return [m.content for m in messages if isinstance(m, HumanMessage)]


# ── (AC3) device_id 검증 + thread_id 도출 ────────────────────────────────────
def test_derive_thread_id_format() -> None:
    user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    assert service.derive_thread_id(user_id, "device-abc-123") == f"{user_id}:device-abc-123"


def test_derive_thread_id_accepts_uuid_device() -> None:
    user_id = uuid.uuid4()
    device = str(uuid.uuid4())
    assert service.derive_thread_id(user_id, device) == f"{user_id}:{device}"


@pytest.mark.parametrize(
    "bad_device",
    [
        "",  # 빈값
        "short",  # 8자 미만
        "x" * 129,  # 과길이
        "has space",  # 공백
        "ctrl\x00char",  # 제어문자
        "user:evil",  # 구분자(:) — thread_id 오염 차단
        "한글디바이스",  # 비ASCII
    ],
)
def test_validate_device_id_rejects_invalid(bad_device: str) -> None:
    with pytest.raises(DomainError) as exc_info:
        service.validate_device_id(bad_device)
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    assert exc_info.value.status_code == 422


# ── (AC3) 멀티턴 맥락 유지 ────────────────────────────────────────────────────
def test_multi_turn_context_retained(auth_env: None) -> None:
    fake = _RecordingFakeModel(["첫 응답이에요", "두 번째 응답이에요"])
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    thread_id = "u1:device-aaaa-1111"

    reply1 = service.send_message(thread_id, "환불 규정 알려줘", graph=graph)
    reply2 = service.send_message(thread_id, "그럼 취소는?", graph=graph)

    assert reply1 == "첫 응답이에요"
    assert reply2 == "두 번째 응답이에요"
    # 2번째 invoke가 1번째 사용자 메시지를 포함해야 한다(checkpointer 누적 — 함정 #1 회귀 고정).
    assert _human_texts(fake.calls[0]) == ["환불 규정 알려줘"]
    assert _human_texts(fake.calls[1]) == ["환불 규정 알려줘", "그럼 취소는?"]


# ── (AC4) thread 격리 ────────────────────────────────────────────────────────
def test_thread_isolation(auth_env: None) -> None:
    fake = _RecordingFakeModel(["A응답", "B응답"])
    graph = build_graph(model=fake)  # type: ignore[arg-type]

    service.send_message("u1:device-aaaa-1111", "A의 질문", graph=graph)
    service.send_message("u2:device-bbbb-2222", "B의 질문", graph=graph)

    # 다른 thread는 독립 이력 — B 호출이 A의 메시지를 포함하지 않는다.
    assert _human_texts(fake.calls[1]) == ["B의 질문"]


# ── (AC4) get_transcript 재수화 ──────────────────────────────────────────────
def test_get_transcript_empty_thread_returns_empty(auth_env: None) -> None:
    fake = _RecordingFakeModel([])
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    assert service.get_transcript("u1:never-talked-1", graph=graph) == []


def test_get_transcript_rehydrates_roles(auth_env: None) -> None:
    fake = _RecordingFakeModel(["안녕하세요, 룸메이트예요"])
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    thread_id = "u1:device-aaaa-1111"

    service.send_message(thread_id, "안녕", graph=graph)
    transcript = service.get_transcript(thread_id, graph=graph)

    assert transcript == [
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "안녕하세요, 룸메이트예요"},
    ]


# ── (AC5) reset_session 초기화 ───────────────────────────────────────────────
def test_reset_session_clears_transcript(auth_env: None) -> None:
    fake = _RecordingFakeModel(["응답"])
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    thread_id = "u1:device-aaaa-1111"

    service.send_message(thread_id, "질문", graph=graph)
    assert service.get_transcript(thread_id, graph=graph)  # 비어있지 않음

    service.reset_session(thread_id, graph=graph)
    assert service.get_transcript(thread_id, graph=graph) == []  # 초기화


def test_reset_session_is_idempotent(auth_env: None) -> None:
    fake = _RecordingFakeModel([])
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    # 없는 thread 폐기도 no-op(예외 없음).
    service.reset_session("u1:never-existed-1", graph=graph)


# ── (AC3) LLM 업스트림 예외 정규화 ───────────────────────────────────────────
def test_llm_error_normalized_to_provider_unavailable(auth_env: None) -> None:
    # 기본 프로바이더(openai)의 네이티브 예외 root를 던지면 502로 정규화돼야 한다(비밀 미노출).
    native_exc_cls = get_provider_spec("openai").native_exceptions[0]
    fake = _RaisingFakeModel(native_exc_cls("upstream failed api_key=sk-LEAK-999"))
    graph = build_graph(model=fake)  # type: ignore[arg-type]

    with pytest.raises(DomainError) as exc_info:
        service.send_message("u1:device-aaaa-1111", "질문", graph=graph)

    assert exc_info.value.code == ErrorCode.LLM_PROVIDER_UNAVAILABLE
    assert exc_info.value.status_code == 502
    assert "sk-LEAK-999" not in exc_info.value.message  # 비밀 미노출


def test_failed_turn_input_rolled_back_no_duplicate_on_retry(auth_env: None) -> None:
    """전송 실패 시 입력을 롤백 — 같은 텍스트 재전송 시 중복 누적 금지(AC4 무결성).

    LangGraph는 노드 실패 전 입력을 체크포인트에 영속하므로, 롤백이 없으면 재전송 시 user 메시지가
    thread에 두 번 쌓인다(code-review 2026-06-17 재현 확정 → 회귀 고정).
    """
    native_exc_cls = get_provider_spec("openai").native_exceptions[0]
    fake = _FlakyFakeModel(native_exc_cls("upstream boom"), "이제 답했어요")
    graph = build_graph(model=fake)  # type: ignore[arg-type]
    thread_id = "u1:device-aaaa-1111"

    with pytest.raises(DomainError):  # 1차 전송 — LLM 실패(502 정규화)
        service.send_message(thread_id, "환불 규정 알려줘", graph=graph)

    reply = service.send_message(thread_id, "환불 규정 알려줘", graph=graph)  # 2차 재전송 성공
    assert reply == "이제 답했어요"

    transcript = service.get_transcript(thread_id, graph=graph)
    users = [m for m in transcript if m["role"] == "user"]
    assert len(users) == 1  # 실패 turn 입력이 롤백돼 중복 누적 없음
    assert users[0]["content"] == "환불 규정 알려줘"
