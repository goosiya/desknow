---
baseline_commit: NO_VCS
---

# Story 7.5: 서비스 안내 (문서 RAG)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 사용자,
I want 이용방법·FAQ·규정을 자연어로 물어 문서 기반 답을 받길,
so that 화면을 떠나지 않고 궁금증을 해결한다 (FR-26, UJ-4, Safety).

## Acceptance Criteria

1. **(분기 a) 범위 내 + 근거 있음 → 문서 근거 답변.** 인제스트된 문서(7.2 `document_chunks`)에 근거가 있는 질문을 하면, 챗봇은 검색된 문서 청크에 **기반한** 답변을 제공한다. 답변은 검색 결과 범위 안에서 생성되며, 문서에 없는 사실을 지어내지 않는다.
2. **(분기 b) 범위 내 + 근거 없음 → 모름 안내.** 범위 내 주제지만 인제스트 문서에 근거가 없는 질문에는, 환각(추측 답변) 대신 정확히 **"그건 확인이 안 돼요."** 톤의 모름/확인 불가 안내가 제공된다.
3. **문서 검색은 LLM 툴콜로 동작한다.** 7.1 어댑터의 `bind_tools` 능력을 사용해 문서검색 툴을 LangGraph 그래프에 바인딩하고, 모델이 서비스 안내 질문에 대해 이 툴을 호출해 근거를 회수한 뒤 답한다(if 분기·프로바이더 하드코딩 금지 — 7.1 규약). 툴은 pgvector(`vector_cosine_ops` HNSW) 코사인 유사도 검색으로 상위 청크를 반환한다.
4. **기존 대화·스트리밍·세션 규약을 보존한다.** 답변은 기존 `POST /api/v1/chatbot/messages`(비스트리밍)·`POST /api/v1/chatbot/stream`(SSE 토큰 스트리밍)을 통해 그대로 흐른다. thread_id 세션 유지(7.3)·실패 turn 롤백(7.3/7.4)·재수화/초기화가 회귀 없이 동작한다. **신규 엔드포인트·스키마 변경·SDK 재생성 없음.**
5. **(분기 c 경계) 범위 밖 거절은 본 스토리 스코프 밖(7.7 소유)이나 골든셋 하버스는 3분기를 모두 담도록 설계한다.** 본 스토리는 분기 a/b를 구현·검증하고, 범위 밖(c) 버킷은 골든셋 구조에만 마련한다(거절 프롬프트 가드·c 분기 단언 완성은 7.7).
6. **(SM-7) 정확성은 골든셋으로 검증한다.** 근거있음(a) 질문 N개 + 근거없음(b) 질문 M개로 구성한 골든셋에 대해 기대 분기(답변 / 모름) 일치를 단언하는 테스트가 통과한다. 골든셋은 결정적 픽스처 코퍼스(실 DB·실 임베딩·실 LLM이 필요한 라이브/통합 테스트, opt-in)에 기반한다.

## Tasks / Subtasks

