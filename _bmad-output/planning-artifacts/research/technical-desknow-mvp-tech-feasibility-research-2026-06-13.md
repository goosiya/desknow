---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: ['docs/idea.md']
workflowType: 'research'
lastStep: 6
research_type: 'technical'
research_topic: 'DeskNow MVP 기술 타당성 (네이버 지도/주소, RAG 챗봇, JWT 인증, Railway/EAS 배포)'
research_goals: '브리프/PRD 진입 전, 제품 범위를 좌우하는 핵심 기술 항목의 타당성·제약·대안 확인 (타당성 위주, 빠르게)'
user_name: 'KTH'
date: '2026-06-13'
web_research_enabled: true
source_verification: true
---

# Research Report: technical

**Date:** 2026-06-13
**Author:** KTH
**Research Type:** technical

---

## Research Overview

본 리포트는 스터디룸 예약 서비스 **DeskNow MVP**의 핵심 기술 타당성을, 브리프/PRD 진입 전에 검증하기 위해 수행한 기술조사 결과다. idea.md를 입력으로, 제품 범위를 좌우하는 4개 영역(지도/주소, RAG 챗봇 스택, JWT 인증, Railway/EAS 배포)과 DeskNow 특화 연동(카카오톡 공유·예약 알림·챗봇 스트리밍·웹/앱 REST 공용) 및 아키텍처 결정(백엔드 구조·모노레포·예약 동시성)을 다뤘다. 모든 핵심 주장은 2026-06-13 기준 공개 웹 출처로 검증했고, 신뢰도(High/Medium/Low)를 표기했다.

**결론 요약:** 제안 스택은 MVP 구현에 **전반적으로 타당**하다. 다만 3가지 결정이 제품 범위·비용에 영향을 주므로 PRD 전에 못 박아야 한다 — ① **지도/주소는 네이버 대신 카카오맵 우선 권장**(네이버 무료정책 재편), ② **Railway 상시 컨테이너 과금** 인지·모니터링, ③ **비밀번호 강제 복잡도 정책이 최신 NIST 권고와 충돌**(차기 완화 권장). 또한 idea.md의 "중복 예약 방지"는 복잡한 락이 아니라 **PostgreSQL 유니크/배제 제약**으로 원자적 해결이 가능하다는 점이 핵심 발견이다.

전체 상세 분석은 아래 Technology Stack / Integration Patterns / Architectural Patterns 섹션을, 전략 종합·리스크·로드맵은 말미의 **Executive Synthesis** 섹션을 참조.

---

<!-- Content will be appended sequentially through research workflow steps -->

## Technical Research Scope Confirmation

**Research Topic:** DeskNow MVP 기술 타당성 (네이버 지도/주소, RAG 챗봇, JWT 인증, Railway/EAS 배포)
**Research Goals:** 브리프/PRD 진입 전, 제품 범위를 좌우하는 핵심 기술 항목의 타당성·제약·대안 확인 (타당성 위주, 빠르게)

**Technical Research Scope (4개 영역):**

1. 지도 & 주소 (네이버) — 네이버 지도/주소 API 사용 가능 여부·요금·약관, 좌표↔주소 변환, 반경/행정동 검색, 대안
2. RAG 챗봇 스택 — LangGraph/LangChain + pgvector, OpenAI/Google/Anthropic 멀티 LLM 스위칭, 문서 인제스트 파이프라인
3. 인증/세션 (JWT) — Next.js 웹 + React Native 공용 JWT, FastAPI 구현, 비밀번호 정책
4. 배포 (Railway + EAS) — Railway에서 Next.js/FastAPI/PostgreSQL(+pgvector) 운영, Supabase→Railway 이관, Expo EAS 빌드

**Research Methodology:**

- 최신 공개 웹 데이터 + 엄격한 출처 검증
- 핵심 기술 주장에 대한 다중 출처 교차 검증
- 불확실 정보에 대한 신뢰도(confidence) 표기
- 타당성 중심 — "되는지 / 핵심 제약 / 대안"에 집중

**Scope Confirmed:** 2026-06-13

---

## Technology Stack Analysis

> 4개 영역을 병렬 리서치 에이전트로 조사. 모든 핵심 주장은 2026-06-13 기준 웹 출처로 검증. 신뢰도(High/Medium/Low)와 최신성을 함께 표기.

