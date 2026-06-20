// 본인 예약현황 목록 쿼리 (Story 4.8 — AC1·AC4). 로그인한 예약자의 예약을 한 곳에서 본다.
//
// ⚠️ 키 프리픽스 = ["reservations"] (최상위 독립). ["rooms", ...] 프리픽스 **금지** — useFavorites
//    선례(deferred L153 정신): 지도/시트가 ["rooms",...]를 쓰므로 광역 무효화가 그 캐시까지 휩쓴다.
//    예약현황은 독립 키 + 정확 키 invalidate 만 한다(취소 onSuccess 도 ["reservations"] 만).
//
// 미로그인 시 비활성(useSession `!!user` — useFavorites 선례). 백엔드 호출은 생성 SDK 경유만
// (직접 fetch 금지 — 1.9 가드). credentials:"include" 는 api-client 전역(booker 세션).
import { useInfiniteQuery } from "@tanstack/react-query";

import { reservationsListReservations } from "@/lib/api-client";
import { useSession } from "@/features/auth/useSession";
import {
  INITIAL_CURSOR,
  flattenPages,
  getNextCursorParam,
} from "@/lib/pagination";

/** 예약현황 캐시 키 — 최상위 독립(절대 ["rooms"] 프리픽스 금지, useFavorites 선례). */
export const RESERVATIONS_KEY = ["reservations"] as const;

/**
 * 본인 예약 목록(미로그인 시 비활성 — enabled). ReservationList 가 소비.
 *
 * **F 무한스크롤:** 커서 페이징(`useInfiniteQuery`). `select`로 페이지들을 평탄화해 `data`를
 * 기존처럼 `ReservationListItem[]`로 노출한다(소비 컴포넌트 무변경) — 추가로 `fetchNextPage`·
 * `hasNextPage`·`isFetchingNextPage`로 하단 sentinel을 구동한다.
 */
export function useReservations() {
  const { data: user } = useSession();
  return useInfiniteQuery({
    queryKey: RESERVATIONS_KEY,
    enabled: !!user,
    initialPageParam: INITIAL_CURSOR,
    queryFn: async ({ pageParam }) => {
      const { data } = await reservationsListReservations({
        query: { cursor: pageParam ?? undefined },
        throwOnError: true,
      });
      return data ?? { items: [], next_cursor: null };
    },
    getNextPageParam: getNextCursorParam,
    select: flattenPages,
  });
}
