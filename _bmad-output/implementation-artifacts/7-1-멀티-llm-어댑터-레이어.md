---
baseline_commit: NO_VCS
---

# Story 7.1: 멀티 LLM 어댑터 레이어

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 개발자,
I want OpenAI/Google/Anthropic의 요청·응답·스트리밍·에러 차이를 **단일 공통 인터페이스로 흡수**하는 어댑터 레이어를 두길,
so that 설정만 바꿔 프로바이더/모델을 전환해도 챗봇의 공통 5종 기능(채팅·시스템프롬프트·툴콜·스트리밍·범위밖거절)이 **if 분기 없이** 동일하게 동작한다 (FR-29, NFR-2·6).

## Acceptance Criteria

1. **(AC1 — 어댑터 표면)** `apps/api/app/chatbot/llm/` 아래에 `base.py`(공통 인터페이스·팩토리·프로바이더 레지스트리) + `adapters/openai.py` + `adapters/anthropic.py` + `adapters/google.py`가 존재하고, 설정값(`LLM_PROVIDER`, `LLM_MODEL`)으로 프로바이더/모델을 전환하면 동일한 호출 코드가 세 프로바이더 모두에서 동작한다. **프로바이더 분기는 if/elif 체인이 아니라 레지스트리 조회로만** 이뤄진다(아키텍처 안티패턴 L299 "멀티 LLM을 if 분기로 처리" 금지).

2. **(AC2 — 공통 5종 능력 보장)** 어댑터가 반환하는 모델 핸들이 다음 5종을 **프로바이더 무관 단일 표면**으로 지원함을 테스트로 실증한다:
   - ① 단일·멀티턴 채팅 (`invoke`/`ainvoke`),
   - ② 시스템 프롬프트 (`SystemMessage` 주입),
   - ③ 2개 툴콜 능력 (`bind_tools` — 문서검색·예약DB **자리표시 도구**로 바인딩이 동작함만 실증. 실제 도구는 7.5/7.6 소유 — 본 스토리에서 실도구를 만들지 않는다),
   - ④ 토큰 스트리밍 (`astream` → `AIMessageChunk` 점진 수신),
   - ⑤ 범위 밖 거절 (시스템프롬프트 기반 거절이 **어댑터 표면에서 표현 가능함**만 실증. 골든셋·실거절 프롬프트는 7.7 소유).

3. **(AC3 — 정규화 경계)** 프로바이더별 고유 샘플링 파라미터(temperature 등)는 **공통 표면에서 정규화하지 않는다(Out of Scope)**. 어댑터는 오직 **요청/응답/스트리밍/에러 스키마 차이만** 흡수한다. 단, 프로바이더별 네이티브 예외(`openai.*` / `anthropic.*` / `google.api_core.exceptions.*`)는 **단일 도메인 예외로 정규화**한다(에러는 LangChain이 통일해 주지 않으므로 어댑터가 직접 매핑 — Dev Notes §에러 정규화 참조).

4. **(AC4 — 기준/best-effort 구분)** 기준 프로바이더는 **OpenAI**(≤2초 SLA 대상, `OPENAI_API_KEY` 필수 키 — 이미 `config.py` REQUIRED), Anthropic/Google는 **best-effort**(`ANTHROPIC_API_KEY`/`GOOGLE_AI_API_KEY` 선택 키 — 이미 OPTIONAL). 선택 프로바이더 키 미설정 시 그 프로바이더 선택만 명확한 에러로 실패하고, **앱 기동·기준 프로바이더 동작은 정상**이다.

5. **(AC5 — 게이트 그린)** `cd apps/api && uv run ruff check . && uv run mypy && uv run pytest`가 모두 통과한다(신규 의존성 설치 포함). 네트워크가 필요한 실프로바이더 호출 테스트는 키 부재 시 `skip`(integration 마커)되며, 기본 단위 테스트는 **네트워크 없이** 페이크 모델로 5종을 실증한다.

## Tasks / Subtasks

- [x] **Task 1 — 의존성 추가 (AC1, AC5)**
  - [x] `apps/api/pyproject.toml` `dependencies`에 LangChain v1 런타임 패키지 추가(버전 핀은 Dev Notes §의존성 참조): `langchain`, `langchain-openai`, `langchain-anthropic`, `langchain-google-genai`. (`langgraph`는 본 스토리 범위 밖 — 에이전트 그래프/checkpointer는 7.3이 추가. 어댑터 레이어는 LangChain chat model만 필요.)
  - [x] `uv lock` → `uv sync`로 설치 확인. import smoke(`python -c "from langchain.chat_models import init_chat_model"`).
