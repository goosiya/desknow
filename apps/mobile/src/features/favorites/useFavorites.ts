// 즐겨찾기 쿼리/뮤테이션 — 웹 useFavorites.ts 복사 (Story 9.1 — AC4 · 옵티미스틱 토글).
//
// ⚠️ 키 프리픽스 = ["favorites"](최상위 독립). ["rooms", ...] 프리픽스 **금지** — 지도/시트가
//    ["rooms",...]를 쓰므로 즐겨찾기가 ["rooms"] 광역 무효화를 도입하면 그 캐시까지 휩쓴다.
//
// **F 무한스크롤:** 목록은 커서 페이징(useInfiniteQuery)이라 캐시 형태가 InfiniteData<CursorPage>다.
// 옵티미스틱 토글은 이 봉투 구조를 직접 조작한다. `select` 평탄화로 소비처(useFavorites().data)는
// 기존처럼 FavoriteRoomItem[]을 본다. 백엔드 호출은 SDK 경유만.
import {
  type InfiniteData,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import {
  favoritesAddFavorite,
  favoritesListFavorites,
  favoritesRemoveFavorite,
  type FavoriteRoomItem,
} from "@/lib/api-client";
import { useSession } from "@/features/auth/useSession";
import {
  type CursorPage,
  INITIAL_CURSOR,
  flattenPages,
  getNextCursorParam,
} from "@/lib/pagination";

/** 즐겨찾기 캐시 키 — 최상위 독립(절대 ["rooms"] 프리픽스 금지). */
export const FAVORITES_KEY = ["favorites"] as const;

/** 즐겨찾기 무한 캐시 형태(옵티미스틱 토글이 직접 조작하는 봉투 구조). */
type FavoritesCache = InfiniteData<CursorPage<FavoriteRoomItem>>;

/** 공통 무한쿼리 옵션 — useFavorites(목록)와 useFavoriteIds(멤버십 Set)가 **같은 캐시 엔트리**를
 *  공유하도록 동일 key/queryFn을 쓴다(별도 조회 없음 — select만 다름). */
function favoritesQueryOptions(enabled: boolean) {
  return {
    queryKey: FAVORITES_KEY,
    enabled,
    initialPageParam: INITIAL_CURSOR,
    queryFn: async ({ pageParam }: { pageParam: string | null }) => {
      const { data } = await favoritesListFavorites({
        query: { cursor: pageParam ?? undefined },
        throwOnError: true,
      });
      return data ?? { items: [], next_cursor: null };
    },
    getNextPageParam: getNextCursorParam,
  };
}

/** 즐겨찾기 목록(미로그인 시 비활성 — enabled). `data`는 select 평탄화로 FavoriteRoomItem[]. */
export function useFavorites() {
  const { data: user } = useSession();
  return useInfiniteQuery({
    ...favoritesQueryOptions(!!user),
    select: flattenPages,
  });
}

/** 멤버십 판정용 Set<room_id> — useFavorites와 동일 캐시를 select로 파생(단일 조회 공유). */
export function useFavoriteIds() {
  const { data: user } = useSession();
  return useInfiniteQuery({
    ...favoritesQueryOptions(!!user),
    select: (data: FavoritesCache) =>
      new Set(flattenPages(data).map((item) => item.room_id)),
  });
}

type ToggleVars = { roomId: string; next: boolean };
type ToggleContext = { previous: FavoritesCache | undefined };

/** 옵티미스틱 placeholder — 추가 시 멤버십(하트 채움)을 즉시 반영하기 위한 최소 행.
 *  실제 메타는 onSettled invalidate가 신선 조회로 채운다. */
function optimisticItem(roomId: string): FavoriteRoomItem {
  return {
    room_id: roomId,
    name: "",
    price_per_hour: 0,
    room_type: "",
    amenities: [],
    remaining_slots: 0,
    is_active: true,
    favorited_at: new Date().toISOString(),
  };
}

// ── InfiniteData 봉투 조작 헬퍼(평탄 배열이 아니라 pages 구조를 다룬다) ──────────────
/** roomId가 어느 페이지에든 존재하는지(중복 추가 멱등 판정). */
function cacheHasRoom(
  cache: FavoritesCache | undefined,
  roomId: string,
): boolean {
  return (cache?.pages ?? []).some((page) =>
    page.items.some((item) => item.room_id === roomId),
  );
}

/** 첫 페이지 맨 앞에 항목을 prepend한다(캐시 없으면 단일 페이지로 생성). */
function prependItem(
  cache: FavoritesCache | undefined,
  item: FavoriteRoomItem,
): FavoritesCache {
  if (!cache || cache.pages.length === 0) {
    return {
      pages: [{ items: [item], next_cursor: null }],
      pageParams: [INITIAL_CURSOR],
    };
  }
  const [first, ...rest] = cache.pages;
  return {
    ...cache,
    pages: [{ ...first, items: [item, ...first.items] }, ...rest],
  };
}

/** 모든 페이지에서 roomId 항목을 제거한다(해제·placeholder 교체 전 정리). */
function removeRoom(
  cache: FavoritesCache | undefined,
  roomId: string,
): FavoritesCache | undefined {
  if (!cache) return cache;
  return {
    ...cache,
    pages: cache.pages.map((page) => ({
      ...page,
      items: page.items.filter((item) => item.room_id !== roomId),
    })),
  };
}

/**
 * 즐겨찾기 토글 뮤테이션(옵티미스틱 — AC4). `next`=목표 상태(true=추가/false=해제).
 *
 * - onMutate: cancelQueries → 스냅샷 previous → setQueryData로 즉시 반영.
 * - onError: previous로 롤백.
 * - onSettled: ["favorites"] **정확 키만** invalidate(절대 ["rooms"] 광역 무효화 금지).
 */
export function useToggleFavorite() {
  const queryClient = useQueryClient();
  return useMutation<FavoriteRoomItem | null, Error, ToggleVars, ToggleContext>({
    mutationFn: async ({ roomId, next }) => {
      if (next) {
        const { data } = await favoritesAddFavorite({
          body: { room_id: roomId },
          throwOnError: true,
        });
        return data ?? null;
      }
      await favoritesRemoveFavorite({
        path: { room_id: roomId },
        throwOnError: true,
      });
      return null;
    },
    onMutate: async ({ roomId, next }) => {
      await queryClient.cancelQueries({ queryKey: FAVORITES_KEY });
      const previous = queryClient.getQueryData<FavoritesCache>(FAVORITES_KEY);
      queryClient.setQueryData<FavoritesCache>(FAVORITES_KEY, (old) => {
        if (next) {
          if (cacheHasRoom(old, roomId)) return old; // 멱등
          return prependItem(old, optimisticItem(roomId));
        }
        return removeRoom(old, roomId);
      });
      return { previous };
    },
    onSuccess: (added, { roomId }) => {
      // add 성공 시 placeholder(빈 메타)를 서버 실데이터로 즉시 교체.
      if (!added) return;
      queryClient.setQueryData<FavoritesCache>(FAVORITES_KEY, (old) =>
        prependItem(removeRoom(old, roomId), added),
      );
    },
    onError: (_error, _vars, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(FAVORITES_KEY, context.previous);
      }
    },
    onSettled: () => {
      // 정확 키만 — ["rooms"] 프리픽스 광역 무효화 절대 금지.
      queryClient.invalidateQueries({ queryKey: FAVORITES_KEY });
    },
  });
}
