// TanStack Query 클라이언트 — 웹 query-client.ts RN 포팅 (Story 9.1 — 서버 상태 단일 출처).
//
// 핀 데이터는 **느슨한 스냅샷**([[availability-freshness-policy]]): 실시간 푸시·서버 캐시 없이 GET
// 멱등 재조회로 갱신한다. staleTime을 짧게(30s) 두고 refetchOnMount:'always'로 화면 복귀 시 재조회,
// refetchOnReconnect로 재연결 시 자동 재조회한다(웹과 동일 신선도 계약).
//
// RN 차이: 네트워크 단절 감지는 `navigator.onLine`이 아니라 **NetInfo**다. react-query의 onlineManager를
// NetInfo에 연결해 단절 시 쿼리를 pause하고 재연결 시 자동 재개(refetchOnReconnect)한다. 이 배선은
// 모듈 로드 시 1회 수행한다(앱 전역 단일 효과).
import { QueryClient, onlineManager } from "@tanstack/react-query";
import NetInfo from "@react-native-community/netinfo";

// react-query 온라인 상태를 NetInfo에 연결(단절 시 pause·재연결 시 refetchOnReconnect). 1회만.
onlineManager.setEventListener((setOnline) => {
  return NetInfo.addEventListener((state) => {
    // isConnected가 명시적 false일 때만 단절로 본다(null=불명은 연결로 간주 — 콜드 깜빡임 방지).
    setOnline(state.isConnected !== false);
  });
});

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // 느슨한 스냅샷: 30초 동안만 fresh, 이후 stale → 복귀/재연결 시 재조회 대상.
        staleTime: 30_000,
        // 화면으로 복귀(마운트)할 때마다 재조회한다(신선도 계약 — 웹과 동일).
        refetchOnMount: "always",
        // 재연결 시 자동 재조회(단절→연결 — NetworkNotice "연결되면 다시 보여드릴게요" 충족).
        refetchOnReconnect: true,
        retry: 1,
      },
    },
  });
}
