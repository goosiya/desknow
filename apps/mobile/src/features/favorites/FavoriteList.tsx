import { FlatList, StyleSheet, View } from 'react-native';
import { router, type Href } from 'expo-router';

import { NetworkNotice } from '@/components/NetworkNotice';
import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';
import { useOnlineStatus } from '@/lib/useOnlineStatus';
import { useSession } from '@/features/auth/useSession';
import { InfoCard, RetryCard } from '@/features/list/ListStates';

import { useFavorites } from './useFavorites';
import { FavoriteRow } from './FavoriteRow';

// 즐겨찾기 모아보기 — 웹 FavoriteList RN 포팅 (Story 9.1 — AC4·AC5). 저장한 룸을 나열하고 각 행에서
// 상세(9.2 스텁)로 이동한다. 막다른 화면 금지: 미로그인=로그인 유도·로딩=스켈레톤·에러=다시 시도·
// 빈=안내·단절=NetworkNotice. FlatList 무한스크롤.

/** 로딩 자리 — 스켈레톤 5행. */
function ListSkeleton() {
  return (
    <View style={styles.skeletonWrap} accessibilityLabel="즐겨찾기 불러오는 중">
      {Array.from({ length: 5 }).map((_, i) => (
        <View key={i} style={styles.skeletonRow} />
      ))}
    </View>
  );
}

export function FavoriteList() {
  const {
    data: user,
    isLoading: sessionLoading,
    isError: sessionError,
    refetch: refetchSession,
  } = useSession();
  const {
    data,
    isLoading,
    isError,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useFavorites();
  const isOnline = useOnlineStatus();

  const goLogin = () => router.push('/login?next=/favorites' as Href);

  // 세션 판별 중 — 스켈레톤(미로그인/목록 깜빡임 방지).
  if (sessionLoading) {
    return <ListSkeleton />;
  }

  // 세션 판별 실패(네트워크/5xx) — 로그아웃 UI가 아니라 오류/재시도(미로그인과 구분).
  if (sessionError) {
    return <RetryCard title="로그인 상태를 확인하지 못했어요." onRetry={() => refetchSession()} />;
  }

  // 세션 미확정 + 단절: 로그인 여부를 모르므로 로그인 유도 대신 단절 안내(미로그인 오인 방지).
  if (!isOnline && user === undefined) {
    return <NetworkNotice />;
  }

  // 미로그인 — 로그인 유도(막다른 화면 금지).
  if (!user) {
    return (
      <InfoCard
        title="로그인하면 즐겨찾기를 모아볼 수 있어요."
        text="마음에 든 스터디룸을 저장해두고 다음에 빠르게 다시 찾아보세요."
        action={{ label: '로그인', onPress: goLogin }}
      />
    );
  }

  // 네트워크 단절(로그인됨): 캐시된 즐겨찾기가 있으면 행 + 배너, 없으면 배너만.
  if (!isOnline) {
    if (data && data.length > 0) {
      return (
        <FlatList
          data={data}
          keyExtractor={(f) => f.room_id}
          ListHeaderComponent={<NetworkNotice style={styles.notice} />}
          renderItem={({ item }) => <FavoriteRow favorite={item} />}
          contentContainerStyle={styles.listContent}
        />
      );
    }
    return <NetworkNotice />;
  }

  // 로딩: 스켈레톤.
  if (isLoading) {
    return <ListSkeleton />;
  }

  // 에러: 안내 + 다시 시도(단절은 위에서 가로챔).
  if (isError) {
    return <RetryCard title="즐겨찾기를 못 불러왔어요." onRetry={() => refetch()} />;
  }

  // 빈: 즐겨찾기 유도.
  if (!data || data.length === 0) {
    return (
      <InfoCard
        title="아직 즐겨찾기한 곳이 없어요."
        text="마음에 든 곳을 즐겨찾기해두면 여기 모여요."
        action={{ label: '스터디룸 찾기', onPress: () => router.push('/' as Href) }}
      />
    );
  }

  // 목록 + 무한스크롤.
  return (
    <FlatList
      data={data}
      keyExtractor={(f) => f.room_id}
      renderItem={({ item }) => <FavoriteRow favorite={item} />}
      contentContainerStyle={styles.listContent}
      onEndReachedThreshold={0.5}
      onEndReached={() => {
        if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
      }}
      ListFooterComponent={
        isFetchingNextPage ? (
          <ThemedText type="bodySm" themeColor="textSecondary" style={styles.footer}>
            불러오는 중…
          </ThemedText>
        ) : null
      }
    />
  );
}

const styles = StyleSheet.create({
  skeletonWrap: { gap: Spacing[2] },
  listContent: { gap: Spacing[2], paddingBottom: Spacing[6] },
  notice: { marginBottom: Spacing[2] },
  skeletonRow: {
    height: 80,
    borderRadius: Radius.lg,
    backgroundColor: Colors.light.backgroundElement,
  },
  footer: { textAlign: 'center', paddingVertical: Spacing[3] },
});
