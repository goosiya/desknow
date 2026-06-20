import { StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { ReservationList } from '@/features/reservation/ReservationList';
import { Spacing } from '@/constants/theme';

// 예약현황 화면 (Story 1.6 셸 → 9.2 소유). 본인 예약을 다가오는/지난으로 구분해 나열하고, 취소·후기·
// 공유까지 한 화면에서 한다(ReservationList). 미로그인/로딩/에러/빈/단절을 일관 처리한다. 제목은
// 화면 상단에 두고 목록이 그 아래 채운다(favorites 탭 패턴).
export default function ReservationsScreen() {
  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['left', 'right']} style={styles.safeArea}>
        <ThemedText type="display" style={styles.title}>
          예약현황
        </ThemedText>
        <ReservationList />
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  safeArea: { flex: 1, padding: Spacing[4], gap: Spacing[3] },
  title: { marginBottom: Spacing[1] },
});
