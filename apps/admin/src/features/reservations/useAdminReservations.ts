// 운영 확정 예약목록 쿼리 (Story 8.3, AC4). 백엔드 호출은 생성 SDK 경유만(1.9 가드).
//
// `GET /api/v1/admin/reservations`(adminListReservations)를 페이지 단위로 조회한다(confirmed-only).
// 키는 페이지를 포함해 페이지 전환 시 캐시가 분리된다. 인증/권한은 백엔드가 401/403으로 최종 강제.
// useAdminAccounts(8.1) 패턴을 그대로 미러한다.
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import {
  adminListReservations,
  type AdminReservationListResponse,
} from "@/lib/api-client";

/** 예약목록 페이지 크기(백엔드 상한 100 이내 — accounts와 동일). */
export const RESERVATIONS_PAGE_SIZE = 20;

export function useAdminReservations(page: number) {
  return useQuery<AdminReservationListResponse>({
    queryKey: ["admin", "reservations", { page }],
    queryFn: async () => {
      const { data } = await adminListReservations({
        query: { page, page_size: RESERVATIONS_PAGE_SIZE },
        throwOnError: true,
      });
      // throwOnError:true면 성공 시 data가 보장된다(에러는 throw → 쿼리 isError).
      return data as AdminReservationListResponse;
    },
    // 페이지 전환 시 이전 페이지를 유지해 표가 깜빡이지 않게 한다(데이터테이블 UX).
    placeholderData: keepPreviousData,
  });
}
