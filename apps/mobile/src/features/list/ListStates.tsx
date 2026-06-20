import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

// 목록/즐겨찾기 공용 상태 카드 (Story 9.1 — 5상태 매트릭스). 안내(빈/미활성)·재시도(에러)·미로그인을
// 한 톤으로 그린다(막다른 화면 금지 — 카피는 친절한 해요체).

/** 안내 카드(빈/미활성/미로그인 안내) — 제목(선택) + 본문 + 액션(선택). */
export function InfoCard({
  title,
  text,
  action,
}: {
  title?: string;
  text: string;
  action?: { label: string; onPress: () => void };
}) {
  return (
    <View style={styles.card}>
      {title ? (
        <ThemedText type="h3" themeColor="cardForeground" style={styles.center}>
          {title}
        </ThemedText>
      ) : null}
      <ThemedText type="bodySm" themeColor="textSecondary" style={styles.center}>
        {text}
      </ThemedText>
      {action ? (
        <Pressable onPress={action.onPress} accessibilityRole="button" style={styles.primaryButton}>
          <ThemedText type="label" themeColor="primaryForeground">
            {action.label}
          </ThemedText>
        </Pressable>
      ) : null}
    </View>
  );
}

/** 에러 카드 — 안내 + 다시 시도(막다른 화면 금지). */
export function RetryCard({ title, onRetry }: { title: string; onRetry: () => void }) {
  return (
    <View style={styles.card}>
      <ThemedText type="h3" themeColor="cardForeground" style={styles.center}>
        {title}
      </ThemedText>
      <Pressable onPress={onRetry} accessibilityRole="button" style={styles.primaryButton}>
        <ThemedText type="label" themeColor="primaryForeground">
          다시 시도
        </ThemedText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: Spacing[2],
    padding: Spacing[6],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
    alignItems: 'center',
  },
  center: { textAlign: 'center' },
  primaryButton: {
    minHeight: 44,
    marginTop: Spacing[1],
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
});
