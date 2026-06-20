import { StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { FavoriteList } from '@/features/favorites/FavoriteList';
import { Spacing } from '@/constants/theme';

// 즐겨찾기 모아보기 화면 (Story 9.1 — AC4). 저장한 스터디룸을 나열하고, 미로그인/로딩/에러/빈/단절을
// 일관 처리한다(FavoriteList). 제목은 화면 상단에 두고 목록이 그 아래 채운다.
export default function FavoritesScreen() {
  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['left', 'right']} style={styles.safeArea}>
        <ThemedText type="display" style={styles.title}>
          즐겨찾기
        </ThemedText>
        <FavoriteList />
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  safeArea: { flex: 1, padding: Spacing[4], gap: Spacing[3] },
  title: { marginBottom: Spacing[1] },
});