### 1. 지도 & 주소 (Map / Geocoding)

**네이버 지도 API (NCP Maps)** — _결론: 조건부 가능_
- 구 "AI NAVER API ▶ 지도 API"는 2025-05-22 신규 신청 차단, 무료 이용량 2025-06-30 종료 → 신규는 **Maps 단독 상품**으로 재신청해야 무료분 제공. SDK(Web Dynamic Map v3, React Native 래퍼) 사용 가능, 상업적 이용 허용(결제수단 등록 필수).
- 제약: 현행 건당 단가·무료 한도가 콘솔 로그인/요금계산기에서만 확정 가능 → 초기 비용 예측에 불확실성.
- _Source: https://www.ncloud.com/support/notice/all/1930 , https://www.ncloud.com/product/applicationService/maps , https://guide.ncloud-docs.com/docs/maps-overview_
- _신뢰도: Medium-High (종료 사실·프레임워크 호환 확정 / 현행 단가 Medium)_

**Geocoding / Reverse Geocoding (주소↔좌표)** — _결론: 가능_
- 주소→좌표, 좌표→(법정동·행정동·지번·도로명) 모두 REST 지원, 한국 주소 정확도 최상위. 무료 한도는 Maps 단독 상품 기준으로 재편 → 콘솔 확인 필요.
- _Source: https://guide.ncloud-docs.com/docs/maps-geocoding-api , https://guide.ncloud-docs.com/docs/maps-reversegeocoding-api_
- _신뢰도: Medium_

**반경(km) 검색 vs 행정동 검색** — _결론: 가능 (둘 다 저장 권장)_
- 반경: 좌표(lat/lng) 저장 후 ① Haversine 직접계산(소규모 OK) ② **PostGIS `ST_DWithin`**(GiST 인덱스, 성능 우수) ③ earthdistance/cube(경량 대안).
- 행정동: 법정동/행정동 표준코드 매핑 저장 → 코드 prefix 매칭(공간연산 불필요, 최저비용). Reverse Geocoding으로 좌표→코드 자동 부여.
- 권장: 좌표 + 행정동 코드를 **둘 다 저장**해 두 검색 UX 동시 지원.
- _Source: https://postgis.net/docs/manual-3.0/postgis-ko_KR.html_
- _신뢰도: High (확립된 표준 기술)_

**대안 비교**
- **카카오맵(가장 관대):** 지도 SDK 일 300,000건 무료(초과 0.1원/건), 로컬 API(주소↔좌표·좌표→행정구역) 각 일 100,000건 무료. 한국 주소 정확도·문서 품질 우수. _Source: http://developers.kakao.com/docs/ko/getting-started/quota_
- **Google Maps Platform:** 2025-03 정책변경으로 월 $200 크레딧 폐지 → SKU별 무료 임계치(동적지도 ~월 28,500 maploads)로 축소, 구독제 도입, USD 과금, 국내 주소/POI 정확도 약함. _Source: https://developers.google.com/maps/billing-and-pricing/march-2025_
- _신뢰도: High_

### 2. RAG 챗봇 스택 (LangGraph/LangChain + pgvector + 멀티 LLM)

**pgvector 벡터 스토어** — _결론: 가능_
- 2026년 프로덕션 검증 완료, MVP~중규모 RAG에 충분. **HNSW가 기본 인덱스**(0.8에서 빌드 속도·스트리밍 insert 개선). ~500만 벡터 이하에서 한 자릿수 ms — 스터디룸 MVP 문서량은 한계에 한참 못 미침. Railway·Supabase 모두 즉시 사용 가능.
- _Source: https://github.com/langchain-ai/langchain-postgres , https://railway.com/deploy/pgvector-latest_
- _신뢰도: High (2026.3~6 자료)_

