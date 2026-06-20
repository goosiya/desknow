---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-06-14'
inputDocuments:
  - '_bmad-output/planning-artifacts/prds/prd-desknow-2026-06-14/prd.md'
  - '_bmad-output/planning-artifacts/prds/prd-desknow-2026-06-14/addendum.md'
  - '_bmad-output/planning-artifacts/research/technical-desknow-mvp-tech-feasibility-research-2026-06-13.md'
  - '_bmad-output/planning-artifacts/ux-designs/ux-desknow-2026-06-14/EXPERIENCE.md'
  - '_bmad-output/planning-artifacts/ux-designs/ux-desknow-2026-06-14/DESIGN.md'
  - '_bmad-output/planning-artifacts/briefs/brief-desknow-2026-06-14/brief.md'
  - '_bmad-output/planning-artifacts/briefs/brief-desknow-2026-06-14/addendum.md'
  - 'docs/idea.md'
workflowType: 'architecture'
project_name: 'desknow'
user_name: 'KTH'
date: '2026-06-14'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:** FR 34개(FR-1~33 + FR-18a), 13개 기능군.
- 계정·인증(FR-1~3), 지도 탐색(FR-4~7), 목록 탐색(FR-8~9), 즐겨찾기(FR-10),
  상세·예약(FR-11~16), 예약관리(FR-17), 알림(FR-18·18a), 공유(FR-19),
  후기(FR-20~21), 제공자 공간(FR-22), 제공자 예약(FR-23~24),
  챗봇(FR-25~30), 운영(FR-31~33).
- 아키텍처적으로 가장 무거운 FR: FR-15(동시성 불변식), FR-29(멀티 LLM 어댑터),
  FR-30(SSE 스트리밍), FR-33(인제스트 멱등성).

**Non-Functional Requirements (PRD §10):**
- 시간·타임존: slot_start=UTC, 판정=Asia/Seoul (5개 시간경계의 결정성 전제).
- 성능: 첫 지도 ≤2초 / 챗봇 첫 토큰 ≤2초 / 로컬 피드백 ≤100ms (p90·웜).
- 보안: 외부 API 키 백엔드 격리, JWT 공용, RBAC 백엔드 최종 강제, 비번 해싱.
- 신뢰성: 동시 예약(겹치는 구간 포함) 중복·부분점유 0건, 상태전이 원자·멱등.
- 접근성: WCAG AA, 색 비의존, 키보드/스크린리더, 상태 매트릭스 빈셀 0.

**Scale & Complexity:**
- Primary domain: 풀스택(사용자 웹 + 관리자 웹 + RN 앱 + FastAPI + AI/RAG)
- Complexity level: Medium-High (통합 복잡도 중심)
- Estimated architectural components: 6 (API 모놀리스 / 챗봇 서비스 /
  PostgreSQL+pgvector / 사용자 웹 / 관리자 웹 / RN 앱)

### Technical Constraints & Dependencies

- 플랫폼: Railway 상시 컨테이너 과금(서비스 수 = 비용) → 서비스 수 최소화 압력.
- 지도: 카카오맵(약관 적합성 1차 확인 필요), 좌표+행정동 코드 이중 저장.
- 모바일: RN(Expo) — SSE 미지원(react-native-sse), 카카오 공유 네이티브 모듈
  (EAS dev build), localhost 미접근.
- LLM: 프로바이더별 파라미터 비대칭 → 어댑터 레이어 필수, 임베딩 단일 고정.
- 인증: refresh 즉시 무효화 저장소(Redis 또는 DB) 선택 필요.
- 데이터: pgvector와 예약 테이블 동일 PostgreSQL 공존.

### Cross-Cutting Concerns Identified

1. 동시성·데이터 정합성 (UNIQUE 제약 + 단일 트랜잭션 + 상태 머신)
2. 시간·타임존 (UTC 저장 / KST 판정 — 5개 시간경계 종속)
3. 인증·인가 (단일 JWT, 3역할 RBAC, 토큰보관 이원화, 최종강제 백엔드)
4. 멀티 LLM 추상화 (요청/응답/스트리밍/에러 정규화 어댑터)
5. 멀티 서피스 타입 안전성 (OpenAPI → TS SDK 자동생성, CORS, API 버저닝)
6. 비용·운영 (Railway 상시 과금 모니터링, 챗봇 배포 토폴로지)
7. 접근성·상태 설계 (WCAG AA, 상태 매트릭스, 색 비의존)
8. 보안 경계 (외부 API 키 백엔드 격리, 스트리밍 엔드포인트 인증)

