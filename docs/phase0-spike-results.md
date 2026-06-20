# Phase 0 검증 스파이크 결과 (Story 1.3)

> **★ 이 문서는 영속 산출물입니다.** 스파이크 코드는 폐기되더라도 이 결론은 남아,
> E3(지도 go/no-go)·E7(챗봇 SSE)·배포(이관 절차)가 이 결론 위에서 시작합니다.
>
> - 작성일: 2026-06-14
> - 환경: Windows 11 / Python 3.12 / Node(pnpm 11) / PostgreSQL 18(로컬) / **docker 없음**
> - 키: `apps/api/.env`에 `KAKAO_REST_API_KEY`·`KAKAO_JS_KEY`·`OPENAI_API_KEY` 충전됨. `DATABASE_URL` 비어 있음.
> - 스파이크 서버: `spikes/phase0/sse/server.py` (standalone FastAPI, 포트 8001) — 프로덕션 `apps/api`(8000) 미접촉.

## 결론 요약 (한눈에)

| # | 검증 항목 | 결론 | 검증 방식 |
|---|-----------|------|-----------|
| ① | 카카오 지오코딩 e2e (REST 프록시) | ✅ **가능(검증 완료)** — 콘솔 활성화 후 실좌표 반환 | curl(자동) ✅ |
| ① | 카카오 지도표시 (JS SDK 렌더+핀) | ✅ **가능(검증 완료)** — 브라우저 지도+핀+핀이동 확인 | 브라우저 ✅ |
| ① | 카카오 약관 적합성(스터디룸 예약 중개) | ✅ **적합** (1.1에서 판정 완료) | 문서 확인 |
| ② | SSE 토큰 스트리밍 + `Authorization` 헤더 수신 | ✅ **가능** — 서버측 검증 완료 | curl(자동) ✅ |
| ② | SSE 웹 소비(fetch-stream) | ✅ **가능(검증 완료)** — 브라우저 토큰 누적+[DONE] 확인 | 브라우저 ✅ |
| ② | SSE RN 소비(react-native-sse) | ⏳ 코드·dep 준비 — **Expo Go SDK 불일치로 기기검증 보류**(E7 dev build) | dev build 필요 |
| ③ | pgvector 덤프/복원 + 유사도 검색 | ✅ **가능(검증 완료)** — Supabase→Railway 이관 + 검색 동작 | psql ✅ |

> **핵심 의사결정 영향:** ①의 카카오 콘솔 "카카오맵/로컬" 서비스가 **비활성**으로 확인됨 →
> 지오코딩·지도 모두 차단 상태. **E3 go/no-go 전에 소유자 콘솔 활성화 + 약관 적합성 판정이 선행돼야 함.**

---

## ① 카카오맵 e2e + 약관 적합성

### 결론
- **지오코딩(REST 프록시):** ✅ **가능(검증 완료).** 소유자가 카카오 콘솔에서 "카카오맵/로컬" 서비스를 활성화한 뒤
  재검증 → 주소→좌표 e2e 정상 동작. 백엔드 REST 프록시(키 분리 NFR-6) 경유로 실좌표 반환 확인.
  (활성화 전에는 `403 NotAuthorizedError: disabled OPEN_MAP_AND_LOCAL` — 키 무효가 아닌 서비스 미활성이었고, 코드 변경 없이 콘솔 토글로 해결됨.)
- **지도표시(JS SDK):** ✅ **가능(검증 완료, 2026-06-15).** `http://localhost:3000/spike-kakao`에서 지도 타일 +
  핀 렌더 + 주소 입력→핀 이동까지 브라우저로 확인. **도메인 등록 함정 발견:** 지도 JS SDK 도메인은
  "제품 링크 관리 → 웹 도메인"(카카오톡 공유용)이 아니라 **[앱 키 → JavaScript 키 → JavaScript SDK 도메인]** 에
  `http://localhost:3000`(스킴 포함) 등록해야 함. 잘못된 위치 등록 시 `401 AccessDeniedError: domain mismatched`.
- **약관 적합성:** ✅ **적합(판정 완료).** Story 1.1에서 카카오 운영자 데브톡 공식 답변을 근거로 "적합" 판정·기록됨
  (`docs/external-services-setup.md` §1 — "지도 API 상업적 사용 제한 없음", "주소→좌표 등록 후 마커 표시 패턴 허용").
  운영 제약: 카카오맵 가이드라인(로고/저작권 표기) 준수, 쿼터 모니터링, Local API 결과 대량 DB화 금지(제공자 등록 좌표만 저장 — 허용 범위).
  → **R1(아키텍처가 지목한 차단 가능 리스크)는 적합으로 닫힘.** E3 차단은 콘솔 서비스 활성화 + 도메인 등록만 남음.

