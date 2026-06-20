// DeskNow 디자인 토큰 단일 출처 — "에너제틱 만다린" (Story 1.6).
//
// ⚠️ 이 파일은 **플랫폼 무관 순수 데이터/타입**만 담는다.
//    React·react-dom·react-native·DOM API를 절대 import 하지 않는다
//    (web/admin/RN 세 표면이 모두 안전하게 import 할 수 있어야 하므로).
//
// 값은 DESIGN.md frontmatter 정본 그대로다. web/admin은 이 값을 미러한
// `packages/config/tailwind-preset.css`(CSS 변수)로 소비하고, RN은 이 파일을
// 직접 import 해서 소비한다. CSS ↔ TS 드리프트는 parity 테스트
// (`tokens.parity.test.ts`)가 강제로 막는다.
//
// 라이트 전용: 다크 값/`dark` 키는 두지 않는다(시맨틱 구조만 — AC2).
// 다크 확장은 후속에 별도 스킴으로 추가한다.

/**
 * 색 토큰 (라이트 전용).
 *
 * shadcn 시맨틱 키 규약(`primary`/`background`/`ring`…)을 그대로 따르므로
 * 후속 `shadcn add` 컴포넌트가 자동으로 만다린 토큰을 입는다.
 *
 * 색 사용 규약(소비 컴포넌트가 지킬 계약 — DESIGN Do/Don't):
 *  - `primary`(만다린)는 **상태 의미로 쓰지 않는다.** 상태는 의미색 사용.
 *  - 의미색(`success`/`pinAvailable`/`pinFull`/`destructive`)은 **색만으로
 *    상태를 표현하지 않는다** — 반드시 아이콘/텍스트를 동반한다(접근성).
 */
export const colors = {
  // 면/본문
  background: '#FFFCF4', // 크림 배경(순백 아님)
  foreground: '#28200F', // 본문 텍스트
  card: '#FFFFFF', // 카드 면(크림 위에 뜸)
  cardForeground: '#28200F',
  popover: '#FFFFFF',
  popoverForeground: '#28200F',
  // 주요 액션 — 상태 의미로 사용 금지
  primary: '#FF8A1E',
  primaryForeground: '#3A2400',
  // 보조 칩·배너 배경
  secondary: '#FFF0D6',
  secondaryForeground: '#3A2400',
  // 강조 배지
  accent: '#FFC24D',
  accentForeground: '#3A2400',
  // 면색·보조 텍스트
  muted: '#F4EDDF',
  mutedForeground: '#7A6E55',
  // 경계선·인풋
  border: '#F4E2C2',
  input: '#F4E2C2',
  // 포커스 링(크림 배경 대비 ≥3:1 — AC3)
  ring: '#D86E0A',
  // 취소·삭제·즐겨찾기 하트 활성
  destructive: '#CC3328',
  destructiveForeground: '#FFFFFF',
  // 의미색(만다린과 색상환 분리) — 아이콘/텍스트 동반 필수
  success: '#157F45', // = pinAvailable: 예약 가능/성공
  pinAvailable: '#157F45',
  pinFull: '#7E7466', // 마감(웜 그레이)
} as const;

/** 단일 타이포 스텝의 형상. fontSize/lineHeight 는 단위 없는 숫자(px/배수). */
export type TypographyStep = {
  /** px */
  fontSize: number;
  fontWeight: number;
  /** 배수(unitless) — 한글 가독성을 위해 본문은 1.6 하한 */
  lineHeight: number;
  /** 선택: em 단위 자간 */
  letterSpacing?: string;
};

/**
 * 타이포 램프 (Pretendard).
 * 본문 행간 1.6 은 한글 가독성 하한 — 줄이지 말 것.
 */
export const typography = {
  display: { fontSize: 32, fontWeight: 700, lineHeight: 1.3, letterSpacing: '-0.01em' },
  h1: { fontSize: 24, fontWeight: 700, lineHeight: 1.4, letterSpacing: '-0.01em' },
  h2: { fontSize: 20, fontWeight: 600, lineHeight: 1.45 },
  h3: { fontSize: 18, fontWeight: 600, lineHeight: 1.5 },
  body: { fontSize: 16, fontWeight: 400, lineHeight: 1.6 },
  bodySm: { fontSize: 14, fontWeight: 400, lineHeight: 1.6 },
  label: { fontSize: 14, fontWeight: 500, lineHeight: 1.4 },
  caption: { fontSize: 12, fontWeight: 400, lineHeight: 1.45 },
} as const satisfies Record<string, TypographyStep>;

/**
 * spacing 스텝 (4px 기반, px 숫자).
 * Tailwind v4 기본 스케일과 동일하므로 web 은 재정의하지 않는다(RN 소비용).
 */
export const spacing = {
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
  16: 64,
} as const;

/** radius — CSS rem 문자열(web/admin preset 미러용). */
export const radius = {
  sm: '0.25rem',
  md: '0.375rem',
  DEFAULT: '0.5rem',
  lg: '0.5rem',
  xl: '0.75rem', // 바텀시트 상단
  full: '9999px', // 배지·FAB
} as const;

/** radius — RN 소비용 px 숫자(가변 rem 불가). radius 와 1:1. */
export const radiusPx = {
  sm: 4,
  md: 6,
  DEFAULT: 8,
  lg: 8,
  xl: 12,
  full: 9999,
} as const;

/**
 * elevation — CSS `box-shadow` 문자열(DESIGN 값 그대로).
 * 위계 장식용 그림자 금지: 기본 면은 flat, 그림자는 sheet/dialog/toast/fab 에만.
 * RN 은 `boxShadow` 스타일 prop(RN 0.76+)으로 동일 문자열을 소비할 수 있다.
 */
export const elevation = {
  flat: 'none',
  sheet: '0 -4px 24px rgba(40,32,15,0.12)',
  dialog: '0 8px 32px rgba(40,32,15,0.16)',
  toast: '0 4px 16px rgba(40,32,15,0.14)',
  fab: '0 4px 12px rgba(40,32,15,0.18)',
} as const;

/** 접근성 하한선 (AC3). */
export const a11y = {
  /** 키보드 포커스 링 색(크림 대비 ≥3:1) */
  focusRing: '#D86E0A',
  /** 터치 타겟 최소 크기 */
  touchTarget: { ios: 44, android: 48 },
  /** 모션: reduced-motion 에서도 보존하는 기능 피드백 상한(ms) */
  motion: { functionalFeedbackMaxMs: 100 },
} as const;

/** 토큰 전체를 한 객체로도 노출(소비처 편의). */
export const tokens = {
  colors,
  typography,
  spacing,
  radius,
  radiusPx,
  elevation,
  a11y,
} as const;

export type ColorToken = keyof typeof colors;
export type TypographyToken = keyof typeof typography;
export type SpacingToken = keyof typeof spacing;
export type RadiusToken = keyof typeof radius;
export type ElevationToken = keyof typeof elevation;
export type Tokens = typeof tokens;