## Starter Template Evaluation

### Primary Technology Domain
풀스택 모노레포(Next.js 웹 ×2 + Expo 모바일 + FastAPI + PostgreSQL/pgvector)

### Starter Options Considered
- create-t3-turbo — Next.js+Expo 모노레포이나 tRPC 올-TS라 FastAPI/OpenAPI와 충돌 → 부적합.
- full-stack-fastapi-template(공식) — FastAPI+JWT+PostgreSQL 정합하나 프론트가
  React+Vite 단일 웹, 모노레포/Expo/관리자 분리 부재 → OpenAPI→TS 패턴만 차용.
- create-turbo(공식 Turborepo) — 깔끔한 JS 모노레포 골격, Expo/Python 미포함 → 골격 채택.

### Selected Starter: 하이브리드 스캐폴드 (create-turbo 골격 + 앱별 공식 스캐폴드)

**Rationale for Selection:**
단일 스타터가 3 JS 서피스 + Python 백엔드 조합을 모두 만족하지 못함. 공식 도구를
조합해 각 서피스를 최신·정공법으로 세우고, 파이썬은 느슨한 결합으로 공존(기술조사 권고).

**Initialization Command (구현 1번 스토리):**

```bash
# 1) 모노레포 골격 (pnpm)
pnpm dlx create-turbo@latest desknow --package-manager pnpm

# 2) 웹 앱 2종 (Next.js 16, App Router, TS, Tailwind)
pnpm dlx create-next-app@latest apps/web --ts --tailwind --app --src-dir
pnpm dlx create-next-app@latest apps/admin --ts --tailwind --app --src-dir

# 3) 모바일 (Expo SDK 56)
pnpm dlx create-expo-app@latest apps/mobile

# 4) 백엔드 (FastAPI, uv 기반 — 느슨한 공존)
cd apps/api && uv init && uv add fastapi uvicorn[standard] sqlmodel psycopg[binary] \
  pyjwt "pwdlib[argon2]" pgvector

# 5) OpenAPI→TS SDK 공유 패키지
#    packages/api-client 에 @hey-api/openapi-ts 설정, FastAPI openapi.json 소비
```

**Architectural Decisions Provided by Starter:**
- 언어/런타임: 프론트 TypeScript(strict), 백엔드 Python(uv 관리).
- 빌드: Turborepo 2.9 태스크 캐싱 + pnpm 워크스페이스. 파이썬은 1급 워크스페이스
  밖, OpenAPI 스키마로만 결합.
- 스타일: shadcn/ui + Tailwind (DESIGN.md 토큰 매핑).
- 코드 구성: apps/{web,admin,mobile,api} + packages/{api-client,ui,config}.
- 타입 안전: SQLModel → Pydantic → OpenAPI → TS(@hey-api/openapi-ts) 풀체인.
- 버전(2026-06 기준): Turborepo 2.9.x / Next.js 16.2.x / Expo SDK 56(RN 0.85·React 19.2).

**Note:** 위 초기화 명령은 구현 1번 스토리로 둔다. 버전은 init 시점 최신으로 재확인.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- 동시성: UNIQUE(room_id, slot_start) + 단일 트랜잭션 multi-row INSERT (all-or-nothing).
- 시간: slot_start=UTC 저장 / 판정=Asia/Seoul.
- 인증: 단일 JWT(access+refresh) + refresh 무효화 = PostgreSQL 테이블.
- 데이터 계층: SQLModel (SQLModel→Pydantic→OpenAPI→TS 타입 체인).

**Important Decisions (Shape Architecture):**
- 챗봇 배포: API 통합 시작 → 부하 시 분리(단계적, 비용 최소화).
- 임베딩: OpenAI text-embedding-3-small 단일 고정(교체 시 전체 재임베딩).
- 멀티 LLM 기준 프로바이더: OpenAI(GPT) — FR-30 ≤2초 보증 대상.
- 영업시간 모델: 요일별 영업시간 + 휴무일 예외 테이블.

