// TanStack Query 클라이언트 (Story 8.1 — admin 서버 상태 단일 출처, architecture.md L91).
//
// web(apps/web/src/lib/query-client.ts) 미러. 관리자 화면은 지도 핀 같은 느슨한 스냅샷이 아니라
// 운영 데이터(계정목록 등)라, 화면 진입 시 신선 조회를 선호한다(staleTime 짧게). 전역 스피너
// 금지 — 로딩은 화면별 스켈레톤으로 표시한다(architecture.md L280).
import { QueryClient } from "@tanstack/react-query";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
      },
    },
  });
}
