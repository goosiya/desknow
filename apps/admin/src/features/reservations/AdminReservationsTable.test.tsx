import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { adminCancelReservation, adminListReservations } from "@/lib/api-client";
import { AdminReservationsTable } from "./AdminReservationsTable";

// 확정 예약목록 데이터테이블 + 임의취소 테스트 (Story 8.3, AC4·AC5).
// adminListReservations/adminCancelReservation mock → 행 렌더·취소 뮤테이션·목록 invalidate·에러.
vi.mock("@/lib/api-client", () => ({
  adminListReservations: vi.fn(),
  adminCancelReservation: vi.fn(),
}));

const mockList = vi.mocked(adminListReservations);
const mockCancel = vi.mocked(adminCancelReservation);

function item(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    room_id: "r1",
    room_name: "강남 스터디룸",
    booker_id: "b1",
    booker_email: "booker@desknow.kr",
    status: "confirmed",
    slot_starts: ["2099-01-05T05:00:00Z"],
    created_at: "2026-06-18T00:00:00Z",
    ...overrides,
  };
}

function page(items: unknown[], total: number, pageNo: number) {
  return {
    data: { items, total, page: pageNo, page_size: 20 },
    response: new Response(null, { status: 200 }),
  } as never;
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AdminReservationsTable", () => {
  it("확정 예약 행을 렌더한다(룸·예약자 실 이메일·이용 시간)", async () => {
    mockList.mockResolvedValue(page([item("1")], 1, 1));

    render(<AdminReservationsTable />, { wrapper });

    expect(await screen.findByText("강남 스터디룸")).toBeInTheDocument();
    expect(screen.getByText("booker@desknow.kr")).toBeInTheDocument();
    expect(screen.getByText(/총 1개/)).toBeInTheDocument();
    // 취소 버튼 1개(확정 예약 1건).
    expect(screen.getAllByRole("button", { name: "취소" })).toHaveLength(1);
  });

  it("빈 목록 → 안내 문구", async () => {
    mockList.mockResolvedValue(page([], 0, 1));

    render(<AdminReservationsTable />, { wrapper });

    expect(
      await screen.findByText("취소할 확정 예약이 없습니다.")
    ).toBeInTheDocument();
  });

  it("다음 페이지 버튼이 page를 증가시켜 재조회한다", async () => {
    mockList.mockImplementation((opts) => {
      const p = (opts as { query?: { page?: number } })?.query?.page ?? 1;
      const room = p === 1 ? "첫 페이지 룸" : "둘째 페이지 룸";
      return page([item(String(p), { room_name: room })], 25, p);
    });
    const user = userEvent.setup();

    render(<AdminReservationsTable />, { wrapper });
    expect(await screen.findByText("첫 페이지 룸")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "다음" }));

    await waitFor(() =>
      expect(screen.getByText("둘째 페이지 룸")).toBeInTheDocument()
    );
    expect(mockList).toHaveBeenCalledWith(
      expect.objectContaining({ query: expect.objectContaining({ page: 2 }) })
    );
  });

  it("취소: 2단계 확인 → 뮤테이션 호출 + 목록 invalidate", async () => {
    mockList.mockResolvedValue(page([item("res-1")], 1, 1));
    mockCancel.mockResolvedValue({
      data: item("res-1", { status: "cancelled" }),
      response: new Response(null, { status: 200 }),
    } as never);
    const user = userEvent.setup();

    render(<AdminReservationsTable />, { wrapper });
    await user.click(await screen.findByRole("button", { name: "취소" }));

    // 확인 단계 — 슬롯 재활성/예약자 통지 경고 카피.
    expect(
      screen.getByText(/점유 슬롯이 다시 열리고 예약자에게 취소 통지가 전송/)
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "확인" }));

    await waitFor(() =>
      expect(mockCancel).toHaveBeenCalledWith(
        expect.objectContaining({ path: { reservation_id: "res-1" } })
      )
    );
    // 성공 시 목록을 재조회한다(취소된 예약이 confirmed 목록에서 사라짐) — list가 다시 호출됨.
    await waitFor(() => expect(mockList.mock.calls.length).toBeGreaterThan(1));
  });

  it("취소 실패(404/네트워크) → 에러 카피 표시", async () => {
    mockList.mockResolvedValue(page([item("res-1")], 1, 1));
    mockCancel.mockRejectedValue(new Error("network"));
    const user = userEvent.setup();

    render(<AdminReservationsTable />, { wrapper });
    await user.click(await screen.findByRole("button", { name: "취소" }));
    await user.click(screen.getByRole("button", { name: "확인" }));

    expect(await screen.findByText(/취소에 실패했어요/)).toBeInTheDocument();
  });
});
