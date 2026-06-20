import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useGeolocation } from "./useGeolocation";

// useGeolocation 단위 테스트 (Story 3.5 — AC1·AC3). navigator.geolocation 을 모킹해 granted/
// denied/unsupported 상태 전이를 검증한다. enabled=false 면 요청하지 않는다(지도/지역 모드).

const original = Object.getOwnPropertyDescriptor(navigator, "geolocation");
const originalPermissions = Object.getOwnPropertyDescriptor(navigator, "permissions");

afterEach(() => {
  if (original) Object.defineProperty(navigator, "geolocation", original);
  // permissions 는 jsdom 기본 미지원(레거시 경로) — 새 테스트가 모킹한 뒤 원복하지 않으면 다른
  // 테스트가 영향받는다. 원래 디스크립터로 복원하거나, 없었으면 미지원 상태로 되돌린다.
  if (originalPermissions) {
    Object.defineProperty(navigator, "permissions", originalPermissions);
  } else {
    Object.defineProperty(navigator, "permissions", {
      value: undefined,
      configurable: true,
      writable: true,
    });
  }
  vi.restoreAllMocks();
});

function setGeolocation(value: unknown): void {
  Object.defineProperty(navigator, "geolocation", {
    value,
    configurable: true,
    writable: true,
  });
}

// Permissions API 모킹 — state 로 query 결과를 고정한다(change 리스너는 no-op). query=undefined 면
// Permissions API 미지원(레거시 경로)을 모사한다.
function setPermissions(state: PermissionState | null): void {
  const value =
    state === null
      ? undefined
      : {
          query: vi.fn(async () => ({
            state,
            addEventListener: vi.fn(),
            removeEventListener: vi.fn(),
          })),
        };
  Object.defineProperty(navigator, "permissions", {
    value,
    configurable: true,
    writable: true,
  });
}

describe("useGeolocation (AC1·AC3)", () => {
  it("enabled=false 면 요청하지 않고 idle 에 머문다", () => {
    const getCurrentPosition = vi.fn();
    setGeolocation({ getCurrentPosition });
    const { result } = renderHook(() => useGeolocation(false));
    expect(result.current.status).toBe("idle");
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  it("허용 시 granted + 좌표를 노출한다", async () => {
    setGeolocation({
      getCurrentPosition: (success: PositionCallback) =>
        success({
          coords: { latitude: 37.5, longitude: 127.0 },
        } as GeolocationPosition),
    });
    const { result } = renderHook(() => useGeolocation(true));
    await waitFor(() => expect(result.current.status).toBe("granted"));
    expect(result.current.coords).toEqual({ lat: 37.5, lng: 127.0 });
  });

  it("거부 시 denied(AC3 비활성 신호)", async () => {
    setGeolocation({
      getCurrentPosition: (
        _success: PositionCallback,
        error: PositionErrorCallback,
      ) => error({ code: 1, message: "denied" } as GeolocationPositionError),
    });
    const { result } = renderHook(() => useGeolocation(true));
    await waitFor(() => expect(result.current.status).toBe("denied"));
    expect(result.current.coords).toBeUndefined();
  });

  it("navigator.geolocation 부재 시 unsupported(AC3 비활성 신호)", async () => {
    setGeolocation(undefined);
    const { result } = renderHook(() => useGeolocation(true));
    await waitFor(() => expect(result.current.status).toBe("unsupported"));
  });

  it("탭 복귀(focus) 시 위치를 다시 시도한다 — 설정 변경 즉시 반영", async () => {
    // 처음엔 거부(설정 OFF) → 사용자가 설정에서 켜고 돌아옴 → focus 에 재시도해 granted 로.
    let mode: "granted" | "denied" = "denied";
    const getCurrentPosition = vi.fn(
      (success: PositionCallback, error?: PositionErrorCallback | null) => {
        if (mode === "granted") {
          success({
            coords: { latitude: 37.5, longitude: 127.0 },
          } as GeolocationPosition);
        } else {
          error?.({ code: 1, message: "denied" } as GeolocationPositionError);
        }
      },
    );
    setGeolocation({ getCurrentPosition });

    const { result } = renderHook(() => useGeolocation(true));
    await waitFor(() => expect(result.current.status).toBe("denied"));

    // 설정을 허용으로 바꾼 뒤 탭 복귀(focus) → 재측정 성공.
    mode = "granted";
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(result.current.status).toBe("granted"));
    expect(result.current.coords).toEqual({ lat: 37.5, lng: 127.0 });
  });
});

describe("useGeolocation 권한 판정 신호 (permissionResolved — KTH 2026-06-19)", () => {
  it("레거시 경로(Permissions API 미지원)에서도 판정 후 permissionResolved=true", async () => {
    setPermissions(null); // 레거시 경로
    setGeolocation({
      getCurrentPosition: (success: PositionCallback) =>
        success({
          coords: { latitude: 37.5, longitude: 127.0 },
        } as GeolocationPosition),
    });
    const { result } = renderHook(() => useGeolocation(true));
    await waitFor(() => expect(result.current.permissionResolved).toBe(true));
    expect(result.current.status).toBe("granted");
  });

  it("Permissions API granted → 자동 측정 + permission=granted + resolved", async () => {
    setPermissions("granted");
    const getCurrentPosition = vi.fn((success: PositionCallback) =>
      success({
        coords: { latitude: 37.5, longitude: 127.0 },
      } as GeolocationPosition),
    );
    setGeolocation({ getCurrentPosition });
    const { result } = renderHook(() => useGeolocation(true));
    await waitFor(() => expect(result.current.permission).toBe("granted"));
    expect(result.current.permissionResolved).toBe(true);
    expect(getCurrentPosition).toHaveBeenCalled();
  });

  it("Permissions API prompt → 자동 측정 안 함(깜짝 프롬프트 금지)·idle·resolved", async () => {
    setPermissions("prompt");
    const getCurrentPosition = vi.fn();
    setGeolocation({ getCurrentPosition });
    const { result } = renderHook(() => useGeolocation(true));
    await waitFor(() => expect(result.current.permissionResolved).toBe(true));
    expect(result.current.permission).toBe("prompt");
    expect(result.current.status).toBe("idle");
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  it("Permissions API denied → 측정 안 함·permission=denied·resolved", async () => {
    setPermissions("denied");
    const getCurrentPosition = vi.fn();
    setGeolocation({ getCurrentPosition });
    const { result } = renderHook(() => useGeolocation(true));
    await waitFor(() => expect(result.current.permissionResolved).toBe(true));
    expect(result.current.permission).toBe("denied");
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });

  it("geolocation 부재(unsupported) 도 permissionResolved=true", async () => {
    setGeolocation(undefined);
    const { result } = renderHook(() => useGeolocation(true));
    await waitFor(() => expect(result.current.status).toBe("unsupported"));
    expect(result.current.permissionResolved).toBe(true);
  });
});
