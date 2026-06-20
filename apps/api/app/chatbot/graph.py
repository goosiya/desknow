"""LangGraph 챗봇 그래프 + 인메모리 checkpointer (Story 7.3 → 7.5 react 확장).

"어느 화면에서나 열어 맥락이 이어지는 대화"를 동작시키는 코어다. 7.5에서 **문서검색 RAG**를
얹기 위해 단일 노드 그래프를 **react(툴콜) 패턴**으로 최소 확장했다.

★설계:

- ``MessagesState`` 기반 ``StateGraph``. ``call_model`` 노드는 7.1 ``create_chat_model()``로 만든
  모델에 **문서검색 툴을 bind_tools** 한 뒤(if 분기·프로바이더 하드코딩 금지 — 7.1 규약) 시스템
  프롬프트를 prepend해 ``invoke``한다. ``add_messages`` 리듀서가 응답을 누적한다(멀티턴).
- **react 라우팅(7.5):** ``call_model →(tools_condition)→ tools → call_model`` / 또는 ``→ END``.
  모델이 **스스로 언제 문서를 검색할지 판단**한다(매 턴 무조건 검색 아님 — 7.6 예약툴·7.7 거절과
  한 그래프 공존 정합). ``tools`` 노드는 ``ToolNode``(langgraph.prebuilt)가 툴을 실행한다.
- ``checkpointer=MemorySaver()``(인메모리, MVP). ``thread_id``로 키잉해 같은 thread의 이전
  메시지를 자동 로드·누적한다.
- 스트리밍(``astream`` + SSE)은 7.4가 동일 그래프에 입힌다 — react 첫 패스(tool_call) AIMessage는
  content가 비어 ``stream_message``의 ``if delta:`` 필터에 자연 제외되고, 둘째 패스(최종 답변)
  토큰만 흐른다(불변식 보존 — service.py).

★함정 #1 — 그래프·MemorySaver는 **프로세스 싱글톤**(모듈 레벨 1회 생성, ``get_graph()`` lazy
accessor). 요청마다 새로 만들면 매 요청 메모리가 비어 맥락이 절대 유지되지 않는다(AC3/AC4 전면
실패). ★함정 #2 — MemorySaver는 프로세스 로컬이라 멀티워커/재시작 시 대화가 휘발한다. MVP는
단일 워커(Phase 0) 전제이며, 영속 PostgresSaver(재시작 내성)는 배포/스케일 defer다.

테스트는 ``build_graph(model=fake)``로 페이크 모델을 주입해 네트워크/실키 없이 검증한다(7.2 store
주입 정신과 동일). ``bind_tools``를 지원하지 않는 페이크는 ``_bind_tools``가 원본을 그대로 써
**툴 미호출 일반 대화 경로**로 자연 강등된다(기존 7.3/7.4 페이크 회귀 0).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.chatbot.llm import create_chat_model
from app.chatbot.prompts import build_system_prompt
from app.chatbot.tools import search_available_rooms, search_service_docs

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage
    from langgraph.graph.state import CompiledStateGraph

    # 컴파일된 챗봇 그래프 별칭(4개 제네릭 StateT·ContextT·InputT·OutputT — 구체화 불요).
    ChatGraph = CompiledStateGraph[Any, Any, Any, Any]

logger = logging.getLogger(__name__)

# 그래프에 바인딩하는 툴 목록(단일 출처). 7.5 문서검색 + 7.6 예약검색이 한 react 그래프에 공존
# 한다 — 모델이 질문 유형에 맞는 툴을 스스로 고른다(if 분기·프로바이더 하드코딩 금지). 7.7 거절
# 가드는 프롬프트로 협력 추가된다(툴 아님).
_TOOLS = [search_service_docs, search_available_rooms]

# 툴 내부 예외 발생 시 모델에 재투입할 **통제된 메시지**(7.5 deferred L29 회수 — Story 8.4).
# 내부 사유(DB 단절·get_engine 오류·임베딩 실패 스택)는 노출하지 않고, 이것이 "검색 결과"가 아니라
# "도구 오류"임을 모델이 알도록 명시한다 — 그래야 에러 문자열을 그라운딩 근거로 오인해 환각하지
# 않고, 사용자에게 "잠시 후 다시 시도"하라고 안내한다(NFR-6 키/내부 격리).
_TOOL_ERROR_MESSAGE = (
    "문서/예약 검색 도구를 일시적으로 사용할 수 없습니다. 이것은 검색 결과가 아니라 도구 오류이니, "
    "근거로 삼지 말고 사용자에게 잠시 후 다시 시도하도록 안내하세요."
)


def _handle_tool_error(exc: Exception) -> str:
    """ToolNode가 흡수한 툴 내부 예외를 통제된 메시지로 치환한다(내부 사유 미노출 — 함정 #6).

    기본 ``handle_tool_errors=True``는 예외 문자열을 그대로 ToolMessage로 모델에 재투입해 모델이
    그것을 그라운딩 근거로 오인할 수 있다(7.5 defer L29). 여기서는 원문 대신 고정 메시지를 돌려주고
    내부 예외는 로그로만 남긴다(관측성 확보 + 사용자/모델에는 미노출).
    """
    logger.warning("챗봇 툴 실행 중 예외 — 통제된 메시지로 치환합니다.", exc_info=exc)
    return _TOOL_ERROR_MESSAGE


def _bind_tools(model: BaseChatModel) -> Any:
    """모델이 툴 바인딩을 지원하면 ``_TOOLS``를 바인딩하고, 아니면 원본을 반환한다.

    프로바이더 분기가 아니라 **'툴콜 능력 유무' 가드**다 — 운영 모델(ChatOpenAI 등 7.1 어댑터)은
    항상 바인딩돼 react가 동작하고, ``bind_tools`` 미구현/미지원 페이크(7.3/7.4 단위 테스트)는
    ``NotImplementedError``/``AttributeError``를 흡수해 **툴 없는 일반 대화 경로**로 강등된다
    (기존 페이크 회귀 0 — Task 6). 이때 모델은 tool_calls를 내지 않으므로 ``tools_condition``이
    곧장 END로 분기해 ``tools`` 노드는 도달되지 않는다.
    """
    try:
        return model.bind_tools(_TOOLS)
    except (NotImplementedError, AttributeError):
        # 페이크(테스트)는 의도된 강등 경로지만, 운영 모델이 여기 오면 툴 바인딩 버그로 RAG가
        # 말없이 비활성되는 것이라 경고로 남긴다(동작·페이크 호환 불변·관측성만 확보 — 리뷰 D1).
        logger.warning(
            "모델이 bind_tools를 지원하지 않아 문서검색 RAG 없이 일반 대화로 강등됩니다 "
            "(운영 모델이면 툴 바인딩 버그 가능). model=%s",
            type(model).__name__,
        )
        return model


def build_graph(model: BaseChatModel | None = None) -> ChatGraph:
    """react 챗봇 그래프를 컴파일한다(테스트는 페이크 ``model`` 주입, 운영은 7.1 어댑터 기본값).

    ``model`` 미지정 시 ``create_chat_model()``(설정 ``LLM_PROVIDER``/``LLM_MODEL``)을 사용한다.
    페르소나 시스템 프롬프트는 **매 호출 prepend**하고 상태에 영속시키지 않는다 — 7.7이 프롬프트만
    바꿔도 과거 대화에 옛 프롬프트가 박제되지 않게 한다.
    """
    chat_model = model if model is not None else create_chat_model()
    bound_model = _bind_tools(chat_model)

    def call_model(state: MessagesState) -> dict[str, list[BaseMessage]]:
        # 매 호출마다 현재 KST 날짜를 주입한 시스템 프롬프트를 prepend한다(상대/부분 날짜 환산용 —
        # "오늘"·"내일"·"19일"을 정확한 ISO로 환산해 예약검색 툴에 넘기게 한다.
        # 영속 0 — 날짜 박제 방지).
        messages = [SystemMessage(content=build_system_prompt()), *state["messages"]]
        response = bound_model.invoke(messages)
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("call_model", call_model)
    # ToolNode에 handle_tool_errors 명시 정책(7.5 defer L29 회수) — 툴 내부 예외를 통제된 메시지로
    # 치환해 모델이 에러 원문을 "근거"로 오인·환각하지 않게 한다(기본 True의 원문 재투입을 교체).
    builder.add_node("tools", ToolNode(_TOOLS, handle_tool_errors=_handle_tool_error))
    builder.add_edge(START, "call_model")
    # tool_calls가 있으면 "tools" 노드로, 없으면 END로 분기(react). tools_condition은 마지막
    # AIMessage의 tool_calls 유무만 본다 — 페이크가 툴을 안 부르면 곧장 END.
    builder.add_conditional_edges("call_model", tools_condition)
    # 툴 회수 결과(ToolMessage)를 모델에 재투입해 근거 기반 최종 답변을 생성한다(둘째 패스).
    builder.add_edge("tools", "call_model")
    # checkpointer=MemorySaver()로 thread_id별 메시지 이력을 자동 로드·누적(멀티턴 맥락 유지).
    return builder.compile(checkpointer=MemorySaver())


# 프로세스 싱글톤(함정 #1). 모듈 레벨 lazy 생성 — 첫 요청에 1회 컴파일하고 이후 재사용한다.
_graph: ChatGraph | None = None


def get_graph() -> ChatGraph:
    """컴파일된 그래프 싱글톤을 반환한다(없으면 1회 생성). 요청마다 재생성 금지(함정 #1)."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