**LangGraph + LangChain 챗봇** — _결론: 가능_
- **LangChain v1.0**(안정 API, 시맨틱 버저닝) 출시. 대화 메모리=LangGraph **checkpointer**(DB 영속·세션 격리), 문서검색+DB검색=`@tool` 멀티툴 에이전트(`create_agent()`), 범위 밖 질문 거부=`before_model` 미들웨어/조건부 라우팅(PROCEED/ASK/REFUSE/UNKNOWN).
- 주의: 구버전 `LLMChain`/`ConversationChain` deprecated → 신규는 LangGraph 기반. langchain-core CVE 패치 활발 → 버전 고정.
- _Source: https://docs.langchain.com/oss/python/langchain/rag , https://docs.langchain.com/oss/python/langchain/guardrails_
- _신뢰도: High_

**멀티 LLM 스위칭 (OpenAI/Gemini/Anthropic)** — _결론: 가능_
- `init_chat_model("anthropic:..."/"openai:..."/"google_genai:...")` 추상화로 런타임 교체, `configurable_fields`로 동적 전환.
- 주의: ① 모델 ID 정확 명시(Anthropic 최신 `claude-opus-4-8`/비용·속도 균형 `claude-sonnet-4-6`). Opus 4.7/4.8은 `temperature`/`top_p`/`top_k` 제거(전달 시 400) → adaptive thinking 사용 ⇒ 공통 `temperature` 인자를 전 프로바이더에 그대로 쓰면 깨질 수 있어 래핑 레이어에서 분기 필요. ② 구조화출력·툴콜·토큰한도 등 기능 비대칭 → MVP는 채팅+툴콜 공통기능에 한정.
- _Source: https://reference.langchain.com/python/langchain/chat_models/base/init_chat_model , https://docs.langchain.com/oss/python/integrations/chat_
- _신뢰도: High(스위칭) / Medium(파라미터 비대칭은 구현 시 실측)_

**문서 인제스트 파이프라인 + 임베딩** — _결론: 가능_
- 표준: DocumentLoader(디렉토리) → TextSplitter 청킹 → Embeddings → **PGVectorStore** 적재 → similarity search. 공식 `langchain-postgres` 사용(`PGVector` deprecated → `PGVectorStore`, async/psycopg3, FastAPI 정합). 인제스트/검색 파이프라인 분리 권장.
- 임베딩 요금(1M 토큰): OpenAI `text-embedding-3-small` **$0.02**(균형 기본값), Google `gemini-embedding-001` $0.006~(최저가), Voyage(품질 특화). **임베딩 모델은 단일 고정 원칙**(교체 시 전체 재임베딩).
- _Source: https://github.com/langchain-ai/langchain-postgres , https://tokenmix.ai/blog/text-embedding-models-comparison_
- _신뢰도: High_

### 3. 인증 / 세션 (JWT)

**웹+앱 공용 JWT** — _결론: 가능_
- 동일 FastAPI 발급 JWT를 웹/앱이 공유하는 표준 패턴. access(5~15분)+refresh(7~30일). 보관: 웹=access 메모리/refresh httpOnly+Secure+SameSite 쿠키, RN(Expo)=`expo-secure-store`(Keychain/Keystore)+Bearer 헤더. **"웹은 쿠키 / 앱은 헤더" 양쪽 추출 지원 의존성**이 흔히 빠뜨리는 부분.
- _Source: https://workos.com/blog/secure-jwt-storage , RFC 9700_
- _신뢰도: Medium-High_

**FastAPI 구현 라이브러리** — _결론: 가능_
- 2026 권장 = **PyJWT**(토큰) + **pwdlib[argon2]**(해싱). 공식 FastAPI 튜토리얼이 이 조합으로 갱신됨. `python-jose`(유지보수 우려)·passlib+bcrypt 호환 경고는 신규 채택 비권장.
- _Source: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/_
- _신뢰도: High (공식 문서 직접 확인)_

**refresh 회전 / 로그아웃 / RBAC** — _결론: 조건부 가능_
- refresh 회전 + 로그아웃(무효화) + 3역할 RBAC는 MVP 수준 충분. 단 즉시 무효화 위해 **서버측 저장소(Redis 또는 DB, refresh 해싱 저장)가 사실상 필수**. RBAC는 JWT `role` 클레임 + FastAPI 의존성(난이도 하). Redis 도입 여부가 핵심 결정 포인트.
- _Source: https://www.obsidiansecurity.com/blog/refresh-token-security-best-practices , RFC 9700_
- _신뢰도: Medium-High_

