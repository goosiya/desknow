// 예약 취소 뮤테이션 훅 테스트 (Story 4.8 — AC2 · Story 4.9 — AC4). reservationsCancelReservation
// SDK 를 모킹해 ① 성공 시 ["reservations"] + 슬롯 prefix(["room",id,"slots"]) + 핀(["rooms",
// "availability"]) 3키 invalidate(광역 ["rooms"] 단일키는 금지) ② 클럭 스큐 409 는 ["reservations"]만
// (취소 실패=슬롯 무변화) ③ 본문 경로·generic 실패 분기를 검증한다.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { reservationsCancelReservation } from "@/lib/api-client";
import { useCancelReservation } from "./useCancelReservation";

vi.mock("@/lib/api-client", () => ({ reservationsCancelReservation: vi.fn() }));

const mockCancel = vi.mocked(reservationsCancelReservation);

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useCancelReservation(), { wrapper });
  return { result, invalidateSpy };
}

function calledBroadRooms(invalidateSpy: ReturnType<typeof vi.spyOn>): boolean {
  return invalidateSpy.mock.calls.some((args: unknown[]) => {
    const key = (args[0] as { queryKey?: unknown })?.queryKey;
    return Array.isArray(key) && key.length === 1 && key[0] === "rooms";
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useCancelReservation", () => {
  it("성공 시 ['reservations']+슬롯 prefix+핀 3키 invalidate(광역 ['rooms'] 단일키 금지)", async () => {
    mockCancel.mockResolvedValue({ data: { id: "r1", status: "cancelled" } } as never);
    const { result, invalidateSpy } = setup();

    act(() => {
      result.current.mutate({ roomId: "room-1", reservationId: "r1" });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // ① 자기 목록 ② 슬롯 prefix(룸 전 날짜 — Story 4.9) ③ 핀 색 집계.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["reservations"] });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["room", "room-1", "slots"],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["rooms", "availability"],
    });
    // 광역 ["rooms"] **단일키**(지도/시트 휩쓸기)는 절대 금지(룸 범위 prefix 는 위반 아님).
    expect(calledBroadRooms(invalidateSpy)).toBe(false);
  });

  it("경로 room_id·reservation_id 로 SDK 를 호출한다", async () => {
    mockCancel.mockResolvedValue({ data: { id: "r9" } } as never);
    const { result } = setup();

    act(() => {
      result.current.mutate({ roomId: "room-9", reservationId: "r9" });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockCancel).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { room_id: "room-9", reservation_id: "r9" },
        throwOnError: true,
      }),
    );
  });

  it("클럭 스큐 409 CANCEL_WINDOW_PASSED → 목록 재조회(버튼 상태 갱신·graceful)", async () => {
    // SDK 는 throwOnError 시 파싱된 본문 {detail:{code,message}} 를 throw.
    mockCancel.mockRejectedValue({
      detail: { code: "CANCEL_WINDOW_PASSED", message: "이제 6시간이 안 남아서 취소가 어려워요." },
    });
    const { result, invalidateSpy } = setup();

    act(() => {
      result.current.mutate({ roomId: "room-1", reservationId: "r1" });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["reservations"] });
    // 취소 실패라 슬롯/핀은 무변화 → ["reservations"]만(슬롯 prefix·핀 invalidate 안 함).
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: ["room", "room-1", "slots"],
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: ["rooms", "availability"],
    });
    expect(calledBroadRooms(invalidateSpy)).toBe(false);
  });

  it("generic 실패(detail.code 없음) → isError·invalidate 미호출(재조회 불요)", async () => {
    mockCancel.mockRejectedValue(new Error("boom"));
    const { result, invalidateSpy } = setup();

    act(() => {
      result.current.mutate({ roomId: "room-1", reservationId: "r1" });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
