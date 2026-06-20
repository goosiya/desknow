import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  notificationsDismissNotification,
  notificationsDismissReminder,
  notificationsListNotifications,
} from "@/lib/api-client";
import {
  NOTIFICATIONS_KEY,
  useDismissNotification,
  useDismissReminder,
  useNotifications,
} from "./useNotifications";

// useNotifications 테스트 (Story 5.1·5.2 — AC2~AC5). 옵티미스틱 제거·정확 키 invalidate(광역 금지)·게이팅.
vi.mock("@/lib/api-client", () => ({
  authMe: vi.fn(() =>
    Promise.resolve({
      data: { id: "u1", role: "booker" },
      response: new Response(null, { status: 200 }),
    }),
  ),
  notificationsListNotifications: vi.fn(() => Promise.resolve({ data: [] })),
  notificationsDismissNotification: vi.fn(() => Promise.resolve({ data: undefined })),
  notificationsDismissReminder: vi.fn(() => Promise.resolve({ data: undefined })),
}));

const mockList = vi.mocked(notificationsListNotifications);
const mockDismiss = vi.mocked(notificationsDismissNotification);
const mockDismissReminder = vi.mocked(notificationsDismissReminder);

let client: QueryClient;
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.clearAllMocks();
  // clearAllMocks는 구현이 아니라 call history만 비우므로 기본 구현을 명시 재설정한다(누수 방지).
  mockList.mockResolvedValue({ data: [] } as never);
  mockDismiss.mockResolvedValue({ data: undefined } as never);
  mockDismissReminder.mockResolvedValue({ data: undefined } as never);
});

describe("useNotifications 게이팅 (AC3)", () => {
  it("로그인 시 미확인 통지를 조회한다", async () => {
    mockList.mockResolvedValue({
      data: [{ id: "n1", type: "status_change", reservation_id: "r1" }],
    } as never);
    const { result } = renderHook(() => useNotifications(), { wrapper });

    await waitFor(() => expect(result.current.data?.length).toBe(1));
    expect(result.current.data?.[0].id).toBe("n1");
    expect(mockList).toHaveBeenCalledWith({ throwOnError: true });
  });
});

describe("useDismissNotification 옵티미스틱 (AC5)", () => {
  it("onMutate 가 ≤100ms 로 해당 통지를 캐시에서 제거한다(옵티미스틱)", async () => {
    mockDismiss.mockReturnValue(new Promise(() => {}) as never); // 미해결 — 옵티미스틱 고정
    client.setQueryData(NOTIFICATIONS_KEY, [{ id: "n1" }, { id: "n2" }]);
    const { result } = renderHook(() => useDismissNotification(), { wrapper });

    act(() => {
      result.current.mutate({ notificationId: "n1" });
    });

    await waitFor(() => {
      const list = client.getQueryData<{ id: string }[]>(NOTIFICATIONS_KEY);
      expect(list?.some((n) => n.id === "n1")).toBe(false);
    });
    // 다른 통지는 보존.
    const list = client.getQueryData<{ id: string }[]>(NOTIFICATIONS_KEY);
    expect(list?.some((n) => n.id === "n2")).toBe(true);
    expect(mockDismiss).toHaveBeenCalledWith({
      path: { notification_id: "n1" },
      throwOnError: true,
    });
  });

  it("onError 가 서버 실패 시 이전 상태로 롤백한다", async () => {
    mockDismiss.mockRejectedValue(new Error("server down"));
    mockList.mockResolvedValue({ data: [{ id: "n1" }] } as never);
    client.setQueryData(NOTIFICATIONS_KEY, [{ id: "n1" }]);
    const { result } = renderHook(() => useDismissNotification(), { wrapper });

    await act(async () => {
      await result.current
        .mutateAsync({ notificationId: "n1" })
        .catch(() => {});
    });

    const list = client.getQueryData<{ id: string }[]>(NOTIFICATIONS_KEY);
    expect(list?.some((n) => n.id === "n1")).toBe(true); // 롤백됨(배너 복원)
  });

  it("onSettled 는 ['notifications'] 정확 키만 invalidate 한다(광역 금지)", async () => {
    const invalSpy = vi.spyOn(client, "invalidateQueries");
    client.setQueryData(NOTIFICATIONS_KEY, [{ id: "n1" }]);
    const { result } = renderHook(() => useDismissNotification(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ notificationId: "n1" });
    });

    expect(invalSpy).toHaveBeenCalledWith({ queryKey: ["notifications"] });
    // 절대 ["rooms"]/["reservations"] 프리픽스 광역 무효화를 호출하지 않는다(favorites 선례).
    const touchedForbidden = invalSpy.mock.calls.some(([arg]) => {
      const key = JSON.stringify(arg?.queryKey);
      return key === JSON.stringify(["rooms"]) || key === JSON.stringify(["reservations"]);
    });
    expect(touchedForbidden).toBe(false);
  });
});