### 증거
- 지오코딩 요청/응답(주소→좌표) — curl 자동 검증(콘솔 활성화 후):
  ```
  GET /_spike/geocode?query=서울특별시 강남구 테헤란로 152
  → {"count":1,"results":[{"address":"서울 강남구 테헤란로 152","lat":37.5000242,"lng":127.0365086}]}
  GET /_spike/geocode?query=부산광역시 해운대구 우동
  → {"count":4,"results":[{"address":"부산 해운대구 우동","lat":35.1727272,"lng":129.1483996}, ...]}
  GET /_spike/geocode?query=서울특별시 종로구 세종대로 175
  → {"count":2,"results":[{"address":"서울 종로구 세종대로 175","lat":37.5718479,"lng":126.9761683}, ...]}
  ```
  좌표 정확(강남역·해운대·광화문 인근). 프록시→카카오→좌표 e2e 체인 정상.
- 지도+핀 렌더: ✅ 브라우저 확인 완료(2026-06-15) — 지도 타일 + 파란 핀 + 지오코딩→핀 이동 동작.
  (다중 결과 예: "부산광역시 해운대구 우동" → `count:4`[우동/우1동/우2동/우3동], 스파이크는 `results[0]`만 단일 핀 표시.)

### 후속 영향 (E3)
- **카카오 지도 경로 = E3 GO(green, 완전 검증).** 약관 적합 ✅ + 콘솔 서비스 활성화 ✅ + 지오코딩 e2e ✅ + 지도 렌더+핀 ✅.
  대안 지도 제공자 검토 불필요. R1 리스크 완전 닫힘.
- **E3 설계 입력(다중 매칭 처리):** 지오코딩이 한 질의에 후보 여러 개 반환 가능(예 "우동"→4건). E3는 최상위 1개 사용 /
  사용자 선택 / 모두 표시 중 UX 결정 필요. (스파이크는 `results[0]` 단일 핀으로 체인만 증명.)
- **E3/배포 운영 교훈(도메인 등록 위치):** 지도 JS SDK 도메인 화이트리스트는 **[앱 키 → JavaScript 키 → JavaScript SDK 도메인]**
  에 등록(스킴 `http://` 포함). "제품 링크 관리 → 웹 도메인"(카카오톡 공유용)과 혼동 금지. 배포 도메인도 동일 위치에 추가.
- 검증된 코드 경로(백엔드 REST 프록시 + 프론트 JS SDK, 키 분리 NFR-6)를 E3가 프로덕션 위치로 이식.

---

## ② 챗봇 SSE 3면 + 인증 헤더

### 결론
- **서버 토큰 스트리밍 + `Authorization` 헤더 수신:** ✅ **가능(검증 완료).** standalone FastAPI
  `StreamingResponse(text/event-stream)`가 토큰을 `data: {token}\n\n` 형식으로 순차 전송하고 `data: [DONE]`로 종료.
  클라이언트가 보낸 `Authorization: Bearer spike-test-token`이 **서버에 도달함을 로그로 확인**. POST 바디(prompt)도 수신·echo.
- **웹(fetch-stream) 소비:** ✅ **가능(검증 완료, 2026-06-15).** `localhost:3000/spike-sse`에서 토큰 순차 누적 +
  `✅ 완료([DONE] 수신)` 확인. POST 바디 echo(`[echo:룸 예약 도와줘]`)로 바디 전달도 증명. `fetch`+`ReadableStream`
  리더 경로(네이티브 `EventSource`는 커스텀 헤더 불가라 미사용).
- **RN(react-native-sse, POST+헤더+바디) 소비:** ⏳ 코드(`apps/mobile/src/app/spike-sse.tsx`) + dep(`react-native-sse@^1.2.1`)
  준비 완료. 기기 검증은 **보류** — **핵심 발견:** 프로젝트가 **Expo SDK 56 / RN 0.85(프리뷰급 최신)** 라
  **스토어 Expo Go가 실행 불가**(`Project is incompatible with this version of Expo Go — requires a newer version`).
  → **모바일은 처음부터 development build(`expo run:android`/`prebuild`) 또는 EAS dev client 필요**(Expo Go 워크플로 불가).
  서버측(curl)·웹 fetch-stream으로 SSE 전송·인증헤더는 이미 검증됨 + react-native-sse는 표준 JS 라이브러리라
  잔여 리스크 낮음 → **RN 기기 검증은 E7(dev client 도입 시)로 이관**.

