"""멀티 LLM 어댑터 단위 테스트 (Story 7.1 — 네트워크/실키 불필요).

검증 항목:
  (AC1) 레지스트리에 3 프로바이더 등록 + 미등록 프로바이더 명확한 에러(if 분기 아님=레지스트리 조회)
  (AC1/footgun) 팩토리가 init_chat_model을 **명시 model_provider** + **올바른 api_key kwarg**로 호출
                (Gemini vertexai 추론·Google env 이름 불일치 회귀 방지)
  (AC4) 선택 프로바이더 키 미설정 시 그 선택만 명확한 에러(기준 openai는 정상)
  (AC3) 에러 매퍼가 네이티브 예외 → LLM_PROVIDER_UNAVAILABLE(502)로 정규화, 비밀 미노출
  (AC2) 공통 5종을 페이크 모델(invoke/system/astream/거절) + 실 어댑터 표면(bind_tools)으로 실증
  (AC5) config 신규 필드(LLM_PROVIDER/LLM_MODEL)가 기본값으로 동작, 빈 값은 기본 복원

네트워크/실키 불필요: 페이크 모델은 LangChain ``GenericFakeChatModel``, 실 어댑터 표면은
더미 키로 생성(생성·bind_tools·with_retry는 모두 로컬 — invoke/stream만 네트워크).
"""
from __future__ import annotations

import asyncio

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import tool

from app.chatbot.llm import (
    LLMConfigurationError,
    base,
    create_chat_model,
    get_provider_spec,
    list_providers,
    normalize_llm_error,
    with_transient_retry,
)
from app.core.config import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER, get_settings
from app.core.errors import DomainError, ErrorCode

# 필수 키 최소 집합(.env 무시, 환경변수만). OPENAI_API_KEY는 기준 프로바이더라 채운다.
_BASE_ENV = {
    "KAKAO_REST_API_KEY": "x-kakao-rest",
    "KAKAO_JS_KEY": "x-kakao-js",
    "OPENAI_API_KEY": "sk-test-openai",
    "DATABASE_URL": "postgresql://u:p@localhost:5432/desknow",
    "JWT_SECRET_KEY": "a" * 40,
}


