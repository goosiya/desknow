// 세션 슬라이딩 연장 + 만료 안내/리다이렉트 — 웹 SessionKeeper.tsx RN 포팅 (Story 9.1 code-review 회수).
// 전역 1회 마운트(_layout.tsx, QueryClientProvider 안). null 렌더.
//
// access 토큰은 기본 15분이지만 **앱을 쓰는 동안 계속 연장**한다 — 앱이 포그라운드(AppState active)인
// 동안 10분 주기로 토큰 쌍을 회전 발급한다(refresh 토큰 본문 전송 → secure-store 재기록). 백그라운드면
// 갱신하지 않아(setInterval throttle + active 게이트) 유휴 세션은 자연 만료된다. 만료(authMe 401 →
// 세션 null 전이)되면 "로그인 시간이 만료됐어요" 안내와 함께 /login 으로 보낸다. **수동 로그아웃은
// 만료가 아니므로** 제외한다(sessionExpiry 플래그).
//
// 웹과의 차이(ADR-9.1-A 결): ① 활동 신호 = 웹은 pointer/keydown/scroll, RN은 앱 포그라운드(active)를
// 활동 프록시로 쓴다 ② 갱신 = 웹은 쿠키(`body:{}`)지만 모바일은 단일-flight refreshSession(refresh
// 토큰 본문·api-client 인터셉터와 회전 합류) ③ 유휴 만료 즉시 감지 = 웹 refetchOnWindowFocus 대신
// 포그라운드 복귀 시 ["auth","me"] invalidate(모바일 query-client 는 focusManager 미배선).
import { useEffect, useRef } from "react";
import { AppState } from "react-native";
import { router, usePathname, type Href } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";

import { refreshSession } from "@/lib/api-client";

import { consumeManualLogout } from "./sessionExpiry";
import { SESSION_QUERY_KEY, useSession } from "./useSession";

// 활동(포그라운드) 시 갱신 최소 간격(< access TTL 15분 — 활동 중엔 만료 전 항상 1회 이상 갱신).
const REFRESH_INTERVAL_MS = 10 * 60_000;

export function SessionKeeper() {
  const { data: user } = useSession();
  const queryClient = useQueryClient();
  const pathname = usePathname();
  // 직전 로그인 여부 — 로그인→null **전이**에서만 만료 처리(최초 미로그인엔 발화 금지).
  const wasAuthed = useRef(false);

  // 슬라이딩 갱신 — 로그인 상태 + 앱 포그라운드(active)일 때만 tick 마다 토큰을 회전한다. 갱신 실패
  // (refresh 토큰 만료 등)는 무시 — 다음 authMe 401 전이에서 만료 처리가 이어진다. refreshSession 은
  // api-client 인터셉터와 동일한 단일-flight 라 401 재시도와 회전이 겹쳐도 1회로 합쳐진다.
  useEffect(() => {
    if (!user) return;
    const id = setInterval(() => {
      if (AppState.currentState !== "active") return; // 유휴/백그라운드 → 갱신 안 함(자연 만료 허용)
      void refreshSession().catch(() => {});
    }, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [user]);

  // 유휴 만료 즉시 감지 — 앱 포그라운드 복귀 시 ["auth","me"]를 재조회한다(웹 refetchOnWindowFocus 등가).
  // 만료됐으면 authMe 401 → (인터셉터 refresh 실패 → 토큰 정리) → null 전이로 아래 만료 effect 발화.
  useEffect(() => {
    if (!user) return;
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        void queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
      }
    });
    return () => sub.remove();
  }, [user, queryClient]);

  // 만료 감지 — 로그인→null 전이. 수동 로그아웃이면 skip(만료 아님), 아니면 안내+로그인 이동.
  useEffect(() => {
    if (user) {
      wasAuthed.current = true;
      return;
    }
    if (user === null && wasAuthed.current) {
      wasAuthed.current = false;
      if (consumeManualLogout()) return; // 직접 로그아웃 → 만료 안내/리다이렉트 없음
      // 만료 → 로그인 화면으로(현재 경로를 next 로, 단 /login 자기 자신은 제외).
      const onLogin = pathname?.startsWith("/login");
      const next =
        pathname && !onLogin ? `&next=${encodeURIComponent(pathname)}` : "";
      if (!onLogin) router.replace(`/login?expired=1${next}` as Href);
    }
  }, [user, pathname]);

  return null;
}
