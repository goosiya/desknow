// 단일 룸 신선 요약 훅 (Story 3.3 — 바텀시트 콘텐츠, AC1·AC4).
//
// `GET /rooms/{room_id}` 를 TanStack Query 로 가져온다. 키 `['rooms', roomId]`(단일)는
// `['rooms','map']`/`['rooms','availability']`(3.2 집계)와 별개다. query-client 기본
// refetchOnMount:'always' 라 **시트를 열 때마다 신선** 조회한다 → 예약 가능 배지가 핀 탭 시점의
// 동결 스냅샷이 아니라 신선 remaining_slots 가 된다(3.2 stale 배지 회수, AC4).
//
// 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드). throwOnError:true 로 비-2xx 를
// throw → react-query isError(시트 에러 분기 AC5). roomId 가 빈 문자열이면 비활성(시트 미선택).
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
