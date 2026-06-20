import { StyleSheet, Text, type TextProps } from 'react-native';

import { Fonts, ThemeColor } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

// DESIGN 타이포 램프 (Pretendard). lineHeight 는 RN 이므로 px(배수 환산값).
// 본문 행간 1.6(=16*1.6≈26) 은 한글 가독성 하한 — 줄이지 말 것.
export type ThemedTextType =
  | 'display'
  | 'h1'
  | 'h2'
  | 'h3'
  | 'body'
  | 'bodySm'
  | 'label'
  | 'caption';

export type ThemedTextProps = TextProps & {
  type?: ThemedTextType;
  themeColor?: ThemeColor;
};

export function ThemedText({ style, type = 'body', themeColor, ...rest }: ThemedTextProps) {
  const theme = useTheme();

  return (
    <Text style={[{ color: theme[themeColor ?? 'text'] }, styles[type], style]} {...rest} />
  );
}

const styles = StyleSheet.create({
  display: { fontFamily: Fonts?.bold, fontSize: 32, lineHeight: 42, letterSpacing: -0.32 },
  h1: { fontFamily: Fonts?.bold, fontSize: 24, lineHeight: 34, letterSpacing: -0.24 },
  h2: { fontFamily: Fonts?.semibold, fontSize: 20, lineHeight: 29 },
  h3: { fontFamily: Fonts?.semibold, fontSize: 18, lineHeight: 27 },
  body: { fontFamily: Fonts?.sans, fontSize: 16, lineHeight: 26 },
  bodySm: { fontFamily: Fonts?.sans, fontSize: 14, lineHeight: 22 },
  label: { fontFamily: Fonts?.medium, fontSize: 14, lineHeight: 20 },
  caption: { fontFamily: Fonts?.sans, fontSize: 12, lineHeight: 17 },
});
