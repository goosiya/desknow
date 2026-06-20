"""chatbot 라우터 통합 테스트 (Story 7.3·7.4 — AC3·AC4·AC5·AC6 + 스트리밍, DB/네트워크/실키 불필요).

``TestClient(app)``(모듈 레벨, lifespan 미실행 — 1.4 불변식) + 실 access 토큰으로 인증을 검증한다.
프로세스 **싱글톤 그래프**(``app.chatbot.graph._graph``)에 페이크 모델을 주입해, 라우터가 요청마다
그래프를 재생성하지 않고 요청 간 메모리를 공유함(멀티턴)을 실증한다(핵심 함정 #1 회귀 고정).

검증 항목:
  (AC6) 미인증 401 — 4 엔드포인트 전부(POST messages·GET·DELETE·POST stream)
  (AC3) POST → reply 반환, **같은 thread 2요청 맥락 유지**(싱글톤 메모리 공유)
  (AC4) GET → transcript 재수화
  (AC5) DELETE → 204, 이후 GET 빈 이력(초기화)
  (7.4 AC1·AC2) POST /stream → SSE 토큰 프레임(data: {delta}) + event: done, 싱글톤 멀티턴
  (7.4 AC4) LLM 실패 → event: error(code=LLM_PROVIDER_UNAVAILABLE) 인밴드
  (7.4 AC2·L129) 프레이밍 견고성 — 토큰에 \n·공백·[DONE] 섞여도 클라가 정확 재조립
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from app.chatbot import graph as graph_module
from app.chatbot.graph import build_graph
from app.core.security import create_access_token
from app.main import app
from tests.chatbot.test_chatbot_stream import _StreamingFakeModel

client = TestClient(app)

_DEVICE_ID = "device-aaaa-1111"


class _RecordingFakeModel:
    """요청 간 호출을 기록하는 스파이(싱글톤 메모리 공유·누적 실증). 응답은 호출 순서대로 반환."""

    def __init__(self) -> None:
        self.calls: list[list[Any]] = []
        self._turn = 0

    def invoke(self, messages: list[Any], *args: Any, **kwargs: Any) -> AIMessage:
        self.calls.append(list(messages))
        self._turn += 1
        return AIMessage(content=f"응답{self._turn}")


@pytest.fixture
def fake_graph(auth_env: None) -> Iterator[_RecordingFakeModel]:
    """싱글톤 그래프에 페이크 모델 백엔드 그래프를 주입하고 끝나면 복원한다(테스트 격리).

    ``auth_env``로 settings(LLM_PROVIDER 도출·get_provider_spec)를 갖춘다. 라우터는 graph 인자
    없이 ``get_graph()``(싱글톤)를 쓰므로, 모듈 전역 ``_graph``를 페이크 백엔드로 교체한다.
    """
    fake = _RecordingFakeModel()
    saved = graph_module._graph
    graph_module._graph = build_graph(model=fake)  # type: ignore[arg-type]
    try:
        yield fake
    finally:
        graph_module._graph = saved


def _token() -> str:
    return create_access_token(uuid.uuid4(), "booker")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── (AC6) 미인증 401 — 3 엔드포인트 ──────────────────────────────────────────
def test_post_messages_requires_auth() -> None:
    res = client.post(
        "/api/v1/chatbot/messages",
        json={"message": "안녕", "device_id": _DEVICE_ID},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_get_messages_requires_auth() -> None:
    res = client.get("/api/v1/chatbot/messages", params={"device_id": _DEVICE_ID})
    assert res.status_code == 401


def test_delete_session_requires_auth() -> None:
    res = client.delete("/api/v1/chatbot/session", params={"device_id": _DEVICE_ID})
    assert res.status_code == 401


# ── (AC3) POST → reply + 싱글톤 멀티턴 맥락 유지 ─────────────────────────────
def test_post_returns_reply(fake_graph: _RecordingFakeModel) -> None:
    token = _token()
    res = client.post(
        "/api/v1/chatbot/messages",
        json={"message": "환불 규정?", "device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["reply"] == "응답1"
    assert body["thread_id"].endswith(f":{_DEVICE_ID}")


def test_singleton_graph_retains_context_across_requests(
    fake_graph: _RecordingFakeModel,
) -> None:
    # 같은 사용자(토큰)·디바이스 = 같은 thread → 두 요청이 메모리를 공유해야 한다(요청마다 그래프
    # 재생성 시 맥락 유실 — 함정 #1). 두 번째 invoke가 첫 메시지를 포함함을 실증.
    token = _token()
    client.post(
        "/api/v1/chatbot/messages",
        json={"message": "첫 질문", "device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    client.post(
        "/api/v1/chatbot/messages",
        json={"message": "두 번째 질문", "device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    human_texts_turn2 = [
        m.content for m in fake_graph.calls[1] if isinstance(m, HumanMessage)
    ]
    assert human_texts_turn2 == ["첫 질문", "두 번째 질문"]


# ── (AC4) GET 재수화 ─────────────────────────────────────────────────────────
def test_get_transcript_after_post(fake_graph: _RecordingFakeModel) -> None:
    token = _token()
    client.post(
        "/api/v1/chatbot/messages",
        json={"message": "안녕", "device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    res = client.get(
        "/api/v1/chatbot/messages",
        params={"device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    assert res.status_code == 200
    messages = res.json()["messages"]
    assert messages == [
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "응답1"},
    ]


def test_get_transcript_empty_for_new_thread(fake_graph: _RecordingFakeModel) -> None:
    res = client.get(
        "/api/v1/chatbot/messages",
        params={"device_id": _DEVICE_ID},
        headers=_auth(_token()),
    )
    assert res.status_code == 200
    assert res.json()["messages"] == []


# ── (AC5) DELETE → 204 → 이후 GET 빈 이력(초기화) ────────────────────────────
def test_delete_session_resets_conversation(fake_graph: _RecordingFakeModel) -> None:
    token = _token()  # 같은 토큰 = 같은 user_id → 같은 thread
    client.post(
        "/api/v1/chatbot/messages",
        json={"message": "안녕", "device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    del_res = client.delete(
        "/api/v1/chatbot/session",
        params={"device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    assert del_res.status_code == 204

    get_res = client.get(
        "/api/v1/chatbot/messages",
        params={"device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    assert get_res.json()["messages"] == []  # 초기화됨


# ── 입력 검증(device_id 형식) ────────────────────────────────────────────────
def test_post_rejects_invalid_device_id(fake_graph: _RecordingFakeModel) -> None:
    res = client.post(
        "/api/v1/chatbot/messages",
        json={"message": "안녕", "device_id": "bad:id"},
        headers=_auth(_token()),
    )
    assert res.status_code == 422


def test_post_rejects_empty_message(fake_graph: _RecordingFakeModel) -> None:
    res = client.post(
        "/api/v1/chatbot/messages",
        json={"message": "", "device_id": _DEVICE_ID},
        headers=_auth(_token()),
    )
    assert res.status_code == 422


# ── (7.4) 스트리밍 엔드포인트 ────────────────────────────────────────────────
@pytest.fixture
def streaming_fake_graph(auth_env: None) -> Iterator[_StreamingFakeModel]:
    """싱글톤 그래프에 스트리밍 페이크(``_stream`` 구현)를 주입한다.

    ``turns``/``exc``/``fail_at``은 ``_stream`` 호출 시점에 lazy 읽기라, 테스트가 post 전에 fake를
    구성할 수 있다. 라우터는 graph 인자 없이 ``get_graph()``(싱글톤)를 쓰므로 모듈 전역을 교체한다.
    """
    fake = _StreamingFakeModel()
    saved = graph_module._graph
    graph_module._graph = build_graph(model=fake)  # type: ignore[arg-type]
    try:
        yield fake
    finally:
        graph_module._graph = saved


def _parse_sse(text: str) -> list[dict[str, str]]:
    """SSE 응답 본문을 [{event, data}] 프레임 리스트로 파싱한다.

    JSON 인코딩(deferred L129 회수) 덕에 ``data``는 항상 단일 라인이다(델타의 \\n은 \\\\n으로
    이스케이프 — 실제 개행이 프레임을 깨지 않는다). 라인 종결자 차이(\\r\\n/\\n)는 정규화한다.
    """
    events: list[dict[str, str]] = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        if not block.strip():
            continue
        frame = {"event": "message", "data": ""}
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                frame["event"] = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        frame["data"] = "\n".join(data_lines)
        events.append(frame)
    return events


def test_stream_requires_auth() -> None:
    res = client.post(
        "/api/v1/chatbot/stream",
        json={"message": "안녕", "device_id": _DEVICE_ID},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_stream_emits_delta_frames_and_done(streaming_fake_graph: _StreamingFakeModel) -> None:
    streaming_fake_graph.turns = [["환불은 ", "24시간 ", "전까지 ", "가능해요"]]
    res = client.post(
        "/api/v1/chatbot/stream",
        json={"message": "환불 규정?", "device_id": _DEVICE_ID},
        headers=_auth(_token()),
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    frames = _parse_sse(res.text)
    deltas = [json.loads(f["data"])["delta"] for f in frames if f["event"] == "message"]
    assert len(deltas) > 1  # 토큰 단위
    assert "".join(deltas) == "환불은 24시간 전까지 가능해요"
    # 정상 종료 신호(event: done) 존재, error 프레임 없음.
    assert any(f["event"] == "done" for f in frames)
    assert all(f["event"] != "error" for f in frames)


def test_stream_singleton_retains_context(streaming_fake_graph: _StreamingFakeModel) -> None:
    # 같은 토큰·디바이스 = 같은 thread → 두 스트림이 메모리 공유(요청마다 재생성 시 유실 — 함정 #1).
    streaming_fake_graph.turns = [["첫 ", "응답"], ["둘째 ", "응답"]]
    token = _token()
    client.post(
        "/api/v1/chatbot/stream",
        json={"message": "첫 질문", "device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    client.post(
        "/api/v1/chatbot/stream",
        json={"message": "두 번째 질문", "device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    # 2번째 노드 호출이 1번째 사용자 메시지를 포함(checkpointer 누적).
    human_texts_turn2 = [
        m.content for m in streaming_fake_graph.recorded[1] if isinstance(m, HumanMessage)
    ]
    assert human_texts_turn2 == ["첫 질문", "두 번째 질문"]


def test_stream_completed_turn_persisted_for_rehydration(
    streaming_fake_graph: _StreamingFakeModel,
) -> None:
    # 스트림 완료 후 GET 재수화 시 완성 AI 메시지가 일관 보존된다(AC2).
    streaming_fake_graph.turns = [["안녕", "하세요"]]
    token = _token()
    client.post(
        "/api/v1/chatbot/stream",
        json={"message": "안녕", "device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    res = client.get(
        "/api/v1/chatbot/messages",
        params={"device_id": _DEVICE_ID},
        headers=_auth(token),
    )
    assert res.json()["messages"] == [
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "안녕하세요"},
    ]


def test_stream_llm_failure_emits_error_event(
    streaming_fake_graph: _StreamingFakeModel,
) -> None:
    from app.chatbot.llm import get_provider_spec

    native_exc_cls = get_provider_spec("openai").native_exceptions[0]
    streaming_fake_graph.turns = [["x"]]
    streaming_fake_graph.exc = native_exc_cls("upstream boom")
    streaming_fake_graph.fail_at = 0  # 첫 토큰 전 실패
    res = client.post(
        "/api/v1/chatbot/stream",
        json={"message": "질문", "device_id": _DEVICE_ID},
        headers=_auth(_token()),
    )
    # 스트림 시작 후엔 200(헤더 송신됨) — 실패는 인밴드 event: error.
    assert res.status_code == 200
    frames = _parse_sse(res.text)
    error_frames = [f for f in frames if f["event"] == "error"]
    assert len(error_frames) == 1
    payload = json.loads(error_frames[0]["data"])
    assert payload["code"] == "LLM_PROVIDER_UNAVAILABLE"


def test_stream_framing_robust_to_special_chars(
    streaming_fake_graph: _StreamingFakeModel,
) -> None:
    # 토큰에 개행·공백·리터럴 [DONE]이 섞여도 JSON 인코딩 프레이밍이 깨지지 않고 정확 재조립된다
    # (deferred-work L129 회수 — 스파이크 공백분할/[DONE] 결함 차단). 회귀 고정.
    payload = ["줄1\n줄2", "  ", "[DONE]", " 끝"]
    streaming_fake_graph.turns = [payload]
    res = client.post(
        "/api/v1/chatbot/stream",
        json={"message": "질문", "device_id": _DEVICE_ID},
        headers=_auth(_token()),
    )
    assert res.status_code == 200
    frames = _parse_sse(res.text)
    deltas = [json.loads(f["data"])["delta"] for f in frames if f["event"] == "message"]
    assert "".join(deltas) == "줄1\n줄2  [DONE] 끝"  # 무손실 재조립
    assert any(f["event"] == "done" for f in frames)