**Deferred Decisions (Post-MVP):**
- 비밀번호 정책 완화(NIST Rev.4 길이우선+유출목록) — 차기(PRD §8 Q8).
- 챗봇 별도 서비스 물리 분리 — 부하 발생 시.
- Redis 도입 — 무효화/캐시 부하가 DB를 압박할 때.

### Data Architecture

- **DB:** PostgreSQL(단일) + pgvector(HNSW). 예약 테이블과 벡터 테이블 공존.
- **ORM:** SQLModel — FastAPI 생태계 표준, Pydantic 통합으로 타입 체인 매끄러움.
- **동시성:** 고정 1시간 슬롯 → `UNIQUE(room_id, slot_start)`. 연속 N슬롯은
  단일 트랜잭션 multi-row INSERT(`ON CONFLICT` 후 affected=N 검증, 아니면 ROLLBACK).
  부분 점유 0건. 상태 전이(확정→취소/거절) 원자·멱등, 슬롯 재활성 동일 트랜잭션.
- **영업시간/휴무:** room별 요일별(weekday 0~6) 영업시간 행 + 휴무일 예외(date) 테이블.
  슬롯은 (요일별 영업시간 − 휴무일 − 이미 예약) 으로 도출. 확정 예약은 slot_start
  자체 보유 → 영업시간 변경에 독립(FR-22).
- **지도/주소:** 좌표(lat/lng) + 행정동 코드 둘 다 저장(반경/행정동 두 검색). 반경은
  pgvector와 별개로 PostGIS ST_DWithin 또는 Haversine(MVP 규모는 후자도 충분).
  - **※ 용어(법정동 vs 행정동 — KTH 확정 2026-06-15):** 본 문서가 "행정동 코드"로 표기하나,
    **실제 구현 기준은 법정동(b_code)이다.** 2.2가 카카오 `address.b_code`(법정동)를
    `admin_dong_code`에 저장했고 지번 주소 기준으로 더 안정적·표준이라 그대로 채택한다.
    "행정동"은 "동 단위 지역"의 느슨한 라벨이며, 데이터·콤보 참조(법정동코드 전체자료)는
    모두 법정동 기준이다(Story 3.4). 행정동(h_code) 전환은 2.2/모델/마이그레이션/백필 필요라 비채택.
- **마이그레이션:** Alembic.

### Authentication & Security

- **인증:** 단일 FastAPI 발급 JWT(access 단기 + refresh 장기). PyJWT + pwdlib(Argon2).
- **refresh 무효화:** PostgreSQL 테이블에 refresh 해시 저장 → 로그아웃/탈취 시 즉시 무효화.
  (Railway 서비스 추가 없이 비용 0; 부하 증가 시 Redis로 이전 — Deferred.)
- **토큰 보관 이원화:** 웹=httpOnly+Secure+SameSite 쿠키 / RN=expo-secure-store + Bearer 헤더.
  백엔드는 쿠키·헤더 양쪽 추출 지원.
- **RBAC:** JWT role 클레임(booker/provider/admin) + FastAPI 의존성. 최종 강제는 백엔드,
  Next.js 미들웨어는 라우트 보호 보조.
- **키 격리:** 카카오·LLM·지도 키는 백엔드 환경변수만. 지도 JS SDK 도메인 키는 도메인 화이트리스트.
- **스트리밍 보호:** 챗봇 SSE 엔드포인트도 JWT 보호.
- **비밀번호:** MVP는 8자+대/특/숫 강제(백엔드 신뢰경계). NIST Rev.4 완화는 차기.

### API & Communication Patterns

- **백엔드 구조:** FastAPI 모듈러 모놀리스(도메인 모듈: auth, rooms, reservations,
  reviews, notifications, chatbot, admin).
- **API:** REST + OpenAPI, `/api/v1` 버저닝(모바일 구버전 잔존 대비 하위 호환).
- **타입 안전:** OpenAPI → @hey-api/openapi-ts → packages/api-client 공유 SDK.
- **CORS:** 웹 origin 등록(CORSMiddleware), RN은 미적용.
- **에러 표준:** 구조화 에러 스키마(코드+메시지), 동시성 충돌은 409 → UI는 우아한 안내+인접 슬롯.
- **챗봇 통신:** SSE(text/event-stream) 토큰 스트리밍. 웹=표준 EventSource/fetch-stream,
  RN=react-native-sse(인증 헤더·POST 바디 위해 fetch 기반).

