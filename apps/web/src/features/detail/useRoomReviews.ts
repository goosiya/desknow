// 룸 상세 후기 목록 쿼리 (Story 5.5 — AC4). 룸 상세 3차 섹션이 후기를 한 곳에서 본다.
//
// ⚠️ 키 = ["rooms", roomId, "reviews"]. 작성 성공(useCreateReview)이 이 키를 invalidate해 새 후기가
//    상세에 즉시 반영된다. ["rooms", roomId](useRoomSummary 단일 요약)와 **다른 키**라 후기 작성이
//    요약 배지를 불필요하게 재조회시키지 않는다(정확 키 — useFavorites/4.x 선례).
//
// 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드). reviewsListRoomReviews는 공개·무인증
// 엔드포인트라 쿠키 불요. roomId 가 빈 문자열이면 비활성(상세 미선택).
import { useInfiniteQuery } from "@tanstack/react-query";

import { reviewsListRoomReviews } from "@/lib/api-client";
import {
  INITIAL_CURSOR,
  flattenPages,
  getNextCursorParam,
} from "@/lib/pagination";

/** 룸 후기 캐시 키 — 단일 요약(["rooms", roomId])과 분리(후기 작성 invalidate 대상). */
export function roomReviewsKey(roomId: string) {
  return ["rooms", roomId, "reviews"] as const;
}

/**
 * 룸 후기 목록(공개·무인증). ReviewSection 이 소비. 최신순은 서버가 보장(created_at desc).
 *
 * **F 무한스크롤:** 커서 페이징(`useInfiniteQuery`) — `select` 평탄화로 `data`는 기존처럼
 * `ReviewListItem[]`. provider 후기 화면(useProviderReviews)도 같은 엔드포인트를 쓴다.
 */
export function useRoomReviews(roomId: string) {
  return useInfiniteQuery({
    queryKey: roomReviewsKey(roomId),
    enabled: roomId !== "",
    initialPageParam: INITIAL_CURSOR,
    queryFn: async ({ pageParam }) => {
      const { data } = await reviewsListRoomReviews({
        path: { room_id: roomId },
        query: { cursor: pageParam ?? undefined },
        throwOnError: true,
      });
      return data ?? { items: [], next_cursor: null };
    },
    getNextPageParam: getNextCursorParam,
    select: flattenPages,
  });
}
