// 단일 룸 신선 요약 훅 — 웹 useRoomSummary.ts 복사 (Story 9.1 — 바텀시트 콘텐츠, AC3).
//
// `GET /rooms/{room_id}`를 가져온다. query-client 기본 refetchOnMount:'always'라 **시트를 열 때마다
// 신선** 조회한다 → 예약 가능 배지가 동결 스냅샷이 아니라 신선 remaining_slots가 된다(신선도 계약).
// roomId가 빈 문자열이면 비활성(시트 미선택).
import { useQuery } from "@tanstack/react-query";

import { roomsGetRoom } from "@/lib/api-client";

export function useRoomSummary(roomId: string) {
  return useQuery({
    queryKey: ["rooms", roomId],
    // 시트가 닫혀 선택이 없으면(roomId="") 조회하지 않는다(불필요 요청·UUID 미일치 422 회피).
    enabled: roomId !== "",
    queryFn: async () => {
      const { data } = await roomsGetRoom({
        path: { room_id: roomId },
        throwOnError: true,
      });
      return data;
    },
  });
}
