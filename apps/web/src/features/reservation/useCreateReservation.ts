// 즉시 예약 확정 뮤테이션 (Story 4.5 — AC4·AC5). 4.4 selection seam → 실제 예약 확정.
//
// `useToggleFavorite`(useFavorites.ts) canonical 미러 — `useMutation` + `onSuccess` 에서 **정확
// 키만** invalidate(광역 금지). 단 **옵티미스틱은 적용하지 않는다**: 예약은 서버 확정이 진실이라
// (충돌 가능) 응답 성공 후에만 성공 표시한다(favorites 토글의 onMutate/onError 롤백 패턴을 그대로
// 베끼지 말 것 — 잘못 잡힌 것처럼 보이면 안 됨, Dev Notes).
//
// 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드). credentials:"include" 는 api-client.ts
// 전역 설정이라 인증 쿠키가 자동 동봉된다(favorites 동형 — booker 세션).
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { reservationsCreateReservation } from "@/lib/api-client";
import { isSlotConflict } from "./errors";

/** 제출 변수 — 점유할 슬롯 시작시각(서버 UTC ISO) + invalidate 대상 날짜(슬롯 키). */
type CreateVars = { slotStarts: string[]; selectedDate: string };

/**
 * 즉시 예약 확정 뮤테이션(AC4·AC5). 성공 시 정확 키만 invalidate(광역 금지 — useFavorites 선례).
 *
 * - `mutationFn`: `reservationsCreateReservation`(SDK) — 경로 room_id·본문 slot_starts. throwOnError
 *   로 비-2xx 를 throw → `isError`(generic 실패 UX·재시도). 충돌(409)·404·5xx 모두 동일하게 throw.
 * - `onSuccess`: 슬롯 쿼리(`["room", roomId, "slots", date]`)와 핀 집계(`["rooms","availability"]`)만
 *   invalidate한다(점유 즉시 반영 경로 — 실제 차감 표시는 4.9 seam). `["rooms"]` 광역 무효화 금지.
 * - `onError`: **`SLOT_CONFLICT`(409)일 때만** 그날 슬롯 쿼리를 invalidate해 `SlotGrid`를 재조회한다
 *   (= 인접 빈 슬롯 즉시 재표시 — Story 4.6 AC3). generic 실패(404·5xx 등)는 재조회 불요(selection
 *   유지·재시도). 광역 invalidate 금지(정확 키만 — useFavorites/4.5 선례).
 * - 옵티미스틱 없음(서버 확정이 진실). 성공/실패 카피·selection 초기화는 컴포넌트가 소유한다.
 */
export function useCreateReservation(roomId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ slotStarts }: CreateVars) => {
      const { data } = await reservationsCreateReservation({
        path: { room_id: roomId },
        body: { slot_starts: slotStarts },
        throwOnError: true,
      });
      return data;
    },
    onSuccess: (_data, { selectedDate }) => {
      // 정확 키만 — 방금 점유한 슬롯의 날짜별 쿼리 + 핀 색 집계. 광역(["rooms"]) 금지(useFavorites 선례).
      queryClient.invalidateQueries({
        queryKey: ["room", roomId, "slots", selectedDate],
      });
      queryClient.invalidateQueries({ queryKey: ["rooms", "availability"] });
    },
    onError: (error, { selectedDate }) => {
      // Story 4.6 — SLOT_CONFLICT 일 때만 그날 슬롯을 재조회(인접 빈 슬롯 재표시). 정확 키만.
      // ⚠️ 4.9 경계: 4.9 차감 배선 전이라 재조회해도 방금 남이 잡은 슬롯이 여전히 available 로
      //    보일 수 있다(get_room_slots reserved_starts=frozenset()) — 데이터 정확도는 4.9 소관.
      if (isSlotConflict(error)) {
        queryClient.invalidateQueries({
          queryKey: ["room", roomId, "slots", selectedDate],
        });
      }
    },
  });
}
