// TanStack Query 클라이언트 (Story 3.2 — 서버 상태 단일 출처, architecture.md L91).
//
// 핀 데이터는 **느슨한 스냅샷**(신선도 정책 — availability-freshness-policy 메모): 실시간
// 푸시·서버 캐시 없이 GET 멱등 재조회로 갱신한다. 따라서 staleTime 을 짧게 두고
// refetchOnMount:'always' 로 **지도 화면 복귀 시 재조회**한다(유저가 상세에서 "찼음"을 본 뒤
// 지도로 돌아오면 그 핀이 회색으로 갱신). 예약-구동 변화는 4.9(예약 차감 연결) 후 완성된다.
//
// ⚠️ 전역 스피너 금지 — 로딩은 화면별 스켈레톤으로 표시한다(architecture.md L280).
import { QueryClient } from "@tanstack/react-query";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // 느슨한 스냅샷: 30초 동안만 fresh, 이후 stale → 복귀/포커스 시 재조회 대상.
        staleTime: 30_000,
        // 지도 화면으로 복귀(마운트)할 때마다 재조회한다(신선도 계약 — 3.2 소유).
        refetchOnMount: "always",
        retry: 1,
      },
    },
  });
}