**비밀번호 정책 검증** — _결론: 조건부 가능 (함정 주의)_
- 검증은 **백엔드(Pydantic)가 신뢰 경계 필수**, 프론트는 UX 보조. ⚠️ idea.md의 "8자+대/특/숫 각 1 강제"는 **최신 NIST SP 800-63B Rev.4(2025)와 어긋남** — NIST는 강제 복잡도 제거·길이 우선·유출목록 대조 권고. MVP 수용은 가능하나 차기 개선 항목으로 명시 권장.
- _Source: https://drata.com/learn/nist/password-guidelines , OWASP_
- _신뢰도: High (NIST Rev.4 기준)_

### 4. 배포 (Railway + Expo EAS)

**Railway: Next.js+FastAPI+PostgreSQL** — _결론: 조건부 가능_
- 한 프로젝트에 3서비스(각 별도 서비스) 운영 가능, 내부 네트워크 통신. 요금: Free($0, 크레딧 $1) / Hobby($5) / Pro($20), 모두 **사용량 기반**(플랜가=최소지출, CPU·RAM·egress 추가과금). ⚠️ **컨테이너 상시 과금** — 트래픽 0이어도 1vCPU/1GB 24h ≈ $30/월. 3서비스 상시 가동 시 Hobby $5 크레딧 쉽게 초과 → 비용 모니터링 필수.
- _Source: https://docs.railway.com/pricing/plans , https://blog.railway.com/p/best-serverless-platforms-2026_
- _신뢰도: High_

**Railway pgvector** — _결론: 가능_
- 기존 관리형 Postgres 사후 활성화는 까다로움 → **pgvector 사전탑재 템플릿으로 신규 배포** 권장 후 `CREATE EXTENSION vector;`. PG14+ 필요.
- _Source: https://railway.com/deploy/pgvector-latest_
- _신뢰도: High_

**Supabase → Railway 이관** — _결론: 가능_
- `pg_dump --no-owner --no-privileges`(순환 FK시 `--disable-triggers`) 후 **pgvector가 켜진 타깃 DB**에 restore(미설치 시 vector 컬럼 복원 실패). 벡터 인덱스 재빌드 시간 유의. 연결은 Railway `DATABASE_URL`.
- _Source: https://supabase.com/docs/guides/platform/migrating-to-supabase/postgres_
- _신뢰도: Medium-High_

**Expo EAS Build** — _결론: 가능_
- **Free 플랜으로 MVP 충분**: 월 iOS 15+Android 15 빌드, EAS Submit 포함. SDK/CLI 영구 무료. 별도 비용: Apple Developer $99/년, Google Play $25(1회). 무료 빌드 소진 시 큐 대기·횟수 제한이 주 제약 → 초과 시 Starter($19) 승급.
- _Source: https://expo.dev/pricing , https://docs.expo.dev/billing/usage-based-pricing/_
- _신뢰도: High_

### Technology Adoption / 종합 신뢰도

- **High 확정:** RAG 스택(pgvector·LangChain v1.0·멀티 LLM 스위칭·임베딩), JWT 라이브러리(PyJWT+pwdlib), 비밀번호 NIST 기준, Railway/EAS 요금·pgvector, PostGIS 검색.
- **Medium(추가 확인 권장):** 네이버 Maps 현행 건당 단가·무료 한도(콘솔 확인), 멀티 LLM 프로바이더별 파라미터 비대칭(구현 시 실측), Supabase→Railway 벡터 데이터 이관(실덤프 검증).
- **주요 리스크 플래그:** ① 네이버 무료정책 재편 → **지도/주소는 카카오맵 우선 검토**, ② Railway 상시 컨테이너 과금 → 비용 모니터링, ③ 비밀번호 강제 복잡도 정책 ↔ NIST Rev.4 충돌.

---

## Integration Patterns Analysis

> DeskNow에 실제 해당하는 연동 지점만 조사(이미 다룬 지도/LLM/JWT는 제외). 2026-06-13 웹 출처 검증.

### 카카오톡 공유 (예약 사항 SNS 공유)

