// provider 후기 보기 + 답글 훅 (idea.md L39 — 후기 보기 및 답글 달기).
//
// 후기는 룸 단위라 내 룸(useMyRoom)의 room_id 로 조회한다. 답글은 reviewsCreateReply. 백엔드 호출은
// 생성 SDK 경유만(1.9 가드).
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import { reviewsCreateReply, reviewsListRoomReviews } from "@/lib/api-client";
import {
  INITIAL_CURSOR,
  flattenPages,
  getNextCursorParam,
} from "@/lib/pagination";

import { useMyRoom } from "./useProviderRoom";

export const providerReviewsKey = (roomId: string) => ["rooms", roomId, "reviews"];

/**
 * 내 룸 후기 목록(내 룸이 없으면 비활성). 내 room_id 도 함께 노출(답글 무효화 키용).
 *
 * **F 무한스크롤:** 커서 페이징(`useInfiniteQuery`) — `select` 평탄화로 `reviews`는 평탄 배열.
 * 하단 sentinel 구동용 `fetchNextPage`·`hasNextPage`·`isFetchingNextPage`를 함께 노출한다.
 * 룸 상세 후기(useRoomReviews)와 같은 키·엔드포인트라 캐시를 공유한다.
 */
export function useProviderReviews() {
  const myRoom = useMyRoom();
  const roomId = myRoom.data?.room_id ?? "";
  const reviews = useInfiniteQuery({
    queryKey: providerReviewsKey(roomId),
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
  return {
    roomId,
    hasRoom: myRoom.isSuccess && myRoom.data !== null,
    isLoading: myRoom.isLoading || reviews.isLoading,
    isError: myRoom.isError || reviews.isError,
    reviews: reviews.data ?? [],
    fetchNextPage: reviews.fetchNextPage,
    hasNextPage: reviews.hasNextPage,
    isFetchingNextPage: reviews.isFetchingNextPage,
  };
}

/** 후기 답글 작성 — 성공 시 해당 룸 후기 목록 무효화(답글이 붙은 채 갱신). */
export function useReplyToReview(roomId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, Error, { reviewId: string; text: string }>({
    mutationFn: async ({ reviewId, text }) => {
      const { response } = await reviewsCreateReply({
        path: { review_id: reviewId },
        body: { text },
      });
      if (!response?.ok) throw new Error("답글 작성에 실패했어요.");
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: providerReviewsKey(roomId) });
    },
  });
}
