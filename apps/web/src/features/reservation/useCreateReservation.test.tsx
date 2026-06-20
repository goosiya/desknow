// 즉시 예약 뮤테이션 훅 테스트 (Story 4.5 — AC4·AC5). reservationsCreateReservation SDK 를 모킹해
// 성공 시 정확 키 invalidate(슬롯 키 + 핀 집계 · 광역 ["rooms"] 금지)·본문 형태·실패 시 isError 노출을
// 검증한다.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { reservationsCreateReservation } from "@/lib/api-client";
import { useCreateReservation } from "./useCreateReservation";

vi.mock("@/lib/api-client", () => ({ reservationsCreateReservation: vi.fn() }));

const mockCreate = vi.mocked(reservationsCreateReservation);

function setup(roomId = "room-1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useCreateReservation(roomId), { wrapper });
  return { result, invalidateSpy };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useCreateReservation", () => {
  it("성공 시 슬롯 키 + 핀 집계 키만 정확 invalidate한다(광역 ['rooms'] 금지)", async () => {
    mockCreate.mockResolvedValue({ data: { id: "r1" } } as never);
    const { result, invalidateSpy } = setup("room-1");

    act(() => {
      result.current.mutate({
        slotStarts: ["2026-06-15T05:00:00Z"],
        selectedDate: "2026-06-15",
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // 슬롯 날짜별 키 + 핀 색 집계 키 정확 invalidate.
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["room", "room-1", "slots", "2026-06-15"],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["rooms", "availability"],
    });
    // 광역 ["rooms"] 단일 프리픽스 무효화 금지(useFavorites 선례 — 지도/시트 캐시 휩쓸기 방지).
    const broad = invalidateSpy.mock.calls.some(([arg]) => {
      const key = (arg as { queryKey?: unknown })?.queryKey;
      return Array.isArray(key) && key.length === 1 && key[0] === "rooms";
    });
    expect(broad).toBe(false);
  });

  it("slot_starts(snake_case) 본문 + 경로 room_id 로 SDK 를 호출한다", async () => {
    mockCreate.mockResolvedValue({ data: { id: "r1" } } as never);
    const { result } = setup("room-9");

    act(() => {
      result.current.mutate({
        slotStarts: ["2026-06-15T05:00:00Z", "2026-06-15T06:00:00Z"],
        selectedDate: "2026-06-15",
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { room_id: "room-9" },
        body: { slot_starts: ["2026-06-15T05:00:00Z", "2026-06-15T06:00:00Z"] },
        throwOnError: true,
      }),
    );
  });

  it("generic 실패(detail.code 없음) → isError 노출 · invalidate 미호출(재조회 불요)", async () => {
    // detail.code 가 없는 실패(네트워크/일반 에러)는 SLOT_CONFLICT 가 아니므로 재조회하지 않는다.
    mockCreate.mockRejectedValue(new Error("409 conflict"));
    const { result, invalidateSpy } = setup();

    act(() => {
      result.current.mutate({
        slotStarts: ["2026-06-15T05:00:00Z"],
        selectedDate: "2026-06-15",
      });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  // ── Story 4.6 — SLOT_CONFLICT(409) 시 그날 슬롯만 재조회(인접 빈 슬롯 재표시) ──
  it("SLOT_CONFLICT(409) → 그날 슬롯 키만 정확 invalidate한다(광역 ['rooms'] 금지)", async () => {
    // SDK 는 throwOnError 시 파싱된 본문 {detail:{code,message}} 를 throw(client-fetch 실측).
    mockCreate.mockRejectedValue({
      detail: { code: "SLOT_CONFLICT", message: "선택한 시간 중 이미 예약된 슬롯이 있습니다." },
    });
    const { result, invalidateSpy } = setup("room-7");

    act(() => {
      result.current.mutate({
        slotStarts: ["2026-06-15T05:00:00Z"],
        selectedDate: "2026-06-15",
      });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    // 그날 슬롯 키만 invalidate(인접 빈 슬롯 재표시 = 그리드 재조회).
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["room", "room-7", "slots", "2026-06-15"],
    });
    // 광역 ["rooms"] 단일 프리픽스 무효화 금지(정확 키만 — useFavorites 선례).
    const broad = invalidateSpy.mock.calls.some(([arg]) => {
      const key = (arg as { queryKey?: unknown })?.queryKey;
      return Array.isArray(key) && key.length === 1 && key[0] === "rooms";
    });
    expect(broad).toBe(false);
    // 핀 집계(["rooms","availability"])는 onSuccess 전용 — 실패 경로에선 호출 안 함.
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: ["rooms", "availability"],
    });
  });
});
