// 후기 작성 뮤테이션 — 웹 reservation/useCreateReview.ts 미러 (Story 9.2 — AC5). 예약현황의 이용
// 완료 행에서 후기를 작성한다.
//
// useCreateReservation/useCancelReservation 선례 미러 — `useMutation` + onSuccess 에서 **정확
// 키만** invalidate(광역 금지). 옵티미스틱 없음(서버 확정이 진실).
//
// onSuccess: ① ["reservations"](예약현황 — has_review 갱신 → 행이 "후기 완료"로 전환) +
// ② ["rooms", roomId, "reviews"](룸 상세 후기 — 새 후기 즉시 반영). 광역 ["rooms"] 단일키 금지.
// onError: 409(이용 완료 안 됨/이미 작성)는 ["reservations"] 재조회로 게이팅 갱신(graceful).
//
// 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9). 인증 헤더(Bearer)는 인터셉터가 주입.
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { reviewsCreateReview } from "@/lib/api-client";

import { roomReviewsKey } from "@/features/detail/useRoomReviews";
import { isReservationNotCompleted, isReviewAlreadyExists } from "./errors";
import { RESERVATIONS_KEY } from "./useReservations";

/** 작성 변수 — 경로(예약 id) + 본문(별점·텍스트) + invalidate 대상 룸 id. */
type CreateReviewVars = {
  reservationId: string;
  roomId: string;
  rating: number;
  text: string;
};

/**
 * 후기 작성 뮤테이션(AC5). 성공 시 ["reservations"] + ["rooms", roomId, "reviews"] 정확 invalidate.
 *
 * - `mutationFn`: `reviewsCreateReview`(SDK) — 경로 reservation_id·본문 rating/text. throwOnError 로
 *   비-2xx 를 throw → onError 분기(409/422/기타).
 * - `onSuccess`: 예약현황(has_review 게이팅) + 룸 상세 후기 캐시 무효화(새 후기 반영). 광역 금지.
 * - `onError`: 409(이용 완료 안 됨/이미 작성)면 예약현황 재조회로 행 상태 갱신(graceful). 그 외는
 *   재조회 불요(컴포넌트가 friendly 카피로 안내).
 */
export function useCreateReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ reservationId, rating, text }: CreateReviewVars) => {
      const { data } = await reviewsCreateReview({
        path: { reservation_id: reservationId },
        body: { rating, text },
        throwOnError: true,
      });
      return data;
    },
    onSuccess: (_data, { roomId }) => {
      // ① 예약현황 — has_review 갱신(행이 "후기 완료"로 전환·폼 숨김).
      queryClient.invalidateQueries({ queryKey: RESERVATIONS_KEY });
      // ② 룸 상세 후기 — 새 후기 즉시 반영(["rooms", roomId, "reviews"] 정확 키).
      queryClient.invalidateQueries({ queryKey: roomReviewsKey(roomId) });
    },
    onError: (error) => {
      // 클럭 스큐(이용 완료 안 됨)·경합(이미 작성) 409 → 예약현황 재조회로 게이팅 갱신(graceful).
      if (isReservationNotCompleted(error) || isReviewAlreadyExists(error)) {
        queryClient.invalidateQueries({ queryKey: RESERVATIONS_KEY });
      }
    },
  });
}
