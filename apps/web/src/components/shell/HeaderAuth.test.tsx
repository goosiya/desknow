import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authMe, authLogout } from "@/lib/api-client";
import { HeaderAuth } from "./HeaderAuth";

// HeaderAuth 테스트 — 미로그인=로그인 링크(/login), 로그인=이메일+로그아웃, 로그아웃 클릭=authLogout 호출.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

vi.mock("@/lib/api-client", () => ({
  authMe: vi.fn(),
  authLogout: vi.fn(() => Promise.resolve({ response: new Response(null, { status: 204 }) })),
  authLogin: vi.fn(),
  authRegister: vi.fn(),
}));

const mockAuthMe = vi.mocked(authMe);
const mockLogout = vi.mocked(authLogout);

function loggedIn() {
  mockAuthMe.mockResolvedValue({
    data: { id: "u1", email: "me@b.com", role: "booker" },
    response: new Response(null, { status: 200 }),
  } as never);
}
function loggedOut() {
  mockAuthMe.mockResolvedValue({
    data: undefined,
    response: new Response(null, { status: 401 }),
  } as never);
}

function renderHeader() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactNode = <HeaderAuth />;
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("HeaderAuth", () => {
  it("미로그인 → /login 로그인 링크", async () => {
    loggedOut();
    renderHeader();
    await waitFor(() => {
      const link = screen.getByRole("link", { name: "로그인" });
      expect(link).toHaveAttribute("href", "/login");
    });
  });

  it("로그인 → 이메일 + 로그아웃 버튼", async () => {
    loggedIn();
    renderHeader();
    await waitFor(() =>
      expect(screen.getByText("me@b.com")).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "로그아웃" })).toBeInTheDocument();
  });

  it("로그아웃 클릭 → authLogout 호출", async () => {
    loggedIn();
    renderHeader();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "로그아웃" })).toBeInTheDocument(),
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "로그아웃" }));
    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
  });
});
