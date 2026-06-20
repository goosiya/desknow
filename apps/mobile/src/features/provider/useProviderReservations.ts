// provider 예약자 현황 + 예약 거부 훅 — 웹 useProviderReservations.ts 미러 (Story 9.3 — AC1·AC2).
//
// 백엔드 호출은 생성 SDK 경유만(1.9 가드). 거부는 백엔드가 슬롯 재활성 + 예약자 통지를 동일
// 트랜잭션 원자 처리한다([[langgraph-failed-turn-input-rollback]]와 무관 — 6.2 거절 원자성).
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import {
  reservationsListProviderReservations,
  reservationsRejectReservation,
} from "@/lib/api-client";
import {
  INITIAL_CURSOR,
  flattenPages,
  getNextCursorParam,
} from "@/lib/pagination";

export const PROVIDER_RESERVATIONS_QUERY_KEY = ["provider", "reservations"];

/**
 * 내 스터디룸의 확정 예약 목록(예약자는 익명 라벨 — [[anonymous-booker-label-no-display-name]]).
 *
 * 커서 페이징(`useInfiniteQuery`) — `select` 평탄화로 `data`는 `ProviderReservationItem[]`.
 * FlatList `onEndReached`는 `fetchNextPage`·`hasNextPage`로 구동(웹 sentinel의 RN 등가).
 */
export function useProviderReservations() {
  return useInfiniteQuery({
    queryKey: PROVIDER_RESERVATIONS_QUERY_KEY,
    initialPageParam: INITIAL_CURSOR,
    queryFn: async ({ pageParam }) => {
      const { data } = await reservationsListProviderReservations({
        query: { cursor: pageParam ?? undefined },
        throwOnError: true,
      });
      return data ?? { items: [], next_cursor: null };
    },
    getNextPageParam: getNextCursorParam,
    select: flattenPages,
  });
}

/** 예약 거부 — 성공 시 목록 무효화(슬롯 재활성·예약자 통지는 백엔드가 처리). 옵티미스틱 없음. */
export function useRejectReservation() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (reservationId: string) => {
      const { response } = await reservationsRejectReservation({
        path: { reservation_id: reservationId },
      });
      if (!response?.ok) throw new Error("예약 거부에 실패했어요.");
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: PROVIDER_RESERVATIONS_QUERY_KEY,
      });
    },
  });
}
