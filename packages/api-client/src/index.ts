// @desknow/api-client — 백엔드 OpenAPI 계약에서 생성한 타입 안전 TS SDK (Story 1.9).
//
// 세 프론트(web·admin·mobile)는 **오직 이 패키지를 통해서만** 백엔드를 호출한다(직접 fetch 금지,
// AC2). 생성 산출물(src/generated/**)은 형상관리(커밋)되며 드리프트 게이트의 비교 기준이다 —
// 직접 수정하지 말고 `pnpm --filter @desknow/api-client generate`로 재생성한다.
//
// ⚠️ 와이어 snake_case 보존(AC1): 생성 타입의 필드명은 access_token·refresh_token·created_at
//    등 백엔드 스키마 그대로다(camelCase 변환 없음).
import { client } from './generated/client.gen';

// 생성 SDK 함수(authRegister·authLogin·authRefresh·authLogout·authMe·healthHealth)와
// 전 타입(RegisterRequest·UserPublic·LoginRequest·TokenResponse·ErrorResponse·ErrorCode …)을 노출.
export * from './generated';

// 생성 fetch 클라이언트 인스턴스(인터셉터·헤더 등 고급 설정 지점). 각 표면이 필요 시 직접 접근.
export { client };

/**
 * 생성 SDK의 전역 fetch 클라이언트 baseUrl(+ 선택적 credentials)을 설정한다(각 표면이 시작 시 1회 호출).
 *
 * @param baseUrl 백엔드 **origin만**(예: `http://localhost:8000`). 경로(`/api/v1/...`)는
 *   openapi.json에 이미 포함되므로 baseUrl에 `/api/v1`을 붙이지 않는다(AC2 anti-pattern).
 * @param credentials fetch `credentials` 정책(선택). 웹은 `"include"`로 크로스오리진 httpOnly
 *   쿠키(1.8 로그인 쿠키)를 동봉해 인증 필요 SDK 호출이 세션을 전달한다(Story 3.7 AC5). 모바일은
 *   Bearer 헤더라 쿠키 정책이 불필요해 생략한다(미지정 시 fetch 기본 `same-origin`).
 */
export function configureApiClient({
  baseUrl,
  credentials,
}: {
  baseUrl: string;
  credentials?: RequestCredentials;
}): void {
  client.setConfig({ baseUrl, ...(credentials ? { credentials } : {}) });
}
