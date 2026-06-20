// vitest 전역 setup (Story 8.1 — web 미러). @testing-library/jest-dom 매처(toBeInTheDocument 등)를
// expect에 등록하고, 각 테스트 뒤 DOM을 정리한다.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