### 증거 (curl 자동 검증)
```
$ curl -s -D - -X POST http://localhost:8001/_spike/stream \
    -H "Authorization: Bearer spike-test-token" -H "Content-Type: application/json" \
    -d '{"prompt":"hello"}'
HTTP/1.1 200 OK
cache-control: no-cache
x-accel-buffering: no
content-type: text/event-stream; charset=utf-8

data: [echo:hello]
data: 안녕하세요
data: 룸메이트입니다
data: 무엇을
data: 도와드릴까요
data: [DONE]

# 서버 콘솔 로그(헤더·바디 수신 증명):
[SSE] Authorization 수신: 'Bearer spike-test-token'
[SSE] prompt 수신: 'hello'
```
- 웹 화면(토큰 순차 누적): ✅ 브라우저 확인 완료(2026-06-15) — `[echo:룸 예약 도와줘] 안녕하세요 룸메이트입니다 무엇을 도와드릴까요` + [DONE].
- RN 화면(토큰 순차 누적) 스크린샷: _Expo 기기 확인 대기_

### 알려진 이슈 / 메모
- **Windows cp949 콘솔:** 한글 토큰/prompt를 print할 때 `UnicodeEncodeError`로 500이 발생 → 서버 시작 시
  stdout/stderr를 UTF-8(errors=replace)로 재설정해 해결(`apps/api/config.py`와 동일 패턴). E7 프로덕션 로깅도 동일 주의.
- **Expo `CdpInterceptor`** 가 SSE를 가로채는 알려진 디버깅 이슈(research L189) — Expo 수동 검증 시 발생하면 여기 우회법 기록.
- 웹 인증 헤더 케이스는 반드시 **fetch-stream**(native EventSource는 커스텀 헤더 불가).

### 후속 영향 (E7)
- 검증된 전송 패턴(StreamingResponse + 헤더 propagation + fetch-stream/react-native-sse)을 E7이 프로덕션 위치
  `apps/api/app/chatbot/` + `/api/v1/chatbot/stream`로 이식. LangGraph/LLM·실 JWT(1.7/1.8)는 E7/인증 스토리 몫.

---

## ③ pgvector 덤프/복원 이관

### 결론
- **이관(덤프→복원)·유사도 검색:** ✅ **가능(검증 완료, 2026-06-15).** 소스 **Supabase(PostgreSQL 17.6)** →
  타깃 **Railway(PostgreSQL 18.4, pgvector 0.8.2)** 로 `spike_items(vector(1536))` 10행을 덤프/복원 →
  복원 후 코사인 유사도 검색 정상 동작. 행 수·HNSW 인덱스까지 충실히 이관됨.
- **타깃 확장 선설치 교훈:** ✅ **실증됨.** 타깃에 `CREATE EXTENSION vector` 없이 복원 시
  `ERROR: type "public.vector" does not exist`로 **실패**. 확장 설치 후 복원하면 성공 → "타깃 vector 확장 선설치 필수"가 결정적임을 확인.

### 증거 (실 이관 로그)
```
# 소스 시드(Supabase): seeded_rows=10, 인덱스 spike_items_pkey + spike_items_embedding_hnsw, 벡터 행마다 distinct
# 덤프: pg_dump --no-owner --no-privileges --table=public.spike_items → dump.sql 165,743 bytes (데이터 10행 + HNSW DDL)

# [교훈] 확장 없이 복원 시도 →
psql:dump.sql:34: ERROR:  type "public.vector" does not exist  (embedding public.vector(1536))

# CREATE EXTENSION vector → vector | 0.8.2
# 복원(확장 후): COPY 10행 + ALTER TABLE(pkey) + CREATE INDEX(hnsw), 에러 0

# verify.sql (타깃):
 extname=vector / extversion=0.8.2
 restored_rows=10
 spike_items_pkey (btree) / spike_items_embedding_hnsw (hnsw vector_cosine_ops)
 유사도 검색 ORDER BY embedding <=> :q LIMIT 3 → id 8/4/3 (cosine_distance 0.245/0.248/0.248)
```

