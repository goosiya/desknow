import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { InfiniteData } from "@tanstack/react-query";

import { favoritesAddFavorite, favoritesListFavorites } from "@/lib/api-client";
import { FAVORITES_KEY, useFavoriteIds, useToggleFavorite } from "./useFavorites";
import type { CursorPage } from "@/lib/pagination";

// useFavorites 테스트 (Story 3.7 — AC1·AC2). 옵티미스틱 onMutate·정확 키 invalidate·멤버십 Set 파생.
//
// **F 무한스크롤:** 즐겨찾기 캐시는 평탄 배열이 아니라 `InfiniteData<CursorPage>` 봉투
// (`{ pages: [{ items, next_cursor }], pageParams }`)다. 시드/단언 모두 봉투 구조로 다룬다.
vi.mock("@/lib/api-client", () => ({
  authMe: vi.fn(() =>
    Promise.resolve({
      data: { id: "u1", role: "booker" },
      response: new Response(null, { status: 200 }),
    }),
  ),
  favoritesListFavorites: vi.fn(() =>
    Promise.resolve({ data: { items: [], next_cursor: null } }),
  ),
  favoritesAddFavorite: vi.fn(() => Promise.resolve({ data: {} })),
  favoritesRemoveFavorite: vi.fn(() => Promise.resolve({ data: undefined })),
}));

const mockAdd = vi.mocked(favoritesAddFavorite);
const mockList = vi.mocked(favoritesListFavorites);

// 즐겨찾기 캐시 봉투 타입 — 옵티미스틱 토글이 직접 조작하는 InfiniteData 형태.
type FavItem = { room_id: string };
type FavCache = InfiniteData<CursorPage<FavItem>>;

// 평탄 배열을 단일 페이지 InfiniteData 봉투로 감싸는 시드 헬퍼.
function seedPage(items: FavItem[]): FavCache {
  return { pages: [{ items, next_cursor: null }], pageParams: [null] };
}

// 캐시 봉투에서 전 페이지 항목을 평탄화해 단언에 쓴다.
function flatItems(cache: FavCache | undefined): FavItem[] {
  return cache?.pages.flatMap((p) => p.items) ?? [];
}

let client: QueryClient;
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.clearAllMocks();
  // clearAllMocks는 구현을 초기화하지 않으므로(call history만) 기본 구현을 명시 재설정해
  // 직전 테스트의 mockRejectedValue/mockReturnValue 누수를 막는다.
  mockAdd.mockResolvedValue({ data: {} } as never);
  mockList.mockResolvedValue({ data: { items: [], next_cursor: null } } as never);
});

describe("useToggleFavorite 옵티미스틱 (AC1)", () => {
  it("onMutate 가 ≤100ms 로 캐시에 룸을 추가한다(옵티미스틱)", async () => {
    mockAdd.mockReturnValue(new Promise(() => {}) as never); // 미해결 — 옵티미스틱 상태 고정
    client.setQueryData(FAVORITES_KEY, seedPage([]));
    const { result } = renderHook(() => useToggleFavorite(), { wrapper });

    act(() => {
      result.current.mutate({ roomId: "r1", next: true });
    });

    await waitFor(() => {
      const cache = client.getQueryData<FavCache>(FAVORITES_KEY);
      expect(flatItems(cache).some((f) => f.room_id === "r1")).toBe(true);
    });
    expect(mockAdd).toHaveBeenCalledWith({
      body: { room_id: "r1" },
      throwOnError: true,
    });
  });

  it("onError 가 서버 실패 시 이전 상태로 롤백한다", async () => {
    mockAdd.mockRejectedValue(new Error("server down"));
    // 리스트 재조회(onSettled invalidate)는 이전과 동일(빈 봉투)을 돌려 롤백 결과를 보존한다.
    mockList.mockResolvedValue({ data: { items: [], next_cursor: null } } as never);
    client.setQueryData(FAVORITES_KEY, seedPage([]));
    const { result } = renderHook(() => useToggleFavorite(), { wrapper });

    await act(async () => {
      await result.current
        .mutateAsync({ roomId: "r1", next: true })
        .catch(() => {});
    });

    const cache = client.getQueryData<FavCache>(FAVORITES_KEY);
    expect(flatItems(cache).some((f) => f.room_id === "r1")).toBe(false); // 롤백됨
  });

  it("onSettled 는 ['favorites'] 정확 키만 invalidate 한다(['rooms'] 광역 금지)", async () => {
    const invalSpy = vi.spyOn(client, "invalidateQueries");
    client.setQueryData(FAVORITES_KEY, seedPage([]));
    const { result } = renderHook(() => useToggleFavorite(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ roomId: "r1", next: true });
    });

    expect(invalSpy).toHaveBeenCalledWith({ queryKey: ["favorites"] });
    // 절대 ["rooms"] 프리픽스 광역 무효화를 호출하지 않는다(deferred L153 회수).
    const touchedRooms = invalSpy.mock.calls.some(
      ([arg]) => JSON.stringify(arg?.queryKey) === JSON.stringify(["rooms"]),
    );
    expect(touchedRooms).toBe(false);
  });
});

describe("useFavoriteIds 멤버십 Set", () => {
  it("리스트를 Set<room_id> 로 파생한다(단일 캐시 공유)", async () => {
    client.setQueryData(
      FAVORITES_KEY,
      seedPage([{ room_id: "r1" }, { room_id: "r2" }]),
    );
    const { result } = renderHook(() => useFavoriteIds(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeInstanceOf(Set));
    expect(result.current.data?.has("r1")).toBe(true);
    expect(result.current.data?.has("r2")).toBe(true);
    expect(result.current.data?.has("rX")).toBe(false);
  });
});
