// vitest 전역 setup (Story 3.2·3.3). @testing-library/jest-dom 매처(toBeInTheDocument·
// toHaveAccessibleName 등)를 expect 에 등록한다. 각 테스트 뒤 DOM 을 정리한다.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom 미구현 브라우저 API 폴리필 (Story 3.3 — vaul 바텀시트가 사용). vaul 은 matchMedia 와
// Element.scrollIntoView 를 호출하는데 jsdom 에 없어 호출 시 throw 한다(visualViewport 는 vaul 이
// 옵셔널 가드). 물리 드래그 제스처(PointerEvent 픽셀)는 테스트 범위 밖이라 폴리필하지 않는다.
if (typeof window !== "undefined") {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
  // Radix Select(shadcn) 폴리필 (Story 3.4 — 지역 콤보). Radix 는 트리거 열림 시 pointer
  // capture API 와 ResizeObserver 를 호출하는데 jsdom 에 없어 throw 한다. 물리 포인터 제스처는
  // 검증 범위 밖이라 no-op 으로 폴리필해 콤보 열림·옵션 선택만 검증 가능하게 한다(3.3 vaul 선례).
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
    Element.prototype.setPointerCapture = vi.fn();
    Element.prototype.releasePointerCapture = vi.fn();
  }
  if (!window.ResizeObserver) {
    window.ResizeObserver = class {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
    };
  }
}

afterEach(() => {
  cleanup();
});
