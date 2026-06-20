// SessionKeeper 테스트 — 슬라이딩 연장 + 만료 리다이렉트 + 수동 로그아웃 제외(KTH 2026-06-18).
// useSession·next/navigation·authRefresh 를 모킹하고 user 전이를 rerender 로 구동한다.
import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionKeeper } from "./SessionKeeper";
import { markManualLogout, consumeManualLogout } from "./sessionExpiry";

const replace = vi.fn();
// pathname·세션 값을 테스트별 제어(vi.hoisted 로 mock 팩토리에서 참조).
const { pathnameRef, sessionRef } = vi.hoisted(() => ({
  pathnameRef: { current: "/reservations" },
  sessionRef: { current: null as unknown },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathnameRef.current,
}));
vi.mock("./useSession", () => ({
  useSession: () => ({ data: sessionRef.current }),
}));
const { authRefreshMock } = vi.hoisted(() => ({
  authRefreshMock: vi.fn(() => Promise.resolve({ response: { ok: true } })),
}));
vi.mock("@/lib/api-client", () => ({ authRefresh: authRefreshMock }));

beforeEach(() => {
  vi.clearAllMocks();
  consumeManualLogout(); // 잔여 플래그 제거
  pathnameRef.current = "/reservations";
  sessionRef.current = null;
});

afterEach(() => {
  vi.useRealTimers();
});

describe("SessionKeeper 만료 처리", () => {
  it("로그인→null 전이(만료) 시 /login?expired=1&next= 로 보낸다", () => {
    sessionRef.current = { id: "u1", email: "a@b.com", role: "booker" };
    const { rerender } = render(<SessionKeeper />);
    // 토큰 만료 → 세션 null 전이.
    sessionRef.current = null;
    rerender(<SessionKeeper />);
    expect(replace).toHaveBeenCalledWith(
      "/login?expired=1&next=%2Freservations",
    );
  });

  it("수동 로그아웃이면 만료 리다이렉트를 하지 않는다", () => {
    sessionRef.current = { id: "u1", email: "a@b.com", role: "booker" };
    const { rerender } = render(<SessionKeeper />);
    markManualLogout(); // 직접 로그아웃 표시
    sessionRef.current = null;
    rerender(<SessionKeeper />);
    expect(replace).not.toHaveBeenCalled();
  });

  it("최초부터 미로그인(전이 아님)이면 리다이렉트하지 않는다", () => {
    sessionRef.current = null;
    render(<SessionKeeper />);
    expect(replace).not.toHaveBeenCalled();
  });

  it("이미 /login 이면 만료 전이에도 리다이렉트하지 않는다(루프 방지)", () => {
    pathnameRef.current = "/login";
    sessionRef.current = { id: "u1", email: "a@b.com", role: "booker" };
    const { rerender } = render(<SessionKeeper />);
    sessionRef.current = null;
    rerender(<SessionKeeper />);
    expect(replace).not.toHaveBeenCalled();
  });
});

describe("SessionKeeper 슬라이딩 연장", () => {
  it("활동이 있으면 주기마다 authRefresh 로 토큰을 연장한다", () => {
    vi.useFakeTimers();
    sessionRef.current = { id: "u1", email: "a@b.com", role: "booker" };
    render(<SessionKeeper />);
    // 사용자 인터랙션 발생.
    window.dispatchEvent(new Event("pointerdown"));
    vi.advanceTimersByTime(10 * 60_000); // 갱신 주기 경과
    expect(authRefreshMock).toHaveBeenCalledTimes(1);
    expect(authRefreshMock).toHaveBeenCalledWith({ body: {}, throwOnError: false });
  });

  it("활동이 없으면(유휴) 갱신하지 않아 자연 만료를 허용한다", () => {
    vi.useFakeTimers();
    sessionRef.current = { id: "u1", email: "a@b.com", role: "booker" };
    render(<SessionKeeper />);
    // 인터랙션 없이 주기 경과.
    vi.advanceTimersByTime(10 * 60_000);
    expect(authRefreshMock).not.toHaveBeenCalled();
  });
});
