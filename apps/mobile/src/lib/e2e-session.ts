// E2E 세션주입 하니스 (Story 9.1 — AC7 · ADR-9.1-C).
//
// 프로젝트엔 자동화 E2E 계층이 없다("E2E"=Playwright MCP 수동 검증). 로그인 UI를 거치지 않고
// 인증 화면을 구동하기 위해, Expo Web 전역에 토큰 주입 훅 `window.__DESKNOW_E2E__`를 노출한다.
//
// ⚠️ 프로덕션 미포함 보장(AC7): 이 모듈은 `_layout.tsx`에서 **`__DEV__ && EXPO_PUBLIC_E2E_ENABLED`
//    게이트 안에서만 require**된다. 프로덕션 빌드(`!__DEV__`)에선 그 분기가 빌드타임 상수
//    dead-code 제거로 사라져 이 모듈 자체가 번들에 포함되지 않는다(따라서 아래 `__DESKNOW_E2E__`·
//    `injectSession` 심볼도 프로덕션 번들에서 grep으로 부재 확인 가능). 9.2/9.3가 재사용한다.
import type { QueryClient } from "@tanstack/react-query";

import { SESSION_QUERY_KEY } from "@/features/auth/useSession";
import { clearTokens, setTokens } from "@/lib/session-store";

/** Playwright가 호출하는 전역 브릿지 — 시드 계정 토큰을 주입/제거한다. */
type E2EBridge = {
  /** 토큰 쌍을 secure-store(web=localStorage 폴백)에 넣고 세션 쿼리를 무효화한다(즉시 로그인 반영). */
  injectSession: (accessToken: string, refreshToken: string) => Promise<void>;
  /** 토큰을 비우고 세션 쿼리를 무효화한다(미로그인 상태 복귀). */
  clearSession: () => Promise<void>;
};

/**
 * Expo Web 전역에 `window.__DESKNOW_E2E__`를 설치한다(개발·게이트 ON일 때만 호출됨).
 * 네이티브(window 부재)에선 no-op이다.
 */
export function installE2ESessionHarness(queryClient: QueryClient): void {
  if (typeof window === "undefined") return;
  const bridge: E2EBridge = {
    async injectSession(accessToken, refreshToken) {
      await setTokens({ access_token: accessToken, refresh_token: refreshToken });
      await queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
    },
    async clearSession() {
      await clearTokens();
      await queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
    },
  };
  (window as unknown as { __DESKNOW_E2E__?: E2EBridge }).__DESKNOW_E2E__ = bridge;
}
