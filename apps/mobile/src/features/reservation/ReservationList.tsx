import { SectionList, StyleSheet, View } from 'react-native';
import { router, type Href } from 'expo-router';

import { NetworkNotice } from '@/components/NetworkNotice';
import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';
import { useOnlineStatus } from '@/lib/useOnlineStatus';
import { useSession } from '@/features/auth/useSession';
import { InfoCard, RetryCard } from '@/features/list/ListStates';
import type { ReservationListItem } from '@/lib/api-client';

import { isUpcoming } from './reservations';
import { ReservationRow } from './ReservationRow';
import { useReservations } from './useReservations';

// 예약현황 모아보기 — 웹 reservation/ReservationList.tsx RN 포팅 (Story 9.2 — AC4). 본인 예약을
// 다가오는/지난으로 구분해 나열한다. 막다른 화면 금지(FavoriteList 상태 매트릭스 미러): 세션 로딩→
// 스켈레톤 · 세션 판별 실패→재시도 · 미로그인→로그인 유도 · 단절→캐시 우선 + NetworkNotice · 로딩→
// 스켈레톤 · 에러→재시도 · 빈→찾기 유도.
//
// ⚠️ 다가오는/지난·취소 가능 분류는 render-time `now` 파생(reservations.ts 순수 함수). 3축 분리
//    (미로그인≠단절≠세션 판별 실패)는 FavoriteList 그대로(로그아웃 오인 금지).
// ⚠️ SectionList = 최상위 스크롤러라 onEndReached 무한스크롤 사용(룸 상세 후기 섹션과 달리 중첩 아님).

/** 로딩 자리 — 스켈레톤 4행. */
function ListSkeleton() {
  return (
    <View style={styles.skeletonWrap} accessibilityLabel="예약 내역 불러오는 중">
      {Array.from({ length: 4 }).map((_, i) => (
        <View key={i} style={styles.skeletonRow} />
      ))}
    </View>
  );
}

/** 다가오는/지난 분할 SectionList(단절-캐시 경로와 정상 경로 공용). */
function ReservationSections({
  data,
  now,
  header,
  onEndReached,
  footer,
}: {
  data: ReservationListItem[];
  now: Date;
  header?: React.ReactElement;
  onEndReached?: () => void;
  footer?: React.ReactElement | null;
}) {
  // 다가오는 = 빠른 순(earliest asc), 지난 = 서버 순(created_at desc) 유지.
  const upcoming = data
    .filter((item) => isUpcoming(item, now))
    .sort((a, b) => (a.slot_starts[0] ?? '').localeCompare(b.slot_starts[0] ?? ''));
  const past = data.filter((item) => !isUpcoming(item, now));
  const sections = [
    { title: '다가오는 예약', data: upcoming },
    { title: '지난 예약', data: past },
  ].filter((s) => s.data.length > 0);

  return (
    <SectionList
      sections={sections}
      keyExtractor={(item) => item.id}
      ListHeaderComponent={header}
      renderItem={({ item }) => <ReservationRow item={item} now={now} />}
      renderSectionHeader={({ section }) => (
        <ThemedText type="label" themeColor="textSecondary" style={styles.sectionHeader}>
          {section.title}
        </ThemedText>
      )}
      stickySectionHeadersEnabled={false}
      contentContainerStyle={styles.listContent}
      onEndReachedThreshold={0.5}
      onEndReached={onEndReached}
      ListFooterComponent={footer}
    />
  );
}

export function ReservationList() {
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
  } = useReservations();
  const isOnline = useOnlineStatus();
  // 다가오는/지난·6h 취소 가능 분류 기준 시각 — render-time 파생(effect setState 금지).
  const now = new Date();

  const goLogin = () => router.push('/login?next=/reservations' as Href);

  // 세션 판별 중 — 스켈레톤(미로그인/목록 깜빡임 방지).
  if (sessionLoading) {
    return <ListSkeleton />;
  }

  // 세션 판별 실패(네트워크/5xx) — 로그아웃 UI가 아니라 오류/재시도(미로그인과 구분).
  if (sessionError) {
    return <RetryCard title="로그인 상태를 확인하지 못했어요." onRetry={() => refetchSession()} />;
  }

  // 세션 미확정 + 단절: 로그인 여부 모름 → 로그인 유도 대신 단절 안내(미로그인 오인 방지).
  if (!isOnline && user === undefined) {
    return <NetworkNotice />;
  }

  // 미로그인(AC4) — 로그인 유도(막다른 화면 금지).
  if (!user) {
    return (
      <InfoCard
        title="로그인하면 예약 내역을 볼 수 있어요."
        text="예약하신 스터디룸을 한 곳에서 확인하고 관리하세요."
        action={{ label: '로그인', onPress: goLogin }}
      />
    );
  }

  // 네트워크 단절(로그인됨): 캐시된 목록이 있으면 행 + 배너, 없으면 배너만.
  if (!isOnline) {
    if (data && data.length > 0) {
      return (
        <ReservationSections
          data={data}
          now={now}
          header={<NetworkNotice style={styles.notice} />}
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
    return <RetryCard title="예약 내역을 못 불러왔어요." onRetry={() => refetch()} />;
  }

  // 빈: 찾기 유도(막다른 화면 금지).
  if (!data || data.length === 0) {
    return (
      <InfoCard
        title="아직 예약이 없어요."
        text="마음에 드는 곳을 찾아볼까요?"
        action={{ label: '스터디룸 찾기', onPress: () => router.push('/' as Href) }}
      />
    );
  }

  // 목록: 다가오는/지난 두 섹션 + 무한스크롤(onEndReached).
  return (
    <ReservationSections
      data={data}
      now={now}
      onEndReached={() => {
        if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
      }}
      footer={
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
  skeletonRow: {
    height: 80,
    borderRadius: Radius.lg,
    backgroundColor: Colors.light.backgroundElement,
  },
  listContent: { gap: Spacing[2], paddingBottom: Spacing[6] },
  sectionHeader: { marginTop: Spacing[2] },
  notice: { marginBottom: Spacing[2] },
  footer: { textAlign: 'center', paddingVertical: Spacing[3] },
});
