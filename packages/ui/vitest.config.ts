import { defineConfig } from 'vitest/config';

// 토큰 parity 테스트용 최소 설정 (Story 1.6).
// 프론트 테스트 러너(vitest)를 모노레포에서 처음 확립한다.
// 토큰은 순수 데이터이므로 DOM 불필요 → node 환경.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
