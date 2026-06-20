import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useOnboarding } from "./useOnboarding";

// useOnboarding 단위 테스트 (Story 3.9 — AC2·AC3). 첫 방문 판별·영속·graceful 실패.
//
// ⚠️ localStorage 누수 반복함정(3.7/3.8 학습): jsdom localStorage 는 전역 공유라 미정리 시 다음
//    테스트가 "본 적 있음"으로 오염된다 → beforeEach 에서 clear().
const ONBOARDING_SEEN_KEY = "desknow:onboarding:seen";

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useOnboarding (AC2·AC3)", () => {
  it("플래그 없으면 effect 후 shouldShow=true (첫 방문 노출)", async () => {
    const { result } = renderHook(() => useOnboarding());
    // setShouldShow 는 queueMicrotask 로 이월된다(set-state-in-effect 회피) → waitFor 로 flush.
    await waitFor(() => expect(result.current.shouldShow).toBe(true));
  });

  it("플래그 있으면 shouldShow=false (재방문 무노출)", () => {
    localStorage.setItem(ONBOARDING_SEEN_KEY, "1");
    const { result } = renderHook(() => useOnboarding());
    expect(result.current.shouldShow).toBe(false);
  });

  it("dismiss() 는 localStorage 에 영속하고 shouldShow=false 로 만든다", async () => {
    const { result } = renderHook(() => useOnboarding());
    await waitFor(() => expect(result.current.shouldShow).toBe(true));

    act(() => {
      result.current.dismiss();
    });

    expect(localStorage.getItem(ONBOARDING_SEEN_KEY)).toBe("1");
    expect(result.current.shouldShow).toBe(false);
  });

  it("close() 는 영속하지 않고 shouldShow=false 로만 만든다(다음 방문 재노출)", async () => {
    const { result } = renderHook(() => useOnboarding());
    await waitFor(() => expect(result.current.shouldShow).toBe(true));

    act(() => {
      result.current.close();
    });

    expect(localStorage.getItem(ONBOARDING_SEEN_KEY)).toBeNull();
    expect(result.current.shouldShow).toBe(false);
  });

  it("localStorage.getItem 이 throw 해도 graceful — 미표시", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    const { result } = renderHook(() => useOnboarding());
    // throw 를 삼키고 표시하지 않는다(콘솔 에러·막다른 화면 금지).
    expect(result.current.shouldShow).toBe(false);
  });
});