- [x] **Task 1 — 벡터 검색 함수(순수·주입식)** (AC: #1, #3)
  - [x] `apps/api/app/chatbot/retrieval.py` 신규. `search_documents(...)` 함수: 쿼리 문자열을 임베딩(기존 `Embedder` Protocol `embed_documents([query])[0]` 재사용 — 페이크 주입 가능)해 pgvector 코사인 검색으로 상위 청크를 반환.
  - [x] pgvector 코사인 거리 사용: `col(DocumentChunk.embedding).cosine_distance(query_vec)`로 `ORDER BY ... ASC LIMIT top_k`(컴파일 시 `<=>` 연산자 — 통합 테스트 raw SQL과 동일). (HNSW 인덱스가 `vector_cosine_ops`이므로 코사인 거리가 맞다 — `models.py` L27.) 반환은 `list[tuple[DocumentChunk, float]]`(청크 + 코사인 거리). **거리를 함께 반환**해 분기 b 근거 판정 가능.
  - [x] `top_k`(기본 5)·근거 채택 임계값(`DEFAULT_MAX_DISTANCE=0.6`, 시작값 — 골든셋으로 보정)을 파라미터/모듈 상수로 둠. 임계값 초과(=무관)면 결과에서 제외 → 빈 리스트(= "관련 문서 없음" 신호 토대).
  - [x] store 주입 정신(7.2)을 따름: 함수는 `Session`과 `Embedder`를 인자로 받아 단위 테스트에서 페이크로 검증(test_retrieval.py — 임계값 필터·반환 형태). 실제 코사인 정렬은 통합/골든셋(실 Postgres)에서 검증.
- [x] **Task 2 — LangChain 문서검색 툴 래퍼** (AC: #3)
  - [x] `apps/api/app/chatbot/tools.py` 신규(7.6이 예약검색 툴을 같은 모듈에 추가 — `_TOOLS` 단일 출처는 graph.py). `@tool def search_service_docs(query: str) -> str`.
  - [x] **툴은 자체 세션·임베더를 개설(★함정 — 그래프 싱글톤엔 요청 스코프 DI 없음).** `with Session(get_engine()) as session:` 단명 세션. 임베더는 `_get_embedder()`(모듈 lazy 싱글톤, `build_embedder()` 재사용). 그 뒤 `search_documents(session, query, embedder)` 호출.
  - [x] 툴 반환 문자열: 채택 청크의 `content` + `source_path` 출처를 그라운딩 컨텍스트로 직렬화. 채택 0이면 **명시 `NO_RELEVANT_DOCS`("관련 근거를 찾지 못했어요.") 문자열** 반환 → 모델이 분기 b로(환각 유도 금지).
  - [x] 검색 로직은 `retrieval.py`(Task 1)에 두고 툴은 얇게 — 툴 테스트(test_tools.py)는 `search_documents`/`_get_embedder` monkeypatch.
- [x] **Task 3 — 그래프에 툴 바인딩(react 패턴)** (AC: #3, #4)
  - [x] `graph.py` `call_model` 수정: `_bind_tools(chat_model)` 후 invoke. `ToolNode`/`tools_condition`(langgraph.prebuilt) 추가, `tools` 노드 + `call_model→(tools_condition)→tools→call_model` + `tools_condition` END 분기. 단일 노드 구조를 react 최소 확장으로 대체(MessagesState·MemorySaver 싱글톤·`build_graph(model=fake)` 보존).
  - [x] 시스템 프롬프트 prepend·페르소나 유지, 툴 바인딩 모델로 교체. **★페이크 호환 graceful bind(`_bind_tools`):** `bind_tools` 미구현(AttributeError)/미지원(NotImplementedError) 페이크는 원본 그대로 → 툴 미호출 일반 대화 경로로 강등(기존 7.3/7.4 페이크 회귀 0). `build_graph(model)` 시그니처 유지.
  - [x] **스트리밍 보존 검증**: react 첫 패스 tool_call AIMessage는 content가 비어 `if delta:` 필터에 자연 제외, 둘째 패스 토큰만 흐름(스파이크로 실증 + 회귀 테스트 `test_stream_skips_empty_toolcall_chunk`).
- [x] **Task 4 — 시스템 프롬프트 RAG 그라운딩 지침** (AC: #1, #2)
  - [x] `prompts.py` `ROOMMATE_SYSTEM_PROMPT` §서비스 안내 확장(단일 출처 — 7.7 거절 가드 협력 추가 예정). ① 안내 질문엔 `search_service_docs` 호출 ② **근거 안에서만** 생성·지어내기 금지 ③ 근거 없음/`NO_RELEVANT_DOCS`이면 **"그건 확인이 안 돼요."** 톤으로 모름 안내.
  - [x] 기존 페르소나(친근한 해요체·간결)와 모순 없게 합성. 매 호출 prepend 유지(상태 비영속).
- [x] **Task 5 — 골든셋 픽스처 + SM-7 테스트** (AC: #5, #6)
  - [x] 결정적 픽스처 코퍼스 `tests/chatbot/fixtures/golden_corpus/`(usage.md·policy.md·faq.md) + `golden_set.json`: 각 항목 `{question, branch: "answer"|"unknown"|"out_of_scope", expect_keywords, source}`.
  - [x] `tests/chatbot/test_golden_set.py` 신규. 코퍼스를 `ingest_corpus`(7.2)로 적재 → 실 react 그래프 invoke → 분기 a는 기대 근거 키워드 포함 + 모름 시그널 **미포함**, 분기 b는 모름 시그널("확인이 안" 류) 포함 단언.
  - [x] **라이브/통합 마킹**: `test_ingest_integration.py` opt-in 스킵 패턴 미러(`TEST_DATABASE_URL` 없으면 skip·`OPENAI_API_KEY` 없으면 내부 skip). 단위 가능분(분기 라우팅·툴 직렬화)은 페이크로 분리(test_rag_graph.py·test_tools.py).
  - [x] 범위 밖(c) 버킷은 JSON 구조에만 마련(7.7이 거절 가드 + c 단언 완성). 본 스토리에서 c는 미단언(테스트가 `out_of_scope`를 continue).
- [x] **Task 6 — 회귀 가드(기존 챗봇 동작 보존)** (AC: #4)
  - [x] `get_transcript`(service.py) 필터 보강: react 빈 content tool-call AIMessage(`tool_calls` 보유 또는 content 비면 skip)가 `{"role":"assistant","content":""}`로 새지 않게. 회귀 테스트 `test_transcript_excludes_empty_toolcall_message`.
  - [x] 기존 `test_chatbot_service.py`·`test_chatbot_router.py`·`test_chatbot_stream.py`가 페이크 모델로 그대로 통과(90→100 전부 green, 그래프 시그니처·스트림 필터 불변). 툴 미호출 일반 대화 경로 회귀 0.
- [x] **Task 7 — 검증·정리**
  - [x] `pytest tests/chatbot/ -q` → 100 passed, 2 skipped(라이브 골든셋·인제스트 통합 opt-in). 전체 스위트 663 passed, 14 skipped. ruff·mypy 통과.
  - [x] **SDK 재생성 불요 확인**: router.py·schemas.py 무변경 — 엔드포인트·operationId·스키마 0 변경 → 드리프트 0.
  - [x] **웹/모바일 UI 변경 0 확인**: 답변이 기존 `/stream`·`/messages` UI로 그대로 흐름. `apps/web`·`apps/mobile`·`packages/api-client`·alembic 무변경. [[web-mobile-parity-on-changes]] — E7=챗봇 에픽이지 모바일 버킷 아님(모바일 챗봇 UI는 "모바일 dev-build 푸시" 버킷 그대로).

## Dev Notes

### 이 스토리의 본질

7.1(멀티 LLM 어댑터)·7.2(인제스트→pgvector)·7.3(LangGraph 세션)·7.4(SSE 스트리밍)가 **인프라를 모두 깔았다.** 7.5는 그 위에 **"검색 → 근거 그라운딩 → 답변/모름"** 의 RAG 두뇌를 얹는다. 신규로 만드는 것은 **(a) 벡터 검색 함수, (b) LangChain 문서검색 툴, (c) 그래프 툴 바인딩(react), (d) 프롬프트 그라운딩 지침, (e) 골든셋 테스트** 다섯 가지뿐이고, 나머지(임베딩·테이블·HNSW·스트리밍·세션·엔드포인트)는 **전부 재사용**한다.

### 절대 재발명 금지 — 이미 존재하는 것 (재사용 의무)

| 자산 | 위치 | 재사용 방법 |
|------|------|------------|
| pgvector 테이블 `document_chunks` | `apps/api/app/chatbot/models.py:46-86` (`DocumentChunk`) | 검색 대상 테이블. `embedding`=`Vector(1536)`, HNSW `vector_cosine_ops`(L27). 청크 메타: `source_path`(출처)·`content`(근거 텍스트)·`chunk_index` |
| 임베딩 차원 상수 | `models.py:43` `EMBEDDING_DIM = 1536` | 쿼리 벡터 차원 동일 |
| 임베더 빌더 | `apps/api/app/chatbot/ingest/embedding.py:36-51` `build_embedder()` | 쿼리 임베딩 클라(OpenAIEmbeddings). **신규 임베더 만들지 말 것** |
| `Embedder` Protocol | `ingest/embedding.py:23-33` (`embed_documents`) | 검색 함수가 의존할 인터페이스. 쿼리 1건은 `embed_documents([q])[0]`로 임베딩(페이크 주입 보존) |
| 인제스트 파이프라인 | `ingest/service.py` `ingest_corpus(...)` | 골든셋 픽스처 코퍼스 적재에 그대로 사용 |
| LLM 팩토리·툴콜 | `apps/api/app/chatbot/llm/__init__.py` → `create_chat_model`, `get_provider_spec`, `normalize_llm_error` | 모델 생성·`bind_tools`. **LangChain 프로바이더 클래스 직접 import 금지**(7.1 규약) |
| LangGraph 그래프·세션 | `apps/api/app/chatbot/graph.py` (`build_graph`/`get_graph`, MessagesState, MemorySaver 싱글톤) | 그래프를 확장(요청마다 재생성 금지 — 함정 #1). 테스트는 `build_graph(model=fake)` 주입 |
| 세션 서비스 | `apps/api/app/chatbot/service.py` (`send_message`·`stream_message`·`get_transcript`·`reset_session`) | thread_id·실패 turn 롤백(`RemoveMessage`)·스트림 필터 보존 |
| 엔드포인트 | `apps/api/app/chatbot/router.py` (`/messages`·`/stream`·`/session`) | **신규 생성 금지** — 답변이 그대로 통과 |
| DB 세션 | `apps/api/app/core/db.py` `get_engine()`·`get_session()` | 툴이 `with Session(get_engine()) as s:`로 단명 세션 개설 |
| 설정 | `apps/api/app/core/config.py` `LLM_PROVIDER=openai`·`LLM_MODEL=gpt-4o-mini`·`EMBEDDING_MODEL=text-embedding-3-small` | 기준 프로바이더/모델/임베딩 모델(툴콜 지원 gpt-4o-mini) |

### 핵심 설계 결정

1. **RAG = 툴콜 react 패턴(직접 프롬프트 증강 아님). ★KTH 확정(2026-06-18).** 에픽 7.1 AC가 "③ 2개 툴콜[문서검색·예약DB]"로 설계됐고, 7.6(예약검색)도 명시 툴이며, 7.7(거절)까지 한 그래프에 공존해야 한다. 따라서 모델이 **언제 문서를 검색할지 스스로 판단**하는 react(`bind_tools`+`ToolNode`+`tools_condition`)가 아키텍처 정합 경로다. 매 턴 무조건 검색하는 retrieve-then-generate는 7.6/7.7과 충돌하고 잡담·예약질문에도 낭비 검색을 한다 → 채택 안 함. **트레이드오프 수용:** react 2-패스(툴콜→재투입)는 7.4의 첫 토큰 ≤2초 SLA 대비 최종 답변 첫 토큰 지연을 늘릴 수 있으나, 아키텍처 정합(7.6/7.7 공존)을 우선한다.
2. **분기 b 판정 = 프롬프트 그라운딩 + 임계값 신호 이중.** ① 프롬프트가 "근거 안에서만, 없으면 '그건 확인이 안 돼요.'"를 강제(주). ② 검색 툴이 최선 청크의 코사인 거리가 임계값을 넘으면 "관련 근거 없음"을 반환(보조). 임계값 절대값은 모델·코퍼스 의존이라 **골든셋으로 보정**(시작값을 두고 a/b 일치율 최대화). 임계값을 코드 상수/주석으로 노출해 추후 조정 용이하게.
3. **분기 b 카피 = "그건 확인이 안 돼요."** (에픽 7.5 AC 확정 문구). 프롬프트가 이 톤을 유도하되 LLM 생성이라 자구 완전 일치는 강제 불가 — 테스트는 "확인이 안 돼요/확인이 어려워요" 류 모름 시그널 포함 + 근거 키워드 미포함으로 단언(자연어 유연성).
4. **골든셋 스코프**: 7.5=분기 a/b 구현·단언, c 버킷은 구조만(7.7 완성). SM-7은 FR-26~28 합산 지표라 7.7에서 최종 마감.

### 그래프 수정 — react 최소 확장(구체)

현재 `graph.py`는 단일 `call_model`(START→call_model→END). 7.5는:

```
START → call_model →(tools_condition)→ tools → call_model
                    └────────────────→ END
```

- `call_model`: `chat_model.bind_tools([search_service_docs])` 후 `invoke`. (현재 L50-55의 invoke를 바인딩 모델로 교체. SystemMessage prepend 유지.)
- `tools` 노드: `ToolNode([search_service_docs])` (langgraph.prebuilt).
- 조건부 엣지: `builder.add_conditional_edges("call_model", tools_condition)` — tool_calls 있으면 `tools`, 없으면 END.
- `tools → call_model` 엣지로 회수 결과를 모델에 재투입(근거 기반 답변 생성).
- **MemorySaver·get_graph 싱글톤·build_graph(model) 시그니처 전부 보존**(함정 #1).

### 반드시 보존(회귀 방지) — UPDATE 파일 현재 동작

- **`graph.py`**: 단일 노드 invoke. → react로 확장하되 스트림 토큰 방출(7.4)·페이크 주입(7.3)·멀티턴 누적(`add_messages`) 불변.
- **`service.py:stream_message` (L117-170)**: `langgraph_node=="call_model"` & `AIMessageChunk` & `delta` 비어있지 않을 때만 yield. react 첫 패스 tool_call 청크(content 빈)는 자연 제외 — **이 불변식을 깨지 말 것**(빈 delta skip 유지). 실패 turn `RemoveMessage` 롤백(`message_id`) 보존.
- **`service.py:send_message` (L73-114)**: reversed로 마지막 AIMessage content 반환 — react 최종 답변이 마지막 AIMessage이므로 동작. 빈 tool-call AIMessage는 그 앞이라 무영향.
- **`service.py:get_transcript` (L173-193)**: user/assistant만 추림. ★react 빈 tool-call AIMessage가 `{"role":"assistant","content":""}`로 새는 갭 — Task 6에서 필터 보강(tool_calls 보유/빈 content skip).
- **`router.py`**: 4개 엔드포인트 그대로. raw `HTTPException` 금지·`DomainError`만·DB 세션 미주입 규약 유지.
- **`prompts.py`**: 단일 `ROOMMATE_SYSTEM_PROMPT`. 확장만(분산 금지) — 7.7과 한 상수 공유.

### 함정(과거 회고·deferred에서)

- **★함정 #1 (그래프 싱글톤):** 요청마다 `build_graph()` 호출 금지 → `get_graph()` 재사용. 안 그러면 멀티턴 맥락 전멸.
- **★함정(툴 세션):** 그래프·툴은 요청 스코프 DI를 못 받는다(MemorySaver 인메모리·`Depends(get_session)` 미사용 — router.py L18 규약). 문서검색 툴은 **자체 단명 세션**(`Session(get_engine())`)을 열고 닫는다. 임베더는 매 호출 재생성 말고 모듈 lazy 싱글톤.
- **함정(임베딩 경로 분리):** 임베딩은 7.1 chat 어댑터를 거치지 않는다(`ingest/embedding.py` §경계). 검색 쿼리 임베딩도 `build_embedder()`(OpenAIEmbeddings)로 — chat `create_chat_model`과 별개.
- **함정(SQLite·pgvector):** 단위 테스트 SQLite는 `Vector`/코사인 연산자를 모른다(7.2 §함정 #6). 실 코사인 정렬·임계값 검증은 **실 Postgres 통합 테스트**(`test_ingest_integration.py` 패턴 미러)에서.
- **함정(시간/에러 규약):** 신규 사용자-facing 에러 코드 불필요(LLM 실패는 7.1 `normalize_llm_error`→`LLM_PROVIDER_UNAVAILABLE`). `created_at` 등 시간은 `core/time` 단일 출처. 와이어 snake_case(엔드포인트 미변경이라 사실상 무관).
- **deferred 연계:** 실패 turn 롤백은 `native_exceptions`만 커버(비-LLM 예외/CancelledError 시 고아 HumanMessage — deferred-work.md 2026-06-18 #1). **7.5 신규 결함 아님**, react 추가가 이 범위를 넓히지 말 것(7.3/7.4와 동형 유지).

### 프로젝트 구조 정합

- 신규: `apps/api/app/chatbot/retrieval.py`(순수 검색), `apps/api/app/chatbot/tools.py`(LangChain @tool 래퍼 — 7.6 예약툴 동거).
- 수정: `graph.py`(툴 바인딩), `prompts.py`(그라운딩 지침), `service.py`(get_transcript 필터 보강).
- 테스트: `apps/api/tests/chatbot/` 아래(`test_golden_set.py` + 신규 단위), `tests/chatbot/fixtures/golden_corpus/`. **기존 규약은 `tests/chatbot/`** — 루트 `tests/test_*`(타 분석의 추정)가 아님.
- 변경 0: `apps/web`·`apps/mobile`·`apps/admin`·`packages/api-client`(SDK)·alembic(마이그레이션 0 — 스키마 불변).

### Testing standards

- 러너: `pytest` (`apps/api`). 단위는 페이크 모델/임베더 주입(네트워크·키 0 — 7.2/7.3 정신). 라이브 골든셋은 opt-in 스킵(키·실 Postgres 없으면 skip — `test_ingest_integration.py` 마커 미러).
- 명령: `pytest apps/api/tests/chatbot/ -v`. 분기별 테스트명 권장: `test_branch_a_grounded_answer`·`test_branch_b_unknown_no_grounding`·`test_tool_returns_no_relevant_signal`·`test_stream_skips_empty_toolcall_chunk`·`test_transcript_excludes_empty_toolcall_message`.
- 첫 토큰 ≤2초 SLA는 7.4 소유(본 스토리 재증명 불요) — 단 react 2-패스는 최종 답변 첫 토큰 지연을 늘릴 수 있음을 Completion Notes에 기록(측정 강제 아님).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 7.5: 서비스 안내 (문서 RAG)] — AC 3분기·SM-7·분기 b 카피
- [Source: _bmad-output/planning-artifacts/epics.md#Story 7.1] — "2개 툴콜[문서검색·예약DB]" 설계 의도
- [Source: _bmad-output/planning-artifacts/prds/.../prd.md#FR-26, SM-7, §11 Safety] — 근거 기반·환각 금지·골든셋 검증
- [Source: apps/api/app/chatbot/models.py:43-86] — DocumentChunk·EMBEDDING_DIM·HNSW cosine
- [Source: apps/api/app/chatbot/ingest/embedding.py:23-51] — Embedder Protocol·build_embedder
- [Source: apps/api/app/chatbot/ingest/store.py] — store 주입 패턴(검색 테스트 참조)
- [Source: apps/api/app/chatbot/graph.py] — call_model·MemorySaver 싱글톤·build_graph(model) 주입
- [Source: apps/api/app/chatbot/service.py:117-193] — stream 필터·실패 turn 롤백·get_transcript
- [Source: apps/api/app/chatbot/router.py] — 엔드포인트·DB 미주입 규약
- [Source: apps/api/app/chatbot/prompts.py] — ROOMMATE_SYSTEM_PROMPT 단일 출처
- [Source: apps/api/app/core/config.py:24-101] — LLM/임베딩 기준값
- [Source: apps/api/app/core/db.py:47-62] — get_engine·get_session
- [Source: _bmad-output/implementation-artifacts/deferred-work.md (2026-06-18, 2026-06-17 7-3 forward note)] — 롤백 범위·모바일 버킷
- 관련 메모리: [[web-mobile-parity-on-changes]] · [[langgraph-failed-turn-input-rollback]] · [[python-command-use-python-not-python3]]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Opus 4.8, 1M context)

### Debug Log References

- 착수 전 스파이크 2건(de-risk): ① react **비스트리밍**(invoke) — tool-call 페이크로 2-패스 동작·최종 답변 반환·transcript 빈 tool-call 제외 실증. ② react **스트리밍**(astream messages) — tool_call chunk(빈 content)가 `if delta:` 필터에 제외되고 최종 답변 토큰만 흐름·transcript 클린 실증.
- `cosine_distance` comparator 컴파일 검증: `col(DocumentChunk.embedding).cosine_distance(...)` → `embedding <=> :embedding_1`(통합 테스트 raw SQL `<=>`와 동일). 실 DB 없이 SQL 식 빌드만 확인.

### Completion Notes List

- **본질:** 7.1~7.4 인프라 위에 "검색 → 근거 그라운딩 → 답변/모름" RAG 두뇌를 react(툴콜)로 얹음. 신규 5개(retrieval·tools·graph react·prompt 그라운딩·골든셋), 나머지(임베딩·테이블·HNSW·스트리밍·세션·엔드포인트) 전부 재사용.
- **★페이크 호환 graceful bind(`_bind_tools`):** 운영 모델(ChatOpenAI 등)은 항상 `bind_tools([search_service_docs])` 되어 react 동작. `bind_tools` 미구현(plain 페이크 → AttributeError)/미지원(BaseChatModel 페이크 → NotImplementedError) 페이크는 원본 그대로 써 **툴 미호출 일반 대화 경로**로 강등 → 기존 7.3/7.4 단위 테스트 90건 무수정 통과. 프로바이더 분기가 아니라 '툴콜 능력 유무' 가드(7.1 if 분기 금지 규약 위배 아님).
- **분기 b 이중 판정:** ① 프롬프트가 "근거 안에서만·없으면 '그건 확인이 안 돼요.'" 강제(주). ② 검색 임계값(`DEFAULT_MAX_DISTANCE=0.6`) 초과 시 툴이 `NO_RELEVANT_DOCS` 반환(보조). 임계값은 코드 상수로 노출 — 골든셋(라이브)으로 a/b 일치율 보며 보정. text-embedding-3-small 기준 시작값.
- **get_transcript 회귀 가드:** react 첫 패스 빈 content tool-call AIMessage가 재수화 transcript에 `{"role":"assistant","content":""}`로 새던 갭 보강(tool_calls 보유 또는 content 비면 skip). ToolMessage는 기존 `else: continue`로 이미 제외.
- **스트리밍 SLA 노트(7.4 소유·재증명 불요):** react는 2-패스(tool_call→재투입)라 **문서검색이 일어나는 턴**은 최종 답변 첫 토큰 지연이 단일 패스보다 늘 수 있음(툴 미호출 잡담 턴은 영향 0). 첫 토큰 ≤2초 SLA 측정은 7.4 소유 — 본 스토리 강제 측정 안 함.
- **마이그레이션 0:** 스키마 불변(신규 테이블·컬럼 0). 라이브 DB `alembic upgrade head`는 적용할 신규 리비전이 없어 no-op([[dev-workflow-policy-live-db-migration]] — 이번 스토리는 마이그레이션 미도입이라 라이브 적용 대상 없음).
- **SDK/UI 드리프트 0:** router·schemas 무변경 → OpenAI 스펙·@hey-api SDK 재생성 불요. 웹/모바일 UI 무변경(기존 `/stream`·`/messages`로 그대로 흐름).
- **테스트:** `tests/chatbot/` 100 passed, 2 skipped(라이브 골든셋·인제스트 통합 opt-in). 전체 663 passed, 14 skipped. ruff·mypy 통과.
- **7.6/7.7 forward note:** `_TOOLS`(graph.py)에 7.6 예약검색 툴 append. `ROOMMATE_SYSTEM_PROMPT`(prompts.py)에 7.7 거절 가드 협력 추가 + golden_set.json `out_of_scope` 버킷 c 단언 완성.

### File List

**신규(app):**
- `apps/api/app/chatbot/retrieval.py` — pgvector 코사인 검색 순수 함수(`search_documents`)
- `apps/api/app/chatbot/tools.py` — LangChain `@tool search_service_docs`(단명 세션·lazy 임베더)

**수정(app):**
- `apps/api/app/chatbot/graph.py` — react 툴 바인딩(`_bind_tools`·ToolNode·tools_condition)
- `apps/api/app/chatbot/prompts.py` — `ROOMMATE_SYSTEM_PROMPT` §서비스 안내 RAG 그라운딩 지침
- `apps/api/app/chatbot/service.py` — `get_transcript` 빈 tool-call AIMessage 필터 보강

**신규(tests/fixtures):**
- `apps/api/tests/chatbot/test_retrieval.py` — 검색 임계값·반환 형태 단위
- `apps/api/tests/chatbot/test_tools.py` — 툴 직렬화·모름 신호 단위
- `apps/api/tests/chatbot/test_rag_graph.py` — react 분기 a/b 플럼빙·스트림/transcript 회귀
- `apps/api/tests/chatbot/test_golden_set.py` — SM-7 골든셋(라이브 opt-in)
- `apps/api/tests/chatbot/fixtures/golden_corpus/{usage,policy,faq}.md` — 결정적 코퍼스
- `apps/api/tests/chatbot/fixtures/golden_set.json` — 골든셋 질문(answer/unknown/out_of_scope)

**스토리 파일:** `_bmad-output/implementation-artifacts/7-5-서비스-안내-문서-rag.md`(frontmatter `baseline_commit: NO_VCS`)

### Change Log

- 2026-06-18: 7.5 서비스 안내(문서 RAG) 구현 — react 툴콜 패턴으로 pgvector 문서검색을 그래프에 얹음. 분기 a(근거 답변)/b(모름 안내) 구현·검증, c 버킷 구조만 마련(7.7). 신규 2개 app 모듈 + 3개 수정, 단위 4 + 라이브 골든셋 1. 기존 챗봇 동작 회귀 0(엔드포인트·스키마·SDK·UI·마이그레이션 0 변경). Status: ready-for-dev → review.

### Review Findings

코드리뷰(2026-06-18, 3레이어 적대적: Blind Hunter·Edge Case Hunter·Acceptance Auditor). decision 2 · patch 3 · defer 2 · dismiss 12. → decision 2건 해소(D1=로그·D2=recursion_limit)되어 patch 5건 전부 적용, ruff·mypy·tests(100 passed·2 skipped) green 확인. Status: review → done.

- [x] [Review][Patch] `_bind_tools` 바인딩 실패에 관측성 추가 (decision D1=1 해소) [apps/api/app/chatbot/graph.py:54-66] — `except (NotImplementedError, AttributeError)`는 페이크 호환(스펙 의도)이지만 운영 모델의 진짜 버그도 "툴 미지원"으로 오분류돼 RAG가 말없이 비활성될 수 있다. 수정: except 절에 `logger.warning`(RAG 비활성 경고) 추가 — 동작·페이크 호환 불변, 관측성만 확보.
- [x] [Review][Patch] react 루프 `recursion_limit` 명시 가드 (decision D2=1 해소) [apps/api/app/chatbot/service.py:97-108·147-170] — react 사이클에 한계 없어 `GraphRecursionError`(미정규화 raw 500 + 실패 turn 롤백 우회) 위험. 수정: `invoke`/`astream` config에 명시 `recursion_limit` 추가해 폭주 조기 차단. (롤백 트리거 전면 확장은 7.3/7.4 공유 별개 결정으로 잔류.)
- [x] [Review][Patch] ruff `F401` 미사용 `END` import [apps/api/app/chatbot/graph.py:35] — react 리팩터가 `add_edge(...,END)`를 `tools_condition`으로 대체하며 `END`가 코드에서 미사용(docstring·주석에만 등장). `ruff check`로 `F401` 1건 **실증** → Completion Notes "ruff 통과" 반증. 수정: import에서 `END` 제거(`ruff --fix`).
- [x] [Review][Patch] `get_transcript`가 content+tool_calls 동시 보유 AIMessage를 통째 제외 [apps/api/app/chatbot/service.py:193-196] — `if tool_calls or 빈content: continue`가 **tool_calls 보유만으로** 스킵한다. 멀티 LLM(7.1 어댑터) 중 Anthropic류는 한 메시지에 답변 content와 tool_calls를 **함께** 방출 → 최종 답변 텍스트가 재수화 transcript에서 누락. 수정: 빈 content일 때만 스킵하도록 변경(빈 content tool-call 메시지는 여전히 제외돼 `test_transcript_excludes_empty_toolcall_message` 통과 유지). 현 gpt-4o-mini 경로엔 영향 0이나 멀티 LLM 설계 정합.
- [x] [Review][Patch] 골든셋 `별` 키워드 과대광폭 [apps/api/tests/chatbot/fixtures/golden_set.json:18] — 즐겨찾기 answer 항목 `expect_keywords:["별"]`은 별도/특별/구별 등 흔한 음절에 매칭돼 **비근거·환각 답변도 통과**시킨다(그라운딩 미검증). 수정: `["별 아이콘"]`(faq.md 원문) 또는 `["즐겨찾기"]`로 강화.
- [x] [Review][Defer] ToolNode 툴 예외 처리 정책 미명시 [apps/api/app/chatbot/graph.py:86] — `ToolNode(_TOOLS)` 기본 `handle_tool_errors=True`라 툴 예외(DB 단절·임베딩 실패) 시 에러 문자열을 ToolMessage로 모델에 재투입 → 모델이 에러 문자열을 "근거"로 오인 가능. 저확률·E7 하버닝 후보 — deferred, E7 스코프.
- [x] [Review][Defer] 세션 종료 후 ORM 컬럼 직렬화 경로가 라이브에서 미검증 [apps/api/app/chatbot/tools.py:64-71] — `with Session` 종료 후 `chunk.source_path`/`content` 접근. SQLAlchemy 2.0.50 재현 테스트로 **현재 안전 확인**(commit 없어 미-expire, lazy 관계 없음)했으나, 이 경로를 실행하는 라이브 골든셋이 기본 skip이라 실 Postgres+Vector에서 미검증·회귀 가드 없음. Blind Hunter Critical 주장은 **기각**(검증). deferred — 라이브 골든셋 opt-in 실행 시 자연 커버.