- _결론: 조건부 가능_ — 웹/RN 모두 표준 SDK로 **무료** 구현. 카카오 디벨로퍼스 앱 등록 + 플랫폼/도메인(웹)·키 해시(앱) 등록이 선행.
- 웹(Next.js): Kakao JS SDK `Kakao.Share.sendDefault()` + Feed/Text 기본 템플릿(예약 공유에 충분). 커스텀 템플릿은 메시지 템플릿 도구에서 ID 참조.
- RN(Expo): 공식 SDK 없음 → `@react-native-kakao/share`(mym0404, Expo 공식 지원) 권장. **네이티브 모듈이라 Expo Go 불가 → EAS development build/prebuild 필요.** iOS Info.plist(URL 스킴·LSApplicationQueriesSchemes), Android 키 해시 등록 필수.
- 비용·검수: 공유 API는 **무료·검수 불필요**(유료/검수 대상인 알림톡·친구 메시지와 별개). 공유 이미지 5MB 이하, 카카오 서버 최대 100일 보관.
- _Source: https://developers.kakao.com/docs/ko/kakaotalk-share/js-link , https://github.com/mym0404/react-native-kakao_
- _신뢰도: High_

### 예약 도래 알림 (인앱 배너 방식)

- _결론: 가능_ — idea.md 요구("로그인/접속 시 1일 기준 표시, 다시 보지 않기")는 **푸시가 아니라 접속 시점 인앱 표시**이므로 FCM/Expo Push 없이 충족. 난이도 낮음.
- 표준 구현: 백엔드 `GET /notifications/pending`(임박 예약 조회→페이로드) + dismiss 상태를 user별 DB 영속화(`POST /notifications/{id}/dismiss`). 프론트는 접속 시 조회→인앱 배너, "다시 보지 않기" 시 dismiss 호출.
- 푸시(FCM/Expo Push, 디바이스 토큰·권한)는 **미접속 중 도달이 필요한 차기 버전으로 보류**가 타당.
- _Source: https://m3.material.io/components/banners , https://userguiding.com/blog/website-notification-banner_
- _신뢰도: High_

### 챗봇 실시간 스트리밍 (FastAPI + LangGraph → 웹/RN)

- _결론: 조건부 가능_ — **SSE가 토큰 스트리밍 표준 권장**(단방향, HTTP·프록시 호환, 자동 재연결, 확장성 우수). WebSocket은 양방향 필수일 때만.
- LangGraph: `graph.astream(..., stream_mode="messages")`로 토큰 청크 수신 → FastAPI `StreamingResponse(media_type="text/event-stream")`로 SSE 전달. 대화 유지는 checkpointer + `thread_id`(로그아웃 전까지 스레드 메모리).
- ⚠️ **RN 제약:** 네이티브 `EventSource` 없음 → `react-native-sse` 또는 `react-native-fetch-event-source`(인증 헤더·POST 바디 필요 시 fetch 기반 유리). Expo 디버깅 시 CdpInterceptor가 SSE 가로채는 알려진 이슈.
- _Source: https://docs.langchain.com/oss/python/langgraph/streaming , https://github.com/binaryminds/react-native-sse_
- _신뢰도: High_

### 웹/앱 ↔ FastAPI REST 공용 통합

- _결론: 가능_ — 단일 FastAPI REST를 Next.js·RN이 공용, FastAPI **OpenAPI 스키마로 타입 안전 클라이언트 자동 생성**(`@hey-api/openapi-ts` 또는 `openapi-typescript`+`openapi-fetch`)이 표준. 모노레포에서 생성 SDK를 공유 패키지로.
- ⚠️ 흔한 함정: ① **CORS** — 웹은 `CORSMiddleware` origin 등록 필수, RN은 CORS 미적용이라 "웹에서만 깨짐", ② **API 버전**(`/api/v1`) — 모바일 구버전 장기 잔존 → 하위 호환 중요, ③ 토큰 저장 차이(웹 쿠키 vs RN SecureStore), ④ RN의 `localhost` 접근 불가(에뮬레이터 별도 IP).
- _Source: https://www.vintasoftware.com/blog/nextjs-fastapi-monorepo , https://github.com/hey-api/openapi-ts_
- _신뢰도: High~Medium_

### Integration Security

