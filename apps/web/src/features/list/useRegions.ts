// 지역 콤보 트리 훅 (Story 3.4 — AC1). `GET /rooms/regions` 를 TanStack Query 로 가져온다.
//
// 키 `['rooms','regions']`(3.2 `['rooms','map']`/`['rooms','availability']`·3.3 `['rooms',id]`
// 와 별개). query-client 기본 refetchOnMount:'always' 라 목록 진입마다 신선 조회. 백엔드 호출은
// 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드). throwOnError:true 로 비-2xx 를 throw → isError.
import { useQuery } from "@tanstack/react-query";

import { roomsListRegions } from "@/lib/api-client";

export function useRegions() {
  return useQuery({
    queryKey: ["rooms", "regions"],
    queryFn: async () => {
      const { data } = await roomsListRegions({ throwOnError: true });
      return data ?? [];
    },
  });
}