### Frontend Architecture

- **웹:** Next.js 16 App Router ×2(사용자/관리자 분리 앱). shadcn/ui + Tailwind, DESIGN.md 토큰 매핑.
- **모바일:** Expo SDK 56(RN 0.85). 카카오 공유=네이티브 모듈(EAS dev build), SSE=react-native-sse.
- **상태관리:** 서버 상태=TanStack Query(캐시·옵티미스틱), 클라이언트 상태=경량(Zustand/Context).
  옵티미스틱 토글 ≤100ms(즐겨찾기·슬롯 선택).
- **라우팅:** 웹=App Router, 앱=Expo Router.
- **챗봇 세션:** 사용자×디바이스 단위, LangGraph checkpointer + thread_id, 로그아웃 시 초기화.

### Infrastructure & Deployment

- **호스팅:** Railway 단일 프로젝트 — 서비스: 사용자 웹 / 관리자 웹 / FastAPI(챗봇 통합) /
  PostgreSQL(pgvector). 챗봇 부하 시 별도 서비스 분리(서비스 수=비용 인지).
- **모바일:** Expo EAS Build(Free) + Submit. Apple $99/년, Google $25(1회).
- **모노레포:** Turborepo 2.9 + pnpm. 파이썬은 느슨한 공존(uv), 결합은 OpenAPI 스키마.
- **환경설정:** .env(백엔드) + Railway 변수. 비용 모니터링/알림 필수.
- **챗봇 LLM:** LangGraph + LangChain v1, 멀티 LLM 어댑터(요청/응답/스트리밍/에러 정규화,
  공통 5종). 기준 프로바이더=OpenAI(≤2초 SLA), Anthropic/Google는 best-effort.
- **인제스트:** 디렉터리 배치 → 멱등 인제스트(동일 문서 중복 벡터 미생성), 부분 실패 식별.

### Decision Impact Analysis

**Implementation Sequence:**
1. 모노레포 + FastAPI 골격 + PostgreSQL(pgvector) + Alembic.
2. 인증(JWT + refresh 테이블 + RBAC) + OpenAPI→TS SDK 파이프라인.
3. 도메인: rooms(영업시간/휴무 모델·좌표/행정동) → reservations(UNIQUE·트랜잭션·상태머신).
4. 탐색(지도/목록/반경) · 즐겨찾기 · 후기 · 알림 배너 · 카카오 공유.
5. 챗봇(인제스트→pgvector, LangGraph 2툴, 멀티 LLM 어댑터, SSE).
6. Railway 멀티 서비스 배포 + EAS 빌드 + 비용 모니터링.

**Cross-Component Dependencies:**
- 시간·타임존 규약은 핀색·슬롯·취소·배너·이용완료 전부의 전제(가장 먼저 유틸 고정).
- OpenAPI 스키마가 3개 프론트의 타입 원천 → 백엔드 계약 변경 시 SDK 재생성.
- 영업시간/휴무 모델 → 슬롯 도출 → 예약·핀색 집계 의존.
- refresh 테이블 → 로그아웃/탈취 무효화 → 챗봇 세션 종료 연동.

**Phase 0 검증 스파이크(구현 전 권장):**
① 카카오맵 지도표시+주소변환 e2e (+ 약관 서비스유형 적합성 1차 확인),
② 챗봇 SSE 스트리밍(FastAPI↔웹↔RN),
③ Supabase→Railway pgvector 덤프/복원 1회.

## Implementation Patterns & Consistency Rules

### Critical Conflict Points Identified
Python↔TS↔OpenAPI 경계, DB/API/코드 네이밍, 에러/응답 포맷, 시간 표현,
상태/로딩 처리 — 7개 영역에서 에이전트가 다르게 선택할 수 있음.

### Naming Patterns

**Database (PostgreSQL):**
- 테이블: 복수 snake_case — `rooms`, `reservations`, `business_hours`, `holiday_exceptions`,
  `refresh_tokens`, `favorites`, `reviews`, `notifications`.
