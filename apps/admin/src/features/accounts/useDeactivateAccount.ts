// 계정 비활성 뮤테이션 (Story 8.2, AC1·2·4). 백엔드 호출은 생성 SDK 경유만(1.9 가드).
//
// `POST /api/v1/admin/accounts/{account_id}/deactivate`(adminDeactivateAccount)를 호출한다.
// 비활성은 **단방향**이라 재활성 뮤테이션은 없다(KTH 2026-06-18). 캐스케이드(provider 룸
// 비활성)·멱등·원자성은 전부 백엔드가 보장하므로 여기선 호출 + 캐시 무효화만 한다.
// 성공 시 ["admin","accounts"] prefix를 invalidate해 목록·상태 셀이 새로고침 없이 갱신된다.
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { adminDeactivateAccount } from "@/lib/api-client";

/**
 * 계정 비활성 뮤테이션. throwOnError로 비-2xx를 throw → 컴포넌트가 isError로 에러 카피 표시.
 *
 * - `mutationFn`: 8.2 adminDeactivateAccount(SDK) — 경로 account_id. 멱등/캐스케이드는 서버.
 * - `onSuccess`: ["admin","accounts"] prefix invalidate(모든 페이지 캐시) → 상태 셀 즉시 갱신.
 *   404(ACCOUNT_NOT_FOUND)/네트워크 실패는 throw되어 컴포넌트의 onError에서 카피로 처리한다.
 */
export function useDeactivateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (accountId: string) => {
      const { data } = await adminDeactivateAccount({
        path: { account_id: accountId },
        throwOnError: true,
      });
      return data;
    },
    onSuccess: () => {
      // 페이지별로 키가 분리되므로(useAdminAccounts) prefix로 전 페이지 캐시를 무효화한다.
      queryClient.invalidateQueries({ queryKey: ["admin", "accounts"] });
    },
  });
}
