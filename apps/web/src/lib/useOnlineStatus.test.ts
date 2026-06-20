import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useOnlineStatus } from "./useOnlineStatus";

// useOnlineStatus 단위 테스트 (Story 3.8 — AC1·AC2). navigator.onLine 을 모킹하고 window
// online/offline 이벤트를 디스패치해 초기값·전이·리스너 해제를 검증한다.
//
// ⚠️ vitest mock 누수 반복함정(3.7 학습): clearAllMocks 는 정의를 안 지운다. navigator.onLine 은
//    Object.defineProperty 로 덮으므로 beforeEach 에서 기본 true 로 명시 복원하고 afterEach 에서
//    원래 디스크립터를 되돌린다.
const originalOnLine = Object.getOwnPropertyDescriptor(
  globalThis.Navigator.prototype,
  "onLine",
);

function setOnLine(value: boolean): void {
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    value,
  });
}

beforeEach(() => {
  setOnLine(true); // 기본 연결됨 — 각 테스트가 필요 시 재정의
});

afterEach(() => {
  // 원래 디스크립터 복원(다른 테스트 파일로의 누수 방지).
  if (originalOnLine) {
    Object.defineProperty(
      globalThis.Navigator.prototype,
      "onLine",
      originalOnLine,
    );
  }
  vi.restoreAllMocks();
});

describe("useOnlineStatus (AC1·AC2)", () => {
  it("초기값은 navigator.onLine 을 반영한다(연결됨=true)", () => {
    setOnLine(true);
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(true);
  });

  it("초기값은 navigator.onLine 을 반영한다(단절=false)", () => {
    setOnLine(false);
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(false);
  });

  it("offline 이벤트 디스패치 시 false 로 전이한다", () => {
    setOnLine(true);
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(true);

    act(() => {
      setOnLine(false);
      window.dispatchEvent(new Event("offline"));
    });
    expect(result.current).toBe(false);
  });

  it("online 이벤트 디스패치 시 true 로 전이한다", () => {
    setOnLine(false);
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(false);

    act(() => {
      setOnLine(true);
      window.dispatchEvent(new Event("online"));
    });
    expect(result.current).toBe(true);
  });

  it("언마운트 시 online/offline 리스너를 해제한다", () => {
    const removeSpy = vi.spyOn(window, "removeEventListener");
    const { unmount } = renderHook(() => useOnlineStatus());
    unmount();
    expect(removeSpy).toHaveBeenCalledWith("online", expect.any(Function));
    expect(removeSpy).toHaveBeenCalledWith("offline", expect.any(Function));
  });
});