- 컬럼: snake_case — `room_id`, `slot_start`, `created_at`.
- FK: `{단수}_id` — `room_id`, `user_id`. 인덱스: `idx_{table}_{cols}`,
  제약: `uq_{table}_{cols}` (예 `uq_reservations_room_slot`).
- 시각 컬럼: `*_at`(UTC, timestamptz). 모든 시각은 UTC 저장.

**API (REST):**
- 엔드포인트: 복수 명사 kebab 불가 → snake 경로 세그먼트 지양, 리소스는 복수 —
  `/api/v1/rooms`, `/api/v1/rooms/{room_id}/reservations`.
- 경로 파라미터: `{room_id}` (FastAPI 스타일).
- 쿼리 파라미터 & JSON 필드: **snake_case**(와이어 전 구간 통일, 변환 없음).
- 상태코드: 201(생성), 409(동시성 충돌·중복가입), 403(권한), 401(미인증), 422(검증).

**Code:**
- Python: 모듈/함수/변수 snake_case, 클래스 PascalCase(SQLModel/Pydantic 모델).
- TS: 변수/함수 camelCase, 컴포넌트 PascalCase, 파일 `PascalCase.tsx`(컴포넌트)/
  `kebab-case.ts`(유틸). **API 응답 객체 필드는 snake_case 그대로 사용**(SDK 생성형).

### Structure Patterns

- 백엔드: 도메인 모듈별 패키지 — `apps/api/app/{domain}/{router,models,schemas,service}.py`.
  도메인: auth, rooms, reservations, reviews, notifications, chatbot, admin.
- 프론트: 기능(feature) 단위 폴더. 공유는 `packages/{ui,api-client,config}`.
- 테스트: 백엔드 `tests/` 미러 구조(pytest), 프론트 `*.test.ts(x)` co-located(vitest).
- 환경설정: 백엔드 `.env` + pydantic-settings, 프론트 `.env.local`.

### Format Patterns

- **응답 래퍼 없음** — 리소스를 직접 반환(OpenAPI 스키마가 곧 계약). 목록은 페이지네이션
  메타 포함 객체 `{ items: [...], total, page }`.
- **에러 포맷:** `{ "detail": { "code": "SLOT_CONFLICT", "message": "..." } }`
  (FastAPI HTTPException 확장). 도메인 에러코드 상수화(예 SLOT_CONFLICT, EMAIL_TAKEN,
  CANCEL_WINDOW_PASSED, FORBIDDEN_ROLE).
- **시간:** API는 ISO-8601 UTC 문자열(`2026-06-14T05:00:00Z`). UI 표시는 룸 타임존(KST) 변환.
  날짜 경계 판정은 절대 클라이언트 로컬 타임존에 의존하지 않음.
- boolean true/false, null 명시(누락≠null 구분).

### Communication Patterns

- **상태 전이:** 예약 상태는 서버 단일 연산. 클라이언트는 상태를 추측하지 않고 응답으로 갱신.
- **TanStack Query 키:** `['rooms', filters]`, `['reservations', 'me']`, `['room', roomId, 'slots', date]`.
  뮤테이션 성공 시 관련 키 invalidate(예약 후 slots·핀집계 무효화).
- **옵티미스틱:** 즐겨찾기·슬롯 선택만 옵티미스틱(≤100ms), 예약 확정은 서버 확인 후.
- **챗봇:** SSE 이벤트 `data:` 토큰 청크 + 종료 신호. thread_id로 세션 식별.

### Process Patterns

- **검증 시점:** 프론트=UX 보조, 백엔드=신뢰 경계(Pydantic). 비번 복잡도·역할·소유권 백엔드 최종.
- **에러 처리:** 백엔드 전역 예외 핸들러 → 표준 에러 스키마. 프론트 전역 에러 바운더리 +
  쿼리 에러 → EXPERIENCE.md 마이크로카피("앗, 방금 다른 분이…").
- **로딩:** 화면별 스켈레톤(상태 매트릭스 준수), 전역 스피너 지양.
- **인증 흐름:** 401 → access 만료 시 refresh 1회 자동 재발급 → 실패 시 로그인 유도.

### Enforcement Guidelines