- [x] **Task 2 — 설정 필드 추가 (AC1, AC4)**
  - [x] `app/core/config.py` `Settings`에 `LLM_PROVIDER: str = "openai"`, `LLM_MODEL: str = "<기준 OpenAI 모델 — 구현 시점 현행 id 확인>"` 추가(둘 다 기본값 보유 → fail-fast 대상 아님).
  - [x] ⚠️ **필수**: 신규 필드 2개를 `REQUIRED_KEYS` 또는 `OPTIONAL_KEYS` 목록에 등록한다. 등록을 빼면 `_assert_key_lists_match_model()`(config.py:153)이 **import 시점에 RuntimeError**로 전체 앱·테스트를 죽인다(silent drift 가드). 비밀이 아니므로 `NON_SECRET_KEYS`에도 추가해 진단 출력에서 값 노출 허용 권장(EMBEDDING_MODEL 선례).
  - [x] `apps/api/.env.example`에 `LLM_PROVIDER`/`LLM_MODEL` 항목 + 한국어 설명 추가(EMBEDDING_MODEL 블록 스타일 따름).
- [x] **Task 3 — base.py: 프로바이더 레지스트리 + 팩토리 (AC1, AC3, AC4)**
  - [x] 프로바이더 메타데이터를 데이터로 표현하는 레지스트리(`dict[str, ProviderSpec]`)를 정의. 각 spec은 `model_provider`(LangChain 문자열), `api_key` 설정 attr 이름, 정규화 대상 네이티브 예외 타입 튜플을 보유.
  - [x] `create_chat_model(provider: str | None = None, model: str | None = None, **overrides) -> BaseChatModel` 팩토리: 미지정 시 Settings 기본값 사용, `init_chat_model(model, model_provider=<spec.model_provider>, api_key=<settings에서 명시 주입>, **overrides)` 호출. **`model_provider`를 반드시 명시**(추론 금지 — Gemini footgun, Dev Notes 참조). **api_key를 settings에서 명시 전달**(Google env 이름 불일치 footgun, Dev Notes 참조).
  - [x] 미등록 프로바이더 문자열 → 명확한 `ValueError`/도메인 예외. 선택 프로바이더인데 키 미설정 → 명확한 에러(AC4).
- [x] **Task 4 — 에러 정규화 (AC3)**
  - [x] `app/core/errors.py` `ErrorCode`에 LLM 업스트림 실패 코드 추가(예 `LLM_PROVIDER_UNAVAILABLE` → 502/503; `GEOCODING_UNAVAILABLE`=502 선례 따름). `DEFAULT_STATUS`에도 매핑.
  - [x] `base.py`(또는 `llm/errors.py`)에 `normalize_llm_error(exc, provider) -> DomainError` 매퍼: 각 프로바이더 네이티브 예외(레이트리밋/타임아웃/인증/일반 API 에러)를 단일 `DomainError`로 변환. **에러 메시지에 API 키·요청 본문 등 비밀이 새지 않도록** 마스킹(config.py 비밀 비노출 규약).
  - [x] (선택, 권장) 회복력 헬퍼: LangChain `Runnable.with_retry`(transient 예외 타입으로 좁힘)·`with_fallbacks` 사용 지점을 base에 노출하되, 실제 폴백 정책 배선은 7.3/7.4가 결정(본 스토리는 매퍼+훅 제공까지).
- [x] **Task 5 — adapters/{openai,anthropic,google}.py (AC1)**
  - [x] 각 파일은 자기 프로바이더의 `ProviderSpec`을 선언하고 `base`의 레지스트리에 등록(import 시 등록). google.py에는 `model_provider="google_genai"` 고정 + (필요 시) `safety_settings`/REST 특이사항 주석. 셋 다 LangChain 통합 인터페이스를 공유하므로 파일은 **얇다** — 이게 정상(중복 구현 금지, Dev Notes §설계 의도 참조).
- [x] **Task 6 — 테스트 (AC2, AC5)**
  - [x] `apps/api/tests/chatbot/test_llm_adapter.py`(미러 구조) 신규:
    - 팩토리가 `init_chat_model`을 **명시 `model_provider`로** 호출하는지(monkeypatch/mock — Gemini 추론 footgun 회귀 방지).
    - 레지스트리에 3개 프로바이더 모두 존재.
    - 에러 매퍼가 각 네이티브 예외 → 의도한 `ErrorCode`/status로 정규화(비밀 미노출 단언).
    - 공통 5종을 **페이크 모델**로 실증: `langchain_core.language_models.fake_chat_models`의 `GenericFakeChatModel`/`FakeMessagesListChatModel`로 invoke·astream·bind_tools(테스트 로컬 `@tool`)·SystemMessage·거절문 흐름. (네트워크·실키 불필요.)
  - [x] (선택) `@pytest.mark.integration` 키-게이트 스모크: `OPENAI_API_KEY` 등 실키 존재 시에만 실프로바이더 1콜(`skipif` 미설정). CI 기본 실행에서 제외.
  - [x] `app/core/config.py` 신규 필드가 기존 `tests/core` 설정 테스트를 깨지 않는지 확인(기본값 보유라 통과해야 정상).

