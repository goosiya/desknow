// secure-store 토큰 저장소 (Story 9.1 — AC1 · ADR-9.1-A).
//
// 모바일 인증은 웹과 갈린다: 웹(데스크톱)은 httpOnly 쿠키지만, 모바일은 로그인/refresh 응답 **본문**의
// 토큰(`TokenResponse`)을 저장하고 매 SDK 호출에 `Authorization: Bearer <access>` 헤더로 주입한다
// (api-client.ts 인터셉터). 백엔드는 이미 헤더를 쿠키보다 먼저 추출하므로 백엔드 무변경이다.
//
// 키는 **snake_case 와이어 그대로**(`access_token`/`refresh_token`) — camelCase 변환 금지.
//
// ⚠️ Expo Web 폴백(AC7): 이 버전의 `expo-secure-store`는 web에 네이티브 모듈이 없어 `*Async`가
//    `is not a function`으로 던진다(자동 localStorage 폴백 없음). 그래서 web(Platform.OS==='web')에선
//    `localStorage`를 직접 쓴다(네이티브는 SecureStore). E2E(Expo Web+Playwright) 세션주입 하니스가
//    이 저장소를 통해 토큰을 넣으므로 web 폴백이 필수다. (web=localStorage는 보안 경계가 낮지만, 웹
//    데스크톱 표면은 본래 쿠키 인증이고 이 RN-web은 E2E/미리보기 용도다.)
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

import type { TokenResponse } from "@/lib/api-client";

const ACCESS_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

const isWeb = Platform.OS === "web";

// 플랫폼 분기 저장 — web=localStorage, native=expo-secure-store. 실패는 graceful(크래시 금지).
async function putItem(key: string, value: string): Promise<void> {
  if (isWeb) {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // 저장 실패(프라이빗 모드 등) — 무시(다음 진입 재로그인 감수).
    }
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

async function readItem(key: string): Promise<string | null> {
  if (isWeb) {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }
  return SecureStore.getItemAsync(key);
}

async function removeItem(key: string): Promise<void> {
  if (isWeb) {
    try {
      window.localStorage.removeItem(key);
    } catch {
      // 무시.
    }
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

/** 로그인/refresh 응답 본문(TokenResponse)의 토큰 쌍을 저장한다. */
export async function setTokens(tokens: {
  access_token: string;
  refresh_token: string;
}): Promise<void> {
  // 두 키를 함께 기록한다(부분 저장 방지 — 인터셉터·refresh가 둘 다 의존).
  await Promise.all([
    putItem(ACCESS_KEY, tokens.access_token),
    putItem(REFRESH_KEY, tokens.refresh_token),
  ]);
}

/** 현재 access 토큰(없으면 null). request 인터셉터가 매 요청 최신값을 읽어 Bearer로 주입한다. */
export async function getAccessToken(): Promise<string | null> {
  return readItem(ACCESS_KEY);
}

/** 현재 refresh 토큰(없으면 null). 401 재시도(authRefresh)·로그아웃 본문 전송에 쓴다. */
export async function getRefreshToken(): Promise<string | null> {
  return readItem(REFRESH_KEY);
}

/** 저장된 토큰을 모두 비운다(로그아웃·refresh 실패 — 쿠키 없음, 명시 정리). */
export async function clearTokens(): Promise<void> {
  await Promise.all([removeItem(ACCESS_KEY), removeItem(REFRESH_KEY)]);
}

/** TokenResponse(여분 필드 포함)를 받아 토큰 쌍만 저장하는 편의 래퍼(useAuth가 사용). */
export async function saveTokenResponse(token: TokenResponse): Promise<void> {
  await setTokens({
    access_token: token.access_token,
    refresh_token: token.refresh_token,
  });
}
