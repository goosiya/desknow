---
baseline_commit: NO_VCS
---

# Story 1.3: Phase 0 검증 스파이크

Status: done
<!-- dev-story(2026-06-15): AC1(카카오 지오코딩·지도·핀)·AC2(SSE 서버+웹)·AC3(Supabase→Railway pgvector 이관+검색)·AC4(무회귀·격리) 검증 완료.
     스파이크 3종 핵심 리스크 전부 소각. 유일 잔여=AC2 RN 기기검증은 Expo SDK56↔Expo Go 비호환으로 E7 이관(deferred-work.md, 사용자 승인). → review. -->
<!-- code-review(2026-06-15): 3-레이어 적대 리뷰. AC 위반 0건. Decision 1(pgvector 충실도 갭→AC3 문자충족 수용, 충실도는 실 이관 스토리로 트리거+책임 명시 이관)·Patch 2(웹 지오코딩/SSE 상태표시 fix, web lint 그린)·Defer 3(RN진단·SSE프레이밍·pgvector충실도→E7/실이관)·Dismiss 17(throwaway 범위밖 하드닝). → done. -->


<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 개발자,
I want 본 구현 착수 전에 가장 불확실한 3개 기술 경로(카카오맵 e2e · 챗봇 SSE 3면 · pgvector 이관)를 스파이크로 검증하길,
so that 카카오맵·SSE 스트리밍·pgvector 이관의 리스크가 도메인 구현(E2~E8) 전에 닫히고, 부적합 발견 시 대안 경로를 일찍 잡는다.

> 🎯 **이 스토리의 본질은 "리스크 소각(throwaway spike)"이다.** 목적은 **검증된 사실**이지 재사용 가능한 프로덕션 코드가 아니다.
> - **스파이크 코드는 격리·폐기 대상이다.** 프로덕션 트리(`apps/api/app/{chatbot,rooms,...}`, `apps/web/src/features`, `apps/mobile/src/features`)를 채우거나 오염시키지 않는다. 격리 위치(`spikes/phase0/` + 각 앱의 명시적 `_spike-*` 라우트)에만 둔다.
> - **검증 결과(findings)는 영속이다.** 코드는 버려도 결론은 `docs/phase0-spike-results.md`에 남겨, E3(지도 go/no-go)·E7(챗봇 SSE)·배포(이관)가 그 결론 위에서 시작한다.
> - **1.1의 키와 1.2의 골격에만 의존한다.** DB 연결(1.4)·인증(1.7/1.8)·LangGraph/LLM 어댑터(E7)·디자인 토큰(1.6)은 **범위 밖** — 스파이크는 이들의 *부재* 상태에서 전송·플러밍만 증명한다.

## Acceptance Criteria

1. **(AC1 — 카카오맵 e2e + 약관 적합성)** 카카오 JS·REST 키로, 사용자 웹(Next 16, `apps/web`)에서 **지도가 표시되고 핀이 찍히며**, 주소→좌표 **지오코딩이 e2e로 동작**한다. 그리고 **카카오맵 약관의 서비스 유형(스터디룸 예약 중개) 적합성 1차 확인 결과**가 `docs/phase0-spike-results.md`에 기록된다 — **부적합 판정 시 대안 지도 제공자(네이버 등) 검토 필요성을 명시 메모**하여 E3 진행 판단에 반영한다.
2. **(AC2 — SSE 3면 + 인증 헤더)** FastAPI SSE 엔드포인트에서, **웹(fetch-stream)** 과 **RN(react-native-sse, 인증 헤더 + POST 바디)** 두 표면 모두에서 **토큰이 순차 스트리밍**되고 **`Authorization` 헤더가 서버에 전달됨이 확인**된다. (전송·인증 헤더 플러밍만 검증 — LangGraph/LLM은 E7.)
3. **(AC3 — pgvector 이관)** 소스 pgvector 인스턴스(Supabase 또는 로컬 docker pgvector)와 **Railway PostgreSQL(pgvector 사전 설치)** 사이에서 벡터 데이터를 **1회 덤프/복원**하면, **복원 후 벡터 유사도 검색이 정상 동작**함이 확인되어 이관 경로가 검증된다. (타깃에 `vector` 확장이 선설치되어야 vector 컬럼이 복원됨을 실증.)
4. **(AC4 — 격리·영속·무회귀)** 모든 스파이크 코드는 격리 위치(`spikes/phase0/**` + 각 앱의 `_spike-*` 명시 라우트)에만 존재하고, 프로덕션 골격(1.2 산출: `apps/api/app/main.py`·도메인 빈 모듈·`tests/`)은 **수정되지 않는다**. 검증 후 `docs/phase0-spike-results.md`에 3종 결론(증거 포함)이 기록되고, 기존 게이트(`uv run pytest` 20건 · `turbo lint`/`build`)가 **여전히 그린**이다.

> ⚠️ **회귀 방지 — 1.2 골격 불변식(최우선):** `apps/api/app/main.py`(lifespan·CORS·`/api/v1`·health)·`app/core/config.py`(1.1)·`app/{auth,rooms,...}/__init__.py` 빈 모듈·`tests/`(20건 통과)는 **절대 수정·확장 금지**. SSE 스파이크는 **별도 standalone FastAPI 스크립트(다른 포트 8001)** 로 띄워 프로덕션 `apps/api`를 건드리지 않는다. 이렇게 해야 회귀·스코프 크리프가 원천 차단된다.

## Tasks / Subtasks

> **권장 순서:** Task 1(셋업) → Task 2(①카카오, 즉시 실행 가능) → Task 3(②SSE, 즉시 실행 가능) → Task 4(③pgvector, **Railway 프로비저닝 선행 — 소유자 협업**) → Task 5(영속 결과 기록·정리). ②는 ①과 병렬 가능.

