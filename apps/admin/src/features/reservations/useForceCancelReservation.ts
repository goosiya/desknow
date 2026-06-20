// 예약 임의취소 뮤테이션 (Story 8.3, AC1·2·4). 백엔드 호출은 생성 SDK 경유만(1.9 가드).
//
// `POST /api/v1/admin/reservations/{reservation_id}/cancel`(adminCancelReservation)를 호출한다.
// 슬롯 재활성·예약자 통지·멱등·원자성(단일 트랜잭션)은 전부 백엔드가 보장하므로 여기선 호출 +
// 캐시 무효화만 한다. 성공 시 ["admin","reservations"] prefix를 invalidate해 목록이 갱신되어
// 취소된 예약이 confirmed 목록에서 사라진다(useDeactivateAccount 8.2 미러).
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { adminCancelReservation } from "@/lib/api-client";

/**
 * 예약 임의취소 뮤테이션. throwOnError로 비-2xx를 throw → 컴포넌트가 isError로 에러 카피 표시.
 *
 * - `mutationFn`: adminCancelReservation(SDK) — 경로 reservation_id. 멱등/슬롯 재활성/통지는 서버.
 * - `onSuccess`: ["admin","reservations"] prefix invalidate(모든 페이지 캐시) → 목록 즉시 갱신.
 *   404(RESERVATION_NOT_FOUND: 목록과 경합으로 이미 취소됨)/네트워크 실패는 throw되어 컴포넌트의
 *   onError에서 카피로 처리한다.
 */
export function useForceCancelReservation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (reservationId: string) => {
      const { data } = await adminCancelReservation({
        path: { reservation_id: reservationId },
        throwOnError: true,
      });
      return data;
    },
    onSuccess: () => {
      // 페이지별로 키가 분리되므로(useAdminReservations) prefix로 전 페이지 캐시를 무효화한다.
      queryClient.invalidateQueries({ queryKey: ["admin", "reservations"] });
    },
  });
}
