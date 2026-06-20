import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { router, type Href } from 'expo-router';

import { NetworkNotice } from '@/components/NetworkNotice';
import { ThemedText } from '@/components/themed-text';
import { Colors, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { FavoriteButton } from '@/features/favorites/FavoriteButton';
import { StatusBadge } from '@/features/map/StatusBadge';
import {
  AMENITY_LABELS,
  ROOM_TYPE_LABELS,
  formatHours,
  formatPrice,
  labelFor,
  summaryStatus,
  todayBusinessHours,
} from '@/features/map/roomSummary';
import { useRoomSummary } from '@/features/map/useRoomSummary';
import { isRoomNotFound } from '@/features/reservation/errors';
import { ReservationPanel } from '@/features/reservation/ReservationPanel';
import { useOnlineStatus } from '@/lib/useOnlineStatus';

import { ReviewSection } from './ReviewSection';
import { RoomLocationMap } from './RoomLocationMap';

// 룸 상세 화면 — 웹 detail/RoomDetail.tsx RN 포팅 (Story 9.2 — AC1). 9.1 스텁 라우트를 실제 상세로
// 채운다. 3단 정보 위계 + 같은 화면 예약 전개(reservationOpen) + 미니 지도 + 후기 표시.
//
// ⚠️ 슬롯 anti-pattern 회피(architecture.md L367): 예약 가능 배지는 **서버 신선 remaining_slots**
//    (summaryStatus)로 도출한다. 데이터 = 바텀시트와 동일한 useRoomSummary(키 ["rooms", roomId]·
//    refetchOnMount:'always' 신선 조회 — [[availability-freshness-policy]] 상세=신선).
// ⚠️ 막다른 화면 금지: 로딩=스켈레톤 / 실패=재시도+찾기로 / 404="그 방은 더 이상 없어요" /
//    네트워크 단절=NetworkNotice(읽기 캐시 유지). 단절을 에러로 오인 표시하지 않는다(isOnline 게이팅).
// ⚠️ 룸 상세는 ScrollView 단일 스크롤러 — 후기 목록은 ReviewSection이 .map()+더보기 버튼으로 담당
//    (세로 FlatList 중첩 금지·VirtualizedList 경고 회피).

/** "찾기로 돌아가기" — 막다른 화면 방지 공용(404·실패 분기에서 재사용). */
function BackToExploreButton() {
  return (
    <Pressable
      onPress={() => router.replace('/' as Href)}
      accessibilityRole="button"
      style={styles.outlineButton}
    >
      <ThemedText type="label" themeColor="cardForeground">
        찾기로 돌아가기
      </ThemedText>
    </Pressable>
  );
}

export function RoomDetail({ roomId }: { roomId: string }) {
  const { data, isError, error, refetch } = useRoomSummary(roomId);
  // 네트워크 단절 감지 — 단절을 일반 에러로 오인 표시하지 않도록 최우선 게이팅.
  const isOnline = useOnlineStatus();
  // 같은 화면 내 예약 전개 토글(AC2) — 라우트 변경 0, 섹션만 펼친다.
  const [reservationOpen, setReservationOpen] = useState(false);

  const showError = isOnline && isError;
  const notFound = showError && isRoomNotFound(error);

  // 1차 배지 상태 — 신선 remaining_slots(summaryStatus). 로드 전에는 미표시(스켈레톤).
  const status = data ? summaryStatus(data.remaining_slots) : undefined;
  const todayHours = data ? todayBusinessHours(data.business_hours) : null;

  // ── 막다른 화면 분기(404 / 실패 / 로딩 / 단절-콜드) ──
  if (showError) {
    return (
      <ScrollView contentContainerStyle={styles.content}>
        {notFound ? (
          // AC1 404: 미존재/비활성 룸 — 막다른 화면 금지(안내 + 찾기로).
          <View style={styles.stateBlock}>
            <ThemedText type="h1" themeColor="text">
              그 방은 더 이상 없어요
            </ThemedText>
            <ThemedText type="body" themeColor="textSecondary">
              찾으시는 스터디룸이 사라졌거나 잠시 닫혔어요. 다른 후보를 둘러봐 주세요.
            </ThemedText>
            <BackToExploreButton />
          </View>
        ) : (
          // AC1 정보 로드 실패(비-2xx) — 다시 시도 + 찾기로(막다른 화면 금지).
          <View style={styles.stateBlock}>
            <ThemedText type="body" themeColor="text" style={styles.bold}>
              정보를 못 불러왔어요.
            </ThemedText>
            <ThemedText type="bodySm" themeColor="textSecondary">
              잠시 후 다시 시도하거나, 찾기로 돌아갈 수 있어요.
            </ThemedText>
            <View style={styles.actionRow}>
              <Pressable onPress={() => refetch()} accessibilityRole="button" style={styles.primaryButton}>
                <ThemedText type="label" themeColor="primaryForeground">
                  다시 시도
                </ThemedText>
              </Pressable>
              <BackToExploreButton />
            </View>
          </View>
        )}
      </ScrollView>
    );
  }

  if (!data) {
    return (
      <ScrollView contentContainerStyle={styles.content}>
        {!isOnline ? <NetworkNotice style={styles.notice} /> : null}
        {isOnline ? (
          // AC1 로딩: 상세 스켈레톤(정보 자리).
          <View style={styles.stateBlock} accessibilityLabel="상세 불러오는 중">
            <View style={styles.skelImage} />
            <View style={styles.skelLineWide} />
            <View style={styles.skelLine} />
            <View style={styles.skelMap} />
          </View>
        ) : (
          // 네트워크 단절 + 캐시 없음(콜드): 배너(위)만 두고 막다른 화면을 만들지 않는다.
          <ThemedText type="bodySm" themeColor="textSecondary">
            연결되면 상세 정보를 보여드릴게요.
          </ThemedText>
        )}
      </ScrollView>
    );
  }

  // ── 정상: 3단 정보 위계 ──
  return (
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      {!isOnline ? <NetworkNotice style={styles.notice} /> : null}

      {/* 헤더: 이미지 placeholder + 제목 + 메타 + 즐겨찾기. */}
      <View style={styles.header}>
        <View style={styles.imagePlaceholder}>
          <ThemedText type="bodySm" themeColor="textSecondary">
            사진은 준비 중이에요
          </ThemedText>
        </View>
        <View style={styles.titleRow}>
          <View style={styles.titleCol}>
            <ThemedText type="h1" themeColor="text">
              {data.name}
            </ThemedText>
            <ThemedText type="bodySm" themeColor="textSecondary">
              {labelFor(data.room_type, ROOM_TYPE_LABELS)} · 최대 {data.capacity}인
            </ThemedText>
          </View>
          <FavoriteButton roomId={roomId} />
        </View>
      </View>

      {/* ── 1차: 가격 · 오늘 영업시간 · 예약 가능 배지(신선 remaining_slots) ── */}
      <View style={styles.section}>
        {status ? <StatusBadge status={status} /> : null}
        <View style={styles.priceRow}>
          <ThemedText type="display" themeColor="text">
            {formatPrice(data.price_per_hour)}
          </ThemedText>
          <ThemedText type="body" themeColor="textSecondary">
            {' '}
            / 시간
          </ThemedText>
        </View>
        {data.is_closed_today || !todayHours ? (
          <ThemedText type="bodySm" themeColor="text">
            오늘 휴무
          </ThemedText>
        ) : (
          <ThemedText type="bodySm" themeColor="textSecondary">
            오늘 영업{' '}
            <ThemedText type="bodySm" themeColor="text">
              {formatHours(todayHours.open_time, todayHours.close_time)}
            </ThemedText>
          </ThemedText>
        )}

        {/* 같은 화면 내 예약 전개(AC2) — 라우트 이동 0. 펼침 시에만 ReservationPanel 렌더(슬롯 조회). */}
        <Pressable
          onPress={() => setReservationOpen((open) => !open)}
          accessibilityRole="button"
          accessibilityState={{ expanded: reservationOpen }}
          style={styles.primaryButtonWide}
        >
          <ThemedText type="label" themeColor="primaryForeground">
            예약 가능 시간 보기
          </ThemedText>
        </Pressable>
        {reservationOpen ? (
          <View style={styles.reservationBox}>
            <ReservationPanel
              roomId={roomId}
              pricePerHour={data.price_per_hour}
              roomName={data.name}
            />
          </View>
        ) : null}
      </View>

      {/* ── 2차: 부대시설 · 수용 · 룸 형태 · 위치 미니 지도 ── */}
      <View style={styles.section}>
        {data.amenities.length > 0 ? (
          <View style={styles.chips}>
            {data.amenities.map((code) => (
              <View key={code} style={styles.chip}>
                <ThemedText type="caption" themeColor="secondaryForeground">
                  {labelFor(code, AMENITY_LABELS)}
                </ThemedText>
              </View>
            ))}
          </View>
        ) : null}
        <View style={styles.metaRow}>
          <ThemedText type="bodySm" themeColor="textSecondary">
            수용
          </ThemedText>
          <ThemedText type="bodySm" themeColor="text">
            최대 {data.capacity}인
          </ThemedText>
        </View>
        <View style={styles.metaRow}>
          <ThemedText type="bodySm" themeColor="textSecondary">
            룸 형태
          </ThemedText>
          <ThemedText type="bodySm" themeColor="text">
            {labelFor(data.room_type, ROOM_TYPE_LABELS)}
          </ThemedText>
        </View>
        <View style={styles.locationBlock}>
          <ThemedText type="bodySm" themeColor="text" style={styles.bold}>
            위치
          </ThemedText>
          {/* 상세 지도도 드래그/줌 허용(웹 RoomLocationMap 동형 — KTH 2026-06-20). 스크롤뷰 안
              제스처는 WebView nestedScrollEnabled 로 처리(지도 위 드래그=팬, 밖=페이지 스크롤). */}
          <RoomLocationMap lat={data.lat} lng={data.lng} name={data.name} interactive />
        </View>
      </View>

      {/* ── 3차: 후기 섹션(읽기) ── */}
      <ReviewSection roomId={roomId} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
    padding: Spacing[5],
    paddingBottom: Spacing[12],
    gap: Spacing[8],
  },
  notice: { marginBottom: Spacing[2] },
  stateBlock: { gap: Spacing[4], alignItems: 'flex-start', paddingVertical: Spacing[8] },
  bold: { fontWeight: '600' },
  header: { gap: Spacing[4] },
  imagePlaceholder: {
    height: 160,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.backgroundElement,
  },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: Spacing[2] },
  titleCol: { flex: 1, gap: Spacing[1] },
  section: { gap: Spacing[3] },
  priceRow: { flexDirection: 'row', alignItems: 'baseline' },
  reservationBox: {
    marginTop: Spacing[2],
    padding: Spacing[4],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.backgroundElement,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing[2] },
  chip: {
    borderRadius: Radius.full,
    backgroundColor: Colors.light.secondary,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[1],
  },
  metaRow: { flexDirection: 'row', gap: Spacing[2] },
  locationBlock: { gap: Spacing[2], marginTop: Spacing[2] },
  primaryButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  primaryButtonWide: {
    minHeight: 44,
    alignSelf: 'stretch',
    marginTop: Spacing[2],
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  outlineButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing[2] },
  skelImage: { height: 160, borderRadius: Radius.lg, backgroundColor: Colors.light.backgroundElement, alignSelf: 'stretch' },
  skelLineWide: { height: 28, width: '60%', borderRadius: Radius.sm, backgroundColor: Colors.light.backgroundElement },
  skelLine: { height: 20, width: '40%', borderRadius: Radius.sm, backgroundColor: Colors.light.backgroundElement },
  skelMap: { height: 176, borderRadius: Radius.lg, backgroundColor: Colors.light.backgroundElement, alignSelf: 'stretch' },
});
