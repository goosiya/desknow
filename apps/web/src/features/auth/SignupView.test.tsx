import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authLogin, authRegister } from "@/lib/api-client";
import { SignupView } from "./SignupView";
import { clearPendingSignup, getPendingSignup } from "./pendingSignup";

// SignupView 테스트 — booker=가입+자동로그인 후 리다이렉트, provider=가입 미루고 룸 화면으로 이동,
// 409=중복 카피, 422=정책/서버 message.
const replace = vi.fn();
const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh, push }),
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("@/lib/api-client", () => ({
  authRegister: vi.fn(),
  authLogin: vi.fn(),
  authLogout: vi.fn(),
}));

const mockRegister = vi.mocked(authRegister);
const mockLogin = vi.mocked(authLogin);

function created() {
  return { data: {}, error: undefined, response: new Response(null, { status: 201 }) };
}
function conflict() {
  return {
    data: undefined,
    error: { detail: { code: "EMAIL_ALREADY_REGISTERED", message: "" } },
    response: new Response(null, { status: 409 }),
  };
}
function validation(message: string) {
  return {
    data: undefined,
    error: { detail: { code: "VALIDATION_ERROR", message } },
    response: new Response(null, { status: 422 }),
  };
}

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactNode = <SignupView />;
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

async function fillAndSubmit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("이메일"), "new@b.com");
  await user.type(screen.getByLabelText("비밀번호"), "Passw0rd!");
  await user.click(screen.getByRole("button", { name: "가입하고 시작하기" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  clearPendingSignup(); // 모듈 메모리 보관소 — 테스트 격리.
});

describe("SignupView", () => {
  it("성공 → role=booker 가입 + 자동 로그인 연쇄 후 replace", async () => {
    mockRegister.mockResolvedValue(created() as never);
    mockLogin.mockResolvedValue({
      data: {},
      error: undefined,
      response: new Response(null, { status: 200 }),
    } as never);
    renderView();
    await fillAndSubmit();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(mockRegister).toHaveBeenCalledWith({
      body: { email: "new@b.com", password: "Passw0rd!", role: "booker" },
    });
    expect(mockLogin).toHaveBeenCalledWith({
      body: { email: "new@b.com", password: "Passw0rd!" },
    });
  });

  it("제공자 선택 → 가입을 미루고 정보 보관 후 룸 등록 화면으로 이동(가입은 룸 등록 시점)", async () => {
    const user = userEvent.setup();
    renderView();
    // 역할 토글에서 제공자 선택 → 버튼 라벨이 "스터디룸 정보 등록"으로 바뀐다.
    await user.click(screen.getByRole("button", { name: /제공자/ }));
    await user.type(screen.getByLabelText("이메일"), "host@b.com");
    await user.type(screen.getByLabelText("비밀번호"), "Passw0rd!");
    await user.click(screen.getByRole("button", { name: "스터디룸 정보 등록" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/provider/room"));
    // 이 단계에서는 아직 가입하지 않는다(떠도는 계정 방지 — 룸 등록 시점에 가입).
    expect(mockRegister).not.toHaveBeenCalled();
    // 가입 정보는 메모리에 보관돼 RoomForm 이 등록 시점에 사용한다.
    expect(getPendingSignup()).toEqual({ email: "host@b.com", password: "Passw0rd!" });
  });

  it("409 → 이미 가입된 이메일 카피", async () => {
    mockRegister.mockResolvedValue(conflict() as never);
    renderView();
    await fillAndSubmit();
    await waitFor(() =>
      expect(screen.getByText("이미 가입된 이메일이에요.")).toBeInTheDocument(),
    );
    expect(mockLogin).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it("422 → 서버 message 노출", async () => {
    mockRegister.mockResolvedValue(validation("비밀번호가 정책에 맞지 않아요.") as never);
    renderView();
    await fillAndSubmit();
    await waitFor(() =>
      expect(screen.getByText("비밀번호가 정책에 맞지 않아요.")).toBeInTheDocument(),
    );
  });

  it("역할 전환 시 직전 가입 에러 카피가 사라진다(stale 에러 방지 — register.reset)", async () => {
    const user = userEvent.setup();
    mockRegister.mockResolvedValue(conflict() as never);
    renderView();
    // 예약자로 제출 → 409 에러 카피 노출.
    await fillAndSubmit();
    await waitFor(() =>
      expect(screen.getByText("이미 가입된 이메일이에요.")).toBeInTheDocument(),
    );
    // 제공자로 토글 → register 에러가 리셋되어 stale 카피가 사라진다(픽스 없으면 잔존).
    await user.click(screen.getByRole("button", { name: /제공자/ }));
    await waitFor(() =>
      expect(screen.queryByText("이미 가입된 이메일이에요.")).not.toBeInTheDocument(),
    );
  });
});
