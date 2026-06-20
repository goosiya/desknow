import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authMe } from "@/lib/api-client";
import { AdminGate } from "./AdminGate";

// AdminGate 테스트 (Story 8.1, AC2 — 역할 게이트). admin → children, 비-admin/미로그인 → /login
// 리다이렉트. 백엔드 403이 최종 강제이고 이 게이트는 보조다.
vi.mock("@/lib/api-client", () => ({ authMe: vi.fn() }));

const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

const mockAuthMe = vi.mocked(authMe);

function authResult(status: number, data: unknown) {
  return { data, response: new Response(null, { status }) } as never;
}

function renderGate() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return render(
    <AdminGate>
      <div>보호된 콘텐츠</div>
    </AdminGate>,
    { wrapper }
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AdminGate", () => {
  it("admin 세션 → 자식 렌더(리다이렉트 없음)", async () => {
    mockAuthMe.mockResolvedValue(authResult(200, { id: "u1", email: "a@b.com", role: "admin" }));

    renderGate();

    expect(await screen.findByText("보호된 콘텐츠")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("booker 세션 → /login 리다이렉트(자식 미렌더)", async () => {
    mockAuthMe.mockResolvedValue(authResult(200, { id: "u1", email: "a@b.com", role: "booker" }));

    renderGate();

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("보호된 콘텐츠")).not.toBeInTheDocument();
  });

  it("미로그인(401) → /login 리다이렉트", async () => {
    mockAuthMe.mockResolvedValue(authResult(401, undefined));

    renderGate();

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("보호된 콘텐츠")).not.toBeInTheDocument();
  });

  it("진짜 오류(5xx) → 리다이렉트하지 않고 재시도 노출", async () => {
    mockAuthMe.mockResolvedValue(authResult(500, undefined));

    renderGate();

    expect(await screen.findByRole("button", { name: "다시 시도" })).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