**All AI Agents MUST:**
- 와이어 전 구간 snake_case 유지(camelCase 변환 레이어 금지).
- 모든 시각 UTC 저장 / ISO-8601 UTC 전송 / 표시만 KST 변환.
- 도메인 에러는 표준 에러코드 상수 사용(문자열 하드코딩 금지).
- 슬롯 점유/재활성은 상태 전이와 동일 트랜잭션 안에서만.
- 프론트는 OpenAPI 생성 SDK(packages/api-client)로만 백엔드 호출(직접 fetch 금지).

**Anti-Patterns (금지):**
- 클라이언트가 핀마다 슬롯 N회 계산(서버 집계값 사용).
- 멀티 LLM을 if 분기로 처리(어댑터 레이어 정규화).
- 색만으로 상태 표현(색+아이콘/텍스트 병행).
- 로컬 타임존으로 날짜 경계 판정.

## Project Structure & Boundaries

### Complete Project Directory Structure

```
desknow/
├── README.md
├── package.json                # pnpm 워크스페이스 루트
├── pnpm-workspace.yaml
├── turbo.json                  # Turborepo 파이프라인
├── .github/workflows/ci.yml
├── apps/
│   ├── web/                    # 사용자 웹 (Next.js 16, App Router)
│   │   ├── src/app/            # 라우트: /(찾기) /rooms/[room_id] /reservations /favorites /login
│   │   ├── src/features/       # map, list, room-detail, reservation, favorites, reviews, chatbot
│   │   ├── src/components/ui/  # shadcn
│   │   ├── src/lib/            # query-client, kakao-map, kakao-share, sse
│   │   └── .env.local
│   ├── admin/                  # 관리자 웹 (Next.js 16, 분리 앱)
│   │   └── src/app/            # /accounts /reservations /ingest
│   ├── mobile/                 # RN (Expo SDK 56)
│   │   ├── app/                # Expo Router: 동일 화면 + (provider) 영역
│   │   ├── src/features/       # web과 동일 도메인, 터치 우선
│   │   └── src/lib/            # secure-store, rn-sse, kakao-share(native)
│   └── api/                    # FastAPI (uv, 느슨한 공존)
│       ├── pyproject.toml
│       ├── app/
│       │   ├── main.py         # FastAPI 앱, CORS, /api/v1 라우터 등록
│       │   ├── core/           # config(pydantic-settings), db, security(jwt), time(utc/kst), errors
│       │   ├── auth/           # router/models/schemas/service — FR-1~3, refresh_tokens
│       │   ├── rooms/          # FR-4~9,22 — room, business_hours, holiday_exceptions, 좌표/행정동
│       │   ├── reservations/   # FR-11~17,23,24,31,32 — UNIQUE·트랜잭션·상태머신·슬롯도출
│       │   ├── favorites/      # FR-10
│       │   ├── reviews/        # FR-20,21
│       │   ├── notifications/  # FR-18,18a — pending/dismiss
│       │   ├── chatbot/        # FR-25~30 — langgraph agent, llm/adapters, tools, ingest, sse
│       │   └── admin/          # FR-31~33
│       ├── alembic/            # 마이그레이션
│       ├── docs_corpus/        # 챗봇 인제스트 대상 디렉터리
│       └── tests/              # pytest 미러 구조 (+ 동시성 테스트 SM-4)
├── packages/
│   ├── api-client/             # @hey-api/openapi-ts 생성 SDK (openapi.json 소비)
│   ├── ui/                     # 공유 shadcn 토큰·컴포넌트 (DESIGN.md 매핑)
│   └── config/                 # eslint, tsconfig, tailwind preset
└── docs/                       # idea.md 등
```

### Architectural Boundaries

**API Boundaries:**
- 외부 표면: `/api/v1/*` REST + 챗봇 `/api/v1/chatbot/stream`(SSE). OpenAPI가 단일 계약.
- 내부: 도메인 모듈 간 직접 import 금지, service 계층 통해서만. 챗봇 예약검색 툴은
  reservations.service를 호출(SQL 직접 접근 금지).
- 인증/인가 경계: core/security 의존성으로 라우터 진입에서 role 강제(백엔드 최종).

