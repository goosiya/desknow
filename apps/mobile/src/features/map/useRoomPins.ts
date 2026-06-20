// 지도 핀 데이터 훅 — 웹 useRoomPins.ts 복사 (Story 9.1 — 두 공개 GET을 room_id로 조인, AC3).
//
// `['rooms','map']`(좌표) + `['rooms','availability']`(색) 두 쿼리를 가져와 joinAvailability로
// RoomPin[]을 도출한다. RN이 SDK로 조회해 WebView에 주입한다(WebView는 캔버스만 — 직접 fetch 안 함).
// 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지). throwOnError:true로 비-2xx를 throw → isError.
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { roomsAggregateAvailability, roomsListRooms } from "@/lib/api-client";

import { joinAvailability, type RoomPin } from "./pin";

export type UseRoomPinsResult = {
  pins: RoomPin[];
  isLoading: boolean;
  isError: boolean;
  /** 룸 목록이 로드됐고 활성 룸이 0개(빈 상태). 로딩/에러와 구분한다. */
  isEmpty: boolean;
  refetch: () => void;
};

export function useRoomPins(): UseRoomPinsResult {
  const roomsQuery = useQuery({
    queryKey: ["rooms", "map"],
    queryFn: async () => {
      const { data } = await roomsListRooms({ throwOnError: true });
      return data ?? [];
    },
  });
  const availabilityQuery = useQuery({
    queryKey: ["rooms", "availability"],
    queryFn: async () => {
      const { data } = await roomsAggregateAvailability({ throwOnError: true });
      return data ?? [];
    },
  });

  const pins = useMemo(
    () => joinAvailability(roomsQuery.data ?? [], availabilityQuery.data ?? []),
    [roomsQuery.data, availabilityQuery.data],
  );

  return {
    pins,
    isLoading: roomsQuery.isLoading || availabilityQuery.isLoading,
    // 좌표(핀 자체)를 못 받으면 에러. 가용성(색)만 실패하면 degrade(joinAvailability가 미존재를
    // "마감"=회색으로 처리 — 신선도 정책상 색은 느슨한 스냅샷).
    isError: roomsQuery.isError,
    isEmpty: roomsQuery.isSuccess && roomsQuery.data.length === 0,
    refetch: () => {
      void roomsQuery.refetch();
      void availabilityQuery.refetch();
    },
  };
}
