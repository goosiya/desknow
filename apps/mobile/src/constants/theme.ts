/**
 * 모바일 테마 — DeskNow "에너제틱 만다린" 토큰 매핑 (Story 1.6).
 *
 * 값의 정본은 packages/ui/src/tokens.ts(@desknow/ui)이며, web/admin 과 구성상 동일하다.
 * 라이트 전용: `dark` 키/값을 두지 않는다(AC2). 색 스킴은 라이트로 고정한다.
 */

import '@/global.css';

import { Platform } from 'react-native';
import { colors, radiusPx, spacing } from '@desknow/ui';

// shadcn 시맨틱 토큰을 RN 화면이 쓰기 쉬운 이름으로 매핑(라이트 단일 세트).
export const Colors = {
  light: {
    text: colors.foreground,
    textSecondary: colors.mutedForeground,
    background: colors.background,
    card: colors.card,
    cardForeground: colors.cardForeground,
    backgroundElement: colors.muted,
    backgroundSelected: colors.secondary,
    // 보조 칩·배너(예약 가능 배지·네트워크 단절 배너·반경 토글 등) — 웹 secondary 토큰 미러.
    secondary: colors.secondary,
    secondaryForeground: colors.secondaryForeground,
    border: colors.border,
    primary: colors.primary,
    primaryForeground: colors.primaryForeground,
    ring: colors.ring,
    success: colors.success,
    pinAvailable: colors.pinAvailable,
    pinFull: colors.pinFull,
    destructive: colors.destructive,
  },
} as const;

export type ThemeColor = keyof typeof Colors.light;

// Pretendard 정적 weight(app.json expo-font 로 임베드 — dev build 필요).
// 가변 axis 불가 → weight 별 패밀리 이름으로 참조한다.
export const Fonts = Platform.select({
  default: {
    sans: 'Pretendard-Regular',
    medium: 'Pretendard-Medium',
    semibold: 'Pretendard-SemiBold',
    bold: 'Pretendard-Bold',
  },
  web: {
    sans: 'Pretendard, var(--font-display)',
    medium: 'Pretendard, var(--font-display)',
    semibold: 'Pretendard, var(--font-display)',
    bold: 'Pretendard, var(--font-display)',
  },
});

// 4px 기반 spacing — packages/ui 토큰과 일치(키는 RN 화면 가독성을 위해 숫자 스텝).
export const Spacing = {
  1: spacing[1],
  2: spacing[2],
  3: spacing[3],
  4: spacing[4],
  5: spacing[5],
  6: spacing[6],
  8: spacing[8],
  10: spacing[10],
  12: spacing[12],
  16: spacing[16],
} as const;

export const Radius = radiusPx;

export const MaxContentWidth = 800;
