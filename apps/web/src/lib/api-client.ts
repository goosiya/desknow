// web 백엔드 호출 배선 (Story 1.9).
//
// 백엔드 호출은 **오직 @desknow/api-client SDK로만** 한다(직접 fetch 금지 — eslint 가드로 강제,
// AC2). 이 모듈이 SDK 클라이언트의 baseUrl을 앱 시작 시 1회 설정하고 SDK를 re-export하므로,
// 소비처는 `@/lib/api-client`에서 SDK 함수/타입을 가져온다.
import { configureApiClient } from "@desknow/api-client";

// baseUrl = 백엔드 **origin만**(경로 /api/v1/... 는 생성 SDK에 포함 → /api/v1 중복 금지, AC2).
// 미설정 시 로컬 백엔드 기본값. 환경별 값은 .env.local의 NEXT_PUBLIC_API_BASE_URL로 주입.
const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// credentials:"include" — 크로스오리진(localhost:3000→8000) httpOnly 인증 쿠키(1.8 로그인 쿠키)를
// 동봉한다(Story 3.7 AC5). 미설정 시 fetch 기본 same-origin이라 쿠키가 빠져 인증 필요 호출
// (favorites·authMe)이 401이 된다. 기존 공개 호출(rooms 등)은 쿠키 동봉돼도 무해.
configureApiClient({ baseUrl, credentials: "include" });

// 백엔드 origin 단일 출처(Story 7.4). SDK로 소비 불가한 챗봇 SSE 스트리밍(`features/chatbot/
// streamMessage.ts`의 raw fetch)이 동일 baseUrl을 재사용하도록 export한다 — `NEXT_PUBLIC_API_BASE_URL`
// 로직이 두 곳에서 갈라지는 드리프트를 막는다(SDK와 스트리밍이 같은 백엔드를 가리킴 보장).
export function getApiBaseUrl(): string {
  return baseUrl;
}

// 생성 SDK 함수(authLogin·authRegister …)·타입(TokenResponse·ErrorResponse …)을 노출.
export * from "@desknow/api-client";
