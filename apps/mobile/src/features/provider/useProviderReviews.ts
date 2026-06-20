// provider 후기 보기 + 답글 훅 — 웹 useProviderReviews.ts 미러 (Story 9.3 — AC3).
//
// 후기는 룸 단위라 내 룸(useMyRoom)의 room_id로 조회한다. 답글은 reviewsCreateReply. 백엔드 호출은
// 생성 SDK 경유만(1.9 가드). 후기 키는 룸 상세(useRoomReviews)와 **동일**(roomReviewsKey)이라
// 캐시를 공유한다 — 답글 작성 후 양쪽(상세·provider)이 정확 invalidate된다.
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import { reviewsCreateReply, reviewsListRoomReviews } from "@/lib/api-client";
import { roomReviewsKey } from "@/features/detail/useRoomReviews";
import {
  INITIAL_CURSOR,
  flattenPages,
  getNextCursorParam,
} from "@/lib/pagination";

import { useMyRoom } from "./useProviderRoom";

/**
 * 내 룸 후기 목록(내 룸이 없으면 비활성). 내 room_id도 함께 노출(답글 무효화 키용).
 *
 * 커서 페이징(`useInfiniteQuery`) — `select` 평탄화로 `reviews`는 평탄 배열. 룸 상세 후기
 * (useRoomReviews)와 같은 키(roomReviewsKey)·엔드포인트라 캐시를 공유한다.
 */
export function useProviderReviews() {
  const myRoom = useMyRoom();
  const roomId = myRoom.data?.room_id ?? "";
  const reviews = useInfiniteQuery({
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

/** 후기 답글 작성 — 성공 시 해당 룸 후기 목록 무효화(답글이 붙은 채 갱신). 옵티미스틱 없음. */
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
      await queryClient.invalidateQueries({ queryKey: roomReviewsKey(roomId) });
    },
  });
}
