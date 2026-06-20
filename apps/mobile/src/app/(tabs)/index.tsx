import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { OnboardingOverlay } from '@/components/OnboardingOverlay';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { ExploreView } from '@/features/list/ExploreView';
import { Spacing } from '@/constants/theme';

// 스터디룸 찾기 홈 (Story 9.1 → 9.4 — AC3·AC4·AC5·AC6). 지도/목록 탐색·지역/반경 검색은 ExploreView가
// 담당하고, 첫 방문 온보딩 오버레이(3.9 재사용)를 그 위에 얹는다("다시 보지 않기"만 영속). 9.4(HOME-2):
// 웹 홈(app/page.tsx:14-20)의 제목·부제를 ExploreView 위에 둔다(기존 모바일은 제목/부제 누락).
export default function FindScreen() {
  return (
    <ThemedView style={styles.container}>
      {/* top은 글로벌 헤더(9.4)가, 하단은 탭 바가 인셋을 처리하므로 좌우만 안전영역 적용. */}
      <SafeAreaView edges={['left', 'right']} style={styles.safeArea}>
        <View style={styles.heading}>
          <ThemedText type="h1">내 주변 스터디룸</ThemedText>
          <ThemedText type="bodySm" themeColor="textSecondary">
            지금 비어 있는 곳을 지도나 목록에서 한눈에 확인하고 바로 예약하세요.
          </ThemedText>
        </View>
        <ExploreView />
      </SafeAreaView>
      <OnboardingOverlay />
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  safeArea: { flex: 1 },
  heading: { gap: Spacing[1], paddingHorizontal: Spacing[4], paddingTop: Spacing[4], paddingBottom: Spacing[2] },
});
