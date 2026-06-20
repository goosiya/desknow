import {
  onlineManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { authMe } from "@/lib/api-client";
import {
  clearPendingSignup,
  setPendingSignup,
} from "@/features/auth/pendingSignup";
import { ProviderGuard } from "./ProviderGuard";

// ProviderGuard 테스트 (인계 3 — provider 웹 표면 역할 가드). 미로그인→로그인 / booker→홈 리다이렉트,
// provider·가입보류(pendingSignup)는 통과, 세션 판별 실패는 재시도.
vi.mock("@/lib/api-client", () => ({
  authMe: vi.fn(),
}));

// next/navigation — replace 호출만 단언하면 충분(실 라우팅은 통합/E2E 영역).
const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  usePathname: () => "/provider/room",
}));

const mockAuthMe = vi.mocked(authMe);

function asProvider() {
  mockAuthMe.mockResolvedValue({
    data: { id: "p1", role: "provider" },
    response: new Response(null, { status: 200 }),
  } as never);
}
function asBooker() {
  mockAuthMe.mockResolvedValue({
    data: { id: "b1", role: "booker" },
    response: new Response(null, { status: 200 }),
  } as never);
}
function loggedOut() {
  mockAuthMe.mockResolvedValue({
    data: undefined,
    response: new Response(null, { status: 401 }),
  } as never);
}

function renderGuard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactNode = (
    <ProviderGuard>
      <p>제공자 전용 콘텐츠</p>
    </ProviderGuard>
  );
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  clearPendingSignup();
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
  onlineManager.setOnline(true);
});
afterEach(() => {
  clearPendingSignup();
});

describe("역할 가드 (인계 3)", () => {
  it("provider → 콘텐츠 통과(리다이렉트 없음)", async () => {
    asProvider();
    renderGuard();
    expect(await screen.findByText("제공자 전용 콘텐츠")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("미로그인 → /login?next= 로 리다이렉트(콘텐츠 미노출)", async () => {
    loggedOut();
    renderGuard();
    // 리다이렉트가 일어날 때까지 대기(effect). 복귀 경로를 ?next= 로 싣는다.
    await vi.waitFor(() =>
      expect(mockReplace).toHaveBeenCalledWith(
        "/login?next=%2Fprovider%2Froom",
      ),
    );
    expect(screen.queryByText("제공자 전용 콘텐츠")).not.toBeInTheDocument();
  });

  it("booker → 홈(/)으로 리다이렉트(콘텐츠 미노출)", async () => {
    asBooker();
    renderGuard();
    await vi.waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/"));
    expect(screen.queryByText("제공자 전용 콘텐츠")).not.toBeInTheDocument();
  });

  it("가입 보류(pendingSignup) → 미로그인이라도 통과(가입+등록 원자 흐름)", async () => {
    loggedOut();
    setPendingSignup({ email: "p@test.desknow", password: "Test1234!" });
    renderGuard();
    expect(await screen.findByText("제공자 전용 콘텐츠")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("세션 판별 실패(5xx) → 리다이렉트 아닌 오류·재시도(로그아웃 오인 금지)", async () => {
    mockAuthMe.mockResolvedValue({
      data: undefined,
      response: new Response(null, { status: 500 }),
    } as never);
    renderGuard();
    expect(
      await screen.findByText("로그인 상태를 확인하지 못했어요."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
