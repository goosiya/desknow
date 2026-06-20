// 날짜별 슬롯 신선 조회 훅 — 웹 reservation/useRoomSlots.ts 미러 (Story 9.2 — AC2).
//
// `GET /rooms/{room_id}/slots?date=` 를 TanStack Query 로 가져온다. 키 `['room', roomId, 'slots',
// date]`(architecture.md L275 정확 일치 — 단수 `room`, useRoomSummary 의 `['rooms', roomId]` 와
// 별개)로 **날짜별 캐시 분리**한다. query-client 기본 refetchOnMount:'always' 라 전개/날짜 변경
// 시 **신선** 조회한다([[availability-freshness-policy]] — 상세·슬롯=진입 시 최신).
//
// 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드). 인증 헤더(Bearer)는 api-client.ts
// 인터셉터가 주입한다(웹은 쿠키, 모바일은 Bearer — 이 훅은 무관). throwOnError:true 로 비-2xx 를
// throw → react-query isError(슬롯 영역 에러 분기 AC2). roomId/date 가 비면 비활성.
import { useQuery } from "@tanstack/react-query";

import { roomsGetRoomSlots } from "@/lib/api-client";

export function useRoomSlots(roomId: string, date: string) {
  return useQuery({
    queryKey: ["room", roomId, "slots", date],
    // roomId/date 가 비면 조회하지 않는다(불필요 요청·UUID 미일치/빈 date 422 회피).
    enabled: roomId !== "" && date !== "",
    queryFn: async () => {
      const { data } = await roomsGetRoomSlots({
        path: { room_id: roomId },
        query: { date },
        throwOnError: true,
      });
      return data;
    },
  });
}
