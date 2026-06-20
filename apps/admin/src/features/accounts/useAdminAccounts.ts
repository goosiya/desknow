// 운영 계정목록 쿼리 (Story 8.1, AC4). 백엔드 호출은 생성 SDK 경유만(1.9 가드).
//
// `GET /api/v1/admin/accounts`(adminListAccounts)를 페이지 단위로 조회한다. 키는 페이지를
// 포함해 페이지 전환 시 캐시가 분리된다. 인증/권한은 백엔드가 401/403으로 최종 강제한다.
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import {
  adminListAccounts,
  type AdminAccountListResponse,
} from "@/lib/api-client";

/** 계정목록 페이지 크기(백엔드 상한 100 이내). */
export const ACCOUNTS_PAGE_SIZE = 20;

export function useAdminAccounts(page: number) {
  return useQuery<AdminAccountListResponse>({
    queryKey: ["admin", "accounts", { page }],
    queryFn: async () => {
      const { data } = await adminListAccounts({
        query: { page, page_size: ACCOUNTS_PAGE_SIZE },
        throwOnError: true,
      });
      // throwOnError:true면 성공 시 data가 보장된다(에러는 throw → 쿼리 isError).
      return data as AdminAccountListResponse;
    },
    // 페이지 전환 시 이전 페이지를 유지해 표가 깜빡이지 않게 한다(데이터테이블 UX).
    placeholderData: keepPreviousData,
  });
}
