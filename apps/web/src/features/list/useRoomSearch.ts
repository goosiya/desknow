// 통합 룸 검색 훅 (Story 3.5 — AC1·AC4). 두 검색방식(지역·반경)을 하나의 `GET /rooms/search`
// 호출로 통합한다. 3.4 의 `useRoomList(regionCode)` 를 일반화한 것 — region 동작·캐시 키는 그대로
// 보존하고(무회귀), radius 를 추가한다.
//
// **enabled** 로 무제한 초기 스캔을 막는다: region=지역 선택 시, radius=현위치 좌표 확보 시에만
// 조회한다. 키는 검색방식별로 분리(`['rooms','list',code]` / `['rooms','radius',lat,lng,km]`)해
// 캐시가 섞이지 않는다. query-client 기본 refetchOnMount:'always' 라 진입마다 신선 remaining_slots.
// 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드). throwOnError:true 로 비-2xx 를 throw
// → isError(목록 에러 분기 AC5).
import { useInfiniteQuery } from "@tanstack/react-query";

import { roomsSearchRooms } from "@/lib/api-client";
import {
  INITIAL_CURSOR,
  flattenPages,
  getNextCursorParam,
} from "@/lib/pagination";

/** 검색 디스크립터 — 지역(region) 또는 반경(radius). 컨테이너(ExploreView)가 구성해 내려준다. */
export type RoomSearch =
  | { kind: "region"; regionCode?: string }
  | { kind: "radius"; center?: { lat: number; lng: number }; radiusKm: number };

export function useRoomSearch(search: RoomSearch) {
  // 검색방식별 캐시 키 분리. region 키는 3.4 `useRoomList` 와 동일(무회귀).
  const queryKey =
    search.kind === "region"
      ? ["rooms", "list", search.regionCode ?? null]
      : [
          "rooms",
          "radius",
          search.center?.lat ?? null,
          search.center?.lng ?? null,
          search.radiusKm,
        ];

  // region=지역 선택 시, radius=현위치 확보 시에만 조회(무제한 초기 스캔 방지).
  const enabled =
    search.kind === "region" ? !!search.regionCode : !!search.center;

  // **F 무한스크롤:** offset 커서 페이징(`useInfiniteQuery`). `select` 평탄화로 `data`는 기존처럼
  // `RoomListItem[]`(RoomList 무변경). 검색은 거리/지역 계산 정렬이라 서버가 offset 커서를 쓴다.
  return useInfiniteQuery({
    queryKey,
    enabled,
    initialPageParam: INITIAL_CURSOR,
    queryFn: async ({ pageParam }) => {
      // 검색방식별 쿼리 파라미터 구성(snake_case — SDK 와이어 계약). cursor는 공통.
      let query: {
        region_code?: string;
        lat?: number;
        lng?: number;
        radius_km?: number;
        cursor?: string;
      };
      if (search.kind === "region") {
        query = { region_code: search.regionCode };
      } else {
        const center = search.center;
        // enabled 가 center 를 가드하지만, 타입 안전을 위해 방어적으로 빈 페이지 반환.
        if (!center) return { items: [], next_cursor: null };
        query = {
          lat: center.lat,
          lng: center.lng,
          radius_km: search.radiusKm,
        };
      }
      query.cursor = pageParam ?? undefined;
      const { data } = await roomsSearchRooms({ query, throwOnError: true });
      return data ?? { items: [], next_cursor: null };
    },
    getNextPageParam: getNextCursorParam,
    select: flattenPages,
  });
}
