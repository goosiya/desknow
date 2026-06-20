import { defineConfig } from '@hey-api/openapi-ts';

// DeskNow OpenAPI → TS SDK 생성 설정 (Story 1.9).
//
// - input:  백엔드가 오프라인 export한 계약 스냅샷(apps/api/scripts/export_openapi.py 산출).
// - output: src/generated(전부 커밋 — 드리프트 비교 기준).
// - plugins: @hey-api/client-fetch(전역 fetch 기반 → web·admin·RN 모두 호환). typescript(타입)·
//   sdk(함수) 플러그인은 기본 포함.
//
// ⚠️ snake_case 보존(AC1): camelCase 변환/네이밍 트랜스폼 플러그인을 **추가하지 않는다**.
//    hey-api는 기본적으로 스키마 필드명을 변환하지 않으므로 와이어 snake_case가 그대로 유지된다
//    (access_token·refresh_token·created_at·token_type 등). [architecture.md L286]
export default defineConfig({
  input: './openapi.json',
  output: 'src/generated',
  plugins: ['@hey-api/client-fetch'],
});
