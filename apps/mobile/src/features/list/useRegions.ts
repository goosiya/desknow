// 지역 콤보 트리 훅 — 웹 useRegions.ts 복사 (Story 9.1 — AC4). `GET /rooms/regions`를 가져온다.
//
// query-client 기본 refetchOnMount:'always'라 목록 진입마다 신선 조회. 백엔드 호출은 SDK 경유만.
// throwOnError:true로 비-2xx를 throw → isError.
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
