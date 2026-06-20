# @desknow/api-client

백엔드 OpenAPI 스키마에서 **자동 생성**되는 타입 안전 TypeScript SDK 패키지 (Story 1.9).

세 프론트(web·admin·mobile)는 **오직 이 패키지를 통해서만** 백엔드를 호출한다(직접 `fetch` 금지 — lint 가드로 강제).

## 구성

- `openapi.json` — 백엔드 OpenAPI 계약 스냅샷(커밋). `apps/api/scripts/export_openapi.py`가 `app.openapi()`를 결정적으로 직렬화해 산출.
- `openapi-ts.config.ts` — `@hey-api/openapi-ts` 생성 설정(fetch 클라이언트, snake_case 보존).
- `src/generated/**` — 생성 산출물(커밋, 직접 수정 금지). 타입(`types.gen.ts`)·SDK 함수(`sdk.gen.ts`)·fetch 클라이언트(`client.gen.ts` + 번들 런타임).
- `src/index.ts` — 생성 SDK·클라이언트 re-export + `configureApiClient({ baseUrl })` 헬퍼.
- `scripts/check-drift.mjs` — Layer B 드리프트 게이트(`openapi.json` ↔ `src/generated` 일치 검사, `test` 스크립트에 배선).

## 재생성 (계약 변경 시)

```bash
# 1) 백엔드 계약 export (apps/api 에서)
uv run python scripts/export_openapi.py

# 2) SDK 재생성 (repo 루트에서)
pnpm --filter @desknow/api-client generate
```

생성기 버전(`@hey-api/openapi-ts`·번들 fetch 클라이언트)은 **정확 버전 핀**이다 — 범위 버전은 환경 간 생성물 차이로 드리프트 게이트 거짓양성을 유발한다.

## 소비

```ts
import { configureApiClient, authLogin, type TokenResponse } from '@desknow/api-client';

configureApiClient({ baseUrl: 'http://localhost:8000' }); // origin만 — 경로는 SDK가 포함
const { data } = await authLogin({ body: { email, password } });
```
