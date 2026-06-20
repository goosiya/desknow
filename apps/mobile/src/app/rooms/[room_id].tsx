import { StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams } from 'expo-router';

import { ThemedView } from '@/components/themed-view';
import { RoomDetail } from '@/features/detail/RoomDetail';

// 룸 상세 화면 (Story 9.1 seam → 9.2 소유 → 9.4 셸 정렬). 바텀시트 "상세 보기"가 이 라우트로 이동한다
// (파라미터명 room_id snake_case 유지 — RoomSheet가 router.push(`/rooms/${id}`)로 진입). 9.4(DET-1):
// 웹 룸상세는 인앱 "‹ 뒤로" 바가 없고 글로벌 헤더로 네비게이션을 대체한다(웹=정본) → 모바일도 인앱
// 백 바를 제거하고 글로벌 헤더(브랜드→홈) + 네이티브 뒤로(iOS 스와이프·Android 하드웨어 백)에 맡긴다.
// top은 글로벌 헤더가 인셋을 처리한다. 본체(3단 위계·예약·후기)는 RoomDetail이 담당.
export default function RoomDetailScreen() {
  const { room_id } = useLocalSearchParams<{ room_id: string }>();
  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['left', 'right']} style={styles.safeArea}>
        <RoomDetail roomId={room_id ?? ''} />
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  safeArea: { flex: 1 },
});
