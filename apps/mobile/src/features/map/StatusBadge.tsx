import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

import type { PinStatus } from './pin';

// 예약 가능/마감 배지 — 웹 StatusBadge RN 포팅 (Story 9.1 — 색 + 아이콘 + 텍스트 3중 신호, 색 단독
// 금지). 바텀시트·목록 행이 공유한다. 가능=success(✓ 예약 가능) / 마감=pinFull(✕ 오늘 마감).
//
// "마감"은 룸 폐업이 아니라 **오늘 자리 마감**(remaining_slots=0)이다.
export function StatusBadge({ status }: { status: PinStatus }) {
  const available = status === 'available';
  return (
    <View style={[styles.badge, available ? styles.badgeAvailable : styles.badgeFull]}>
      <ThemedText
        type="label"
        themeColor={available ? 'success' : 'pinFull'}
        // aria-hidden 아이콘 + 텍스트를 한 라벨로 — 스크린리더는 "✓ 예약 가능"을 읽는다.
      >
        {available ? '✓ 예약 가능' : '✕ 오늘 마감'}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: Radius.full,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[1],
  },
  badgeAvailable: { backgroundColor: Colors.light.secondary },
  badgeFull: { backgroundColor: Colors.light.backgroundElement },
});