### 후속 영향 (배포)
- **이관 경로 검증 완료(green).** 배포 시 `pg_dump --no-owner --no-privileges` + 타깃 `CREATE EXTENSION vector` 선설치 +
  `psql < dump.sql` + 검색 검증 절차로 진행하면 됨(`RUNBOOK.md`). PG14+ (검증은 17→18 스큐에서도 plain SQL 덤프로 무난).
- **운영 교훈:** Railway 일반 Postgres에도 `vector` 확장이 **available**이라 `CREATE EXTENSION vector`로 설치 가능했음
  (사전탑재 템플릿이 아니어도 됨). 단 복원 **전에** 확장을 먼저 만들어야 함.
- ⚠️ **정리 필요:** 이번 검증으로 Supabase·Railway에 `spike_items` 테스트 테이블이 남음(throwaway). 또한
  `spikes/phase0/pgvector/connections.env`에 **실 접속 비밀번호**가 저장됨(gitignore: `spikes/`+`*.env` 이중 보호). 검증 후
  테스트 테이블 drop + connections.env 삭제(또는 비밀번호 회전/프로젝트 삭제) 권장.

---

## 무회귀 게이트 결과 (AC4)

스파이크 추가 후에도 1.2 골격이 그린임을 확인:

| 게이트 | 결과 |
|--------|------|
| `cd apps/api && uv run pytest` | ✅ **20 passed** (1 warning) |
| `uv run ruff check .` | ✅ All checks passed |
| `uv run mypy app` | ✅ no issues (11 files) |
| `pnpm --filter web lint` | ✅ clean |
| `pnpm --filter web build` | ✅ success (`/spike-kakao`·`/spike-sse` 정적 빌드) |
| `pnpm --filter admin lint` / `build` | ✅ clean / success |
| `pnpm --filter mobile lint` | ✅ exit 0 |
| 프로덕션 트리 미접촉 | ✅ `apps/api/**` 미수정(게이트 그린으로 증명), `apps/web/src/{features,components,lib}` 미생성, mobile 원본 라우트(`_layout`/`index`/`explore`) 미수정 |

### 격리 / 폐기 결정
- 스파이크 코드는 `spikes/phase0/**`(gitignore됨) + 각 앱 `spike-*` 라우트에만 존재.
- **라우팅 네이밍 편차:** 스토리의 `_spike-*` 리터럴은 Next.js(`_` = private 비라우팅)·expo-router(`_` 제외) 모두에서
  페이지가 **라우팅되지 않아 수동 검증 불가** → 라우팅 가능한 `spike-*`로 조정(격리·제거 용이성은 동일하게 충족).
- **폐기 권장:** E3/E7가 검증된 패턴을 프로덕션 위치로 이식한 뒤, `spike-*` 앱 라우트(웹 2개·RN 1개)와
  `spikes/phase0/**`는 제거 권장(프로덕션 빌드 혼입 방지). `react-native-sse` dep은 E7에서 계속 쓰면 유지, 아니면 제거.

---

## 🔔 소유자/후속 액션 (요약)

1. ✅ **완료** — 카카오 콘솔 "카카오맵/로컬" 서비스 활성화 + JS SDK 도메인(localhost:3000/3001) 등록 → 지오코딩·지도 e2e 검증됨.
2. ✅ **완료** — 카카오맵 약관 적합성 = **적합**(1.1 판정).
3. ✅ **완료** — SSE 서버 + 웹 fetch-stream 검증.
4. ✅ **완료** — Supabase→Railway pgvector 이관 + 검색 검증 + 확장 선설치 교훈 실증.
5. ⏳ **E7 이관** — RN(react-native-sse) 기기 검증: Expo SDK 56이 스토어 Expo Go 미지원 → dev build/EAS 필요. 코드·dep·서버+웹 검증 완료라 잔여 리스크 낮음.
6. 🧹 **정리** — ✅ `connections.env`(실 비밀번호) 삭제됨, ✅ 방화벽 8001 규칙 소유자가 제거.
   ⏳ **남음:** Supabase·Railway의 `spike_items` 테스트 테이블 drop(소유자가 대시보드에서 `DROP TABLE IF EXISTS public.spike_items;` 또는 throwaway 프로젝트 통째 삭제 — connections.env 삭제로 dev가 재접속 불가). `spike-*` 라우트·`spikes/` 제거는 code-review 후 E3/E7 이식 시점에.
