import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authLogin, authMe } from "@/lib/api-client";
import LoginPage from "./page";

// 로그인 폼 테스트 (Story 8.1, AC2). 잘못된 자격 → enumeration 비노출 단일 카피. (성공/비-admin
// 분기 로직은 useAuthActions.test에서 결정적으로 검증 — 여기선 폼이 결과 카피를 노출하는지 본다.)
vi.mock("@/lib/api-client", () => ({
  authLogin: vi.fn(),
  authLogout: vi.fn(),
  authMe: vi.fn(),
}));

const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

const mockLogin = vi.mocked(authLogin);
const mockMe = vi.mocked(authMe);

function result(status: number, data: unknown = undefined) {
  return { data, response: new Response(null, { status }) } as never;
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  // 세션 쿼리(useAdminSession)는 미로그인(401)으로 두어 마운트 리다이렉트가 없게 한다.
  mockMe.mockResolvedValue(result(401));
});

describe("LoginPage", () => {
  it("401 → 자격 오류 단일 카피 노출(이동 없음)", async () => {
    mockLogin.mockResolvedValue(result(401));
    const user = userEvent.setup();

    render(<LoginPage />, { wrapper });
    await user.type(screen.getByLabelText("이메일"), "a@b.com");
    await user.type(screen.getByLabelText("비밀번호"), "wrong");
    await user.click(screen.getByRole("button", { name: "로그인" }));

    expect(
      await screen.findByText("이메일 또는 비밀번호가 올바르지 않습니다.")
    ).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
