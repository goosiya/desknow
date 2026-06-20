"""멀티 LLM 어댑터 — 프로바이더 레지스트리 + 팩토리 (Story 7.1).

★설계 의도: LangChain v1의 ``init_chat_model(model, model_provider=...)``이 세 프로바이더를
단일 ``BaseChatModel``로 이미 통일한다 — 채팅(``invoke``/``ainvoke``)·시스템프롬프트·툴콜
(``bind_tools``)·스트리밍(``astream``)이 프로바이더 무관 단일 표면으로 제공된다. 따라서 AC의
"if 분기 금지"(architecture L299)는 이 통합 인터페이스로 자연 충족된다 → 프로바이더별 HTTP
클라이언트를 손으로 짜지 않는다(바퀴 재발명 금지).

이 어댑터가 LangChain 위에 **추가하는 가치**(LangChain이 통일 안 해 주는 것):
  1. 설정 기반 선택 + 명시 ``model_provider``(Gemini 추론 footgun 차단),
  2. ``api_key``를 Settings에서 명시 전달(Google env 이름 불일치 footgun 차단),
  3. 에러 정규화(``llm/errors.py``),
  4. 프로젝트 소유 팩토리 표면(하위 chatbot 코드가 LangChain 프로바이더 클래스에 직접 의존 안 함).

프로바이더 분기는 **if/elif 체인이 아니라 레지스트리(dict) 조회**로만 한다. 각 프로바이더는
``adapters/{openai,anthropic,google}.py``가 자기 ``ProviderSpec``을 import 시점에 등록한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from langchain.chat_models import init_chat_model

from app.chatbot.llm.errors import LLMConfigurationError
from app.core.config import get_settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.runnables import Runnable


@dataclass(frozen=True)
class ProviderSpec:
    """프로바이더 메타데이터(데이터로 표현 — if 분기 대체).

    Attributes:
        name: 레지스트리 키이자 ``LLM_PROVIDER`` 설정값(예: ``"openai"``).
        model_provider: ``init_chat_model``의 ``model_provider`` 인자. **반드시 명시**한다
            (Gemini는 생략 시 ``gemini*`` 프리픽스를 GCP/IAM 기반 ``google_vertexai``로 추론 —
            우리가 원하는 API-키 기반 ``google_genai``가 아님. footgun #1).
        settings_key_attr: API 키를 담은 ``Settings`` 속성명(예: ``"OPENAI_API_KEY"``).
        api_key_kwarg: 모델 생성자에 키를 전달할 kwarg 이름. openai/anthropic은 ``"api_key"``,
            google-genai는 ``"google_api_key"``(기본 env 자동 픽업은 ``GOOGLE_API_KEY``를 읽어
            우리 ``GOOGLE_AI_API_KEY``와 불일치 — 그래서 **명시 전달**한다. footgun #2).
        required: 기준 프로바이더(OpenAI)=True, best-effort(Anthropic/Google)=False(AC4).
        native_exceptions: 에러 정규화 대상 네이티브 예외 root 튜플(``normalize_llm_error``가
            이 타입으로 좁혀 catch). LangChain이 통일 안 해 주는 유일한 영역(AC3).
    """

    name: str
    model_provider: str
    settings_key_attr: str
    api_key_kwarg: str
    required: bool
    native_exceptions: tuple[type[BaseException], ...]


# 프로바이더 레지스트리(단일 출처). adapters/*.py가 import 시점에 register_provider로 채운다.
_REGISTRY: dict[str, ProviderSpec] = {}

# adapters 1회 로드 가드(import 부작용=등록). base가 adapters를 import-time에 끌어오지 않아
# 순환을 피하고, 첫 조회 시점에 지연 로드한다.
_PROVIDERS_LOADED = False


def register_provider(spec: ProviderSpec) -> None:
    """프로바이더 spec을 레지스트리에 등록한다(각 adapter 모듈이 import 시 호출)."""
    _REGISTRY[spec.name] = spec


def _ensure_providers_loaded() -> None:
    """내장 어댑터(openai/anthropic/google)를 1회 import해 레지스트리를 채운다."""
    global _PROVIDERS_LOADED
    if not _PROVIDERS_LOADED:
        from app.chatbot.llm import adapters  # noqa: F401  import 부작용=프로바이더 등록

        _PROVIDERS_LOADED = True


def list_providers() -> dict[str, ProviderSpec]:
    """등록된 프로바이더 전체를 반환한다(레지스트리 사본)."""
    _ensure_providers_loaded()
    return dict(_REGISTRY)


def get_provider_spec(provider: str) -> ProviderSpec:
    """프로바이더 이름으로 spec을 조회한다. 미등록 문자열이면 명확한 설정 오류를 던진다(AC1)."""
    _ensure_providers_loaded()
    spec = _REGISTRY.get(provider)
    if spec is None:
        known = ", ".join(sorted(_REGISTRY)) or "(없음)"
        raise LLMConfigurationError(
            f"알 수 없는 LLM 프로바이더입니다: '{provider}'. 사용 가능: {known}."
        )
    return spec


def create_chat_model(
    provider: str | None = None,
    model: str | None = None,
    **overrides: Any,
) -> BaseChatModel:
    """설정(또는 인자)에 따라 통합 ``BaseChatModel`` 핸들을 생성한다(팩토리).

    - ``provider``/``model`` 미지정 시 ``Settings``(``LLM_PROVIDER``/``LLM_MODEL``) 기본값 사용.
    - **``model_provider``를 항상 명시**해 추론 footgun을 차단한다(Gemini → google_genai).
    - **``api_key``를 Settings에서 명시 전달**한다(env 자동 픽업 의존 금지 — Google 이름 불일치).
    - 미등록 프로바이더/선택 프로바이더 키 미설정 → ``LLMConfigurationError``(기준은 정상, AC4).

    샘플링 파라미터(temperature 등)는 공통 표면에서 정규화하지 않는다(AC3 Out of Scope) —
    필요 시 호출처가 ``**overrides``로 직접 전달한다.
    """
    settings = get_settings()
    provider_name = provider if provider is not None else settings.LLM_PROVIDER

    # provider를 명시했으면 model도 명시해야 한다(전역 기본 model이 타 프로바이더에 잘못 적용되는
    # 비정합 차단). 둘 다 미지정일 때만 settings 기본 쌍(기준 OpenAI)을 함께 사용한다.
    if provider is not None and model is None:
        raise LLMConfigurationError(
            f"provider('{provider_name}')를 명시할 때는 model도 함께 지정해야 합니다 "
            "(전역 기본 모델이 다른 프로바이더에 잘못 적용되는 비정합 방지)."
        )
    model_name = model if model is not None else settings.LLM_MODEL

    # 빈/공백 model은 init_chat_model이 '설정형 모델'(_ConfigurableModel)을 반환해 호출 시점에야
    # 깨지므로, 사실상 미설정인 명시 빈 값을 여기서 명확한 설정 오류로 막는다.
    if not model_name.strip():
        raise LLMConfigurationError(
            "model이 비어 있습니다. 유효한 모델 id를 지정하거나 LLM_MODEL을 설정하세요."
        )

    spec = get_provider_spec(provider_name)

    api_key = getattr(settings, spec.settings_key_attr, None)
    if api_key is None or not str(api_key).strip():
        raise LLMConfigurationError(
            f"'{provider_name}' 프로바이더를 선택했으나 API 키({spec.settings_key_attr})가 "
            "설정되지 않았습니다. .env에 키를 설정하거나 LLM_PROVIDER를 기준(openai)으로 두세요."
        )

    # model_provider는 spec이 결정하는 단일 출처다(footgun #1). overrides로 덮어쓰면
    # init_chat_model에 중복 kwarg가 전달돼 raw TypeError가 나므로 명확한 설정 오류로 선차단한다.
    if "model_provider" in overrides:
        raise LLMConfigurationError(
            "model_provider는 overrides로 지정할 수 없습니다(프로바이더 spec이 단일 출처)."
        )

    # api_key를 프로바이더별 올바른 kwarg로 명시 주입(footgun #2). overrides가 우선권을 갖되,
    # 호출처가 의도적으로 키를 덮어쓰는 경우를 막지 않는다.
    kwargs: dict[str, Any] = {spec.api_key_kwarg: api_key}
    kwargs.update(overrides)
    # init_chat_model은 untyped(Any) 반환 → 통합 표면 타입으로 명시 cast.
    return cast(
        "BaseChatModel",
        init_chat_model(model_name, model_provider=spec.model_provider, **kwargs),
    )


def with_transient_retry(
    model: BaseChatModel,
    provider: str,
    *,
    attempts: int = 2,
) -> Runnable[Any, Any]:
    """transient 업스트림 예외에 한해 재시도하는 회복력 훅(선택 — 7.3/7.4가 정책 결정).

    프로바이더 네이티브 예외 타입으로 재시도를 **좁혀** 비-transient 오류(인증 실패 등)까지
    무한 재시도하지 않는다. 본 스토리는 훅만 제공하고, 실제 폴백/재시도 정책 배선은 후속
    스토리(7.3 그래프·7.4 스트리밍)가 결정한다(``Runnable.with_fallbacks`` 등도 후속 소유).

    ``provider``는 **필수**다 — ``model``은 자신을 생성한 프로바이더를 기록하지 않으므로, 전역
    기본값으로 추측하면 ``model``의 실제 프로바이더와 어긋난 ``native_exceptions``로 좁혀
    재시도가 조용히 무력화될 수 있다(예: anthropic 모델을 openai 예외로 좁힘). 따라서 호출처가
    ``model`` 생성 시 쓴 프로바이더를 반드시 명시한다.

    ``attempts``는 총 시도 횟수이며 1 이상이어야 한다. (0은 tenacity에서 ``stop`` 미설정 →
    무한 재시도, 음수는 즉시 중단으로 조용히 강등되므로 명시적으로 거부한다.)
    """
    if attempts < 1:
        raise ValueError(f"attempts는 1 이상이어야 합니다(받은 값: {attempts}).")
    spec = get_provider_spec(provider)
    return model.with_retry(
        retry_if_exception_type=spec.native_exceptions,
        stop_after_attempt=attempts,
    )
