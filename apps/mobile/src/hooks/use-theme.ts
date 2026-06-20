/**
 * 라이트 스킴 고정 테마 훅 (Story 1.6 — AC2).
 * DeskNow 는 라이트 전용이므로 다크 분기 없이 항상 라이트 토큰을 반환한다.
 */

import { Colors } from '@/constants/theme';

export function useTheme() {
  return Colors.light;
}
