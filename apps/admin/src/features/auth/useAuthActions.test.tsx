import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authLogin, authLogout, authMe } from "@/lib/api-client";
import { useAdminLogin } from "./useAuthActions";

// useAdminLogin 테스트 (Story 8.1, AC1·AC2·AC3). 로그인 성공/실패/비-admin 분기를 결정적으로
// 검증한다(authMe role 확인·비-admin 즉시 로그아웃).
vi.mock("@/lib/api-client", () => ({
  authLogin: vi.fn(),
  authLogout: vi.fn(),
  authMe: vi.fn(),
}));

const mockLogin = vi.mocked(authLogin);
const mockLogout = vi.mocked(authLogout);
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
});

describe("useAdminLogin", () => {
  it("성공 & admin → 'ok'(로그아웃 호출 안 함)", async () => {
    mockLogin.mockResolvedValue(result(200, { access_token: "a", refresh_token: "r" }));
    mockMe.mockResolvedValue(result(200, { id: "u1", email: "a@b.com", role: "admin" }));

    const { result: hook } = renderHook(() => useAdminLogin(), { wrapper });
    const outcome = await hook.current.mutateAsync({ email: "a@b.com", password: "p" });

    expect(outcome).toBe("ok");
    expect(mockLogout).not.toHaveBeenCalled();
  });

  it("401 → 'invalid'(me 조회 안 함)", async () => {
    mockLogin.mockResolvedValue(result(401));

    const { result: hook } = renderHook(() => useAdminLogin(), { wrapper });
    const outcome = await hook.current.mutateAsync({ email: "a@b.com", password: "x" });

    expect(outcome).toBe("invalid");
    expect(mockMe).not.toHaveBeenCalled();
  });

  it("성공 & 비-admin → 'not-admin' + 즉시 로그아웃", async () => {
    mockLogin.mockResolvedValue(result(200, { access_token: "a", refresh_token: "r" }));
    mockMe.mockResolvedValue(result(200, { id: "u1", email: "a@b.com", role: "booker" }));
    mockLogout.mockResolvedValue(result(204) as never);

    const { result: hook } = renderHook(() => useAdminLogin(), { wrapper });
    const outcome = await hook.current.mutateAsync({ email: "a@b.com", password: "p" });

    expect(outcome).toBe("not-admin");
    await waitFor(() => expect(mockLogout).toHaveBeenCalledTimes(1));
  });

  it("로그인 5xx → 'network'", async () => {
    mockLogin.mockResolvedValue(result(503));

    const { result: hook } = renderHook(() => useAdminLogin(), { wrapper });
    const outcome = await hook.current.mutateAsync({ email: "a@b.com", password: "p" });

    expect(outcome).toBe("network");
  });

  it("fetch reject(서버 단절) → 'network'", async () => {
    mockLogin.mockRejectedValue(new Error("network down"));

    const { result: hook } = renderHook(() => useAdminLogin(), { wrapper });
    const outcome = await hook.current.mutateAsync({ email: "a@b.com", password: "p" });

    expect(outcome).toBe("network");
  });
});
