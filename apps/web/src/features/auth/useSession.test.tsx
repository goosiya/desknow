import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authMe } from "@/lib/api-client";
import { useSession } from "./useSession";

// useSession 테스트 (Story 3.7 — AC5). authMe 를 모킹해 200=로그인·401=미로그인(null)·5xx=오류 전파를
// 검증한다. 실제 SDK(throwOnError:false)는 `{ data, response }`를 돌려주므로 response.status를 함께 모킹.
vi.mock("@/lib/api-client", () => ({ authMe: vi.fn() }));

const mockAuthMe = vi.mocked(authMe);

/** authMe SDK 응답 모킹(데이터 + Response.status). */
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

describe("useSession (AC5)", () => {
  it("200 → 로그인 사용자(UserPublic)", async () => {
    const user = { id: "u1", email: "a@b.com", role: "booker" };
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

  it("5xx → 미로그인이 아니라 오류 전파(isError, 로그아웃 오인 방지)", async () => {
    mockAuthMe.mockResolvedValue(authResult(500, undefined));

    const { result } = renderHook(() => useSession(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined(); // null(미로그인) 아님
  });
});
