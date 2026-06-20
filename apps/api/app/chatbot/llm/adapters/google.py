"""Google(Gemini) 어댑터 등록 (Story 7.1 — best-effort 프로바이더).

``langchain-google-genai``의 ``ChatGoogleGenerativeAI``를 그대로 쓰는 얇은 등록 파일.

★footgun 두 개를 ProviderSpec 데이터로 차단한다(base.py 팩토리가 적용):
  1. ``model_provider="google_genai"`` 고정 — 생략 시 ``gemini*`` 프리픽스가 GCP/IAM 기반
     ``google_vertexai``로 추론된다(우리가 원하는 API-키 기반 google_genai가 아님).
  2. ``api_key_kwarg="google_api_key"`` — langchain-google-genai는 기본 env로 ``GOOGLE_API_KEY``를
     읽지만 우리 설정 키는 ``GOOGLE_AI_API_KEY``(불일치). 그래서 Settings에서 명시 전달한다.

⚠️ 7.4(실스트리밍) 주의: google_genai는 ``bind_tools`` 후 ``astream``이 토큰별이 아니라 전체를
단일 청크로 줄 수 있는 오픈 이슈가 있다. 본 스토리(7.1)는 어댑터 능력 실증이 목표라 영향 없으나,
7.4에서 Gemini는 프로바이더별 실테스트·필요 시 폴백 대상이다(기준=OpenAI라 SLA 리스크는 격리됨).

native 예외: langchain-google-genai 4.x는 신형 ``google-genai`` SDK(``google.genai.errors``)를
쓴다 — 구버전 ``google.api_core.exceptions``가 아니다(구현 시 런타임 확인). ``APIError``가 root로
``ClientError``(4xx, 429 레이트리밋 포함)/``ServerError``(5xx)를 모두 포괄한다.
"""
from __future__ import annotations

from google.genai import errors as genai_errors

from app.chatbot.llm.base import ProviderSpec, register_provider

register_provider(
    ProviderSpec(
        name="google",
        model_provider="google_genai",  # ★ footgun #1: vertexai 추론 차단
        settings_key_attr="GOOGLE_AI_API_KEY",
        api_key_kwarg="google_api_key",  # ★ footgun #2: env 이름 불일치(GOOGLE_API_KEY) 차단
        required=False,
        native_exceptions=(genai_errors.APIError,),
    )
)