describe("useDismissReminder 옵티미스틱 (Story 5.2 — AC2·AC4)", () => {
  it("해당 reservation_id의 reservation_reminder만 제거(status_change·타 예약 리마인드 불변)", async () => {
    mockDismissReminder.mockReturnValue(new Promise(() => {}) as never); // 미해결 — 옵티미스틱 고정
    client.setQueryData(NOTIFICATIONS_KEY, [
      { id: null, type: "reservation_reminder", reservation_id: "r1" },
      { id: "n2", type: "status_change", reservation_id: "r1" }, // 같은 예약 status_change(불변)
      { id: null, type: "reservation_reminder", reservation_id: "r2" }, // 타 예약 리마인드(불변)
    ]);
    const { result } = renderHook(() => useDismissReminder(), { wrapper });

    act(() => {
      result.current.mutate({ reservationId: "r1" });
    });

    await waitFor(() => {
      const list = client.getQueryData<
        { type: string; reservation_id: string }[]
      >(NOTIFICATIONS_KEY);
      // r1 리마인드만 사라짐.
      expect(
        list?.some(
          (n) => n.type === "reservation_reminder" && n.reservation_id === "r1",
        ),
      ).toBe(false);
    });
    const list = client.getQueryData<
      { type: string; reservation_id: string }[]
    >(NOTIFICATIONS_KEY);
    // 같은 예약 status_change·타 예약 리마인드는 보존.
    expect(
      list?.some((n) => n.type === "status_change" && n.reservation_id === "r1"),
    ).toBe(true);
    expect(
      list?.some(
        (n) => n.type === "reservation_reminder" && n.reservation_id === "r2",
      ),
    ).toBe(true);
    expect(mockDismissReminder).toHaveBeenCalledWith({
      path: { reservation_id: "r1" },
      throwOnError: true,
    });
  });

  it("onError 가 서버 실패 시 이전 상태로 롤백한다", async () => {
    mockDismissReminder.mockRejectedValue(new Error("server down"));
    client.setQueryData(NOTIFICATIONS_KEY, [
      { id: null, type: "reservation_reminder", reservation_id: "r1" },
    ]);
    const { result } = renderHook(() => useDismissReminder(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ reservationId: "r1" }).catch(() => {});
    });

    const list = client.getQueryData<{ reservation_id: string }[]>(NOTIFICATIONS_KEY);
    expect(list?.some((n) => n.reservation_id === "r1")).toBe(true); // 롤백됨(배너 복원)
  });

  it("onSettled 는 ['notifications'] 정확 키만 invalidate 한다(광역 금지)", async () => {
    const invalSpy = vi.spyOn(client, "invalidateQueries");
    client.setQueryData(NOTIFICATIONS_KEY, [
      { id: null, type: "reservation_reminder", reservation_id: "r1" },
    ]);
    const { result } = renderHook(() => useDismissReminder(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ reservationId: "r1" });
    });

    expect(invalSpy).toHaveBeenCalledWith({ queryKey: ["notifications"] });
    const touchedForbidden = invalSpy.mock.calls.some(([arg]) => {
      const key = JSON.stringify(arg?.queryKey);
      return key === JSON.stringify(["rooms"]) || key === JSON.stringify(["reservations"]);
    });
    expect(touchedForbidden).toBe(false);
  });
});
