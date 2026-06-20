// 후기 작성 뮤테이션 훅 테스트 (Story 5.5 — AC5). reviewsCreateReview SDK 를 모킹해 ① 성공 시
// ["reservations"] + ["rooms", roomId, "reviews"] 2키 invalidate(광역 ["rooms"] 단일키 금지)
// ② 409(이용 완료 안 됨/이미 작성) → ["reservations"]만(룸 후기 무변화) ③ 본문 인자 분기를 검증한다.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { reviewsCreateReview } from "@/lib/api-client";
import { useCreateReview } from "./useCreateReview";

vi.mock("@/lib/api-client", () => ({
  reviewsCreateReview: vi.fn(),
  reviewsListRoomReviews: vi.fn(), // useRoomReviews 모듈 import 대역(키 함수만 사용)
}));

const mockCreate = vi.mocked(reviewsCreateReview);

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useCreateReview(), { wrapper });
  return { result, invalidateSpy };
}

function calledBroadRooms(invalidateSpy: ReturnType<typeof vi.spyOn>): boolean {
  return invalidateSpy.mock.calls.some((args: unknown[]) => {
    const key = (args[0] as { queryKey?: unknown })?.queryKey;
    return Array.isArray(key) && key.length === 1 && key[0] === "rooms";
  });
}

const vars = { reservationId: "r1", roomId: "room-1", rating: 4, text: "좋아요" };

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useCreateReview (AC5)", () => {
  it("성공 시 ['reservations'] + ['rooms', roomId, 'reviews'] 2키 invalidate(광역 ['rooms'] 금지)", async () => {
    mockCreate.mockResolvedValue({ data: { id: "rev-1" } } as never);
    const { result, invalidateSpy } = setup();

    act(() => {
      result.current.mutate(vars);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["reservations"] });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["rooms", "room-1", "reviews"],
    });
    expect(calledBroadRooms(invalidateSpy)).toBe(false);
  });

  it("경로 reservation_id·본문 rating/text 로 SDK 를 호출한다", async () => {
    mockCreate.mockResolvedValue({ data: { id: "rev-1" } } as never);
    const { result } = setup();

    act(() => {
      result.current.mutate(vars);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { reservation_id: "r1" },
        body: { rating: 4, text: "좋아요" },
        throwOnError: true,
      }),
    );
  });

  it("409 REVIEW_ALREADY_EXISTS → ['reservations']만 재조회(룸 후기 무변화)", async () => {
    mockCreate.mockRejectedValue({
      detail: { code: "REVIEW_ALREADY_EXISTS", message: "이미 후기를 작성한 예약이에요." },
    });
    const { result, invalidateSpy } = setup();

    act(() => {
      result.current.mutate(vars);
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["reservations"] });
    // 작성 실패라 룸 상세 후기는 무변화 → ["rooms", roomId, "reviews"] invalidate 안 함.
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: ["rooms", "room-1", "reviews"],
    });
  });

  it("generic 실패(detail.code 없음) → invalidate 미호출(재조회 불요)", async () => {
    mockCreate.mockRejectedValue(new Error("boom"));
    const { result, invalidateSpy } = setup();

    act(() => {
      result.current.mutate(vars);
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
