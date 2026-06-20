// 지도 핀 데이터 훅 (Story 3.2 — 두 공개 GET 을 room_id 로 조인, AC1·AC2).
//
// `['rooms','map']`(좌표) + `['rooms','availability']`(색) 두 쿼리를 TanStack Query 로 가져와
// joinAvailability 로 RoomPin[] 을 도출한다(useMemo). 두 키 모두 지도 화면 복귀 시 재조회된다
// (query-client.ts refetchOnMount:'always' — 신선도 계약). 백엔드 호출은 생성 SDK 경유만
// (직접 fetch 금지, 1.9 가드). throwOnError:true 로 비-2xx 를 throw → react-query isError.
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { roomsAggregateAvailability, roomsListRooms } from "@/lib/api-client";
import { joinAvailability, type RoomPin } from "./pin";

export type UseRoomPinsResult = {
  pins: RoomPin[];
  isLoading: boolean;
  isError: boolean;
  /** 룸 목록이 로드됐고 활성 룸이 0개(빈 상태 — AC5②). 로딩/에러와 구분한다. */
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
    // 좌표(핀 자체)를 못 받으면 에러 화면(핀을 찍을 수 없음). 가용성(색)만 실패하면 에러로 막지
    // 않고 degrade 한다 — joinAvailability 가 가용성 미존재를 "마감"(회색)으로 처리하므로 핀은
    // 전부 회색으로 표시된다(신선도 정책상 색은 느슨한 스냅샷 — KTH code-review 결정 ①).
    isError: roomsQuery.isError,
    // 좌표 쿼리가 성공적으로 로드됐고 활성 룸이 0개일 때만 빈 상태(에러/로딩과 분리).
    isEmpty: roomsQuery.isSuccess && roomsQuery.data.length === 0,
    refetch: () => {
      void roomsQuery.refetch();
      void availabilityQuery.refetch();
    },
  };
}
