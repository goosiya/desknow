import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// admin 프론트 테스트 러너 (Story 8.1 — web 미러). 컴포넌트/훅 상태 테스트라 jsdom 환경 +
// React 플러그인(JSX 변환)이 필요하다. setup에서 @testing-library/jest-dom 매처를 전역 등록한다.
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