## Dev Notes

### 이 스토리의 본질 — 무엇을 만들고 무엇을 만들지 않는가

7.1은 **Epic 7의 토대(developer-facing 인프라)** 다. "공통 5종이 동일 동작"을 **어댑터 표면 수준에서 보장**하는 게 목표이지, 5종의 *실제 제품 기능*을 완성하는 게 아니다. 실기능은 후속 스토리가 소유한다:

| 능력 | 7.1 책임 | 실기능 소유 스토리 |
|---|---|---|
| ① 채팅(단일·멀티턴) | 통합 invoke/ainvoke 표면 + 테스트 | (7.3 세션/그래프 배선) |
| ② 시스템 프롬프트 | SystemMessage 주입 동작 실증 | 7.5(RAG)·7.7(거절) 프롬프트 |
| ③ 2 툴콜(문서검색·예약DB) | `bind_tools` **능력** 실증(자리표시 도구) | **실도구=7.5/7.2(문서검색)·7.6(예약DB)** |
| ④ 토큰 스트리밍 | `astream` 청크 수신 실증 | **SSE 엔드포인트=7.4** |
| ⑤ 범위 밖 거절 | 거절을 표면에서 표현 가능 실증 | **거절 프롬프트·골든셋=7.7** |

**IN(본 스토리):** `chatbot/llm/` 패키지(base+3 adapters), 설정 기반 프로바이더/모델 선택, 에러 정규화, 5종 능력의 어댑터 레벨 단위 테스트.
**OUT(만들지 말 것 — 반복함정 #reinvent):** LangGraph 에이전트 그래프·checkpointer(7.3), SSE 엔드포인트 `/api/v1/chatbot/stream`(7.4), 실제 문서검색 RAG 도구(7.2/7.5), 실제 예약DB 도구(7.6 — `reservations.service` 호출, SQL 직접 접근 금지), 거절 시스템프롬프트·골든셋(7.7), 샘플링 파라미터 정규화(AC3 명시 Out of Scope).
→ 실도구·실엔드포인트를 7.1에서 선구현하면 7.2/7.4/7.5/7.6과 **중복·충돌**한다. `bind_tools` 능력은 **테스트 로컬 `@tool`** 로 실증하고, 자리표시 도구 모듈을 코드베이스에 남기지 말 것(후속 스토리가 진짜를 만든다).

### ★설계 의도 — LangChain v1이 곧 정규화 레이어 (바퀴 재발명 금지)

LangChain v1의 `init_chat_model(model, model_provider=...)`는 세 프로바이더를 **단일 `BaseChatModel`** 로 이미 통일한다. 채팅·시스템프롬프트·스트리밍(`astream`)·툴콜(`bind_tools`)이 프로바이더 무관 단일 표면으로 제공된다 → **AC의 "if 분기 금지"가 이 통합 인터페이스로 자연 충족**된다.

**그러므로 절대 하지 말 것:** 프로바이더별로 `httpx`/SDK를 직접 호출하는 HTTP 클라이언트를 손으로 짜는 것. 그건 LangChain이 이미 한 일을 재발명하는 것이고 체크리스트 1순위 disaster다. `adapters/*.py`는 **프로바이더 메타데이터 등록(얇은 파일)** 이면 충분하다 — 파일이 비어 보일 만큼 얇은 게 정상이다.

**어댑터가 진짜 추가하는 가치(LangChain이 통일 안 해 주는 것):**
1. **설정 기반 선택 + 명시 `model_provider`**(추론 footgun 차단),
2. **에러 정규화**(아래 §),
3. 프로젝트 소유 팩토리 표면(하위 `chatbot/*` 코드가 LangChain 프로바이더 클래스에 직접 의존하지 않도록).

분기를 if/elif가 아니라 **레지스트리(dict) 조회**로 구현하면 "if 분기 금지"를 코드 구조로도 만족한다.

### ★에러 정규화 — 여기만 프로바이더 인지가 불가피 (AC3)

리서치 확인: `langchain_core.exceptions`는 파싱/트레이싱 등 LangChain 자체 에러만 있고, **프로바이더 API/네트워크/레이트리밋 예외는 wrapping 없이 네이티브로 그대로 전파**된다(공통 베이스 예외 없음).
- OpenAI → `openai.APIError`/`openai.RateLimitError`/`openai.APITimeoutError`/`openai.AuthenticationError` (확인됨, high confidence)
- Anthropic → `anthropic.*`(예 `anthropic.RateLimitError`) — 정확한 클래스명은 구현 시 런타임 확인 권장
- Google(genai) → `google.api_core.exceptions.*`(레이트리밋=`ResourceExhausted`/HTTP 429) — 구현 시 확인 권장

→ **각 spec이 자기 네이티브 예외 타입 튜플을 들고**, `normalize_llm_error`가 그걸로 catch해 단일 `DomainError(LLM_PROVIDER_UNAVAILABLE, ...)`로 매핑한다. 이 한 곳만 프로바이더 인지가 불가피하며, AC3의 "에러 스키마 차이 흡수"가 이걸 가리킨다. **비밀 누출 주의**: 네이티브 예외 메시지에 키/요청이 섞일 수 있으니 사용자 메시지는 안전한 고정 문구로(원문은 `logger`로만, 평문 키 금지 — config.py `mask_secret` 정신).

### ★알려진 함정 (구현 전 반드시 확인 — 프리플라이트)

1. **Gemini `model_provider` 추론 footgun:** `model_provider` 생략 시 `gemini...` 프리픽스는 **`google_vertexai`(GCP/IAM)로 추론**된다 — 우리가 원하는 API-키 기반 `google_genai`가 아님! → 팩토리에서 **항상 `model_provider` 명시**. (테스트로 회귀 방지 — Task 6.)
2. **Google API 키 env 이름 불일치:** `langchain-openai`는 `OPENAI_API_KEY`, `langchain-anthropic`는 `ANTHROPIC_API_KEY`를 자동 인식하지만, `langchain-google-genai`는 기본 **`GOOGLE_API_KEY`** 를 읽는다 — 우리 설정은 `GOOGLE_AI_API_KEY`(불일치)! → 세 프로바이더 모두 **api_key를 Settings에서 명시 전달**(env 자동 픽업에 의존하지 말 것). 키 백엔드 격리(NFR-6)와도 일치.
3. **config `_assert_key_lists_match_model()` 가드:** 신규 Settings 필드를 REQUIRED/OPTIONAL 목록에 등록 안 하면 import 시점 RuntimeError(Task 2 참조). EMBEDDING_MODEL이 REQUIRED+DEFAULTED 선례.
4. **Gemini 스트리밍+툴 동시 버그(오픈 이슈):** Gemini는 `bind_tools` 후 `astream`이 토큰별이 아니라 전체를 단일 청크로 줄 수 있다(google_genai). 본 스토리는 능력 실증이 목표라 페이크 모델로 충분하지만, 7.4 실스트리밍에서 Gemini는 프로바이더별 실테스트·필요 시 폴백 대상임을 주석으로 남길 것. (기준 프로바이더=OpenAI라 ≤2초 SLA 리스크는 격리됨.)
5. **모델 id 하드코딩 금지:** OpenAI 기준 모델 id는 시점에 따라 바뀐다(지식 컷오프 주의). `LLM_MODEL` 설정으로 두고 구현 시점 현행 id를 확인해 기본값을 채울 것.
6. **langchain-google-genai 4.x:** `with_structured_output` 기본 method가 `json_schema`로 바뀌었고 REST-only다. 본 스토리는 structured output을 쓰지 않으므로 영향 적으나, 후속(7.6 자연어→구조화 검색조건)에서 주의 포인트.

### 의존성 (버전 핀 — 2026-06 기준 리서치, `uv add` 시 호환 범위로 고정)

| 패키지 | 리서치 시점 최신 | 권장 핀 |
|---|---|---|
| `langchain` | 1.3.9 | `>=1.3,<2` |
| `langchain-core` | 1.4.7 | (langchain 전이 의존 — 명시 불필요, `>=1.4,<2` 가능) |
| `langchain-openai` | 1.3.2 | `>=1.3,<2` |
| `langchain-anthropic` | 1.4.6 | `>=1.4,<2` |
| `langchain-google-genai` | 4.2.5 | `>=4.2,<5` (독립 4.x 라인 — langchain 1.x와 번호 다른 게 정상) |

- LangChain 1.0 GA(2025-10-22)는 "2.0 전까지 breaking 없음" 공약 → `<2` 상한이 안전.
- `init_chat_model`·`langchain.chat_models`는 v0→v1에서 **이동 없음**(그대로 사용).
- Python 3.12 완전 지원(현 스택 OK). 구현 시 `uv lock`이 해석한 실버전을 README/주석에 남길 것.

### 기존 코드·패턴 정렬 (반드시 따를 것)

- **도메인 모듈 구조**(architecture L255): `apps/api/app/{domain}/{router,models,schemas,service}.py`. 단 chatbot은 LLM 하위 패키지가 추가됨: `chatbot/llm/{base.py, errors.py?, adapters/__init__.py, adapters/{openai,anthropic,google}.py}`. `apps/api/app/chatbot/`는 현재 `__init__.py`만 있는 빈 골격 — 본 스토리가 첫 실코드.
- **설정 로딩**: `app/core/config.py`의 `Settings`/`get_settings()`(lru_cache 싱글톤)만 사용. 직접 `os.environ` 읽기 금지. 필수/선택 키 분리 규약(필수=기본값 없음 fail-fast, 선택=`Optional`+None) 준수.
- **에러 스키마**: `app/core/errors.py`의 `DomainError`+`ErrorCode`(StrEnum)+`DEFAULT_STATUS`만 사용. raw `HTTPException` 금지. 신규 코드는 enum에 **추가**(GEOCODING_UNAVAILABLE=502 선례 미러).
- **타입/린트 게이트**: ruff(select E,F,I,B,UP, line-length 100) + mypy(strict, pydantic plugin). `from __future__ import annotations` 헤더 관용. 모든 함수 타입 강제.
- **테스트 미러 구조**: `apps/api/tests/chatbot/test_*.py`. 네트워크/실키 없이 페이크로 단위 검증(notifications/favorites `FakeSession` 충실도 선례 정신 — 단 여기선 LangChain `GenericFakeChatModel`/`FakeMessagesListChatModel` 활용). `conftest.py`의 `auth_env`는 JWT용이라 본 테스트엔 보통 불필요(설정 기본값으로 충분).
- **주석은 한국어**, 변수·함수명은 영어(전역 규약).

### 정책·범위 메모 (혼동 방지)

- **라이브 DB 마이그레이션 정책 — 본 스토리 미해당:** 7.1은 DB 모델/스키마 변경이 **없다**(어댑터는 무상태; pgvector 모델=7.2, 챗봇 세션 checkpointer=7.3). 따라서 매 스토리 dev 완료 시 `alembic upgrade head` 실행 의무가 **트리거되지 않는다**(돌릴 마이그레이션 없음). 빠뜨린 게 아니라 대상 부재임을 명시.
- **웹–모바일 짝 점검 — 본 스토리 미해당:** 7.1은 순수 백엔드 인프라로 UI 표면이 없다. 챗봇 프론트(FAB/대화)는 7.3 소유이며 그 자체가 모바일은 "모바일 dev-build 푸시" 버킷으로 별도 라우팅된다(E7=챗봇 에픽 ≠ 모바일 버킷 — 혼동 주의). 본 스토리 `apps/web`·`apps/mobile`·`apps/admin` 변경 0.
- **deferred-work 의무 회수 — 본 스토리 트리거 없음:** deferred-work.md의 E7 연관 이월(모바일 dev-build·SSE 프레이밍 견고성·pgvector 충실도·web/.env.local Phase-0 잔재 정리)은 각각 **스트리밍 엔드포인트(7.4)·인제스트(7.2)·모바일 스토리·실이관 시점**에 바인딩된다. 어댑터 레이어(7.1)는 이들 중 어느 것의 트리거도 아니다 → 본 스토리에서 끌어오지 말 것(프리플라이트 확인 완료). 단 7.4 착수 시 "SSE 서버 프레이밍 견고성"(deferred-work L125) 의무 회수 대상임을 인지.

### Project Structure Notes

- 신규 디렉터리/파일(예상): `apps/api/app/chatbot/llm/__init__.py`, `chatbot/llm/base.py`, `chatbot/llm/adapters/__init__.py`, `chatbot/llm/adapters/{openai,anthropic,google}.py`, (선택) `chatbot/llm/errors.py`. 테스트 `apps/api/tests/chatbot/__init__.py`, `tests/chatbot/test_llm_adapter.py`.
- 수정: `apps/api/pyproject.toml`(의존성), `apps/api/app/core/config.py`(LLM_PROVIDER/LLM_MODEL + 목록 등록), `apps/api/app/core/errors.py`(LLM 에러코드), `apps/api/.env.example`(신규 키 설명).
- **라우터 등록은 본 스토리 없음:** 어댑터는 라우터를 노출하지 않는다(SSE 엔드포인트는 7.4). `app/main.py` 변경 0 — OpenAPI 계약/SDK 재생성 불필요.
- 변이/충돌: 없음. `chatbot/`는 빈 골격이라 회귀 위험 낮음. config 신규 필드는 기본값 보유라 기존 테스트·기동 무영향(단 목록 등록 누락 시 import RuntimeError — 가드가 즉시 잡음).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 7.1] — AC 원문(공통 5종·정규화 경계·기준/best-effort).
- [Source: _bmad-output/planning-artifacts/epics.md#FR-29] — 멀티 LLM 스위칭(횡단), 고유 파라미터 정규화 안 함(어댑터).
- [Source: _bmad-output/planning-artifacts/architecture.md#L200-201, L386, L299] — LangGraph+LangChain v1, `chatbot/llm/adapters/{openai,anthropic,google}.py + base`, "if 분기 금지" 안티패턴.
- [Source: _bmad-output/planning-artifacts/architecture.md#L131-133, L453] — 기준 프로바이더=OpenAI(≤2초), Anthropic/Google best-effort, 리스크 격리.
- [Source: apps/api/app/core/config.py] — Settings 필수/선택 키 규약, `_assert_key_lists_match_model` 가드, 이미 선언된 OPENAI/ANTHROPIC/GOOGLE_AI 키.
- [Source: apps/api/app/core/errors.py] — DomainError/ErrorCode/DEFAULT_STATUS 표준 스키마, 502 업스트림(GEOCODING_UNAVAILABLE) 선례.
- [Source: apps/api/tests/conftest.py, tests/notifications/test_service.py] — 페이크 기반 네트워크리스 단위 테스트 패턴.
- [Source: _bmad-output/implementation-artifacts/deferred-work.md#L117-128] — Phase 0 스파이크 이월(SSE 프레이밍 L125는 7.4 트리거, pgvector L126-128은 7.2 트리거).
- LangChain v1 리서치(2026-06): `init_chat_model` 공식 표준, `model_provider` 문자열(openai/anthropic/**google_genai**), `bind_tools`/`astream` 프로바이더 공통, 에러 비정규화(네이티브 전파). 출처 — docs.langchain.com/oss/python/langchain/models · /concepts/providers-and-models · reference.langchain.com init_chat_model.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Opus 4.8, 1M context)

### Debug Log References

- `uv lock` / `uv sync` — LangChain v1 런타임 4종 설치. 해석 실버전(README/주석 기록용):
  langchain 1.3.9, langchain-core 1.4.7, langchain-openai 1.3.2, langchain-anthropic 1.4.6,
  langchain-google-genai 4.2.5 (모두 Dev Notes 권장 핀과 일치).
- 첫 `uv sync`는 실행 중이던 dev 서버(uvicorn)가 venv의 websockets `.pyd`를 잠가 실패 →
  사용자 승인 후 서버 종료하고 재실행해 성공(KTH 승인).
- 런타임 footgun 검증(구현 전 프리플라이트): `init_chat_model`이 api_key/google_api_key를
  전달받아 ChatOpenAI/ChatAnthropic/ChatGoogleGenerativeAI를 네트워크 없이 생성, bind_tools가
  로컬 동작함을 실측. `GenericFakeChatModel`은 bind_tools 미구현(NotImplementedError) 확인 →
  툴콜 실증은 실 어댑터 표면으로 대체.
- 게이트: `ruff check .`(clean) · `mypy`(50 files, no issues) · `pytest`(590 passed, 12 skipped).

### Completion Notes List

- **★Dev Notes 두 곳 정정(런타임 확인 결과):**
  1. **google 네이티브 예외 타입**: Dev Notes는 `google.api_core.exceptions.*`로 가정했으나,
     langchain-google-genai **4.x는 신형 `google-genai` SDK(`google.genai.errors`)**를 쓴다.
     실제 root는 `google.genai.errors.APIError`(`ClientError`=4xx/429, `ServerError`=5xx 포괄).
     adapters/google.py가 이 타입으로 등록(런타임 검증 + 테스트로 포섭 실증).
  2. **OpenAPI/SDK 재생성 필요**: Dev Notes는 "라우터 없음 → OpenAPI/SDK 재생성 불필요"라
     했으나, `ErrorCode` enum은 `ErrorDetail.code`로 노출되는 **공개 스키마 컴포넌트**라
     `LLM_PROVIDER_UNAVAILABLE` 추가가 스키마를 변경한다. Layer A 드리프트 게이트
     (`test_openapi_export`)가 이를 잡아, `scripts/export_openapi.py` 재실행 +
     `pnpm --filter @desknow/api-client generate`로 SDK까지 재생성했다(GEOCODING 선례 동형).
- **설계**: 프로바이더 분기는 if/elif가 아니라 `dict[str, ProviderSpec]` 레지스트리 조회로만
  구현(AC1 안티패턴 L299 충족). adapters/*.py는 메타데이터 등록만 하는 얇은 파일(LangChain v1
  통합 인터페이스 재사용 — HTTP 클라이언트 손코딩 0).
- **footgun 차단(테스트 회귀 고정)**: (1) `model_provider`를 항상 명시(Gemini vertexai 추론
  차단), (2) api_key를 Settings에서 프로바이더별 올바른 kwarg(`api_key`/`google_api_key`)로
  명시 전달(GOOGLE_API_KEY env 불일치 차단).
- **에러 정규화(AC3)**: 네이티브 예외 root만 단일 `DomainError(LLM_PROVIDER_UNAVAILABLE, 502)`로
  매핑. 원문(키·요청 섞일 수 있음)은 logger로만, 사용자 메시지는 고정 안전 문구(비밀 비노출).
  미등록 프로바이더/선택 키 미설정은 업스트림 502가 아니라 `LLMConfigurationError`로 분리
  (잘못된 설정을 장애로 위장하지 않음 — 기준 OpenAI는 정상, AC4).
- **공통 5종 실증(AC2)**: ①채팅 invoke/ainvoke·②SystemMessage·④stream/astream(AIMessageChunk
  점진)·⑤거절문 흐름은 네트워크 없는 `GenericFakeChatModel`로, ③bind_tools(자리표시 `@tool` 2종)는
  실 어댑터(ChatOpenAI, 더미 키·로컬 바인딩)로 실증. 자리표시 도구는 테스트 로컬에만 두고
  코드베이스에 남기지 않음(실도구=7.2/7.5/7.6).
- **범위 준수**: LangGraph·SSE 엔드포인트·실 RAG/예약 도구·거절 골든셋·샘플링 정규화는 모두 만들지
  않음(후속 스토리 소유). 회복력 훅(`with_transient_retry`)은 제공만 하고 정책 배선은 7.3/7.4.
- **정책 메모(트리거 없음 확인)**: DB 마이그레이션(어댑터 무상태) · 웹–모바일 짝(백엔드 인프라,
  UI 표면 0) · deferred-work 회수(7.1은 어느 트리거도 아님) — 모두 본 스토리 미해당(프리플라이트 완료).
- **선택 항목 미수행**: `@pytest.mark.integration` 실키 스모크는 Task 6에서 "(선택)"이라 미작성
  (기본 단위 테스트가 네트워크 없이 5종을 실증 — AC5 충족). 후속에서 필요 시 추가 가능.

### File List

**신규(app):**
- `apps/api/app/chatbot/llm/__init__.py` — 패키지 공개 표면(create_chat_model 등 re-export)
- `apps/api/app/chatbot/llm/base.py` — ProviderSpec·레지스트리·팩토리·회복력 훅
- `apps/api/app/chatbot/llm/errors.py` — normalize_llm_error·LLMConfigurationError
- `apps/api/app/chatbot/llm/adapters/__init__.py` — 어댑터 등록 부작용 트리거
- `apps/api/app/chatbot/llm/adapters/openai.py` — OpenAI ProviderSpec 등록(기준)
- `apps/api/app/chatbot/llm/adapters/anthropic.py` — Anthropic ProviderSpec 등록(best-effort)
- `apps/api/app/chatbot/llm/adapters/google.py` — Google ProviderSpec 등록(best-effort, footgun 차단)

**신규(tests):**
- `apps/api/tests/chatbot/__init__.py`
- `apps/api/tests/chatbot/test_llm_adapter.py` — 레지스트리/팩토리/footgun/에러/공통 5종(27 테스트)

**수정:**
- `apps/api/pyproject.toml` — LangChain v1 런타임 4종 의존성 추가
- `apps/api/uv.lock` — 의존성 잠금(재생성)
- `apps/api/app/core/config.py` — LLM_PROVIDER/LLM_MODEL 필드·기본값·OPTIONAL/NON_SECRET 등록·blank 복원
- `apps/api/app/core/errors.py` — ErrorCode.LLM_PROVIDER_UNAVAILABLE(502) + DEFAULT_STATUS 매핑
- `apps/api/.env.example` — LLM_PROVIDER/LLM_MODEL 한국어 설명 블록
- `packages/api-client/openapi.json` — ErrorCode enum 갱신(재생성)
- `packages/api-client/src/generated/*` — TS SDK 재생성(enum 반영)

### Change Log

| 날짜 | 변경 |
|---|---|
| 2026-06-17 | Story 7.1 구현 — 멀티 LLM 어댑터 레이어(base 레지스트리+팩토리, 3 adapters, 에러 정규화). config에 LLM_PROVIDER/LLM_MODEL 추가, ErrorCode.LLM_PROVIDER_UNAVAILABLE(502) 추가. LangChain v1 의존성 4종 추가. 단위 테스트 27종(네트워크리스). OpenAPI/SDK 재생성. ruff/mypy/pytest(590 passed) 그린. |
| 2026-06-17 | 코드 리뷰 patch(5건) — 팩토리 인자 정합 가드: provider 명시 시 model 필수·빈 model 차단·model_provider override 거부; `with_transient_retry` provider 필수화 + attempts<1 거부. 회귀 테스트 4종 추가. ruff/mypy/pytest(594 passed) 그린. Status review→done. |

## Review Findings

코드 리뷰(2026-06-17) — 적대 3레이어(Blind Hunter / Edge Case Hunter / Acceptance Auditor) 병렬 실행. Acceptance Auditor: **AC1~5 전부 충족, 위반 0**(레지스트리·5종·정규화 경계·기준/best-effort·게이트 그린·OUT 범위·footgun #1/#2 회귀 핀 모두 확인). 아래는 견고성 관련 발견.

### Decision-needed (해소 → patch 적용 완료)

- [x] [Review][Decision→Patch] `with_transient_retry` 프로바이더-모델 연결 부재 — KTH 결정: **지금 하드닝**. `provider`를 필수 인자화(기본값 제거)해 호출처가 model 생성 시 쓴 프로바이더를 반드시 명시하도록 강제. 불일치 footgun 차단 + 회귀 테스트. [base.py:138-160]
- [x] [Review][Decision→Patch] `create_chat_model` provider/model 독립 기본값 비정합 — KTH 결정: **provider만 지정 시 model 필수**. provider 명시 + model 미지정이면 `LLMConfigurationError`로 선차단(전역 기본 model이 타 프로바이더에 적용되는 비정합 방지) + 회귀 테스트. [base.py:115-124]

### Patch (적용 완료)

- [x] [Review][Patch] 빈/공백 `model` 인자가 기본값을 우회 → 사용 불가 `_ConfigurableModel` 반환 — `model_name.strip()` 빈값을 `LLMConfigurationError`로 선차단 [base.py:126-130]
- [x] [Review][Patch] `model_provider`를 `**overrides`로 전달 시 raw `TypeError`(중복 kwarg) — `"model_provider" in overrides` 가드로 명확한 설정 오류 변환 [base.py:141-145]
- [x] [Review][Patch] `with_transient_retry` `attempts` 미검증 — `attempts < 1` 시 `ValueError`(0=무한 재시도, 음수=조용한 1회 강등 방지) [base.py:156-157]

### Deferred

- [x] [Review][Defer] `LLMConfigurationError`에 DomainError 정규화/전역 핸들러 없음 → 요청 경로 배선 시 raw 500 노출 우려 [errors.py:24-30, base.py:122] — deferred, 소비처(7.3/7.4)가 호출/핸들러 배선 소유
- [x] [Review][Defer] `adapters/__init__.py`가 3개 SDK 전부 import — 하나라도 import 실패 시 기준(OpenAI) 등록까지 동반 실패 [adapters/__init__.py:8] — deferred, 현재 4개 langchain-* 하드 핀이라 비발생(견고성 하드닝 후보)
- [x] [Review][Defer] `ProviderSpec.required` 미사용(데드) — 기동 시점 필수키 검증 등에 미활용 [base.py:55] — deferred, 후속 기동 검증에서 활용 여지
- [x] [Review][Defer] `_ensure_providers_loaded` 비스레드세이프 + 등록 중 `list_providers` 사본 생성 경합 [base.py:72-84] — deferred, import 락으로 실무 위험 낮음
- [x] [Review][Defer] `normalize_llm_error`가 `provider` 문자열을 사용자 메시지에 그대로 반영 + 잘못된 이름의 `api_key` override 시 불투명 에러 [errors.py:44-47, base.py:129] — deferred, 공개 export이나 신뢰 입력(레지스트리 키) 가정·저위험
