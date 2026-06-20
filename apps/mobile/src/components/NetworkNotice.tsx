import { StyleSheet, View, type ViewStyle } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

// 네트워크 단절 표시 — 웹 NetworkNotice.tsx RN 포팅 (Story 9.1 — 5상태 매트릭스).
//
// 단절 동안 떠 있다가 연결되면 사라지는 인라인 배너(토스트 라이브러리 미도입 — 상태가 곧 표시).
// 카피는 확정 문구 고정([[terminology-network-disconnect-not-offline]] — "오프라인" 금지). a11y:
// accessibilityRole="alert" + accessibilityLiveRegion="polite"로 스크린리더 공지. 배치는 style prop으로
// 오버라이드(지도=상단 떠 있는 배너, 목록=인라인 상단).
export function NetworkNotice({ style }: { style?: ViewStyle }) {
  return (
    <View
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={[styles.banner, style]}
    >
      <ThemedText type="bodySm" themeColor="secondaryForeground">
        네트워크 연결이 끊겼어요. 연결되면 다시 보여드릴게요.
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.secondary,
    paddingHorizontal: Spacing[4],
    paddingVertical: Spacing[2],
  },
});
