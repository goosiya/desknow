import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router, type Href } from 'expo-router';
import BottomSheet, {
  BottomSheetBackdrop,
  BottomSheetScrollView,
  BottomSheetView,
  type BottomSheetBackdropProps,
} from '@gorhom/bottom-sheet';

import { FavoriteButton } from '@/features/favorites/FavoriteButton';
import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

import type { PinStatus } from './pin';
import { StatusBadge } from './StatusBadge';
import {
  AMENITY_LABELS,
  ROOM_TYPE_LABELS,
  formatHours,
  formatPrice,
  labelFor,
  summaryStatus,
  todayBusinessHours,
} from './roomSummary';
import { useRoomSummary } from './useRoomSummary';

// 룸 바텀시트 — 웹 RoomSheet(vaul) RN 포팅 (Story 9.1 — AC3·§범위 4). 핀/목록 항목 탭이 열고,
// @gorhom/bottom-sheet로 드래그-닫기 + controlled open/close. 신선 단일 조회(useRoomSummary)로
// 요약을 보여주되 "상세 보기"는 9.2 소유 룸상세 라우트(/rooms/[id] 스텁)로 네비게이트한다(9.1은
// 탐색→요약까지).
//
// ⚠️ 슬롯 anti-pattern 회피: 예약 배지는 **서버 신선 remaining_slots**(summaryStatus)로 도출한다.
type RoomSheetProps = {
  roomId: string;
  name: string;
  /** 핀/목록 항목이 준 상태(신선 로딩 전 초기 배지 — 깜빡임 방지). 로드되면 신선값으로 대체. */
  fallbackStatus?: PinStatus;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function RoomSheet({
  roomId,
  name,
  fallbackStatus,
  open,
  onOpenChange,
}: RoomSheetProps) {
  const sheetRef = useRef<BottomSheet>(null);
  const insets = useSafeAreaInsets();
  // 챗봇 패널과 동일 구조: snapPoint(60%)에서 핸들을 뺀 고정 높이를 BottomSheetView에 명시한다. 시트가
  // 첫 펼침에 콘텐츠를 측정하지 않고 고정 높이로 슬라이드업해 깜빡임이 없다(스크롤은 그 안에서 흡수).
  const { height: windowHeight } = useWindowDimensions();
  const sheetContentHeight = Math.round(windowHeight * 0.6) - 28;
  const { data, isLoading, isError, refetch } = useRoomSummary(roomId);

  // 닫힘 애니메이션 중 깜빡임 방지(웹 선례): 닫히면 roomId가 ""가 되어 data/name이 사라지므로,
  // roomId가 있을 때의 마지막 값을 보관해 닫히는 동안 직전 룸 콘텐츠를 그대로 유지한다("렌더 중
  // 파생 상태 조정" — 이전 렌더 정보 보관). roomId가 ""(닫힘)이면 갱신을 건너뛴다.
  const [lastRoom, setLastRoom] = useState({ roomId, name, data });
  if (
    roomId &&
    (lastRoom.roomId !== roomId ||
      lastRoom.name !== name ||
      lastRoom.data !== data)
  ) {
    setLastRoom({ roomId, name, data });
  }
  const shownRoomId = roomId || lastRoom.roomId;
  const shownName = roomId ? name : lastRoom.name;
  const shownData = roomId ? data : lastRoom.data;

  // open 변화에 따라 시트를 펼치고/닫는다(controlled — 핀/목록 탭이 연다). 깜빡임 제거 2종 결합:
  // ① 고정 snapPoint(높이 측정/리사이즈 없음) ② **로딩 끝난 뒤 펼침**(open && !isLoading) — 펼치는
  // 도중에 데이터가 도착해 콘텐츠가 로딩→완성으로 바뀌면 슬라이드 중 한 번 깜빡였다. 데이터/에러가
  // 확정된 뒤 완성 콘텐츠로 펼치면 챗봇처럼 깔끔하게 한 번에 올라온다(실기기 2026-06-20).
  useEffect(() => {
    if (open && !isLoading) {
      sheetRef.current?.expand();
    } else if (!open) {
      sheetRef.current?.close();
    }
  }, [open, isLoading]);

  // 드래그-닫기·백드롭 탭으로 닫히면 부모에 알린다(selectedRoom 해제).
  const handleChange = useCallback(
    (index: number) => {
      if (index === -1 && open) onOpenChange(false);
    },
    [open, onOpenChange],
  );

  const renderBackdrop = useCallback(
    (props: BottomSheetBackdropProps) => (
      <BottomSheetBackdrop
        {...props}
        appearsOnIndex={0}
        disappearsOnIndex={-1}
        pressBehavior="close"
      />
    ),
    [],
  );

  // 배지 상태: 로드되면 신선 remaining_slots(summaryStatus), 아니면 fallback(핀 스냅샷).
  const status: PinStatus | undefined = shownData
    ? summaryStatus(shownData.remaining_slots)
    : fallbackStatus;
  const todayHours = shownData
    ? todayBusinessHours(shownData.business_hours)
    : null;

  return (
    // ⚠️ 닫힘 상태에서 BottomSheet 백드롭이 화면 전체 터치를 삼키는 네이티브 버그 차단(실기기 확인 2026-06-20).
    // 비-모달 BottomSheet+백드롭은 항상 마운트되는데, 초기 닫힘(index -1)에서 백드롭 pointerEvents가 'none'으로
    // 떨어지기 전까지 투명하게 전 화면을 덮어 모든 터치를 가로챈다. open일 때만 시트가 터치를 받게 게이팅한다
    // (닫히면 아래 지도/목록으로 통과). ChatbotPanel과 동일 처리.
    <View style={StyleSheet.absoluteFill} pointerEvents={open ? 'auto' : 'none'}>
    <BottomSheet
      ref={sheetRef}
      index={-1}
      // 고정 높이(콘텐츠 측정 안 함) — 펼침이 순수 슬라이드업이 돼 깜빡임이 없다. 콘텐츠가 더 길면
      // 아래 BottomSheetScrollView가 스크롤로 흡수(클립 없음)·짧으면 상단 정렬 + 하단 여백.
      snapPoints={['60%']}
      enablePanDownToClose
      onChange={handleChange}
      backdropComponent={renderBackdrop}
      backgroundStyle={styles.sheetBackground}
      handleIndicatorStyle={styles.handle}
    >
      {/* 고정 높이 BottomSheetView(챗봇 동형) 안에서 스크롤 — 첫 펼침 측정 없이 깔끔히 슬라이드업.
          하단 콘텐츠 패딩에 안전영역 인셋(소프트 내비키)을 더해 '상세 보기'가 소프트키와 안 겹치게. */}
      <BottomSheetView style={{ height: sheetContentHeight }}>
      <BottomSheetScrollView
        style={styles.scroll}
        contentContainerStyle={[styles.content, { paddingBottom: Spacing[8] + insets.bottom }]}
      >
        {/* 헤더: 이름 + 즐겨찾기 + 닫기 */}
        <View style={styles.header}>
          <ThemedText type="h2" style={styles.title} numberOfLines={2}>
            {shownName}
          </ThemedText>
          <View style={styles.headerActions}>
            <FavoriteButton roomId={shownRoomId} />
            <Pressable
              onPress={() => onOpenChange(false)}
              accessibilityRole="button"
              accessibilityLabel="닫기"
              style={styles.close}
            >
              <ThemedText type="h3" themeColor="textSecondary">
                ✕
              </ThemedText>
            </Pressable>
          </View>
        </View>

        {isError ? (
          // 조회 실패 — 막다른 화면 금지(안내 + 다시 시도).
          <View style={styles.block}>
            <ThemedText type="body" themeColor="textSecondary">
              정보를 못 불러왔어요.
            </ThemedText>
            <Pressable
              onPress={() => refetch()}
              accessibilityRole="button"
              style={styles.primaryButton}
            >
              <ThemedText type="label" themeColor="primaryForeground">
                다시 시도
              </ThemedText>
            </Pressable>
          </View>
        ) : isLoading || !shownData ? (
          // 로딩 — fallback 배지(있으면) + 안내(전역 스피너 금지).
          <View style={styles.block}>
            {fallbackStatus ? <StatusBadge status={fallbackStatus} /> : null}
            <ThemedText type="bodySm" themeColor="textSecondary">
              불러오는 중이에요…
            </ThemedText>
          </View>
        ) : (
          <>
            {/* 기본 정보: 예약 배지 · 가격 · 영업시간 · 주소 */}
            <View style={styles.block}>
              {status ? <StatusBadge status={status} /> : null}
              <View style={styles.priceRow}>
                <ThemedText type="display" style={styles.price}>
                  {formatPrice(shownData.price_per_hour)}
                </ThemedText>
                <ThemedText type="bodySm" themeColor="textSecondary">
                  {' '}
                  / 시간
                </ThemedText>
              </View>
              {shownData.is_closed_today || !todayHours ? (
                <ThemedText type="bodySm">오늘 휴무</ThemedText>
              ) : (
                <ThemedText type="bodySm" themeColor="textSecondary">
                  오늘 영업{' '}
                  <ThemedText type="bodySm">
                    {formatHours(todayHours.open_time, todayHours.close_time)}
                  </ThemedText>
                </ThemedText>
              )}
              {shownData.address ? (
                <ThemedText type="bodySm" themeColor="textSecondary">
                  📍 {shownData.address}
                </ThemedText>
              ) : null}
            </View>

            <View style={styles.divider} />

            {/* 부가 정보: 부대시설 · 수용 · 룸 형태 */}
            <View style={styles.block}>
              {shownData.amenities.length > 0 ? (
                <View style={styles.chips}>
                  {shownData.amenities.map((code) => (
                    <View key={code} style={styles.chip}>
                      <ThemedText type="caption" themeColor="secondaryForeground">
                        {labelFor(code, AMENITY_LABELS)}
                      </ThemedText>
                    </View>
                  ))}
                </View>
              ) : null}
              <ThemedText type="bodySm" themeColor="textSecondary">
                수용 <ThemedText type="bodySm">최대 {shownData.capacity}인</ThemedText>
              </ThemedText>
              <ThemedText type="bodySm" themeColor="textSecondary">
                룸 형태{' '}
                <ThemedText type="bodySm">
                  {labelFor(shownData.room_type, ROOM_TYPE_LABELS)}
                </ThemedText>
              </ThemedText>
            </View>

            {/* 상세 보기 — 9.2 소유 룸상세 스텁으로 네비게이트(9.1은 요약까지). */}
            <Pressable
              onPress={() => router.push(`/rooms/${shownRoomId}` as Href)}
              accessibilityRole="button"
              accessibilityLabel="상세 보기"
              style={[styles.primaryButton, styles.detailButton]}
            >
              <ThemedText type="label" themeColor="primaryForeground">
                상세 보기
              </ThemedText>
            </Pressable>
          </>
        )}
      </BottomSheetScrollView>
      </BottomSheetView>
    </BottomSheet>
    </View>
  );
}

const styles = StyleSheet.create({
  sheetBackground: {
    backgroundColor: Colors.light.card,
    borderTopLeftRadius: Radius.xl,
    borderTopRightRadius: Radius.xl,
  },
  handle: { backgroundColor: Colors.light.border, width: 48 },
  scroll: { flex: 1 },
  content: {
    paddingHorizontal: Spacing[5],
    paddingBottom: Spacing[8],
    gap: Spacing[4],
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: Spacing[2],
  },
  title: { flex: 1 },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: Spacing[1] },
  close: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  block: { gap: Spacing[2] },
  priceRow: { flexDirection: 'row', alignItems: 'baseline' },
  price: { fontSize: 28, lineHeight: 36 },
  divider: { height: 1, backgroundColor: Colors.light.border },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing[2] },
  chip: {
    borderRadius: Radius.full,
    backgroundColor: Colors.light.secondary,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[1],
  },
  primaryButton: {
    minHeight: 44,
    alignSelf: 'flex-start',
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  detailButton: { alignSelf: 'stretch', marginTop: Spacing[2] },
});
