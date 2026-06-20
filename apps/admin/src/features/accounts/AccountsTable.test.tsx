import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { adminDeactivateAccount, adminListAccounts } from "@/lib/api-client";
import { AccountsTable } from "./AccountsTable";

// 계정목록 데이터테이블 테스트 (Story 8.1, AC4 · Story 8.2 — 비활성 액션).
// adminListAccounts/adminDeactivateAccount mock → 행 렌더·페이지네이션·비활성 뮤테이션.
vi.mock("@/lib/api-client", () => ({
  adminListAccounts: vi.fn(),
  adminDeactivateAccount: vi.fn(),
}));

const mockList = vi.mocked(adminListAccounts);
const mockDeactivate = vi.mocked(adminDeactivateAccount);

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

describe("AccountsTable", () => {
  it("계정 행을 렌더한다(실 이메일·역할·상태)", async () => {
    mockList.mockResolvedValue(
      page(
        [
          {
            id: "1",
            email: "booker@desknow.kr",
            role: "booker",
            is_active: true,
            created_at: "2026-06-18T00:00:00Z",
          },
        ],
        1,
        1
      )
    );

    render(<AccountsTable />, { wrapper });

    expect(await screen.findByText("booker@desknow.kr")).toBeInTheDocument();
    expect(screen.getByText("예약자")).toBeInTheDocument();
    // "● 활성" 상태 셀로 구체화('비활성' 버튼 텍스트와의 /활성/ 중복 매칭 회피).
    expect(screen.getByText(/● 활성/)).toBeInTheDocument();
    expect(screen.getByText(/총 1개/)).toBeInTheDocument();
  });

  it("다음 페이지 버튼이 page를 증가시켜 재조회한다", async () => {
    // 총 25개 → 2페이지. 1페이지엔 '다음' 활성.
    mockList.mockImplementation((opts) => {
      const p = (opts as { query?: { page?: number } })?.query?.page ?? 1;
      const email = p === 1 ? "first@desknow.kr" : "second@desknow.kr";
      return page(
        [{ id: String(p), email, role: "provider", is_active: true, created_at: "2026-06-18T00:00:00Z" }],
        25,
        p
      );
    });
    const user = userEvent.setup();

    render(<AccountsTable />, { wrapper });
    expect(await screen.findByText("first@desknow.kr")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "다음" }));

    await waitFor(() => expect(screen.getByText("second@desknow.kr")).toBeInTheDocument());
    // page=2로 조회됐는지 확인.
    expect(mockList).toHaveBeenCalledWith(
      expect.objectContaining({ query: expect.objectContaining({ page: 2 }) })
    );
  });

  it("빈 목록 → 안내 문구", async () => {
    mockList.mockResolvedValue(page([], 0, 1));

    render(<AccountsTable />, { wrapper });

    expect(await screen.findByText("표시할 계정이 없습니다.")).toBeInTheDocument();
  });

  // ── 비활성 액션 (Story 8.2, AC1·2·4) ────────────────────────────────────────
  it("활성 행엔 비활성 버튼, 비활성 행엔 '비활성됨' 텍스트(단방향)", async () => {
    mockList.mockResolvedValue(
      page(
        [
          { id: "a", email: "active@desknow.kr", role: "booker", is_active: true, created_at: "2026-06-18T00:00:00Z" },
          { id: "d", email: "dead@desknow.kr", role: "provider", is_active: false, created_at: "2026-06-18T00:00:00Z" },
        ],
        2,
        1
      )
    );

    render(<AccountsTable />, { wrapper });

    expect(await screen.findByText("active@desknow.kr")).toBeInTheDocument();
    // 활성 1건 → 비활성 버튼 1개, 비활성 행엔 '비활성됨' 텍스트(재활성 버튼 없음).
    expect(screen.getAllByRole("button", { name: "비활성" })).toHaveLength(1);
    expect(screen.getByText("비활성됨")).toBeInTheDocument();
  });

  it("provider 비활성: 확인 단계(룸 경고) → 뮤테이션 호출 + 목록 invalidate", async () => {
    mockList.mockResolvedValue(
      page(
        [{ id: "p1", email: "prov@desknow.kr", role: "provider", is_active: true, created_at: "2026-06-18T00:00:00Z" }],
        1,
        1
      )
    );
    mockDeactivate.mockResolvedValue({
      data: { id: "p1", email: "prov@desknow.kr", role: "provider", is_active: false, created_at: "2026-06-18T00:00:00Z" },
      response: new Response(null, { status: 200 }),
    } as never);
    const user = userEvent.setup();

    render(<AccountsTable />, { wrapper });
    await user.click(await screen.findByRole("button", { name: "비활성" }));

    // 확인 단계 — provider는 룸 노출 중단/신규 예약 차단 경고 카피.
    expect(screen.getByText(/룸 노출이 중단되고 신규 예약이 차단/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "확인" }));

    await waitFor(() =>
      expect(mockDeactivate).toHaveBeenCalledWith(
        expect.objectContaining({ path: { account_id: "p1" } })
      )
    );
    // 성공 시 목록을 재조회한다(상태 셀 갱신) — adminListAccounts가 다시 호출됨.
    await waitFor(() => expect(mockList.mock.calls.length).toBeGreaterThan(1));
  });

  it("비활성 실패(404/네트워크) → 에러 카피 표시", async () => {
    mockList.mockResolvedValue(
      page(
        [{ id: "b1", email: "book@desknow.kr", role: "booker", is_active: true, created_at: "2026-06-18T00:00:00Z" }],
        1,
        1
      )
    );
    mockDeactivate.mockRejectedValue(new Error("network"));
    const user = userEvent.setup();

    render(<AccountsTable />, { wrapper });
    await user.click(await screen.findByRole("button", { name: "비활성" }));
    await user.click(screen.getByRole("button", { name: "확인" }));

    expect(await screen.findByText(/비활성에 실패했어요/)).toBeInTheDocument();
  });
});
