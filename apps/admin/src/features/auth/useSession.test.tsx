import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authMe } from "@/lib/api-client";
import { useAdminSession, useSession } from "./useSession";

// useSession 테스트 (Story 8.1 — web 미러). authMe를 모킹해 200=로그인·401=null·5xx=오류 전파 +
// useAdminSession의 isAdmin 파생을 검증한다.
vi.mock("@/lib/api-client", () => ({ authMe: vi.fn() }));

const mockAuthMe = vi.mocked(authMe);

function authResult(status: number, data: unknown) {
  return { data, response: new Response(null, { status }) } as never;
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useSession", () => {
  it("200 → 로그인 사용자(UserPublic)", async () => {
    const user = { id: "u1", email: "a@b.com", role: "admin" };
    mockAuthMe.mockResolvedValue(authResult(200, user));

    const { result } = renderHook(() => useSession(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(user);
  });

  it("401 → null 정규화(미로그인은 에러 아님)", async () => {
    mockAuthMe.mockResolvedValue(authResult(401, undefined));

    const { result } = renderHook(() => useSession(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
    expect(result.current.isError).toBe(false);
  });

  it("5xx → 오류 전파(isError, 로그아웃 오인 방지)", async () => {
    mockAuthMe.mockResolvedValue(authResult(500, undefined));

    const { result } = renderHook(() => useSession(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });
});

describe("useAdminSession (isAdmin 파생)", () => {
  it("admin 세션 → isAdmin true", async () => {
    mockAuthMe.mockResolvedValue(authResult(200, { id: "u1", email: "a@b.com", role: "admin" }));

    const { result } = renderHook(() => useAdminSession(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.isAdmin).toBe(true);
  });

  it("booker 세션 → isAdmin false", async () => {
    mockAuthMe.mockResolvedValue(authResult(200, { id: "u1", email: "a@b.com", role: "booker" }));

    const { result } = renderHook(() => useAdminSession(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.isAdmin).toBe(false);
  });

  it("미로그인(401) → isAdmin false", async () => {
    mockAuthMe.mockResolvedValue(authResult(401, undefined));

    const { result } = renderHook(() => useAdminSession(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.isAdmin).toBe(false);
    expect(result.current.session).toBeNull();
  });
});
