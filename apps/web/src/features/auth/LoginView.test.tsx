import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authLogin } from "@/lib/api-client";
import { LoginView } from "./LoginView";

// LoginView 테스트 — 제출 시 authLogin 호출, 401=자격 카피 인라인, 성공=세션 무효화+리다이렉트.
// next/navigation 과 SDK 를 모킹한다(라우팅·백엔드 부재 환경).
const replace = vi.fn();
const refresh = vi.fn();
// 검색 파라미터를 테스트별로 제어(?expired=1·?next= 등) — vi.hoisted 로 끌어올림.
const { searchParamsRef } = vi.hoisted(() => ({ searchParamsRef: { current: "" } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
  useSearchParams: () => new URLSearchParams(searchParamsRef.current),
}));

vi.mock("@/lib/api-client", () => ({
  authLogin: vi.fn(),
  authLogout: vi.fn(),
  authRegister: vi.fn(),
}));

const mockLogin = vi.mocked(authLogin);

function ok() {
  return { data: {}, error: undefined, response: new Response(null, { status: 200 }) };
}
function unauthorized() {
  return {
    data: undefined,
    error: { detail: { code: "UNAUTHENTICATED", message: "" } },
    response: new Response(null, { status: 401 }),
  };
}

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactNode = <LoginView />;
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

async function fillAndSubmit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("이메일"), "a@b.com");
  await user.type(screen.getByLabelText("비밀번호"), "Passw0rd!");
  await user.click(screen.getByRole("button", { name: "로그인" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsRef.current = ""; // 기본: 파라미터 없음(직접 로그인 진입)
});

describe("LoginView", () => {
  it("?expired=1 진입 시 세션 만료 안내를 보인다(직접 진입엔 미표시)", async () => {
    searchParamsRef.current = "expired=1&next=/reservations";
    renderView();
    expect(
      await screen.findByText("로그인 시간이 만료됐어요. 다시 로그인해 주세요."),
    ).toBeInTheDocument();
  });

  it("expired 파라미터가 없으면 만료 안내를 띄우지 않는다", () => {
    renderView();
    expect(
      screen.queryByText("로그인 시간이 만료됐어요. 다시 로그인해 주세요."),
    ).toBeNull();
  });

  it("성공 → 세션 무효화 후 홈으로 replace", async () => {
    mockLogin.mockResolvedValue(ok() as never);
    renderView();
    await fillAndSubmit();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(mockLogin).toHaveBeenCalledWith({
      body: { email: "a@b.com", password: "Passw0rd!" },
    });
  });

  it("401 → 자격 오류 카피 인라인(막다른 화면 금지: 폼 유지)", async () => {
    mockLogin.mockResolvedValue(unauthorized() as never);
    renderView();
    await fillAndSubmit();
    await waitFor(() =>
      expect(
        screen.getByText("이메일 또는 비밀번호가 올바르지 않아요."),
      ).toBeInTheDocument(),
    );
    expect(replace).not.toHaveBeenCalled();
  });

  it("네트워크 단절(fetch reject) → 표준 단절 카피", async () => {
    mockLogin.mockRejectedValue(new TypeError("Failed to fetch"));
    renderView();
    await fillAndSubmit();
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("네트워크 연결이 끊겼어요"),
    );
  });
});