**Component Boundaries:**
- 프론트는 packages/api-client SDK로만 백엔드 호출. 직접 fetch 금지.
- 서버 상태=TanStack Query, 화면 로컬 상태만 Zustand/Context.
- web/admin/mobile은 도메인 로직을 공유하지 않되(서피스별 구현) 타입·SDK·UI 토큰만 공유.

**Data Boundaries:**
- 단일 PostgreSQL. 예약 테이블 + pgvector 테이블 공존. SQLModel 모델이 스키마 원천.
- 슬롯은 물리 테이블이 아니라 (business_hours − holiday_exceptions − reservations) 도출.
  점유는 reservations 행(room_id, slot_start)으로만 표현 → UNIQUE 제약이 진실의 원천.
- 핀 색 = 서버측 집계 엔드포인트(룸별 잔여 빈 슬롯 수), 클라이언트 N회 계산 금지.

### Requirements to Structure Mapping

- 계정/인증 FR-1~3 → apps/api/app/auth (+ refresh_tokens 테이블).
- 탐색 FR-4~9 → rooms (지도/목록/반경, 좌표+행정동) · web/mobile features/map,list.
- 즐겨찾기 FR-10 → favorites.
- 상세/예약/동시성 FR-11~16 → reservations (트랜잭션·상태머신) · features/reservation.
- 예약관리 FR-17,23,24 → reservations (booker/provider 뷰).
- 알림 FR-18,18a → notifications · 전역 배너 컴포넌트.
- 공유 FR-19 → lib/kakao-share (web JS SDK / RN native).
- 후기 FR-20,21 → reviews.
- 제공자 공간 FR-22 → rooms + provider 영역.
- 챗봇 FR-25~30 → chatbot (langgraph, adapters, tools, sse) · features/chatbot.
- 운영 FR-31~33 → admin (+ apps/admin 화면).

**Cross-Cutting Concerns:**
- 시간(UTC/KST) → core/time, 프론트 lib/datetime. 모든 시간 경계 단일 출처.
- 인증/RBAC → core/security + 프론트 lib/auth(refresh 자동 재발급).
- 멀티 LLM 어댑터 → chatbot/llm/adapters/{openai,anthropic,google}.py + base.
- 에러코드 → core/errors 상수, 프론트 api-client 에러 매핑.

### Integration Points

**Internal:** OpenAPI 스키마 → openapi.json → @hey-api 생성 → packages/api-client.
백엔드 계약 변경 시 SDK 재생성(CI에서 drift 검사).
**External:** 카카오맵(지도/지오코딩), 카카오 공유 SDK, OpenAI/Anthropic/Google LLM,
OpenAI 임베딩. 키는 백엔드 환경변수(지도 JS 도메인 키만 프론트, 화이트리스트).
**Data Flow:** 클라이언트 → SDK → /api/v1 → service → SQLModel → PostgreSQL.
챗봇: 클라이언트 → SSE → langgraph(checkpointer) → tools(문서검색=pgvector / 예약검색=reservations.service).

### Development Workflow Integration

- 개발: `turbo dev`(web/admin/mobile) + `uv run uvicorn`(api, 별도). RN은 LAN IP API base.
- 빌드: Turborepo 캐싱(JS), api는 컨테이너 빌드(Dockerfile). openapi.json 생성 → SDK.
- 배포: Railway 서비스(web/admin/api+chatbot/postgres) + EAS(mobile). 비용 모니터링.

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:** Turborepo 2.9 + pnpm + Next.js 16 + Expo 56 + FastAPI(uv) +
PostgreSQL/pgvector + LangChain v1 조합은 2026-06 기준 상호 호환(웹 검증). 모순 결정 없음.
파이썬-JS 결합은 OpenAPI 스키마로 단일화 → 버전 충돌 표면 최소.

**Pattern Consistency:** 와이어 snake_case 통일이 FastAPI 기본·OpenAPI→TS 생성과 정합.
시간 규약(UTC/KST)이 5개 시간경계 FR과 일관. 에러코드 상수·표준 에러스키마가 전 도메인 공통.

**Structure Alignment:** 도메인 모듈 구조가 결정(모듈러 모놀리스)·패턴(service 경계)을 지지.
슬롯=도출/점유=reservations 행 경계가 동시성 결정(UNIQUE)과 정합.

