import { FlatList, StyleSheet, View } from 'react-native';

import type { RoomListItem } from '@/lib/api-client';
import { NetworkNotice } from '@/components/NetworkNotice';
import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';
import { useOnlineStatus } from '@/lib/useOnlineStatus';

import { RoomListRow } from './RoomListRow';
import { useRoomSearch, type RoomSearch } from './useRoomSearch';
import { InfoCard, RetryCard } from './ListStates';

// 스터디룸 목록 — 웹 RoomList RN 포팅 (Story 9.1 — AC4·AC5). 검색 디스크립터(지역/반경)를 받아
// 신선 가용성과 함께 나열한다. FlatList 무한스크롤(onEndReached → next_cursor). 5상태 일관 처리
// (미활성=안내·로딩=스켈레톤·에러=다시 시도·빈=제안·단절=NetworkNotice). 막다른 화면 금지.
type RoomListProps = {
  search: RoomSearch;
  onSelectRoom: (room: RoomListItem) => void;
};

/** 로딩 자리 — 스켈레톤 5행(전역 스피너 금지). */
function ListSkeleton() {
  return (
    <View style={styles.list} accessibilityLabel="목록 불러오는 중">
      {Array.from({ length: 5 }).map((_, i) => (
        <View key={i} style={styles.skeletonRow} />
      ))}
    </View>
  );
}

export function RoomList({ search, onSelectRoom }: RoomListProps) {
  const {
    data,
    isLoading,
    isError,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useRoomSearch(search);
  const isOnline = useOnlineStatus();

  const isRegion = search.kind === 'region';
  const inactive = isRegion ? !search.regionCode : !search.center;

  // 미활성(조회 비활성): 검색방식별 안내(막힘 아님).
  if (inactive) {
    return (
      <InfoCard
        text={isRegion ? '동네를 골라 주변 스터디룸을 찾아보세요.' : '현위치를 확인하고 있어요…'}
      />
    );
  }

  // 네트워크 단절: 에러보다 우선. 캐시된 목록이 있으면 행 + 상단 배너, 없으면 배너만.
  if (!isOnline) {
    if (data && data.length > 0) {
      return (
        <FlatList
          data={data}
          keyExtractor={(room) => room.room_id}
          ListHeaderComponent={<NetworkNotice style={styles.notice} />}
          renderItem={({ item }) => <RoomListRow room={item} onSelect={onSelectRoom} />}
          contentContainerStyle={styles.listContent}
        />
      );
    }
    return <NetworkNotice />;
  }

  // 로딩: 스켈레톤 행.
  if (isLoading) {
    return <ListSkeleton />;
  }

  // 에러: 안내 + 다시 시도(단절은 위에서 가로채므로 여기는 온라인 진짜 실패).
  if (isError) {
    return <RetryCard title="목록을 못 불러왔어요." onRetry={() => refetch()} />;
  }

  // 빈 결과: 검색방식별 제안(막다른 화면 금지).
  if (!data || data.length === 0) {
    return (
      <InfoCard
        title={isRegion ? '이 지역엔 등록된 곳이 없어요.' : '이 근처엔 아직 없어요.'}
        text={
          isRegion
            ? '다른 동네를 골라보거나, 지도에서 주변을 넓혀볼 수 있어요.'
            : '반경을 넓히거나 지역으로 찾아볼 수 있어요.'
        }
      />
    );
  }

  // 성공: 룸 행 리스트 + 무한스크롤.
  return (
    <FlatList
      data={data}
      keyExtractor={(room) => room.room_id}
      renderItem={({ item }) => <RoomListRow room={item} onSelect={onSelectRoom} />}
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
  list: { gap: Spacing[2] },
  listContent: { gap: Spacing[2], paddingBottom: Spacing[6] },
  notice: { marginBottom: Spacing[2] },
  skeletonRow: {
    height: 80,
    borderRadius: Radius.lg,
    backgroundColor: Colors.light.backgroundElement,
  },
  footer: { textAlign: 'center', paddingVertical: Spacing[3] },
});
