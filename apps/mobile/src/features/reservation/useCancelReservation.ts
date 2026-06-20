// 예약 취소 뮤테이션 — 웹 reservation/useCancelReservation.ts 미러 (Story 9.2 — AC4).
//
// 성공 시 ① **["reservations"] 자기 목록**(취소된 예약이 다가오는→지난[취소됨] 섹션으로 즉시
// 이동) + ② **슬롯/핀 가용성**을 invalidate 한다. 취소는 점유 슬롯을 DELETE(재활성)하므로 그 룸의
// 슬롯 그리드·핀 색이 다시 가용을 반영해야 한다 → ["room", roomId, "slots"] **prefix**(취소 응답이
// 날짜를 안 주므로 룸 단위 prefix가 전 날짜 슬롯 쿼리를 덮는다) + ["rooms","availability"]. 광역
// ["rooms"] 무효화 **절대 금지**(룸 범위 prefix는 위반 아님). + ③ 도래 리마인드 배너 제거
// (["notifications"]).
//
// 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9). 인증 헤더(Bearer)는 인터셉터가 주입.
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { reservationsCancelReservation } from "@/lib/api-client";

import { NOTIFICATIONS_KEY } from "@/features/notifications/useNotifications";

import { isCancelWindowPassed } from "./errors";
import { RESERVATIONS_KEY } from "./useReservations";

/** 취소 변수 — 취소 대상 예약의 경로 파라미터(중첩 라우트 room_id + reservation_id). */
type CancelVars = { roomId: string; reservationId: string };

/**
 * 예약 취소 뮤테이션(AC4). 성공·클럭 스큐 409 모두 정확 키만 invalidate(광역 금지).
 *
 * - `mutationFn`: reservationsCancelReservation(SDK) — 경로 room_id·reservation_id. throwOnError
 *   로 비-2xx 를 throw → onError 분기. 취소 로직(상태 flip·슬롯 재활성·6h·소유권)은 전부 서버.
 * - `onSuccess`: ① ["reservations"](취소→지난 이동) + ② 슬롯/핀 재활성 반영 — ["room", roomId,
 *   "slots"] prefix + ["rooms","availability"] + ③ 도래 리마인드 제거 NOTIFICATIONS_KEY. 광역 금지.
 * - `onError`: **클럭 스큐로 409 CANCEL_WINDOW_PASSED** 면 목록을 재조회해 버튼 상태를 갱신한다
 *   (graceful — 막다른 화면·에러코드 노출 금지). 취소 실패라 슬롯은 무변화 → ["reservations"]만.
 * - 옵티미스틱 없음(서버 확정이 진실 — useCreateReservation 선례).
 */
export function useCancelReservation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ roomId, reservationId }: CancelVars) => {
      const { data } = await reservationsCancelReservation({
        path: { room_id: roomId, reservation_id: reservationId },
        throwOnError: true,
      });
      return data;
    },
    onSuccess: (_data, { roomId }) => {
      // ① 자기 목록 — 취소된 예약이 지난(취소됨) 섹션으로 즉시 이동.
      queryClient.invalidateQueries({ queryKey: RESERVATIONS_KEY });
      // ② 슬롯/핀 재활성 반영. ["room", roomId, "slots"] prefix가 그 룸 전 날짜 슬롯 쿼리를 덮는다
      //    (취소 응답에 날짜 없음) + 핀 색 집계. 광역 ["rooms"] 금지(룸 범위 prefix만).
      queryClient.invalidateQueries({ queryKey: ["room", roomId, "slots"] });
      queryClient.invalidateQueries({ queryKey: ["rooms", "availability"] });
      // ③ 도래 리마인드 배너 제거 — 취소된 예약 리마인드가 stale로 남지 않게 정확 키만 invalidate.
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
    onError: (error) => {
      // 클럭 스큐 409 → 목록 재조회로 버튼 상태 갱신(graceful). 정확 키만(광역 ["rooms"] 금지).
      if (isCancelWindowPassed(error)) {
        queryClient.invalidateQueries({ queryKey: RESERVATIONS_KEY });
      }
    },
  });
}