- JWT 기반 인증은 2단계 참조(access 헤더/쿠키, refresh 무효화 저장소). 외부 API 키(카카오·LLM·지도)는 **백엔드 환경변수로만 관리**, 프론트 노출 금지(지도 JS SDK 도메인 키는 도메인 화이트리스트로 제한). 챗봇 SSE 엔드포인트도 JWT 보호.

---

## Architectural Patterns and Design

> 확정 스택 기준 DeskNow에 맞는 아키텍처 결정. 2026-06-13 모범사례 검증.

### System Architecture Patterns (백엔드 구조)

- _권장: 단일 FastAPI **모듈러 모놀리스**_ — MVP에서 마이크로서비스는 인프라/분산 오버헤드(초기 개발 30~50%↑)로 비권장. 15명+ 팀·독립 스케일링 필요 시에만 MS.
- **챗봇(LangGraph): 같은 레포, 별도 프로세스/서비스 배포** — 코드는 모놀리스에 두되, 장시간 스트리밍 LLM 요청이 동기 예약 API 워커 풀을 잠그지 않도록 Railway에서 별도 서비스로 부하만 격리. 외부 LLM API 사용이라 GPU 격리 불필요, 동시성/타임아웃 격리만.
- _Source: https://www.ness.com/blog/modular-monolith-vs-microservices/ , https://dev.to/kasi_viswanath/streaming-ai-agent-with-fastapi-langgraph-2025-26-guide-1nkn_
- _신뢰도: High(모놀리스) / Medium(챗봇 분리 세부)_

### Repository / 코드 구성 (모노레포)

- _권장: Turborepo + pnpm 모노레포_ — 사용자 Next.js + 관리자 Next.js + RN(Expo)을 담고, FastAPI(파이썬)는 **같은 git 레포의 별도 디렉터리로 느슨하게 공존**(자체 uv/venv 빌드, 연결고리는 OpenAPI 스키마).
- 프론트 3종 공유: `packages/`에 타입·UI 토큰, **FastAPI OpenAPI → `hey-api` 등으로 타입 안전 TS SDK 자동생성**(풀스택 타입 안정성 2026 표준). 2026 Expo SDK는 모노레포 자동 감지.
- 주의: Turborepo는 JS 편향 → 파이썬은 1급 워크스페이스로 관리 불가, 느슨한 결합이 현실적.
- _Source: https://medium.com/better-dev-nextjs-react/setting-up-turborepo-with-react-native-and-next-js-the-2025-production-guide-690478ad75af , https://abhayramesh.com/blog/type-safe-fullstack_
- _신뢰도: High(JS 모노레포) / Medium(파이썬 공존)_

### 관리자 웹 분리 & 권한

- _권장: 관리자 웹을 **별도 Next.js 앱**으로 분리_(모노레포 내 별도 app) — 공격 표면 축소·독립 배포. 인증/인가는 분리하고, 역할(고객/제공자/관리자)은 토큰에 담아 모든 레이어 검증.
- ⚠️ **Next.js 미들웨어는 라우트 보호용일 뿐, 진짜 보안선은 FastAPI RBAC 최종 강제.**
- _Source: https://medium.com/@chiragmehta900/how-to-implement-role-based-access-control-rbac-in-next-js-app-router-2026-guide-ed1c0a8dc32c_
- _신뢰도: Medium-High_

### Data Architecture — 예약 동시성 / 슬롯 모델링 (★ 핵심)

- _권장: 중복 예약은 애플리케이션 락이 아니라 **DB 제약**으로_ — idea.md의 "중복 예약 방지" 요구의 표준 해법.
- **고정 1시간 슬롯 → `UNIQUE(room_id, slot_start_utc)`** 유니크 인덱스 하나로 충분. 동시 삽입 시 한쪽이 제약 위반으로 즉시 실패 → 원자적, 레이스 컨디션 불가. 가장 단순·권장.
- 가변/겹침 시간대 → `tstzrange` + `btree_gist`의 `EXCLUDE USING gist (room_id WITH =, period WITH &&)`, 또는 PostgreSQL 18 `WITHOUT OVERLAPS`.
- `FOR UPDATE` 락·SERIALIZABLE은 고정 슬롯엔 과설계. 트랜잭션은 멀티스텝 일관성에만. pgvector와 예약 테이블은 같은 PostgreSQL 공존 무리 없음.
- _Source: https://amitavroy.com/articles/postgresql-gist-exclusion-constraint... , https://www.postgresql.org/docs/current/rangetypes.html_
- _신뢰도: High_