@pytest.fixture
def llm_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """필수 env를 주입하고 settings 캐시를 비운다(선택 LLM 키는 미설정 — 테스트가 필요시 추가)."""
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    # 선택 LLM 키는 기본 미설정 상태로 격리
    for k in ("ANTHROPIC_API_KEY", "GOOGLE_AI_API_KEY", "LLM_PROVIDER", "LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


class _InitSpy:
    """init_chat_model 호출 인자를 포착하는 스파이(네트워크/실모델 생성 회피)."""

    def __init__(self) -> None:
        self.model: str | None = None
        self.kwargs: dict[str, object] = {}

    def __call__(self, model: str, **kwargs: object) -> object:
        self.model = model
        self.kwargs = kwargs
        return object()  # sentinel 모델 핸들


# ── (AC1) 레지스트리 — if 분기가 아니라 dict 조회 ────────────────────────────
def test_registry_has_three_providers() -> None:
    assert set(list_providers()) == {"openai", "anthropic", "google"}


def test_unknown_provider_raises_config_error(llm_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(LLMConfigurationError):
        create_chat_model(provider="bogus", model="x")


# ── (AC1/footgun) 팩토리: 명시 model_provider + 올바른 api_key kwarg ─────────
def test_factory_openai_explicit_provider_and_api_key(
    llm_env: pytest.MonkeyPatch,
) -> None:
    spy = _InitSpy()
    llm_env.setattr(base, "init_chat_model", spy)
    create_chat_model(provider="openai", model="gpt-test")
    assert spy.model == "gpt-test"
    assert spy.kwargs["model_provider"] == "openai"  # 추론 아님 — 명시
    assert spy.kwargs["api_key"] == "sk-test-openai"  # Settings에서 주입


def test_factory_google_uses_google_genai_and_google_api_key(
    llm_env: pytest.MonkeyPatch,
) -> None:
    # ★ Gemini footgun 회귀: model_provider 생략 시 google_vertexai로 추론됨 → 명시 google_genai.
    # ★ env 이름 불일치(GOOGLE_API_KEY) footgun: api_key가 아니라 google_api_key로 명시 전달.
    llm_env.setenv("GOOGLE_AI_API_KEY", "g-secret-key")
    get_settings.cache_clear()
    spy = _InitSpy()
    llm_env.setattr(base, "init_chat_model", spy)
    create_chat_model(provider="google", model="gemini-test")
    assert spy.kwargs["model_provider"] == "google_genai"  # NOT google_vertexai
    assert spy.kwargs["google_api_key"] == "g-secret-key"
    assert "api_key" not in spy.kwargs  # google은 google_api_key로만 주입


def test_factory_anthropic_uses_api_key_kwarg(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.setenv("ANTHROPIC_API_KEY", "ant-secret")
    get_settings.cache_clear()
    spy = _InitSpy()
    llm_env.setattr(base, "init_chat_model", spy)
    create_chat_model(provider="anthropic", model="claude-test")
    assert spy.kwargs["model_provider"] == "anthropic"
    assert spy.kwargs["api_key"] == "ant-secret"


def test_factory_uses_settings_defaults_when_unspecified(
    llm_env: pytest.MonkeyPatch,
) -> None:
    # provider/model 미지정 → Settings 기본값(openai / DEFAULT_LLM_MODEL) 사용
    spy = _InitSpy()
    llm_env.setattr(base, "init_chat_model", spy)
    create_chat_model()
    assert spy.model == DEFAULT_LLM_MODEL
    assert spy.kwargs["model_provider"] == "openai"


def test_sampling_params_not_normalized_passed_through(
    llm_env: pytest.MonkeyPatch,
) -> None:
    # (AC3) temperature 등 고유 샘플링 파라미터는 공통 표면에서 정규화하지 않고 그대로 전달.
    spy = _InitSpy()
    llm_env.setattr(base, "init_chat_model", spy)
    create_chat_model(provider="openai", model="gpt-test", temperature=0.7)
    assert spy.kwargs["temperature"] == 0.7


# ── (AC4) 기준/best-effort 구분 ──────────────────────────────────────────────
def test_optional_provider_missing_key_fails_clearly(
    llm_env: pytest.MonkeyPatch,
) -> None:
    # ANTHROPIC_API_KEY 미설정 → anthropic 선택만 명확히 실패
    with pytest.raises(LLMConfigurationError):
        create_chat_model(provider="anthropic", model="claude-test")


def test_baseline_provider_works_without_optional_keys(
    llm_env: pytest.MonkeyPatch,
) -> None:
    # 선택 키 전무해도 기준(openai)은 정상 생성(앱 기동·기준 동작 정상, AC4)
    spy = _InitSpy()
    llm_env.setattr(base, "init_chat_model", spy)
    handle = create_chat_model()
    assert handle is not None
    assert spy.kwargs["model_provider"] == "openai"


def test_provider_required_flags() -> None:
    providers = list_providers()
    assert providers["openai"].required is True
    assert providers["anthropic"].required is False
    assert providers["google"].required is False


# ── (AC3) 에러 정규화 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("provider", ["openai", "anthropic", "google"])
def test_normalize_maps_native_to_domain_502(provider: str) -> None:
    # 원문 메시지에 비밀이 섞여도 사용자 메시지로 새지 않아야 한다(비밀 비노출).
    exc = RuntimeError("upstream failed api_key=sk-LEAK-123 body={'q':'x'}")
    err = normalize_llm_error(exc, provider)
    assert isinstance(err, DomainError)
    assert err.code == ErrorCode.LLM_PROVIDER_UNAVAILABLE
    assert err.status_code == 502
    assert "sk-LEAK-123" not in err.message  # 비밀 미노출
    assert provider in err.message  # 프로바이더 이름은 비밀 아님


def test_each_provider_declares_native_exceptions() -> None:
    for spec in list_providers().values():
        assert spec.native_exceptions  # 비어있지 않음
        assert all(
            isinstance(t, type) and issubclass(t, BaseException)
            for t in spec.native_exceptions
        )


def test_native_exceptions_cover_common_failures() -> None:
    # 각 프로바이더의 레이트리밋/타임아웃/인증/서버 예외가 선언된 root에 포섭되는지 실증
    # (normalize는 except spec.native_exceptions로 좁혀 잡으므로 이 포섭이 핵심).
    import anthropic
    import openai
    from google.genai import errors as genai_errors

    specs = list_providers()
    assert issubclass(openai.RateLimitError, specs["openai"].native_exceptions)
    assert issubclass(openai.APITimeoutError, specs["openai"].native_exceptions)
    assert issubclass(openai.AuthenticationError, specs["openai"].native_exceptions)
    assert issubclass(anthropic.RateLimitError, specs["anthropic"].native_exceptions)
    assert issubclass(genai_errors.ClientError, specs["google"].native_exceptions)
    assert issubclass(genai_errors.ServerError, specs["google"].native_exceptions)


# ── (AC2) 공통 5종 능력 실증 ─────────────────────────────────────────────────
# ① 채팅(단일·멀티턴): invoke / ainvoke
def test_capability_chat_invoke() -> None:
    model = GenericFakeChatModel(messages=iter([AIMessage(content="안녕하세요")]))
    out = model.invoke([HumanMessage(content="안녕")])
    assert isinstance(out, AIMessage)
    assert out.content == "안녕하세요"


def test_capability_chat_ainvoke() -> None:
    model = GenericFakeChatModel(messages=iter([AIMessage(content="비동기 응답")]))
    out = asyncio.run(model.ainvoke([HumanMessage(content="안녕")]))
    assert isinstance(out, AIMessage)
    assert out.content == "비동기 응답"


def test_capability_multi_turn_chat() -> None:
    # 멀티턴(과거 AI 응답 포함) 메시지 열을 통합 표면이 수용
    model = GenericFakeChatModel(messages=iter([AIMessage(content="두 번째 턴 응답")]))
    out = model.invoke(
        [
            HumanMessage(content="첫 질문"),
            AIMessage(content="첫 답변"),
            HumanMessage(content="두 번째 질문"),
        ]
    )
    assert out.content == "두 번째 턴 응답"


# ② 시스템 프롬프트 주입
def test_capability_system_prompt_injection() -> None:
    model = GenericFakeChatModel(messages=iter([AIMessage(content="ok")]))
    out = model.invoke(
        [
            SystemMessage(content="너는 스터디룸 안내원이다."),
            HumanMessage(content="안녕"),
        ]
    )
    assert isinstance(out, AIMessage)


# ③ 2 툴콜 능력: bind_tools (실 어댑터 표면 — 페이크는 bind_tools 미구현)
@tool
def doc_search_placeholder(query: str) -> str:
    """문서 검색 자리표시 도구. 실도구는 7.2/7.5 소유 — 본 테스트 전용(코드베이스에 남기지 않음)."""
    return query


@tool
def reservation_db_placeholder(room_id: str) -> str:
    """예약 DB 자리표시 도구. 실도구는 7.6 소유 — 본 테스트 전용."""
    return room_id


def test_capability_bind_tools_on_real_surface(llm_env: pytest.MonkeyPatch) -> None:
    # 더미 키로 실 어댑터(ChatOpenAI) 생성 → bind_tools는 로컬(네트워크 없음)
    model = create_chat_model(provider="openai", model=DEFAULT_LLM_MODEL)
    bound = model.bind_tools([doc_search_placeholder, reservation_db_placeholder])
    assert isinstance(bound, Runnable)  # 바인딩 결과가 호출 가능한 통합 표면


# ④ 토큰 스트리밍: stream / astream → AIMessageChunk 점진 수신
def test_capability_token_streaming() -> None:
    model = GenericFakeChatModel(messages=iter([AIMessage(content="하나 둘 셋 넷")]))
    chunks = list(model.stream([HumanMessage(content="안녕")]))
    assert len(chunks) > 1  # 단일 응답이 아니라 점진 청크
    assert all(isinstance(c, AIMessageChunk) for c in chunks)
    assert "".join(str(c.content) for c in chunks) == "하나 둘 셋 넷"


def test_capability_astream() -> None:
    async def _collect() -> list[AIMessageChunk]:
        model = GenericFakeChatModel(messages=iter([AIMessage(content="가 나 다")]))
        return [c async for c in model.astream([HumanMessage(content="안녕")])]

    chunks = asyncio.run(_collect())
    assert len(chunks) > 1
    assert all(isinstance(c, AIMessageChunk) for c in chunks)


# ⑤ 범위 밖 거절이 어댑터 표면에서 표현 가능(거절 프롬프트·골든셋은 7.7 소유)
def test_capability_out_of_scope_refusal_expressible() -> None:
    refusal = "죄송하지만 그 질문에는 답변할 수 없어요."
    model = GenericFakeChatModel(messages=iter([AIMessage(content=refusal)]))
    out = model.invoke(
        [
            SystemMessage(content="서비스 범위 밖 질문은 정중히 거절하라."),
            HumanMessage(content="오늘 주식 추천해줘"),
        ]
    )
    assert out.content == refusal


# ── 회복력 훅(선택) ──────────────────────────────────────────────────────────
def test_with_transient_retry_returns_runnable(llm_env: pytest.MonkeyPatch) -> None:
    model = create_chat_model(provider="openai", model=DEFAULT_LLM_MODEL)
    wrapped = with_transient_retry(model, "openai", attempts=2)
    assert isinstance(wrapped, Runnable)


def test_with_transient_retry_rejects_non_positive_attempts(
    llm_env: pytest.MonkeyPatch,
) -> None:
    # attempts<1은 거부(0=무한 재시도, 음수=조용한 1회 강등 방지).
    model = create_chat_model(provider="openai", model=DEFAULT_LLM_MODEL)
    for bad in (0, -1):
        with pytest.raises(ValueError):
            with_transient_retry(model, "openai", attempts=bad)


# ── (Review patch) 팩토리 인자 정합 가드 ──────────────────────────────────────
def test_factory_provider_without_model_raises(llm_env: pytest.MonkeyPatch) -> None:
    # provider만 명시하면 전역 기본 model이 타 프로바이더에 잘못 적용되므로 model 필수.
    with pytest.raises(LLMConfigurationError):
        create_chat_model(provider="openai")


def test_factory_blank_model_raises(llm_env: pytest.MonkeyPatch) -> None:
    # 명시 빈/공백 model은 _ConfigurableModel을 반환해 호출 시점에야 깨지므로 선차단.
    with pytest.raises(LLMConfigurationError):
        create_chat_model(provider="openai", model="   ")


def test_factory_model_provider_override_rejected(llm_env: pytest.MonkeyPatch) -> None:
    # model_provider는 spec 단일 출처 — overrides로 덮으면 중복 kwarg TypeError 대신 설정 오류.
    with pytest.raises(LLMConfigurationError):
        create_chat_model(provider="openai", model="gpt-test", model_provider="anthropic")


# ── (AC5) config 신규 필드 ───────────────────────────────────────────────────
def test_settings_llm_defaults(llm_env: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    assert settings.LLM_PROVIDER == DEFAULT_LLM_PROVIDER
    assert settings.LLM_MODEL == DEFAULT_LLM_MODEL


def test_settings_llm_blank_falls_back_to_default(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.setenv("LLM_PROVIDER", "")
    llm_env.setenv("LLM_MODEL", "   ")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.LLM_PROVIDER == DEFAULT_LLM_PROVIDER
    assert settings.LLM_MODEL == DEFAULT_LLM_MODEL


def test_get_provider_spec_returns_dataclass() -> None:
    spec = get_provider_spec("openai")
    assert spec.name == "openai"
    assert spec.model_provider == "openai"
    assert spec.settings_key_attr == "OPENAI_API_KEY"
