---
baseline_commit: NO_VCS
---

# Story 1.9: OpenAPI→TS SDK 자동생성 파이프라인

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 개발자,
I want 백엔드 OpenAPI 스키마에서 타입 안전 TS SDK를 자동 생성해 공유 패키지(`packages/api-client`)로 두길,
so that 세 프론트(web·admin·mobile)가 단일 계약으로 백엔드를 호출하고 계약 변경이 컴파일 타임/CI에서 드러난다.

> **이 스토리는 Epic 1의 마지막 스토리다.** 1.1~1.8로 백엔드(인증/회원가입/RBAC + auth 엔드포인트 5종)와 세 프론트 셸이 섰다. 1.9는 그 둘을 **OpenAPI 계약**으로 잇는 "타입 배관"이다. **신규 백엔드 도메인 로직·신규 UI 화면은 만들지 않는다** — SDK 생성 파이프라인·소비 배선·드리프트 게이트만 세운다.

## Acceptance Criteria

> 출처: [epics.md#Story-1.9 L438-456]. 아래는 epic 원문 + dev가 충족을 *실증*할 검증 조건이다.

**AC1 — SDK 생성 (와이어 snake_case 보존)**
**Given** FastAPI가 노출하는 `openapi.json`(현재 auth 엔드포인트 register/login/refresh/logout/me 포함)
**When** `@hey-api/openapi-ts`로 SDK를 생성하면
**Then** `packages/api-client`에 타입 안전 클라이언트(타입 + SDK 함수 + fetch 클라이언트)가 생성되고, **와이어 전 구간 snake_case가 변환 없이 유지**된다(`access_token`·`refresh_token`·`created_at`·`token_type` 등이 camelCase로 바뀌지 않음 — 변환 플러그인 미사용).
- 검증: 생성 산출물에 `RegisterRequest`/`UserPublic`/`LoginRequest`/`TokenResponse` 등 백엔드 Pydantic 스키마에 대응하는 TS 타입이 존재하고, 필드명이 snake_case 그대로다.
- 검증: 생성 SDK가 **web(TS 5.9)·admin(TS 5.9)·mobile(TS ~6.0) 세 표면 모두에서 `tsc --noEmit` 통과**한다(1.2 이월 TS 버전 스큐 해소 — 아래 Dev Notes 참조).

**AC2 — SDK-only 호출 (직접 fetch 금지)**
**Given** 프론트 코드(web·admin·mobile)
**When** 백엔드를 호출하면
**Then** **오직 `@desknow/api-client` SDK를 통해서만** 호출하고 직접 `fetch`는 사용하지 않는다.
- 검증: 세 표면 각각에 SDK를 소비하는 배선(`src/lib/api-client.ts` — baseURL 설정 + SDK/클라이언트 re-export)이 존재하고 `tsc`로 컴파일된다(= SDK가 세 표면에서 실제 소비 가능함을 실증).
- 검증: lint 가드(직접 `fetch` 사용 시 에러)가 web·admin·mobile에 적용되어 있고, 현재 코드베이스는 위반 0건으로 lint 그린.

**AC3 — CI 드리프트 검사**
**Given** CI(또는 로컬 게이트)
**When** 백엔드 계약이 변경되었는데 `openapi.json`/SDK가 재생성되지 않으면
**Then** **drift 검사가 실패**해 계약-SDK 불일치를 차단한다.
- 검증(2계층, git 비의존 — 본 저장소는 git 미초기화):
  - **Layer A (백엔드/pytest):** 커밋된 `openapi.json` ≠ `app.openapi()` 현재 출력이면 pytest 실패.
  - **Layer B (프론트/turbo):** 커밋된 SDK ≠ `openapi.json`에서 재생성한 SDK이면 `turbo run test`(api-client `check:drift`) 실패.
- 실증: dev가 의도적으로 백엔드 스키마(예: 라우터 응답 필드 추가)를 바꾸고 재생성을 생략하면 위 게이트가 실패함을 1회 시연한 뒤 원복(드리프트 게이트가 실제로 무는지 증명).

## Tasks / Subtasks

- [x] **Task 1 — `packages/api-client` 패키지 골격 확립** (AC: 1)
  - [x] `packages/api-client/package.json` 작성: `@desknow/ui` 패턴을 미러(`main`/`types`/`exports` = `./src/index.ts`, `private`, `type: module`). scripts: `generate`, `check:drift`(= `test`로 배선), `check-types`(`tsc --noEmit`). dependencies: `@hey-api/client-fetch`(런타임, **정확 버전 핀**). devDependencies: `@hey-api/openapi-ts`(**정확 버전 핀**), `typescript: 5.9.2`(root/ui와 정렬), `@types/node: ^20`.
  - [x] `packages/api-client/tsconfig.json` 작성: `packages/ui/tsconfig.json`을 미러(strict·noEmit·`moduleResolution: bundler`·`target ES2022`·`types: ["node"]`). `include`에 `src/**/*.ts`·`openapi-ts.config.ts`·`scripts/**/*.mjs`(또는 별도 처리). 생성물(`src/generated/**`) 포함.
  - [x] placeholder 제거: `src/index.ts`의 `export {}`를 실제 re-export로 교체(Task 3에서 채움). `README.md`를 "생성됨" 상태로 갱신.
  - [x] pnpm 설치 후 "Ignored build scripts" 경고가 hey-api 패키지에서 나면 `pnpm-workspace.yaml` `allowBuilds`에 추가.

- [x] **Task 2 — 백엔드 `openapi.json` 오프라인 export** (AC: 1, 3)
  - [x] `apps/api/scripts/export_openapi.py` 작성: `from app.main import app` → `app.openapi()` → **결정적 직렬화**(`json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True)` + 끝 개행)로 `packages/api-client/openapi.json`에 기록. 출력 경로는 인자/기본값으로. `.env`·DB 불필요(import 안전성은 test_main이 보장 — Dev Notes 참조).
  - [x] (선택, 권장) `apps/api/app/main.py`에 `generate_unique_id_function` 추가로 operationId를 깔끔하게(예: `f"{route.tags[0]}_{route.name}"` → `auth_register`·`auth_login`…). **없으면** FastAPI 기본(`register_api_v1_auth_register_post`)이라 SDK 함수명이 장황. **지금이 계약 확정 시점**(소비처 0 → 안전). 변경 시 `openapi.json` 재생성 필수.
  - [x] `uv run python scripts/export_openapi.py ../../packages/api-client/openapi.json` 실행해 `openapi.json` 생성·커밋. auth 5종 경로(`/api/v1/auth/{register,login,refresh,logout,me}`) + health가 포함됐는지 확인.

- [x] **Task 3 — SDK 생성 + 패키지 export** (AC: 1)
  - [x] `packages/api-client/openapi-ts.config.ts` 작성: `import { defineConfig } from '@hey-api/openapi-ts'` → `input: './openapi.json'`, `output: 'src/generated'`, `plugins: ['@hey-api/client-fetch']`(typescript·sdk 플러그인은 기본 포함). **camelCase 변환/네이밍 트랜스폼 플러그인 미사용**(AC1 snake_case 보존).
  - [x] `pnpm --filter @desknow/api-client generate` (= `openapi-ts`) 실행 → `src/generated/`에 `types.gen.ts`·`sdk.gen.ts`·`client.gen.ts` 생성. **생성물 전부 커밋**(생성 산출물도 형상관리 — 드리프트 비교 기준).
  - [x] `src/index.ts`에서 생성 SDK·클라이언트를 re-export + `configureApiClient({ baseUrl }: { baseUrl: string })` 편의 헬퍼(생성 `client.setConfig({ baseUrl })` 위임) 제공.
  - [x] `pnpm --filter @desknow/api-client check-types` 그린 확인.

- [x] **Task 4 — 세 표면 SDK 소비 배선** (AC: 2)
  - [x] web: `apps/web/src/lib/api-client.ts` — `@desknow/api-client`에서 SDK·`configureApiClient` import, `baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'`로 1회 설정, SDK re-export. `apps/web/next.config.ts`의 `transpilePackages`에 `"@desknow/api-client"` 추가(1.2 이월). `.env.local` 예시/문서에 `NEXT_PUBLIC_API_BASE_URL` 추가.
  - [x] admin: `apps/admin/src/lib/api-client.ts` 동일 패턴. `apps/admin/next.config.ts` `transpilePackages`에 `"@desknow/api-client"` 추가. admin `package.json`에 `"@desknow/api-client": "workspace:*"` 추가.
  - [x] web `package.json`에 `"@desknow/api-client": "workspace:*"` 추가.
  - [x] mobile: `apps/mobile/src/lib/api-client.ts` 동일 패턴, `baseUrl = process.env.EXPO_PUBLIC_API_BASE_URL ?? '<LAN-IP>:8000'`. mobile `package.json`에 `"@desknow/api-client": "workspace:*"` 추가. **metro 확인**: `getDefaultConfig`가 워크스페이스 TS(@desknow/ui)를 이미 트랜스파일(1.6) → api-client도 자동 해소될 가능성 높으나, `pnpm --filter mobile check-types`로 실제 해소·컴파일 검증(실패 시 metro `watchFolders`/`resolver` 보강).
  - [x] **baseUrl = origin만**(예 `http://localhost:8000`). 경로(`/api/v1/auth/...`)는 openapi.json에 이미 포함 → baseUrl에 `/api/v1` 붙이지 말 것.
  - [x] 세 표면 `turbo run check-types` 그린 = 생성 SDK가 TS 5.9·~6.0 양쪽에서 컴파일(AC1 버전 스큐 해소 실증).

- [x] **Task 5 — AC2 직접-fetch 금지 lint 가드** (AC: 2)
  - [x] web/admin: `packages/config/eslint-preset.mjs`에 `no-restricted-globals`(또는 `no-restricted-syntax`)로 `fetch` 금지 룰 추가 + 메시지("백엔드 호출은 @desknow/api-client SDK로만 — 직접 fetch 금지 [architecture.md L290]"). 생성 클라이언트는 `packages/api-client`(preset 미적용)에 있으므로 무영향.
  - [x] mobile: `apps/mobile`의 eslint(`eslint-config-expo`) 설정에 동등한 fetch 금지 룰 추가.
  - [x] 현재 코드 위반 0건 → `turbo run lint` 그린 유지. **주석으로 E7 SSE 예외 예고**(챗봇 스트리밍은 fetch 기반 → E7에서 해당 모듈만 allowlist).
  - [x] (검증) 임시 `fetch('...')` 파일로 lint가 실제 에러내는지 1회 확인 후 제거.

- [x] **Task 6 — 드리프트 게이트(2계층, git 비의존)** (AC: 3)
  - [x] **Layer A (pytest):** `apps/api/tests/test_openapi_export.py` — `app.openapi()`를 export 스크립트와 **동일 직렬화**로 만든 문자열이, 저장소 루트 기준 `packages/api-client/openapi.json` 파일 내용과 일치하는지 단언(불일치 → 실패, 메시지에 "export_openapi.py 재실행 필요"). 경로는 `Path(__file__).resolve().parents[N]`로 루트 도출(cwd=apps/api). DB·env 불필요(import 안전).
  - [x] **Layer B (turbo):** `packages/api-client/scripts/check-drift.mjs` — `openapi.json`에서 SDK를 **임시 디렉터리**에 재생성(`@hey-api/openapi-ts` 프로그래매틱 API 또는 CLI `--output <tmp>`) 후 `src/generated`와 **재귀 파일 비교**. 차이 있으면 비0 종료 + 메시지("pnpm --filter @desknow/api-client generate 재실행 필요"). api-client `package.json`의 `test` 스크립트를 `node scripts/check-drift.mjs`로 설정 → 기존 `turbo run test` 게이트가 SDK 드리프트를 자동 차단.
  - [x] **결정성 주의:** Layer B는 생성기 버전에 민감 → `@hey-api/openapi-ts`·`@hey-api/client-fetch`를 **caret 없이 정확 버전 핀**(환경 간 생성물 차이 = 거짓 드리프트 방지). Layer A는 `sort_keys=True`로 dict 순서 비결정성 제거.
  - [x] **실증:** 백엔드 스키마를 일시 변경(예: `UserPublic`에 더미 필드) → `uv run pytest`가 Layer A로 실패함을 확인 → 원복. `openapi.json`을 일시 변경 → `turbo run test`가 Layer B로 실패함을 확인 → 원복. (게이트가 실제로 무는지 증명, completion note에 기록.)

- [x] **Task 7 — CI 바인딩(`.github/workflows/ci.yml`)** (AC: 3) — *아래 "CI 범위 결정" 참조*
  - [x] 검증된 게이트를 호출하는 최소 워크플로 작성: checkout → setup-node + pnpm(install) → setup-python + uv(install) → ① JS 게이트 `turbo run lint check-types test`(Layer B 포함) ② 백엔드 게이트 `cd apps/api && uv run ruff check . && uv run mypy && uv run pytest`(Layer A 포함). DB 의존 통합테스트는 라이브 DB 부재로 현행처럼 skip 유지.
  - [x] 파일 상단 주석: 본 저장소는 현재 git 미초기화 → 워크플로는 **러너 미실행 상태로 작성만**(드리프트 *명령*은 로컬에서 실증 완료). git/원격 구성(배포 준비) 시점에 활성화.

- [x] **Task 8 — 게이트 회귀 확인** (AC: 1, 2, 3)
  - [x] `turbo run lint check-types test` 전 패키지 그린.
  - [x] `cd apps/api && uv run ruff check . && uv run mypy && uv run pytest` 그린(기존 138 passed·3 skipped 무회귀 + 신규 Layer A 테스트 추가).
  - [x] sprint-status.yaml `1-9-...: review`로 갱신(dev-story 완료 시).

## Dev Notes

### 핵심 라이브러리 — 라이브러리 선택 고정 (재발명/오선택 금지)

- **생성기: `@hey-api/openapi-ts`** — epic·아키텍처가 **명시 지정**. orval/openapi-generator/swagger-codegen 등 **대안 검토 금지**. [Source: epics.md L447·123, architecture.md L115·173·386]
- **버전(2026-06 기준):** 최신 안정 `@hey-api/openapi-ts` ≈ **0.98.x**(설치 시 최신 재확인 — 프로젝트 규약 "init 시점 최신"). `@hey-api/client-fetch`도 최신. **둘 다 정확 버전 핀**(`-E`, caret 금지) — 생성기 버전이 출력을 결정하므로 범위 버전은 드리프트 게이트 거짓양성 유발. [Source: web research heyapi.dev/openapi-ts/get-started — `npm install @hey-api/openapi-ts -D -E`]
- **설정 형식(현행):**
  ```ts
  // packages/api-client/openapi-ts.config.ts
  import { defineConfig } from '@hey-api/openapi-ts';
  export default defineConfig({
    input: './openapi.json',
    output: 'src/generated',
    plugins: ['@hey-api/client-fetch'], // typescript(타입)·sdk(함수)는 기본 플러그인
  });
  ```
  [Source: web research heyapi.dev/openapi-ts/configuration·clients/fetch]
- **런타임 baseURL:** 생성 `client`에 `client.setConfig({ baseUrl })` 또는 `createClient({ baseUrl })`. 각 표면이 시작 시 1회 설정. [Source: web research heyapi.dev/openapi-ts/clients/fetch]
- **fetch 클라이언트 선택 이유:** `@hey-api/client-fetch`는 전역 `fetch` 기반 → **web(Next 16/Node·Edge·브라우저)·RN(Expo 56) 모두 호환**(axios 등 불필요). RN에 node-전용 API 비의존. [Source: architecture.md L182 RN, web research clients]

### snake_case 보존 (AC1 핵심 불변식)

- 아키텍처 **Enforcement**: "와이어 전 구간 snake_case 유지(camelCase 변환 레이어 금지)" + "API 응답 객체 필드는 snake_case 그대로 사용(SDK 생성형)". [Source: architecture.md L286·246·240·448]
- hey-api는 기본적으로 스키마 필드명을 **변환하지 않음** → 별도 네이밍/casing 트랜스폼 플러그인을 **추가하지 않으면** snake_case가 그대로 유지됨. **트랜스폼을 켜지 말 것.**
- 백엔드 응답 스키마는 이미 snake_case(`access_token`·`refresh_token`·`token_type`·`created_at`·`is_active`). [Source: apps/api/app/auth/schemas.py L87-95·59-72]

### 백엔드 openapi.json 오프라인 생성 — 가능 근거 (재발명 금지)

- `app.main` import는 **`.env`·DB 없이 안전**: `get_settings()`/`verify_db_connection()`는 `lifespan`(startup)에서만 호출되고 import 시점엔 실행 안 됨. `test_main.py`가 이미 모듈 레벨 `TestClient(app)`로 이를 실증. → export 스크립트는 `from app.main import app; app.openapi()`만 하면 됨(JWT/DB env 불요). [Source: apps/api/app/main.py L28-42·82-88, apps/api/tests/test_main.py L8-20]
- **operationId 정리(선택, 권장):** 현재 auth 라우터는 명시 `operation_id` 없음 → FastAPI 기본 operationId가 장황(`register_api_v1_auth_register_post`)해 SDK 함수명이 보기 나쁨. `app = FastAPI(..., generate_unique_id_function=custom)`로 `f"{route.tags[0]}_{route.name}"`(→ `auth_register`) 권장. **소비처 0인 지금이 계약 확정 적기.** 변경하면 `openapi.json` 재생성 필요. [Source: apps/api/app/auth/router.py L42·77-162]
- export 직렬화는 **결정적**으로(`sort_keys=True`·고정 indent·끝 개행) — Layer A 드리프트 비교 안정성.

### 드리프트 게이트 설계 — git 미사용 환경 (재발명/오설계 방지)

- **⚠️ 본 저장소는 git 저장소가 아니다**(`.git` 부재, 확인됨). 따라서 흔한 `git diff --exit-code` 기반 드리프트 검사를 **쓸 수 없다.** → **파일 비교 방식**으로 구현(임시 재생성 후 diff).
- **2계층 분리**(전체 계약 체인 = 코드→json→SDK):
  - Layer A: 코드→`openapi.json`. 백엔드 pytest에 편입(이미 도는 `uv run pytest` 게이트가 잡음). Python 토큰체인만 필요.
  - Layer B: `openapi.json`→SDK. 프론트 turbo `test`에 편입(Node만 필요, Python 불요). api-client `test` 스크립트 = `check-drift.mjs`.
- 두 계층이 함께 있어야 **부분 전파**(코드만 바꾸고 json 미갱신, 또는 json만 바꾸고 SDK 미갱신)를 모두 차단. AC3 충족.

### TS 버전 스큐 해소 (1.2 이월 항목 — 본 스토리가 책임 회수)

- **사실:** mobile `typescript ~6.0.3`(create-expo-app 핀) vs root/web/admin/ui `5.9.2`/`^5`. [Source: apps/mobile/package.json L36, package.json L15, apps/web/package.json L34, packages/ui/package.json L17]
- **1.2 코드리뷰가 명시 위임:** "packages/api-client 생성 타입이 web·mobile에 공유되는 Story 1.9 시점에 … 버전 정렬 검토." [Source: deferred-work.md L9]
- **해소 방침(강제 업그레이드 아님):** 생성 SDK는 표준 TS라 5.9·6.0 양쪽 호환이 기대됨. **검증으로 닫는다** — Task 4의 세 표면 `check-types`(web=5.9, mobile=~6.0)가 동일 생성 SDK를 컴파일 → 통과하면 스큐 무해 확정. **실패 시에만** 정렬(api-client tsconfig `target`/`lib` 보수화 또는 버전 핀 조정). Expo가 핀한 TS 6.0.3을 임의 강등하지 말 것(Expo 도구체인 안정성 우선). completion note에 검증 결과 기록.

### 패키지/구조 규약 (오위치 방지)

- 생성 SDK 위치: **`packages/api-client`**(아키텍처 디렉터리 트리 명시). [Source: architecture.md L339·114·252]
- 공유 패키지 export 패턴: **raw `.ts` 소스 export**(빌드 산출물 아님) — `@desknow/ui`가 확립한 패턴(`main`/`types`=`./src/index.ts`, 소비처가 transpile). api-client도 동일하게. [Source: packages/ui/package.json L6-10]
- 소비 transpile: web/admin `next.config.ts` `transpilePackages`에 `@desknow/api-client` 추가(현재 `["@desknow/ui"]`만). mobile은 metro `getDefaultConfig`가 워크스페이스 TS 자동 처리(1.6 패턴) — 단 실제 해소는 `check-types`로 검증. [Source: apps/web/next.config.ts L6, apps/admin/next.config.ts L6, apps/mobile/metro.config.js, deferred-work.md L10]
- TS 변수/함수 camelCase·파일 `kebab-case.ts`(유틸). 단 **API 응답 필드는 snake_case 유지**. [Source: architecture.md L245-246]

### 스코프 경계 (스코프 크리프 방지 — 명시적 IN/OUT)

**IN(이 스토리):** SDK 생성 파이프라인 · `openapi.json` export · 세 표면 SDK 소비 배선(baseURL 설정 + 컴파일 실증) · 직접-fetch lint 가드 · 2계층 드리프트 게이트 · CI 워크플로 파일.

**OUT(이 스토리 아님):**
- **로그인/회원가입 UI 폼·실제 데이터 호출** → 후속 소비 스토리/기능 에픽(1.7 노트 "프론트폼은 1.9 이후 이관" = 1.9 *이후*). 본 스토리는 SDK를 *호출 가능*하게만 만들고 화면은 안 만든다.
- **refresh 401 자동재발급 인터셉터의 완전 구현** → 토큰 저장(web 쿠키 / RN SecureStore)이 표면별이라 실제 인증 소비 스토리에서. 본 스토리는 클라이언트 설정 *지점*(`configureApiClient`·인터셉터 훅 자리)만 제공. (백엔드 refresh 자체는 1.8에 이미 존재.) [Source: epics.md L426-428, 1-8 story]
- **TanStack Query(서버 상태)** → 실제 데이터 화면 스토리(E3+). [Source: architecture.md L183·270]
- **쿠키 cross-origin/SameSite 실브라우저 검증** → 배포 준비(1.8 defer). [Source: deferred-work.md L66·77·78]
- **DB 의존 통합테스트 CI 실행** → 라이브 DB 구성(배포). 현행처럼 skip 유지.

> **✅ 스코프 확정(KTH 2026-06-15):** ① **파이프라인만** — refresh 인터셉터 완전구현·로그인 UI는 후속 소비 스토리(본 스토리는 클라이언트 설정 지점만). ② **CI = 얇은 바인딩** — 드리프트 명령을 1차 산출물로 실증 + `ci.yml`은 호출 바인딩만(러너 미실행). 두 결정 모두 위 IN/OUT·Task 7과 일치(추가 변경 없음).

### 이전 스토리 인텔리전스 (1.8 + 누적)

- **auth 라우터가 OpenAPI 계약을 의도적으로 노출:** `responses={401/409/422: ErrorResponse}`로 에러 계약을, `response_model`로 응답 타입을 노출 — "1.9 SDK가 `detail.code` 타입을 생성하도록" 명시 설계됨. → 생성 SDK에 `ErrorResponse`/`ErrorCode` 타입이 나와야 정상(나오면 AC1 충실). [Source: apps/api/app/auth/router.py L9-14·81·91·111·152]
- **에러 포맷:** `{ detail: { code, message } }` 표준. 프론트 api-client 에러 매핑은 향후 소비 스토리. [Source: architecture.md L260·382, apps/api/app/core/errors.py]
- **게이트 베이스라인(무회귀 기준):** 1.8 종료 시 `ruff·mypy·pytest 138 passed·3 skipped`. 프론트 `turbo run lint check-types test` 그린(ui vitest parity 포함). [Source: sprint-status.yaml L38, MEMORY 1.8]
- **백엔드는 pnpm 워크스페이스 밖(uv)** — JS↔Python 결합은 OpenAPI 스키마로만. export 스크립트가 그 유일 경계. [Source: pnpm-workspace.yaml L1-3, architecture.md L112·193·304]
- **test_main 불변식:** 모듈 레벨 `TestClient(app)`(lifespan 미실행) 패턴 — 신규 테스트도 이 import-안전성을 깨지 말 것. [Source: apps/api/tests/test_main.py L8-20]

### 테스트 표준

- 백엔드: pytest, `tests/` 미러 구조, import 안전(.env/DB 없이 수집). 신규 `test_openapi_export.py`는 DB 무관(Layer A). [Source: architecture.md L253, apps/api/tests/conftest.py]
- 프론트: vitest co-located(`*.test.ts`), 모노레포 러너는 1.6에서 확립. Layer B 드리프트는 vitest가 아닌 node 스크립트(`check-drift.mjs`)로 `test`에 배선. [Source: packages/ui/vitest.config.ts]
- 게이트 명령: `turbo run lint check-types test`(JS) + `uv run ruff check . && uv run mypy && uv run pytest`(api). [Source: package.json L5-9, apps/api/pyproject.toml L48-73]

### Anti-Patterns (금지)

- camelCase 변환 레이어/플러그인 추가(snake_case 깨짐). [architecture.md L286]
- 직접 `fetch`로 백엔드 호출(SDK 우회). [architecture.md L290·354]
- baseUrl에 `/api/v1` 중복(경로가 이미 포함).
- 생성 산출물을 `.gitignore`/미커밋 처리(드리프트 비교 기준이 사라짐 — 반드시 커밋).
- hey-api 생성기 버전을 caret 범위로(거짓 드리프트).
- mobile TS 6.0.3을 임의 강등(Expo 도구체인 위험).

### CI 범위 결정 (Task 7)

AC3는 "Given CI"라 하지만 본 저장소는 git/CI 미구성. **테스트 가능한 실질 산출물 = 드리프트 *명령*(로컬 실증 가능)**. 따라서: ① 드리프트 명령을 1차 산출물로 완성·실증(Task 6) ② `.github/workflows/ci.yml`은 그 명령을 호출하는 얇은 바인딩으로 작성(파일은 존재하나 러너 미실행 — git/원격 구성 시 활성). 이로써 AC3가 "검증 가능한 실제 명령"으로 충족되고 CI 아티팩트도 존재. **단 CI를 전 게이트(DB 통합 포함)로 확장할지는 배포 준비 관심사** — Task 7은 드리프트+기존 정적 게이트로 한정. (열린 질문 #2 참조.)

## Project Structure Notes

신규/수정 파일(예상):

```
packages/api-client/
├── package.json              # 수정: deps·scripts(generate/check:drift=test/check-types)
├── tsconfig.json             # 신규: ui 미러
├── openapi-ts.config.ts      # 신규: hey-api 설정
├── openapi.json              # 신규(커밋): 백엔드 계약 스냅샷 (export 스크립트 산출)
├── README.md                 # 수정: "생성됨" 상태
├── scripts/check-drift.mjs   # 신규: Layer B 드리프트(임시 재생성+파일 비교)
└── src/
    ├── index.ts              # 수정: export {} → 생성 SDK re-export + configureApiClient
    └── generated/            # 신규(커밋): types.gen.ts·sdk.gen.ts·client.gen.ts

apps/api/
├── scripts/export_openapi.py # 신규: app.openapi() → packages/api-client/openapi.json
├── app/main.py               # (선택)수정: generate_unique_id_function
└── tests/test_openapi_export.py # 신규: Layer A 드리프트(pytest)

apps/web/  · apps/admin/
├── src/lib/api-client.ts     # 신규: baseURL 설정 + SDK 소비 배선
├── next.config.ts            # 수정: transpilePackages += @desknow/api-client
└── package.json              # 수정: deps += @desknow/api-client(workspace:*)

apps/mobile/
├── src/lib/api-client.ts     # 신규: baseURL(EXPO_PUBLIC_*) + SDK 소비
├── package.json              # 수정: deps += @desknow/api-client; eslint fetch 룰
└── (metro.config.js 검증; 필요 시 보강)

packages/config/eslint-preset.mjs  # 수정: web/admin 직접-fetch 금지 룰

.github/workflows/ci.yml      # 신규: 게이트 호출 바인딩(러너 미실행 작성)
```

**구조 정합/변이:**
- `packages/api-client`는 아키텍처 디렉터리 트리와 정확히 일치(변이 없음). [architecture.md L339]
- `apps/api/scripts/`는 신규 디렉터리(현재 없음) — Python 보조 스크립트의 자연스러운 위치.
- 생성 산출물을 **커밋**하는 것은 의도(드리프트 비교 기준). lint는 `extend-exclude`/eslint ignore로 생성물 제외 검토(churn 방지) — 단 drift 비교엔 영향 없음.

## References

- [Source: epics.md#Story-1.9 L438-456] — AC 원문(SDK 생성·snake_case·SDK-only·드리프트)
- [Source: epics.md#Epic-1 L201-204·244] — 에픽 목표("세 클라이언트가 OpenAPI 생성 SDK로 연결"), enabler
- [Source: epics.md L106·108·123] — @hey-api/openapi-ts·packages/api-client·"직접 fetch 금지"
- [Source: architecture.md L115·128] — SQLModel→Pydantic→OpenAPI→TS 풀체인
- [Source: architecture.md L173·386-387] — 통합 포인트(openapi.json→@hey-api→api-client, "CI 드리프트 검사")
- [Source: architecture.md L240·246·286] — 와이어 snake_case 불변식
- [Source: architecture.md L290·354] — "SDK로만 호출, 직접 fetch 금지" 경계
- [Source: architecture.md L339·114·252] — packages/api-client 위치·공유 패키지 구조
- [Source: deferred-work.md L9-10] — TS 버전 스큐·transpilePackages(1.9 트리거)
- [Source: deferred-work.md L66·77-78] — 쿠키 cross-origin/SameSite/Secure(1.9/배포 트리거, OUT)
- [Source: apps/api/app/main.py L28-42·53-58·82-88] — lifespan(import 안전)·FastAPI app·auth 라우터 배선
- [Source: apps/api/app/auth/router.py L9-14·42·77-162] — auth 5종 엔드포인트·OpenAPI 계약 노출(responses/response_model)·operationId 부재
- [Source: apps/api/app/auth/schemas.py L35-108] — Register/UserPublic/Login/Token/Refresh/Logout 스키마(snake_case)
- [Source: apps/api/tests/test_main.py L8-20] — 모듈 레벨 TestClient import-안전 패턴(export 근거)
- [Source: apps/api/pyproject.toml L28-73] — dev 게이트(ruff/mypy/pytest), uv 관리
- [Source: packages/ui/package.json·tsconfig.json·vitest.config.ts] — 공유 패키지 미러 템플릿
- [Source: apps/web/next.config.ts, apps/mobile/metro.config.js] — transpile/metro 소비 패턴(1.6)
- [Source: apps/mobile/package.json L36, package.json L15] — TS 버전 스큐 사실
- [Source: web research] heyapi.dev get-started·configuration·clients/fetch (2026-06, v0.98.x): `defineConfig`·`input/output/plugins`·`@hey-api/client-fetch`·`client.setConfig({baseUrl})`·`-E` 정확버전 설치
- [Source: 환경] git 미초기화 확인 → 드리프트는 파일 비교 방식 필수

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Claude Opus 4.8, 1M context) — dev-story 워크플로.

### Debug Log References

- `uv run python scripts/export_openapi.py` → `packages/api-client/openapi.json` (auth 5종 + health, operationId `auth_register`·`auth_login`·… 확인).
- `pnpm --filter @desknow/api-client generate` → `src/generated/` 4 entry(types/sdk/client + 번들 런타임), snake_case 필드 보존 확인.
- 게이트 실측(최종): JS `turbo run lint check-types test` = 10/10 성공. API `ruff`(All checks passed) · `mypy`(Success, 19 files) · `pytest`(139 passed · 3 skipped).

### Completion Notes List

**AC 충족 요약**
- **AC1 (SDK 생성·snake_case 보존):** `@hey-api/openapi-ts@0.98.2`로 `packages/api-client/src/generated` 생성. `RegisterRequest`/`UserPublic`/`LoginRequest`/`TokenResponse`/`ErrorResponse`/`ErrorCode` 등 백엔드 스키마 대응 TS 타입 존재, 필드명 snake_case 그대로(`access_token`·`refresh_token`·`token_type`·`created_at`·`is_active`) — 변환 플러그인 미사용. 세 표면 `tsc --noEmit` 통과(web/admin TS 5.9 + mobile TS ~6.0) → **1.2 TS 버전 스큐 무해 확정**(동일 생성 SDK가 양쪽 컴파일).
- **AC2 (SDK-only 호출):** 세 표면에 `src/lib/api-client.ts`(baseUrl 1회 설정 + SDK re-export) 배선, 모두 컴파일. 직접 `fetch` 금지 lint 가드를 web/admin(공유 preset)·mobile(eslint.config.js)에 추가, 현재 위반 0건(lint 그린). 임시 probe 파일로 가드가 실제 에러냄을 web(global + `globalThis.fetch`)·mobile에서 1회 확인 후 제거.
- **AC3 (드리프트 검사·2계층):** Layer A(pytest `test_openapi_export`) = `app.openapi()` ↔ 커밋 `openapi.json` 비교. Layer B(`check-drift.mjs`, api-client `test`) = `openapi.json` 재생성 SDK ↔ 커밋 `src/generated` 재귀 비교. **실증 완료:** ① 백엔드 `UserPublic`에 더미 필드 추가 → Layer A 실패 확인 → 원복·재그린. ② `openapi.json`에 더미 프로퍼티 주입 → Layer B(`turbo`/`test`) 실패(`types.gen.ts` 불일치, exit 1) 확인 → export 재실행으로 원복·재그린.

**주요 구현 결정 / 스토리 대비 적응(근거)**
- **`@hey-api/client-fetch` 런타임 패키지 미설치(스토리 대비 변경):** init 시점 최신(`@hey-api/openapi-ts@0.98.2`) 확인 결과, 별도 `@hey-api/client-fetch` 패키지는 **v0.73.0부터 deprecated — fetch 클라이언트가 openapi-ts에 번들**됨(npm deprecation 메시지). 생성물도 외부 `@hey-api/*` import 없이 `src/generated/client/`·`core/`로 런타임을 **번들**한다(검증: 생성 디렉터리 내 외부 import 0건). 따라서 런타임 의존성으로 추가하지 않고, 생성기 `@hey-api/openapi-ts`만 **정확 버전 핀(0.98.2)** devDep으로 둔다. 스토리 Dev Notes의 "설치 시 최신 재확인 — init 시점 최신" 규약에 따른 적응이며, 핵심 의무(생성기·fetch 클라이언트·snake_case 보존)는 그대로 충족.
- **api-client `tsconfig` lib에 DOM 추가:** ui 미러(ES2022)는 생성 fetch 클라이언트가 요구하는 `BodyInit`·`Response` 등 앰비언트 타입이 없어 자체 `check-types` 실패 → `lib: ["ES2022","DOM","DOM.Iterable"]`로 보강(소비 표면은 자체 lib로 해소, 패키지 자체 타입체크용). 생성기/하네스 표준 요건.
- **operationId 정리:** `main.py`에 `generate_unique_id_function`(`{tag}_{name}`) 추가 → `auth_register` 등(SDK 함수 `authRegister`). 소비처 0인 지금 계약 확정. `route.tags`는 이 FastAPI 버전이 cast 헬퍼로 설정해 mypy 미인식 → `getattr` 안전 접근으로 mypy strict 그린.
- **baseUrl = origin만:** 기존 `.env*`의 `...:8000/api/v1` 값을 **origin만**(`...:8000`)으로 정정(경로는 SDK 포함 → `/api/v1` 중복 방지, AC2 anti-pattern). web/admin `.env.local`·mobile `.env`/`.env.example` 갱신.
- **CI:** git 미초기화라 `.github/workflows/ci.yml`은 검증된 게이트를 호출하는 **얇은 바인딩**으로 작성(러너 미실행). 드리프트 *명령*은 로컬 실증 완료.
- **무회귀:** 백엔드 pytest 138 → **139 passed**(신규 Layer A +1) · 3 skipped 유지. `test_main` 모듈 레벨 `TestClient` import-안전 불변식 보존. `pnpm-workspace.yaml allowBuilds`는 hey-api가 빌드 스크립트 경고를 내지 않아 변경 없음.

**OUT(후속 처리):** 로그인/가입 UI 폼·실데이터 호출·refresh 401 자동재발급 인터셉터 완전구현·TanStack Query·쿠키 cross-origin 실브라우저 검증·DB 통합테스트 CI 실행 — 전부 스토리 스코프 밖(후속 소비 스토리/배포 준비).

### File List

**신규**
- `packages/api-client/tsconfig.json`
- `packages/api-client/openapi-ts.config.ts`
- `packages/api-client/openapi.json` (커밋 — 계약 스냅샷)
- `packages/api-client/scripts/check-drift.mjs` (Layer B)
- `packages/api-client/src/generated/**` (커밋 — `index.ts`·`types.gen.ts`·`sdk.gen.ts`·`client.gen.ts` + `client/**`·`core/**` 번들 런타임, 총 16파일)
- `apps/api/scripts/export_openapi.py`
- `apps/api/tests/test_openapi_export.py` (Layer A)
- `apps/web/src/lib/api-client.ts`
- `apps/admin/src/lib/api-client.ts`
- `apps/mobile/src/lib/api-client.ts`
- `.github/workflows/ci.yml`

**수정**
- `packages/api-client/package.json` (scripts·@hey-api/openapi-ts devDep 정확 핀)
- `packages/api-client/src/index.ts` (생성 SDK re-export + `configureApiClient`)
- `packages/api-client/README.md` ("생성됨" 상태)
- `apps/api/app/main.py` (`generate_unique_id_function`)
- `apps/web/next.config.ts` · `apps/admin/next.config.ts` (`transpilePackages += @desknow/api-client`)
- `apps/web/package.json` · `apps/admin/package.json` · `apps/mobile/package.json` (`@desknow/api-client: workspace:*`)
- `apps/web/.env.local` · `apps/admin/.env.local` · `apps/mobile/.env` · `apps/mobile/.env.example` (baseUrl origin만)
- `packages/config/eslint-preset.mjs` (web/admin 직접-fetch 금지 룰)
- `apps/mobile/eslint.config.js` (mobile 직접-fetch 금지 룰)
- `pnpm-lock.yaml` (의존성 반영)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (1-9 → in-progress → review)

### Change Log

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-06-15 | Story 1.9 구현 완료(8 Task): OpenAPI→TS SDK 파이프라인 — `@hey-api/openapi-ts@0.98.2` 생성(snake_case 보존)·세 표면 SDK 소비 배선·직접-fetch lint 가드·2계층 드리프트 게이트(실증)·CI 바인딩. 게이트: JS 10/10, API ruff/mypy 그린·pytest 139 passed·3 skipped. Status → review. | Amelia (dev-story, Opus 4.8) |

## Review Findings

> 코드리뷰 2026-06-15 (3-레이어 적대적: Blind Hunter·Edge Case Hunter·Acceptance Auditor). AC1~3 전부 PASS·안티패턴 0·스코프크리프 0(Auditor가 게이트 직접 실행 실증: pytest 139/3·drift 2계층 그린·check-types 5/5·lint 3/3). 0 decision-needed · 3 patch · 7 defer · 12 dismissed.

**Patch (수정 권장 — 모호성 없음):**

- [x] [Review][Patch] `openapi.json` CRLF 비결정성 — 커밋 파일이 CRLF(`{\r\n`, 실증)인데 `serialize_openapi()`는 LF 출력. Layer A 테스트가 `read_text` 개행 정규화로 통과해 "바이트 단위 일치" 주장이 크로스플랫폼에서 거짓. Linux 재생성 시 전라인 변경 churn. **적용:** `write_text(..., newline="\n")` + `openapi.json` LF 재생성(`{\n` 확인). [apps/api/scripts/export_openapi.py:48] (edge, 실증)
- [x] [Review][Patch] 직접-fetch lint 가드가 RN `global.fetch` 미차단 — selector 정규식 `/^(window|globalThis|self)$/`에 RN 표준 전역 객체 `global` 누락 → `global.fetch(url)`이 모바일에서 무검출 통과. **적용:** 정규식에 `global` 추가. 임시 프로브로 `global.fetch`가 이제 에러남을 실증. [packages/config/eslint-preset.mjs:25, apps/mobile/eslint.config.js:21] (blind+edge+auditor)
- [x] [Review][Patch] CI api 잡 `uv sync`가 `--frozen` 미사용 — JS 잡은 `pnpm install --frozen-lockfile`인데 api 잡은 bare `uv sync`(`uv.lock` 존재) → 락 미강제 비대칭. **적용:** `uv sync --frozen`. [.github/workflows/ci.yml:47] (edge)

**게이트 재검증(패치 후):** Layer A `pytest` 139 passed·3 skipped · Layer B drift 클린 · `turbo run lint` 3/3 성공. 무회귀 확인.

**Defer (실재하나 후속/스코프외/잠재 — deferred-work.md 이관):**

- [x] [Review][Defer] operationId `{tag}_{name}` 충돌 위험(향후 라우터) [apps/api/app/main.py:67] — deferred, 현재 충돌 0(검증)·미래 라우터 잠재
- [x] [Review][Defer] web/.env.local 잔존 Phase-0 Kakao JS 키·스파이크 변수 [apps/web/.env.local] — deferred, pre-existing(Story 1.3 유래, 1.9 무관)
- [x] [Review][Defer] prod env 누락 시 localhost:8000 무음 폴백·빈문자열/trailing-slash baseUrl 미검증 [apps/*/src/lib/api-client.ts] — deferred, 배포준비(명시 OUT 스코프)
- [x] [Review][Defer] configureApiClient import 부작용·`sideEffects` 미선언·`@desknow/api-client` 직접 import 시 설정 우회 [packages/api-client/src/index.ts] — deferred, 아키텍처 하드닝(현재 동작 정상)
- [x] [Review][Defer] check-drift.mjs가 `src/generated` 부재 시 ENOENT 크래시(명확 메시지 부재) [packages/api-client/scripts/check-drift.mjs:30] — deferred, 방어적 UX(저가치)
- [x] [Review][Defer] turbo `test` 태스크가 생성기 버전을 input 미포함 → 생성기 범프 시 stale 캐시가 드리프트 은폐 가능 [turbo.json] — deferred, 정확핀으로 완화
- [x] [Review][Defer] env 산출물(`.env.local`/`mobile/.env`)이 gitignore 대상이라 File List 추적 불가 + 신규 export 스크립트/테스트가 mypy `files` 스코프 밖 [.gitignore, apps/api/pyproject.toml] — deferred, git 미초기화로 현시점 무영향