---

# Executive Synthesis — DeskNow MVP 기술 타당성 종합

## Executive Summary

DeskNow MVP의 제안 기술 스택(Next.js·React Native/Expo·FastAPI·PostgreSQL+pgvector·LangGraph/LangChain·Railway·EAS)은 **MVP를 구축하기에 전반적으로 타당하며 기술적 블로커는 없다.** 각 영역은 2026년 기준 성숙한 도구와 표준 패턴을 갖추고 있고, DeskNow 특화 연동(카카오톡 공유·인앱 예약 알림·챗봇 스트리밍·웹/앱 REST 공용)도 모두 외부 비용 없이 표준 방식으로 구현 가능하다.

다만 **제품 범위·비용·정책에 영향을 주는 3가지 결정**은 PRD 작성 전에 확정해야 한다: ① 지도/주소 제공자(네이버 무료정책 재편 → 카카오맵 우선 권장), ② Railway 상시 컨테이너 과금에 대한 비용 인식, ③ 비밀번호 강제 복잡도 정책의 최신 NIST 권고 충돌. 추가로, "중복 예약 방지"라는 핵심 기능 요구는 애플리케이션 락이 아니라 **PostgreSQL 제약(유니크/배제)** 으로 원자적으로 해결된다는 점이 설계를 크게 단순화하는 발견이다.

**Key Technical Findings**
- **타당성:** 4개 핵심 영역 + 4개 연동 모두 구현 가능. RAG/JWT/배포/동시성은 신뢰도 High.
- **지도/주소:** 네이버는 2025.7 무료정책 재편으로 초기 리스크↑ → **카카오맵**(일 30만 지도 / 10만 로컬 무료)이 MVP에 유리. 좌표+행정동 코드 동시 저장으로 두 검색 UX 지원.
- **챗봇:** pgvector(HNSW)+LangChain v1.0+LangGraph로 충분. 멀티 LLM은 `init_chat_model` 추상화, 단 프로바이더별 파라미터 비대칭은 래핑 레이어 분기 필요.
- **동시성:** 1시간 고정 슬롯 → `UNIQUE(room_id, slot_start)` 한 줄로 중복예약 차단.
- **비용 구조:** 외부 연동(카카오·EAS)은 0원, 주 비용은 Railway 상시 컨테이너 + LLM API 호출 + (별도) Apple $99/년·Google $25.

**Top Technical Recommendations**
1. **지도/주소: 카카오맵 채택** (네이버는 비용 불확실성·정책 리스크). 단 최종 결정 전 카카오 약관의 서비스 유형 적합성 1차 확인.
2. **백엔드: FastAPI 모듈러 모놀리스 + 챗봇 별도 배포**, 코드는 Turborepo 모노레포(프론트 3종) + FastAPI 디렉터리, OpenAPI→TS SDK 자동생성.
3. **예약 모델: PostgreSQL 제약 기반 동시성**(유니크 슬롯), pgvector는 동일 DB 공존.
4. **인증: PyJWT + pwdlib(Argon2)**, refresh 무효화용 Redis/DB, 웹=쿠키·앱=헤더 이원화 추출.
5. **알림/공유: 푸시 없이 인앱 배너 + 카카오 공유 SDK** (MVP 범위 충족, 푸시는 차기).

## Risk Register (우선순위순)

