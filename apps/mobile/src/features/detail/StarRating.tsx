import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';

// 별점 표시 — 웹 detail/StarRating.tsx RN 포팅 (Story 9.2 — AC1 · review-accessibility L61).
//
// ⚠️ 색 단독 금지: 채움(★)/빈(☆) 별 형태 + 숫자 텍스트("4/5") + a11y 라벨("별점 5점 만점에 4점")
//    3중 신호. 별 자체는 a11y 트리에서 숨기고 그룹에 단일 라벨을 둔다(별 5개 중복 낭독 방지).
//    웹 lucide Star → RN 글리프(★/☆) + 토큰 색(primary 채움 / border 빈).
export function StarRating({ rating }: { rating: number }) {
  // 방어: 서버 CHECK(1~5)가 보장하나 표시단에서도 범위를 클램프한다(깨진 데이터로 별 음수/초과 방지).
  const filled = Math.max(0, Math.min(5, Math.round(rating)));
  return (
    <View
      accessibilityRole="image"
      accessibilityLabel={`별점 5점 만점에 ${filled}점`}
      style={styles.row}
    >
      <ThemedText
        type="bodySm"
        themeColor="primary"
        accessibilityElementsHidden
        importantForAccessibility="no"
      >
        {'★'.repeat(filled)}
        <ThemedText type="bodySm" themeColor="border">
          {'☆'.repeat(5 - filled)}
        </ThemedText>
      </ThemedText>
      {/* 숫자 텍스트 병행(색·형태 외 3중 신호) — 저시력·흑백 환경 대비. */}
      <ThemedText type="caption" themeColor="textSecondary">
        {filled}/5
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: Spacing[1] },
});
