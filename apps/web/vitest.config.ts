import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// web 프론트 테스트 러너 (Story 3.2 — 프론트 vitest 최초 도입).
// packages/ui 는 node 환경 parity 테스트만 쓰지만, web 은 컴포넌트 상태 테스트가 있어
// jsdom 환경 + React 플러그인(JSX 변환)이 필요하다. setup 에서 @testing-library/jest-dom
// 매처(toBeInTheDocument 등)를 전역 등록한다. @/ 별칭은 tsconfig paths 와 동일하게 매핑한다.
const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(rootDir, "src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
