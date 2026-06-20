"""골든셋 정확성 검증 (Story 7.5 → 7.7 c 분기 단언 완성 / SM-7, 라이브 DB+키 필요, 기본 skip).

근거있음(분기 a) + 근거없음(분기 b) + 범위 밖(분기 c) 질문 골든셋으로 **기대 분기 일치**를
단언한다. 실 Postgres(pgvector)·실 OpenAI 임베딩·실 LLM이 필요하므로
``test_ingest_integration.py``의 opt-in 스킵 패턴을 그대로 미러한다(``TEST_DATABASE_URL`` 미설정 시
자동 skip → CI 회귀 0, ``OPENAI_API_KEY`` 미설정 시 본 테스트 내부에서 skip).

흐름: 결정적 픽스처 코퍼스(``fixtures/golden_corpus/``)를 ``ingest_corpus``(7.2)로 실 임베딩
적재 → 실 react 그래프 invoke → 분기 a는 기대 근거 키워드 포함 + 모름 카피 **미포함**, 분기 b는
모름 시그널("확인이 안 돼요" 류) 포함, 분기 c(범위 밖)는 정중한 거절 시그널 포함(서비스 무관
질문에 근거 없는 답을 지어내지 않음)을 단언. 종료 시 적재 행을 정리한다.

범위 밖(c) 거절 가드는 7.7이 소유한다 — ``prompts.py``의 §범위 밖 거절 블록이 *서비스 무관*
질문을 어떤 툴도 부르지 않고 거절 카피로 안내하도록 못박고, 본 테스트가 그 c 분기를 단언한다
(7.5에서 구조만 마련, 7.7에서 단언 완성 — SM-7 최종 마감).
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
GOLDEN_CORPUS_DIR = FIXTURES_DIR / "golden_corpus"
GOLDEN_SET_PATH = FIXTURES_DIR / "golden_set.json"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL 미설정 — 라이브 DB 골든셋 테스트를 skip 합니다.",
)

# 모름/확인불가(분기 b) 시그널 — LLM 생성이라 자구 완전 일치는 강제 불가하므로 톤 시그널을
# 넓게 본다(Dev Notes §핵심 설계 3 — 자연어 유연성). 분기 b는 이 중 하나 이상을 포함해야 한다.
UNKNOWN_SIGNALS = (
    "확인이 안",
    "확인이 어려",
    "확인하기 어려",
    "확인되지 않",
    "확인할 수 없",
    "알 수 없",
    "찾지 못",
    "모르",
)


def _has_unknown_signal(text: str) -> bool:
    return any(sig in text for sig in UNKNOWN_SIGNALS)


# 범위 밖 거절(분기 c) 시그널 — 거절 카피는 LLM 생성이라 자구 완전 일치를 강제하지 않고 강건한
# 부분 문자열로 본다(Dev Notes §3). 정중한 거절 톤(예: "도와드리기 어려운")과 UX-DR10 다음 행동
# 제시("스터디룸 찾기나 예약")를 함께 담는다 — 분기 c는 이 중 하나 이상을 포함해야 한다. 거절
# 시그널이 있으면 잡담에 그럴듯한 답을 지어내지 않았다는 방증이기도 하다.
REJECT_SIGNALS = (
    "도와드리기 어려",
    "도와드리기 힘들",
    "답변드리기 어려",
    "도와드릴 수 있는 주제",
    "스터디룸 찾기나 예약",
)


def _has_reject_signal(text: str) -> bool:
    return any(sig in text for sig in REJECT_SIGNALS)


def _load_golden_items() -> list[dict]:
    data = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    return data["items"]


def test_golden_set_branch_accuracy(monkeypatch: pytest.MonkeyPatch) -> None:
    """골든셋 분기 a(근거 답변)/b(모름 안내)/c(범위 밖 거절) 기대 일치를 단언한다(SM-7).

    분기 c(out_of_scope)는 7.7에서 단언을 켠다 — 서비스 무관 질문이 정중한 거절 시그널로
    응답함(근거 없는 답 미생성)을 확인한다.
    """
    from alembic.config import Config
    from langchain_core.messages import AIMessage, ToolMessage
    from sqlalchemy import text
    from sqlmodel import Session

    from alembic import command
    from app.chatbot import service
    from app.chatbot.graph import build_graph
    from app.chatbot.ingest import SqlDocumentChunkStore, build_embedder, ingest_corpus
    from app.core.config import get_settings
    from app.core.db import get_engine

    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY 미설정 — 실 임베딩/LLM 골든셋을 skip 합니다.")

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test")
    monkeypatch.setenv("KAKAO_JS_KEY", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-bytes-long-xx")
    get_settings.cache_clear()
    get_engine.cache_clear()

    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")

    embedder = build_embedder()
    try:
        # 결정적 픽스처 코퍼스를 실 임베딩으로 적재(7.2 파이프라인 재사용).
        with Session(get_engine()) as session:
            store = SqlDocumentChunkStore(session)
            report = ingest_corpus(store, GOLDEN_CORPUS_DIR, embedder)
            assert not report.failed, f"코퍼스 적재 실패: {report.failed}"
            assert report.succeeded, "코퍼스에서 적재된 문서가 없습니다."

        # 실 react 그래프(7.1 어댑터 기본 모델 = gpt-4o-mini, 툴콜 지원).
        graph = build_graph()

        failures: list[str] = []
        for item in _load_golden_items():
            branch = item["branch"]
            question = item["question"]
            # 질문마다 독립 thread(맥락 오염 방지).
            thread_id = f"golden-{uuid.uuid4()}:golden-device-0001"
            reply = service.send_message(thread_id, question, graph=graph)

            if branch == "answer":
                missing = [k for k in item["expect_keywords"] if k not in reply]
                if missing:
                    failures.append(
                        f"[answer] '{question}' → 기대 키워드 누락 {missing}: {reply!r}"
                    )
                if _has_unknown_signal(reply):
                    failures.append(
                        f"[answer] '{question}' → 근거 있는데 모름 안내(환각 회피 과잉): {reply!r}"
                    )
            elif branch == "unknown":
                if not _has_unknown_signal(reply):
                    failures.append(
                        f"[unknown] '{question}' → 모름 시그널 없음(환각 의심): {reply!r}"
                    )
            elif branch == "out_of_scope":
                # 서비스 무관 질문 → 정중한 거절 시그널 포함(근거 없는 답을 지어내지 않음).
                if not _has_reject_signal(reply):
                    failures.append(
                        f"[out_of_scope] '{question}' → 거절 시그널 없음(답 지어냄 의심): {reply!r}"
                    )
                # AC2 "툴 미호출" — 거절 카피 부분문자열만으론 "오프토픽 답 + 헬퍼 꼬리표"
                # (예: "…예요. 그 외 스터디룸 찾기나 예약도 도와드릴게요!") 가짜통과를 못 막는다.
                # 이 thread final state에 ToolMessage·tool_calls 방출 AIMessage가 전혀 없음을
                # 함께 단언해 "어떤 툴도 호출하지 않음"을 행동으로 보증한다(7.7 리뷰 P2/D1).
                turn_state = graph.get_state({"configurable": {"thread_id": thread_id}})
                turn_messages = (
                    turn_state.values.get("messages", []) if turn_state.values else []
                )
                if any(isinstance(m, ToolMessage) for m in turn_messages):
                    failures.append(
                        f"[out_of_scope] '{question}' → 툴 호출됨(AC2 위반): {reply!r}"
                    )
                if any(
                    isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
                    for m in turn_messages
                ):
                    failures.append(
                        f"[out_of_scope] '{question}' → tool_calls 방출됨(AC2 위반): {reply!r}"
                    )
            else:
                # 픽스처 신뢰성 가드 — 오타 branch가 세 arm을 모두 건너뛰고 0건 단언으로
                # 조용히 통과(false-green)하지 않도록 명시 실패시킨다(리뷰 P1).
                failures.append(
                    f"[golden_set] '{question}' → 미지의 branch {branch!r}(픽스처 오타 의심)"
                )

        assert not failures, "골든셋 분기 불일치:\n" + "\n".join(failures)
    finally:
        with Session(get_engine()) as session:
            session.execute(text("DELETE FROM document_chunks"))
            session.commit()
        get_settings.cache_clear()
        get_engine.cache_clear()