### Requirements Coverage Validation ✅

**Functional Requirements Coverage (34/34):**
- 계정 FR-1~3 ✅ auth · 탐색 FR-4~9 ✅ rooms · 즐겨찾기 FR-10 ✅ favorites
- 상세/예약/동시성 FR-11~16 ✅ reservations · 예약관리 FR-17 ✅
- 알림 FR-18·18a ✅ notifications · 공유 FR-19 ✅ kakao-share
- 후기 FR-20·21 ✅ reviews · 제공자공간 FR-22 ✅ rooms
- 제공자예약 FR-23·24 ✅ · 챗봇 FR-25~30 ✅ chatbot · 운영 FR-31~33 ✅ admin
누락 FR 없음.

**Non-Functional Requirements Coverage:**
- 시간/타임존 ✅ core/time(UTC저장·KST판정). 성능 ✅ 서버집계 핀색·옵티미스틱 ≤100ms·
  기준 프로바이더 ≤2초·SSE. 보안 ✅ 키 백엔드격리·JWT·RBAC 최종강제·해싱.
- 신뢰성 ✅ UNIQUE+단일트랜잭션 all-or-nothing·상태머신 원자/멱등.
- 접근성 ✅ shadcn AA·색비의존·상태 매트릭스(EXPERIENCE.md 승계).

### Implementation Readiness Validation ✅

**Decision Completeness:** 핵심 결정 버전 명시(2026-06 검증). §8 미해결 8건 모두 처리
(확정 6 / Phase 0 스파이크 2 / Post-MVP 연기). **Structure Completeness:** 모노레포 전체
트리·도메인 모듈·경계·통합지점 정의. **Pattern Completeness:** 네이밍·구조·포맷·통신·
프로세스 패턴 + 금지 안티패턴 명시.

### Gap Analysis Results

**Critical Gaps:** 없음(구현 차단 항목 0).
**Important (구현 전 권장):**
- Phase 0 스파이크 3종(카카오맵 e2e+약관 적합성, SSE 3면, pgvector 이관) — 검증 후 진행.
- 프로바이더별 LLM 파라미터 비대칭 실측은 챗봇 구현 시 어댑터에서 확정.
**Nice-to-Have:** Redis 전환 기준·비용 알림 임계치 수치화는 운영 단계.

### Validation Issues Addressed

- 카카오 약관 적합성(차단 가능 리스크) → Phase 0 스파이크 ①에 명시적 배치, 부적합 시
  지도 제공자 대안 검토 경로 유지.
- 챗봇 ≤2초 SLA 편차 → 기준 프로바이더=OpenAI로 한정, 나머지 best-effort로 리스크 격리.

### Architecture Completeness Checklist

**Requirements Analysis**
- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**Architectural Decisions**
- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed

**Implementation Patterns**
- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**Project Structure**
- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION (16/16 체크, Critical Gap 0)
**Confidence Level:** high — 입력(PRD/UX/기술조사)이 견고하고 §8 미해결이 모두 처리됨.

**Key Strengths:**
- 동시성 불변식을 DB 제약으로 단순·견고하게 닫음(부분점유 0).
- 단일 OpenAPI 계약으로 3 서피스 타입 안전성 확보.
- 멀티 LLM 어댑터·시간 규약·상태머신 등 까다로운 횡단 관심사가 단일 출처로 고정됨.
- 비용(서비스 수=비용)을 의식한 단계적 챗봇 배포·DB 기반 refresh 무효화.

**Areas for Future Enhancement:**
- Redis 도입, 챗봇 물리 분리, 비번정책 NIST 정렬, 비연속 슬롯·EXCLUDE 제약(가변 슬롯).

### Implementation Handoff

**AI Agent Guidelines:**
- 본 문서의 결정·패턴·경계를 그대로 따른다(특히 와이어 snake_case·UTC/KST·동일 트랜잭션 재활성).
- 프론트는 packages/api-client SDK로만 호출. 멀티 LLM은 어댑터로만.
- 모든 아키텍처 질문은 이 문서를 1차 출처로 참조.

**First Implementation Priority:**
Phase 0 스파이크(3종) → 이후 Step 3의 스캐폴드 명령으로 모노레포·FastAPI·PostgreSQL 초기화.