- [x] **Task 1 — 스파이크 격리 작업공간 + 결과 문서 골격 (AC: 4)**
  - [x] `spikes/phase0/` 디렉터리 생성(프로덕션 트리 밖). 하위: `kakao/`, `sse/`, `pgvector/`. 최상단에 `spikes/README.md` — "Phase 0 throwaway 스파이크. 검증 후 폐기. 결론은 `docs/phase0-spike-results.md` 참조." 명시.
  - [x] `docs/phase0-spike-results.md` 골격 생성: 3개 섹션(① 카카오맵 e2e+약관 / ② SSE 3면 / ③ pgvector 이관), 각 섹션에 `결론(가능/조건부/불가)` · `증거(스크린샷/로그/curl)` · `후속 영향(E3/E7/배포)` 자리. **이 문서가 영속 산출물** — 코드가 폐기돼도 남는다.
  - [x] `.gitignore`에 `spikes/`를 추가할지 결정: VCS 도입 시 스파이크는 추적 제외 권장(throwaway). 현재 NO_VCS이므로 디렉터리 분리만으로 격리 충족 — `.gitignore` 변경은 **기존 라인 보존 + append만**(1.2 회귀 방지).

- [x] **Task 2 — 스파이크 ① 카카오맵 지도표시 + 지오코딩 e2e (AC: 1)**
  - [x] **키 분리 원칙 준수(NFR-6):** JS 키(`KAKAO_JS_KEY`)만 프론트 노출(도메인 화이트리스트 전제), REST 키(`KAKAO_REST_API_KEY`)는 **백엔드 전용 — 절대 웹에서 직접 호출 금지**. 지오코딩은 백엔드 프록시 경유.
  - [x] **지오코딩 프록시(standalone, throwaway):** `spikes/phase0/kakao/proxy.py` — 최소 FastAPI(또는 Task 3 SSE 서버와 동일 standalone 앱에 합쳐도 됨, 포트 8001). `GET /_spike/geocode?query=...` → 서버에서 `https://dapi.kakao.com/v2/local/search/address.json?query=...` 호출(헤더 `Authorization: KakaoAK {KAKAO_REST_API_KEY}`) → 좌표(lat/lng) 반환. 키는 1.1의 `app.core.config.get_settings()` 재사용 또는 `os.environ` 직접 로드(스파이크는 프로덕션 config 의존 안 해도 됨).
  - [x] **웹 지도 페이지(격리 라우트):** `apps/web/src/app/_spike-kakao/page.tsx`(`"use client"`). 카카오 Maps JS SDK 동적 로드(`//dapi.kakao.com/v2/maps/sdk.js?appkey={JS_KEY}&libraries=services&autoload=false`), 지도 렌더 + 핀(marker) 1개 이상 표시. 입력창에 한국 주소 입력 → 프록시 `/_spike/geocode` 호출 → 반환 좌표로 지도 중심 이동 + 핀 갱신(e2e 체인 증명).
  - [x] **JS 키 주입(스파이크 로컬):** `apps/web/.env.local`에 `NEXT_PUBLIC_KAKAO_JS_KEY=<JS키>` 추가(JS 키는 프론트 노출 가능 키). 값은 소유자가 1.1에서 발급한 `apps/api/.env`의 `KAKAO_JS_KEY`를 복사. **프록시 base URL**도 `.env.local`에 자리표시(예: `NEXT_PUBLIC_SPIKE_API_BASE=http://localhost:8001`). *(프로덕션 키 전달 방식은 E3가 결정 — 스파이크는 로컬 주입만.)*
  - [x] **도메인 화이트리스트 전제 확인:** 카카오 콘솔에 `localhost`(또는 `http://localhost:3000`)가 JS 플랫폼 도메인으로 등록돼 있어야 지도가 뜬다. 미등록 시 지도 로드 실패 → 소유자에게 등록 요청(1.1 체크리스트 항목, `docs/external-services-setup.md` 참조). 막히면 결과 문서에 기록.
  - [x] **약관 적합성 1차 확인(가장 business-critical):** 카카오맵 서비스 약관/오픈빌더 정책에서 **"스터디룸 예약 중개 서비스"가 지도 SDK 허용 용도에 부합하는지** 1차 검토. 결론(적합/부적합/불명확)과 근거 링크를 `docs/phase0-spike-results.md` ①에 기록. **부적합·불명확 시 대안(네이버 지도 등) 검토 필요성 + E3 진행 게이트 영향**을 명시 메모. *(이것이 아키텍처가 지목한 "차단 가능 리스크" — architecture.md#Validation Issues Addressed L446.)*
  - [x] **증거 캡처:** 지도+핀 스크린샷, 지오코딩 요청/응답(주소→좌표) 로그를 결과 문서에 첨부.

- [ ] **Task 3 — 스파이크 ② 챗봇 SSE 스트리밍 (FastAPI ↔ 웹 ↔ RN) (AC: 2)**
  - [x] **standalone SSE 서버(프로덕션 apps/api 미접촉):** `spikes/phase0/sse/server.py` — 독립 FastAPI 앱, **포트 8001**, `uv run uvicorn ... --host 0.0.0.0 --port 8001`(RN LAN 접근 위해 `0.0.0.0` 필수). Task 2 지오코딩 프록시와 한 앱에 합쳐도 무방(같은 standalone 스파이크 서버).
  - [x] **SSE 엔드포인트:** `POST /_spike/stream` — `StreamingResponse(media_type="text/event-stream")`. 요청의 `Authorization` 헤더를 읽어 **서버 로그로 수신 확인**(예: `print(request.headers.get("authorization"))`), 그리고 짧은 토큰 시퀀스(예: "안녕하세요 룸메이트입니다…"를 어절/문자 단위로 분할)를 `data: {token}\n\n` 형식으로 `asyncio.sleep(~0.05s)` 간격 순차 전송, 종료 시그널(`data: [DONE]\n\n`) 송신. **LangGraph/LLM 불필요** — 전송 플러밍 검증이 목적(LLM 스트리밍은 E7). POST 바디로 프롬프트를 받아 echo해도 됨(POST 바디 전달 검증).
  - [x] **CORS(스파이크 서버):** 웹(`http://localhost:3000`)에서 fetch-stream 호출하므로 permissive CORS 추가(`allow_origins=["*"]` 스파이크 한정 허용). RN은 네이티브라 CORS 무관.
  - [x] **웹 소비(격리 라우트):** `apps/web/src/app/_spike-sse/page.tsx`(`"use client"`). **⚠️ 네이티브 `EventSource`는 커스텀 헤더 불가** → AC2의 "인증 헤더 전달"을 검증하려면 **fetch + `ReadableStream` 리더**(또는 `@microsoft/fetch-event-source`)로 구현. `fetch("/_spike/stream", {method:"POST", headers:{Authorization:"Bearer spike-test-token", ...}, body})` → 스트림 청크를 순차 화면 표시. *(아키텍처 L176 "웹=표준 EventSource/fetch-stream" 중 헤더가 필요한 이 케이스는 fetch-stream 경로.)*
  - [x] **RN 소비(격리 라우트):** `apps/mobile/app/_spike-sse.tsx`. `react-native-sse`(binaryminds) 추가: `pnpm --filter mobile add react-native-sse`. `new EventSource(url, {method:"POST", headers:{Authorization:"Bearer spike-test-token"}, body})` → `addEventListener("message", ...)`로 토큰 순차 수신·표시. **API base는 LAN IP**(`EXPO_PUBLIC_API_BASE_URL` 또는 신규 `EXPO_PUBLIC_SPIKE_BASE`, 예 `http://192.168.x.x:8001`) — RN은 `localhost` 미접근(1.2 학습). Expo Go/dev에서 동작(네이티브 모듈 아님, JS 라이브러리).
  - [ ] **인증 헤더 전달 증명:** 두 표면 모두에서 서버 로그에 `Authorization: Bearer spike-test-token`이 찍힘을 확인(스크린샷/로그). *(실제 JWT 발급은 1.7/1.8 — 스파이크는 스텁 토큰으로 헤더 propagation만 검증.)*
  - [x] **알려진 이슈 메모:** Expo 디버깅 시 `CdpInterceptor`가 SSE를 가로채는 알려진 이슈(research L189) — 발생 시 결과 문서에 우회법 기록.
  - [ ] **증거 캡처:** 웹·RN 각각 토큰이 순차 누적되는 화면 + 서버의 `Authorization` 수신 로그를 결과 문서 ②에 첨부.

- [x] **Task 4 — 스파이크 ③ Supabase→Railway pgvector 덤프/복원 (AC: 3) — 소유자 인프라 협업**
  - [x] **소유자 협업 경계 명시:** 이 스파이크는 **Railway PostgreSQL(pgvector) 프로비저닝**(소유자)이 선행돼야 한다. dev는 (a) 소스 시드·덤프·복원·검증 스크립트를 준비하고, (b) 소유자가 Railway에 pgvector 템플릿 DB를 띄워 `DATABASE_URL`을 제공하면, (c) 함께 1회 이관을 실행·기록한다. *(1.1 산출 `.env`의 `DATABASE_URL`은 현재 비어 있음 — 1.4에서 필수화. 스파이크는 별도 throwaway 연결 문자열 사용.)*
  - [x] **소스 인스턴스(택1):** ⓐ Supabase 무료 프로젝트(이관 충실도 ↑, 권장) 또는 ⓑ 로컬 docker `pgvector/pgvector` 컨테이너(소스 없을 때 폴백). 둘 다 핵심 불변식(덤프/복원 충실도 + 타깃 확장 선설치)은 검증 가능.
  - [x] **시드 스크립트:** `spikes/phase0/pgvector/seed.sql`(또는 `.py`) — 소스에 `CREATE EXTENSION IF NOT EXISTS vector;` + 최소 테이블 `spike_items(id bigserial pk, content text, embedding vector(1536))` + 더미 행 수 개 삽입. **차원 1536 고정**(프로덕션 `text-embedding-3-small` 차원과 일치 — 실 임베딩 대신 합성/랜덤 벡터로 충분, OpenAI 호출 불필요). HNSW 인덱스 1개 생성(`USING hnsw (embedding vector_cosine_ops)`).
  - [x] **덤프:** `pg_dump --no-owner --no-privileges`(순환 FK 있으면 `--disable-triggers`) → `dump.sql`. (research L147 / architecture 이관 절차.)
  - [x] **타깃 선조건(결정적):** Railway 타깃 DB에 **`CREATE EXTENSION vector;` 선실행**(또는 pgvector 사전탑재 템플릿으로 신규 배포). **미설치 시 vector 컬럼 복원이 실패**함을 실증/기록(이것이 검증의 핵심 교훈). PG14+ 필요.
  - [x] **복원 + 검증:** `psql $RAILWAY_DATABASE_URL < dump.sql` → 복원 후 **유사도 검색 쿼리** 실행(`SELECT id, content FROM spike_items ORDER BY embedding <=> :query_vec LIMIT 3;`)이 정상 결과를 반환함을 확인. 행 수·인덱스 존재(`\d spike_items`)도 대조.
  - [x] **증거 캡처:** 덤프 크기·복원 로그·검색 쿼리 결과를 결과 문서 ③에 기록. 인덱스 재빌드 소요(있으면) 메모.
  - [x] **차단 시 처리:** Railway 프로비저닝이 지연되면 ③를 **로컬 docker 소스→로컬 pgvector 타깃**으로 먼저 1회 검증(이관 절차·확장 선설치 교훈 확보)하고, Railway 실타깃 검증은 소유자 준비 시 보강. 진행 상태를 결과 문서·완료 노트에 명시.

- [x] **Task 5 — 영속 결과 기록 · 무회귀 확인 · 정리 (AC: 1, 2, 3, 4)**
  - [x] `docs/phase0-spike-results.md` 3개 섹션을 **결론(가능/조건부/불가) + 증거 + 후속 영향**으로 완성. 특히 ① **카카오 약관 적합성 판정과 E3 go/no-go 영향**, ② SSE 두 표면 + 헤더 검증, ③ pgvector 이관 + 확장 선설치 교훈.
  - [x] **무회귀 게이트:** `cd apps/api && uv run pytest`(20건 그린), `uv run ruff check . && uv run mypy app`, `pnpm turbo lint`/`pnpm turbo build`(web·admin)가 **스파이크 추가 전과 동일하게 통과**함을 확인(프로덕션 골격 미접촉 증명). 결과를 완료 노트에 캡처.
  - [x] **격리 검증:** `apps/api/app/main.py`·도메인 빈 모듈·`tests/`·`apps/web/src/{features,components,lib}` 등 프로덕션 트리에 스파이크 잔재가 없음을 확인. 스파이크 코드는 `spikes/phase0/**`와 각 앱 `_spike-*` 라우트에만 존재.
  - [x] **폐기/격리 결정:** 검증 종료 후 스파이크 코드는 (ⓐ) `spikes/phase0/`에 "검증 완료·폐기 대상" 표식과 함께 격리 보존하거나 (ⓑ) 삭제. **결론 문서는 반드시 남긴다.** `_spike-*` 앱 라우트는 프로덕션 빌드 혼입을 막기 위해 검증 후 제거 권장(남기면 결과 문서에 사유 기록). 어느 쪽이든 완료 노트에 명시.
  - [x] **약관 부적합 발견 시:** ① 결과가 부적합이면 E3 진행 전 `correct-course` 또는 소유자 의사결정이 필요함을 결과 문서·완료 노트에 **에스컬레이션**으로 표기.

### Review Findings

> code-review(2026-06-15) — 3-레이어 적대 리뷰(Blind Hunter / Edge Case Hunter / Acceptance Auditor).
> **Acceptance Auditor: AC1~AC4 위반 0건** — 격리·키분리(NFR-6)·무회귀·라우트 변이(`_spike-*`→`spike-*`, 문서화됨) 모두 정합. 스파이크는 검증 목적 달성. 아래는 throwaway 범위 안에서 남길 가치가 있는 항목만(프로덕션 하드닝 17건은 설계상 범위 밖으로 dismiss).

- [x] [Review][Decision] pgvector 검증 신뢰도 갭 — `verify.sql`은 "복원 후 유사도 쿼리 실행 + 행 반환"은 증명하나 **벡터 데이터 충실도**(임베딩 손상/절단 없이 이관)는 증명 못 함. 랜덤 질의벡터 + 알려진 정답 NN 없음 → 임베딩이 깨져도 3행은 반환됨. **결정(2026-06-15, KTH): (a) AC3 문자충족으로 수용** — 스파이크는 이관 *경로* 증명이 목적이며 충족됨. 충실도 정밀검증은 실데이터가 존재하는 실 이관 시점으로 이관(아래 defer 보강 — 트리거+책임스토리 명시). [spikes/phase0/pgvector/verify.sql, seed.sql]

- [x] [Review][Patch] 웹 지오코딩 실패/0건 시 상태 미갱신 — `handleGeocode`가 `!res.ok || !first`에서 조용히 return → 직전 "✅ 성공" 상태 잔존. 재검증 시 "0건 못 찾음"을 "성공"으로 오판 유발. [apps/web/src/app/spike-kakao/page.tsx:106] — **fixed(2026-06-15):** 실패/0건 분기별 setStatus 추가.
- [x] [Review][Patch] 웹 SSE `start()` try/catch 부재 + `[DONE]` 없이 종료 시 상태 "스트리밍 중…" 고정 — 서버 다운/스트림 절단을 무한 행처럼 보이게 함(콘솔에만 오류). [apps/web/src/app/spike-sse/page.tsx] — **fixed(2026-06-15):** 전체 try/catch + [DONE] 미수신 종료 상태 명시.

- [x] [Review][Defer] RN SSE 진단·견고성 묶음 — error 핸들러 `JSON.stringify(event)`가 `{}` 산출(진단 불가)·connect 타임아웃 분기 없음(잘못된 LAN IP 무한 대기)·하드코딩 폴백 `192.168.0.2`. [apps/mobile/src/app/spike-sse.tsx] — deferred → E7(RN 기기검증과 동반 이관)
- [x] [Review][Defer] SSE 서버 프레이밍 견고성 — 프롬프트/토큰의 `\n\n`·연속 공백·리터럴 `[DONE]`가 SSE 프레임을 깨뜨릴 수 있음(고정 프롬프트엔 미발생). [spikes/phase0/sse/server.py] — deferred → E7(프로덕션 스트리밍 정프레이밍)
- [x] [Review][Defer] pgvector 충실도 검증(행수·체크섬·알려진 NN 단언) — `verify.sql`이 시드 행수(10) 자동 대조 없음 + 충실도 미증명. **트리거:** 소스 pgvector→Railway로 실 임베딩을 처음 1회 이관할 때(E7 임베딩 적재 이후 ~ 배포 준비 시점). **책임 스토리:** 해당 실 이관 스토리. 그 스토리 sprint-planning 시 본 항목을 AC로 회수. [spikes/phase0/pgvector/verify.sql] — deferred(상세는 deferred-work.md)

## Dev Notes

### 이 스토리의 범위 경계 (스코프 크리프 방지 — 매우 중요)

| 항목 | 1.3(이 스토리) | 담당 |
|---|---|---|
| 카카오맵 지도+지오코딩 **e2e 검증** | ✅ throwaway 스파이크 | 1.3 |
| 카카오 **약관 적합성 1차 확인 + E3 영향 메모** | ✅ 영속 기록 | 1.3 |
| SSE **전송 플러밍 + 인증 헤더** 3면 검증 | ✅ throwaway | 1.3 |
| pgvector **덤프/복원 1회 + 검색 검증** | ✅ throwaway | 1.3 |
| **프로덕션 챗봇 엔드포인트**(`/api/v1/chatbot/stream`)·LangGraph·LLM 어댑터·임베딩 | ❌ 스파이크는 표면 전송만 | **E7** |
| **rooms/지도 프로덕션 기능**(핀 집계·반경·행정동) | ❌ | **E2/E3** |
| **DB 연결·Alembic·pgvector 프로덕션 스키마** | ❌ 스파이크용 throwaway 연결만 | **1.4 / E7** |
| **인증(JWT 발급·검증)** | ❌ 스텁 Bearer 토큰만 | **1.7/1.8** |
| **디자인 토큰·shadcn·접근성** | ❌ 스파이크 UI는 미관 무관 | **1.6** |

> 위 ❌를 1.3에서 구현하지 말 것. 스파이크는 **"되는가?"** 만 증명한다. **"어떻게 프로덕션화하는가"** 는 해당 에픽 몫.

### 결정적 시퀀싱 · 협업 경계 — 무엇이 즉시 되고 무엇이 막히나

- **즉시 dev 실행 가능:** ① 카카오(1.1에서 소유자가 `apps/api/.env`에 `KAKAO_JS_KEY`·`KAKAO_REST_API_KEY` 채움 — 검증됨), ② SSE(외부 의존 없음, 합성 토큰). **단 ①은 카카오 콘솔 도메인 화이트리스트에 `localhost` 등록이 전제** — 미등록 시 소유자 요청.
- **소유자 인프라 선행:** ③ pgvector — Railway PostgreSQL(pgvector) 프로비저닝 + `DATABASE_URL` 제공이 필요. 지연 시 로컬 docker 소스/타깃으로 선검증 후 Railway 실타깃 보강(Task 4 폴백).
- **NO_VCS:** 리포에 git 없음. "격리"는 **디렉터리 분리**(`spikes/phase0/`)로 달성. baseline_commit=NO_VCS.
  [Source: epics.md#Story 1.1(L252,L262), #Story 1.3(L306-326); 1-2-...md#회귀 변수(L106-112); 1-1-...md]

### 기술 스펙 / 라이브러리 (검증 대상별)

- **카카오 지도 JS SDK:** `//dapi.kakao.com/v2/maps/sdk.js?appkey={JS_KEY}&libraries=services&autoload=false`. `kakao.maps.load(cb)` 후 `new kakao.maps.Map(el, opts)` + `new kakao.maps.Marker(...)`. **JS 키 = 프론트 노출 가능(도메인 화이트리스트), REST 키 = 백엔드 전용.**
- **카카오 지오코딩(REST, 백엔드 프록시):** `GET https://dapi.kakao.com/v2/local/search/address.json?query={주소}`, 헤더 `Authorization: KakaoAK {KAKAO_REST_API_KEY}`. 응답 `documents[].{x(lng),y(lat)}`. 무료 한도 일 10만(research L83). **웹에서 직접 호출 금지(REST 키 노출=NFR-6 위반).**
- **SSE 서버:** FastAPI `StreamingResponse(generator, media_type="text/event-stream")`, 청크 형식 `data: {token}\n\n`, 종료 `data: [DONE]\n\n`. `--host 0.0.0.0`(RN LAN).
- **웹 SSE 소비:** 인증 헤더 필요 → **네이티브 `EventSource` 불가**(헤더 미지원). `fetch` + `ReadableStream` 또는 `@microsoft/fetch-event-source`. POST 바디 가능.
- **RN SSE 소비:** `react-native-sse`(binaryminds) — `method:"POST"` + `headers` + `body` 지원(아키텍처 L177 지정 라이브러리). Expo Go/dev 동작(네이티브 모듈 아님). 대안 `react-native-fetch-event-source`.
- **pgvector 이관:** `pg_dump --no-owner --no-privileges`(+`--disable-triggers` 순환 FK 시) → 타깃 **`CREATE EXTENSION vector;` 선실행 필수** → `psql < dump.sql`. 검색 `ORDER BY embedding <=> :q LIMIT k`. HNSW(`vector_cosine_ops`). PG14+. Railway는 pgvector 사전탑재 템플릿으로 신규 배포 권장(기존 DB 사후 활성화는 까다로움, research L142).
  [Source: architecture.md#API(L176-177), #Security(L164-165), #Infra(L188-197); research#지도(L83), #SSE(L187-190), #이관(L141-147)]

### 키 · 설정 (1.1 산출 재사용)

- `apps/api/.env`(소유자 입력 완료): `KAKAO_REST_API_KEY`, `KAKAO_JS_KEY`, `OPENAI_API_KEY` 필수 채워짐. `DATABASE_URL` 비어 있음(③용 throwaway 연결은 별도 env로).
- 스파이크 서버는 1.1 `app.core.config.get_settings()`를 **재사용해도 되고**(키 로딩 검증된 경로), 격리를 위해 `os.environ`/별도 `.env`를 직접 읽어도 된다(프로덕션 config에 결합하지 않는 편이 throwaway 정신에 부합).
- 웹: `apps/web/.env.local`에 `NEXT_PUBLIC_KAKAO_JS_KEY`(JS 키 복사, 프론트 노출 OK) + `NEXT_PUBLIC_SPIKE_API_BASE=http://localhost:8001` 추가. 모바일: `EXPO_PUBLIC_SPIKE_BASE=http://{LAN_IP}:8001`.
  [Source: apps/api/.env.example, apps/api/app/core/config.py(L31-77); 1-2-...md#File List]

### 격리 · 무회귀 전략 (1.2 골격 보존 — 절대 불변식)

- **standalone SSE/프록시 서버**를 `spikes/phase0/sse/server.py`로 **별도 포트(8001)** 기동 → 프로덕션 `apps/api/app/main.py`(8000)·`tests/`(20건)·도메인 빈 모듈 **미접촉**. 이것이 회귀·스코프 크리프 0의 핵심 장치.
- 앱 라우트는 명시적 `_spike-*` 세그먼트(`apps/web/src/app/_spike-kakao`, `_spike-sse`; `apps/mobile/app/_spike-sse.tsx`)로만 — 프로덕션 `features/`·`components/`·`lib/` 미오염. 검증 후 제거 권장(프로덕션 빌드 혼입 방지).
- `react-native-sse`는 `apps/mobile`에 dep 추가됨(throwaway) → 폐기 시 제거 또는 결과 문서에 잔존 사유 기록.
- `.gitignore`·`package.json`·`turbo.json` 등 루트 설정 **수정 금지**(append만, 1.2 회귀 방지). 스파이크는 turbo 파이프라인에 등록하지 않는다(독립 실행).
  [Source: 1-2-...md#Dev Notes(L89-104,L185-195), #Review Findings; architecture.md#Boundaries(L345-362)]

### 흔한 실수 방지 (anti-patterns)

- ❌ 스파이크 SSE를 `apps/api/app/chatbot/`에 구현 → E7 오염·회귀 위험. **standalone 포트 8001.**
- ❌ 웹에서 카카오 REST 키로 직접 지오코딩 호출 → REST 키 프론트 노출(NFR-6 위반). **백엔드 프록시 경유.**
- ❌ 웹 SSE를 네이티브 `EventSource`로 → 인증 헤더 못 실음(AC2 미충족). **fetch-stream.**
- ❌ RN에서 `localhost`로 스파이크 서버 접근 → 미접근. **LAN IP + uvicorn `0.0.0.0`.**
- ❌ Railway 타깃에 `vector` 확장 없이 복원 → vector 컬럼 복원 실패. **`CREATE EXTENSION vector;` 선실행.**
- ❌ 스파이크에 LangGraph/LLM·프로덕션 DB 스키마 끌어오기 → 범위 밖(E7/1.4). **전송·이관 플러밍만.**
- ❌ 결과를 코드 주석에만 남기고 코드 폐기 → 검증 사실 소실. **`docs/phase0-spike-results.md`(영속).**
- ❌ 카카오 약관 부적합인데 그냥 통과 처리 → E3에서 차단 폭발. **부적합 시 명시 에스컬레이션.**
- ❌ `apps/api/tests`·`main.py` 수정 → 1.2 회귀. **미접촉 + 20건 그린 재확인.**

### 소스 트리 — 이 스토리에서 만드는/건드리는 위치

```
desknow/
├── spikes/                              # NEW — throwaway 스파이크 격리 루트
│   ├── README.md                        # NEW — 폐기 대상 명시, 결과 문서 포인터
│   └── phase0/
│       ├── kakao/proxy.py               # NEW — 지오코딩 백엔드 프록시(8001, REST 키 격리)
│       ├── sse/server.py                # NEW — standalone SSE 서버(8001, StreamingResponse)
│       └── pgvector/{seed.sql,dump.sql,verify.sql}  # NEW — 시드·덤프·검색 검증
├── docs/
│   ├── phase0-spike-results.md          # NEW — ★영속★ 3종 결론·증거·후속영향
│   └── external-services-setup.md       # READ — 카카오 도메인 화이트리스트 등 참조
├── apps/
│   ├── web/
│   │   ├── src/app/_spike-kakao/page.tsx  # NEW(격리) — 지도+핀+지오코딩 e2e
│   │   ├── src/app/_spike-sse/page.tsx    # NEW(격리) — fetch-stream + 헤더
│   │   └── .env.local                     # UPDATE(append) — NEXT_PUBLIC_KAKAO_JS_KEY, SPIKE_API_BASE
│   ├── mobile/
│   │   ├── app/_spike-sse.tsx             # NEW(격리) — react-native-sse + 헤더
│   │   ├── package.json                   # UPDATE — react-native-sse dep(throwaway)
│   │   └── .env(.example)                 # UPDATE(append) — EXPO_PUBLIC_SPIKE_BASE(LAN IP)
│   └── api/                               # ⛔ 미접촉(1.2 골격 보존: main.py·tests·도메인 빈 모듈)
└── .gitignore                             # UPDATE(append only, 선택) — spikes/ 무시(VCS 도입 시)
```
[Source: architecture.md#Directory Structure(L300-343); 1-2-...md#소스 트리(L145-176)]

### Testing standards

- **스파이크는 throwaway → 영구 자동화 테스트를 만들지 않는다.** 검증=수동 e2e + **증거(스크린샷/로그/curl/쿼리 결과)를 `docs/phase0-spike-results.md`에 기록**.
- **무회귀가 유일한 자동 게이트:** `cd apps/api && uv run pytest`(기존 20건 그린) · `uv run ruff check .`·`uv run mypy app` · `pnpm turbo lint`/`build`(web·admin)가 스파이크 추가 전후 동일 통과. 프로덕션 골격 미접촉 증명.
- 스파이크 서버 자체 검증은 `curl -N -X POST http://localhost:8001/_spike/stream -H "Authorization: Bearer t"`로 토큰 스트림·헤더 수신을 즉석 확인(영구 테스트 아님).
  [Source: 1-2-...md#Testing(L178-183), #Completion(L256-261)]

### Project Structure Notes

- **정합:** 프로덕션 트리는 아키텍처 디렉터리 구조와 1.2 산출 그대로 보존. 스파이크는 구조 밖 격리(`spikes/`) + 명시적 `_spike-*` 라우트 — 아키텍처가 정의하지 않은 의도적 임시 영역.
- **의도된 변이(rationale):** 챗봇 SSE 프로덕션 위치는 `apps/api/app/chatbot/` + `/api/v1/chatbot/stream`(E7)이지만, 스파이크는 회귀·오염 0을 위해 standalone 서버(8001)로 분리. 검증된 전송 패턴만 E7이 프로덕션 위치로 이식.

### References

- [Source: epics.md#Story 1.3: Phase 0 검증 스파이크(L306-326)] — 본 스토리 ACs
- [Source: epics.md#Story 1.1(L246-282)] — 키·약관 적합성·스파이크 ③ 소스 인스턴스 선행
- [Source: epics.md#Epic 1 Enablers(L201-204), #Tech Requirements Phase 0(L111-114)]
- [Source: architecture.md#API & Communication(L168-177)] — SSE 웹/RN, snake_case
- [Source: architecture.md#Authentication & Security(L155-166)] — 키 격리, SSE JWT 보호
- [Source: architecture.md#Infrastructure(L188-197), #Decision Impact(L199-218)] — pgvector·Railway·이관
- [Source: architecture.md#Directory Structure(L300-343), #Boundaries(L345-362)]
- [Source: architecture.md#Validation Issues Addressed(L440-446)] — 카카오 약관=차단 가능 리스크 → Phase 0 ①
- [Source: research#지도(L42,L83,L253,L259), #SSE(L187-190,L273), #pgvector 이관(L141-147,L274), #Phase 0(L278)]
- [Source: 1-2-...md#회귀 변수·골격 보존(L89-112,L185-195), #Completion(L247-263)] — pnpm/Expo·LAN IP·포트 학습
- [Source: 1-1-...md] · [Source: apps/api/app/core/config.py, main.py, .env.example] — 키·config·골격 실측

## Latest Tech Information

- **카카오맵:** JS SDK 일 30만 무료, 로컬(지오코딩) API 일 10만 무료. JS 키=도메인 화이트리스트, REST 키=백엔드. **약관 서비스유형 적합성은 콘솔/약관 직접 확인 필요(미검증 리스크 R1).** [research L83, L259]
- **SSE:** FastAPI `StreamingResponse(text/event-stream)`가 토큰 스트리밍 표준. 웹 인증 헤더는 fetch-stream(native EventSource 헤더 불가). RN=`react-native-sse`(POST·헤더·바디 지원). ⚠️ Expo 디버깅 `CdpInterceptor` SSE 가로채기 알려진 이슈. [research L187-190]
- **pgvector:** 2026 프로덕션 검증, HNSW 기본, ~500만 벡터 이하 한 자릿수 ms. Railway는 pgvector 사전탑재 템플릿 신규 배포 권장. 이관=`pg_dump --no-owner --no-privileges` + 타깃 `CREATE EXTENSION vector` 선설치(미설치 시 vector 복원 실패). PG14+. [research L89-90, L141-147]
- **임베딩 차원:** 프로덕션 `text-embedding-3-small` = 1536차원. 스파이크는 합성/랜덤 1536벡터로 충분(실 임베딩 호출 불필요). [config.py DEFAULT_EMBEDDING_MODEL]

## Project Context Reference

- `project-context.md`은 리포에 없음 — `architecture.md`·`epics.md`·기술 리서치·1.1/1.2 스토리를 1차 컨텍스트로 사용.
- 산출 언어: 한국어(문서·주석·커밋). 코드 식별자는 영어. 스파이크 결과 문서(`docs/phase0-spike-results.md`)도 한국어.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (BMad dev-story 워크플로우)

### Debug Log References

- **카카오 지오코딩 403(핵심 발견):** 프록시→카카오 전송·REST 키 인증은 정상이나 카카오가
  `403 NotAuthorizedError: App(DeskNow) disabled OPEN_MAP_AND_LOCAL service` 반환 →
  콘솔에서 "카카오맵/로컬" 제품 **비활성**. 키 오류 아님. 소유자 콘솔 활성화 필요.
- **SSE 500(cp949):** 한글 prompt/토큰 print 시 Windows cp949 콘솔 `UnicodeEncodeError`로 500 →
  서버 시작 시 stdout/stderr UTF-8(errors=replace) 재설정으로 해결(`config.py`와 동일 패턴).
- **web lint 차단:** 스파이크 카카오 페이지의 `any`(카카오 SDK 전역) + effect 내 동기 setState가
  `@typescript-eslint/no-explicit-any`·`react-hooks/set-state-in-effect` 위반 → 카카오 SDK 표면을 최소
  타입화하고 누락 키 상태를 초기값으로 계산해 게이트 그린 유지.
- **라우팅 네이밍:** Next.js `_`-폴더=private(비라우팅), expo-router `_`-파일 제외 → 스토리의 `_spike-*`로는
  페이지가 라우팅되지 않아 수동 검증 불가 → 라우팅 가능한 `spike-*`로 조정(격리·제거 용이성 동일).

### Completion Notes List

**자동 검증 완료(✅):**
- **AC2 SSE 서버측:** standalone FastAPI(:8001) `StreamingResponse(text/event-stream)`에서 토큰 순차 스트리밍
  + `data: [DONE]` 종료 + 클라이언트 `Authorization: Bearer spike-test-token` 서버 수신 + POST 바디 수신을
  curl로 검증(`200 OK`, `content-type: text/event-stream; charset=utf-8`).
- **AC2 SSE 웹 소비:** ✅ 브라우저 확인(2026-06-15) — `localhost:3000/spike-sse` 토큰 순차 누적 + `[DONE]` + POST 바디 echo.
  (스파이크 박스 글자색만 가독성 보정 — `#f5f5f5` 배경에 다크모드 흰 글자 문제. 미관 무관이나 확인 편의상.)
- **AC1 지오코딩 e2e:** 소유자가 카카오 콘솔 "카카오맵/로컬" 서비스 활성화 후 재검증 → 주소→좌표 정상 반환 확인
  (강남역·해운대·광화문 실좌표). 백엔드 REST 프록시 경유(키 분리 NFR-6). **활성화 전 403은 키 무효 아닌 서비스 미활성이었음.**
- **AC1 약관 적합성:** ✅ 적합 — 1.1에서 카카오 운영자 데브톡 답변 근거로 판정(`docs/external-services-setup.md`). R1 리스크 닫힘.
- **AC1 지도 렌더:** ✅ 브라우저 확인(2026-06-15) — `localhost:3000/spike-kakao` 지도 타일 + 핀 + 지오코딩→핀 이동 동작.
  **도메인 등록 함정 발견:** JS SDK 도메인은 [앱 키 → JavaScript 키 → JavaScript SDK 도메인]에 등록(제품 링크 웹 도메인과 별개). **→ AC1 전체 충족, Task 2 완료.**
- **AC3 pgvector 이관:** ✅ 검증 완료(2026-06-15) — 소스 **Supabase(PG17.6)** → 타깃 **Railway(PG18.4, pgvector 0.8.2)**
  `spike_items(vector(1536))` 10행 덤프/복원 + 코사인 유사도 검색 정상. **확장 선설치 교훈 실증:** 확장 없이 복원 시
  `ERROR: type "public.vector" does not exist`, `CREATE EXTENSION vector` 후 복원 성공. HNSW 인덱스까지 이관됨.
- **AC4 무회귀:** apps/api `pytest 20 passed`·ruff·mypy 클린(미접촉), web/admin lint·build 성공, mobile lint exit 0.
- **AC4 격리:** 스파이크는 `spikes/phase0/**`(gitignore) + `spike-*` 라우트에만. 프로덕션 트리 미접촉 확인.

**유일한 잔여(⏳ — 환경 제약, E7 이관):**
- **AC2 RN 기기 검증:** 코드(`spike-sse.tsx`)·dep(`react-native-sse`)·서버측+웹 검증 완료. 단 **프로젝트가 Expo SDK 56(프리뷰)이라
  스토어 Expo Go 실행 불가**(`Project is incompatible with this version of Expo Go`) → 기기 검증엔 dev build/EAS 필요.
  SSE 전송·인증헤더는 서버(curl)+웹(fetch-stream)으로 이미 증명 + react-native-sse는 표준 JS 라이브러리라 잔여 리스크 낮음
  → **E7(모바일 dev client 도입 시)로 이관**(`deferred-work.md` 기록). 방화벽 8001 인바운드는 소유자가 허용함(검증 후 제거 권장).

상세 결론·증거·후속 영향은 영속 문서 `docs/phase0-spike-results.md` 참조.

**정리 권장:** Supabase·Railway 테스트 테이블(`spike_items`) drop, `spikes/phase0/pgvector/connections.env`(실 비밀번호) 삭제, 방화벽 8001 규칙 제거.

### File List

**신규 (스파이크, throwaway — gitignore됨):**
- `spikes/README.md`
- `spikes/phase0/_spikeenv.py`
- `spikes/phase0/kakao/proxy.py`
- `spikes/phase0/sse/server.py`
- `spikes/phase0/pgvector/seed.sql`
- `spikes/phase0/pgvector/verify.sql`
- `spikes/phase0/pgvector/RUNBOOK.md`
- `apps/web/src/app/spike-kakao/page.tsx`
- `apps/web/src/app/spike-sse/page.tsx`
- `apps/mobile/src/app/spike-sse.tsx`

**신규 (영속 산출물 — 추적됨):**
- `docs/phase0-spike-results.md`

**수정 (append-only / dep 추가):**
- `.gitignore` (append: `spikes/` 무시)
- `apps/web/.env.local` (append: `NEXT_PUBLIC_KAKAO_JS_KEY`, `NEXT_PUBLIC_SPIKE_API_BASE`)
- `apps/mobile/.env`, `apps/mobile/.env.example` (append: `EXPO_PUBLIC_SPIKE_BASE`)
- `apps/mobile/package.json`, `pnpm-lock.yaml` (dep: `react-native-sse@^1.2.1` — 스토리 명시)

**미접촉 (1.2 골격 보존 확인):** `apps/api/**`(main.py·도메인 모듈·tests 20건), `apps/web/src/app/{page,layout,globals}`,
`apps/web/src/{features,components,lib}`(미생성), mobile 원본 라우트(`_layout`/`index`/`explore`).

## Change Log

- 2026-06-14 — Phase 0 스파이크 구현. SSE 서버측(AC2)·지오코딩 플러밍(AC1)·무회귀(AC4)·격리(AC4) 자동 검증 완료.
  카카오 콘솔 서비스 비활성 발견(E3 차단 리스크 조기 포착). AC1 약관/도메인·AC3 pgvector 이관은 소유자/인프라 대기로 HALT.
- 2026-06-15 — 소유자 협업으로 잔여 검증 마감. AC1 완전(카카오 서비스 활성화→지오코딩·지도 렌더·핀 이동 브라우저 확인),
  AC2 웹(fetch-stream) 브라우저 확인, AC3 완전(Supabase→Railway pgvector 이관+검색+확장 선설치 교훈 실증). 무회귀 재확인 그린.
  **AC2 RN 기기 검증만 Expo SDK 56↔Expo Go 비호환으로 E7 이관**(dev build 필요). 스파이크 3종 핵심 리스크 전부 소각.
- 2026-06-15 — code-review 완료(status→done). 적대 3-레이어 AC 위반 0. Patch 2건 적용(웹 지오코딩/SSE 상태표시, web lint 그린). **프로덕션 빌드 혼입 방지: `spike-*` 앱 라우트 3종 제거** — `apps/web/src/app/spike-{kakao,sse}/`, `apps/mobile/src/app/spike-sse.tsx` 삭제(소스 참조 0 확인, web lint EXIT=0). standalone `spikes/phase0/**` 참조 코드와 결론 문서(`docs/phase0-spike-results.md`)는 영속 보존.
