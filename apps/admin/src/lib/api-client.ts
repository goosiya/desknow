// admin 백엔드 호출 배선 (Story 1.9).
//
// 백엔드 호출은 **오직 @desknow/api-client SDK로만** 한다(직접 fetch 금지 — eslint 가드로 강제,
// AC2). 이 모듈이 SDK 클라이언트의 baseUrl을 앱 시작 시 1회 설정하고 SDK를 re-export하므로,
// 소비처는 `@/lib/api-client`에서 SDK 함수/타입을 가져온다.
import { configureApiClient } from "@desknow/api-client";

// baseUrl = 백엔드 **origin만**(경로 /api/v1/... 는 생성 SDK에 포함 → /api/v1 중복 금지, AC2).
// 미설정 시 로컬 백엔드 기본값. 환경별 값은 .env.local의 NEXT_PUBLIC_API_BASE_URL로 주입.
const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// credentials:"include" — 크로스오리진(localhost:3001→8000) httpOnly 인증 쿠키(1.8 로그인 쿠키)를
// 동봉한다(Story 8.1 AC1). 미설정 시 fetch 기본 same-origin이라 쿠키가 빠져 관리자 인증 호출
// (authMe·adminListAccounts)이 100% 401이 된다(web api-client와 동일 — 그대로 미러).
configureApiClient({ baseUrl, credentials: "include" });

// 생성 SDK 함수(authLogin·authRegister …)·타입(TokenResponse·ErrorResponse …)을 노출.
export * from "@desknow/api-client";