| # | 리스크 | 영향 | 대응 | 신뢰도 |
|---|--------|------|------|--------|
| R1 | 네이버 지도 무료정책 재편·콘솔 의존 | 초기 비용/일정 불확실 | **카카오맵 우선 채택**, 약관 적합성 1차 확인 | High |
| R2 | Railway 상시 컨테이너 과금(트래픽 0이어도 과금, 서비스 수=비용) | 운영 비용 | 서비스 수 최소화(초기 챗봇을 API에 통합 후 분리), 비용 모니터링/알림 | High |
| R3 | 비밀번호 강제 복잡도(8자+대/특/숫) ↔ NIST SP 800-63B Rev.4 충돌 | 정책/UX | MVP 수용하되 "길이우선+유출목록 대조"를 차기 개선 항목으로 명시 | High |
| R4 | 멀티 LLM 프로바이더별 파라미터 비대칭(Anthropic 최신 모델 샘플링 파라미터 제거 등) | 챗봇 구현 버그 | 래핑 레이어에서 프로바이더별 분기, 채팅+툴콜 공통기능에 한정 | Medium |
| R5 | RN(Expo) SSE 미지원·카카오 SDK 네이티브 모듈 | 앱 구현 복잡도 | `react-native-sse`/fetch-event-source, EAS dev build 사용 | High |
| R6 | Supabase→Railway 벡터 데이터 이관 미검증 | 운영 이관 시 실패 | 타깃 DB pgvector 선설치 + 1회 실덤프 검증 스파이크 | Medium |

## Implementation Roadmap (기술 관점, 단계 제안)

- **Phase 0 — 검증 스파이크(권장, 1~2일):** ① 카카오맵 지도표시+주소변환 end-to-end, ② 챗봇 SSE 스트리밍(FastAPI↔웹↔RN), ③ Supabase→Railway pgvector 덤프/복원 1회.
- **Phase 1 — 기반:** 모노레포(Turborepo) + FastAPI 모놀리스 + PostgreSQL(pgvector) + JWT 인증(PyJWT/pwdlib, refresh 저장소) + OpenAPI→TS SDK 파이프라인.
- **Phase 2 — 핵심 기능:** 스터디룸 등록/검색(좌표+행정동), 예약(유니크 슬롯 제약·취소), 후기/평점, 인앱 알림, 카카오 공유.
- **Phase 3 — 챗봇:** 문서 인제스트 → pgvector, LangGraph 에이전트(문서검색+예약DB 툴, 범위 밖 거부), 멀티 LLM 스위칭, SSE 스트리밍, 별도 서비스 배포.
- **Phase 4 — 배포:** Railway 멀티 서비스 + EAS 빌드/제출, 비용 모니터링.

## Next Steps

본 기술조사 결과는 **PRD(`bmad-prd`)와 아키텍처(`bmad-create-architecture`)의 입력**으로 활용한다. 특히 R1~R3은 PRD의 범위·가정·향후 고도화 항목에 반영하고, 동시성 모델·모노레포·챗봇 분리 결정은 아키텍처 단계에서 확정한다.

---

## Research Methodology & Source Verification

- **방법론:** idea.md를 입력으로 4개 영역 + 연동 + 아키텍처를 병렬 리서치 에이전트로 조사. 모든 핵심 주장은 2026-06-13 기준 공개 웹 출처(공식 문서 우선)로 검증, 신뢰도 표기.
- **주 출처:** 각 영역 섹션 내 인용 URL 참조(NCP/카카오/구글 지도 공식, LangChain·LangGraph 공식, FastAPI 공식, Railway·Expo 공식 pricing, PostgreSQL/PostGIS 공식, NIST SP 800-63B Rev.4).
- **한계(추가 확인 권장):** 네이버 Maps 현행 단가(콘솔), 멀티 LLM 파라미터 비대칭(구현 시 실측), Supabase→Railway 벡터 이관(실덤프 검증), 카카오맵 약관의 서비스 유형 적합성.
- **신뢰도 종합:** High 다수, Medium 일부(위 한계 항목). 기술적 블로커 없음.

---

**Technical Research Completion Date:** 2026-06-13
**Research Type:** Technical Feasibility (타당성 위주)
**Source Verification:** 모든 핵심 사실 2026-06-13 기준 공개 출처 인용
**Technical Confidence Level:** High — 제안 스택은 MVP에 타당, 3개 결정 항목만 PRD 전 확정 필요

### Deployment Architecture

- Railway 단일 프로젝트에 서비스 4종(사용자 웹 / 관리자 웹 / FastAPI API / LangGraph 챗봇) + PostgreSQL(pgvector). 모바일은 EAS. 상시 컨테이너 과금 고려해 서비스 수 = 비용 → MVP 초기엔 챗봇을 API에 합쳤다가 부하 시 분리하는 단계적 접근도 가능(2단계·배포 비용 트레이드오프).
- _신뢰도: High_
