import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { NetworkNotice } from '@/components/NetworkNotice';
import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';
import { formatPrice } from '@/features/map/roomSummary';
import { useOnlineStatus } from '@/lib/useOnlineStatus';

import { Calendar } from './Calendar';
import { isSlotConflict } from './errors';
import { ShareButton } from './ShareButton';
import { SlotGrid } from './SlotGrid';
import {
  formatDateKorean,
  isSelectionStillAvailable,
  kstToday,
  selectionLabels,
  selectionSlotStarts,
  selectionTotalPrice,
  type SlotSelection,
} from './slots';
import { useCreateReservation } from './useCreateReservation';
import { useRoomSlots } from './useRoomSlots';

// 예약 패널 — 웹 reservation/ReservationPanel.tsx RN 포팅 (Story 9.2 — AC2·AC3). 달력 + 슬롯 피커를
// 조립하고 즉시 예약을 확정한다. RoomDetail이 reservationOpen일 때만 렌더 → 전개 시에만 슬롯 조회.
//
// ⚠️ 부분 degrade(AC2): 슬롯 실패/로딩/단절은 **슬롯 영역만** 영향 — 달력은 즉시·항상 표시(클라
//    계산). 단절은 `isOnline && isError` 게이팅으로 에러로 오인하지 않는다. 404는 상세 본문 가드(Task 3) 하위.
// ⚠️ SLOT_CONFLICT(409)만 특화 처리 — "먼저 잡았어요" 카피 + 슬롯 재조회(훅 onError) + selection 초기화.
//    그 외 실패는 generic. 옵티미스틱 없음(서버 확정이 진실). 에러코드 화면 노출 금지(분기에만).
type ReservationPanelProps = {
  roomId: string;
  /** 시간당 가격 — RoomDetail이 useRoomSummary.data.price_per_hour 전달(추가 조회 0). */
  pricePerHour: number;
  /** 룸 이름 — 즉시예약 성공 배너 공유 텍스트용. RoomDetail이 data.name 전달(추가 조회 0). */
  roomName: string;
};

export function ReservationPanel({ roomId, pricePerHour, roomName }: ReservationPanelProps) {
  // "오늘"·초기 선택일은 useState 초기값으로 한 번 계산(effect 에서 setState 금지).
  const [today] = useState(() => kstToday());
  const [selectedDate, setSelectedDate] = useState(today);
  // 연속 슬롯 선택. 선택 없음 = null.
  const [selection, setSelection] = useState<SlotSelection | null>(null);
  // 날짜 변경 시 선택 리셋(AC3) — Calendar의 prevValue 렌더-중-조정 패턴을 재사용(effect setState 금지).
  const [prevDate, setPrevDate] = useState(selectedDate);
  if (selectedDate !== prevDate) {
    setPrevDate(selectedDate);
    setSelection(null);
  }

  // 네트워크 단절 감지 — 단절을 슬롯 에러로 오인 표시하지 않도록 최우선 게이팅.
  const isOnline = useOnlineStatus();
  const { data, isError, refetch } = useRoomSlots(roomId, selectedDate);

  const showError = isOnline && isError;
  // 선택일의 available 슬롯이 0개(휴무·전부 지난·전부 예약)면 빈 날 안내(AC3).
  const availableCount = data
    ? data.slots.filter((slot) => slot.status === 'available').length
    : 0;
  const isEmptyDay = data !== undefined && availableCount === 0;
  const nextAvailableDate = data?.next_available_date ?? null;
  // 선택 유효성 가드(렌더-중 파생): ① bounds(refetch로 배열이 줄면 인덱스 범위 초과 방지) +
  // ② content(차감 후 선택 구간이 reserved로 stale → isSelectionStillAvailable). 위반이면 null.
  const safeSelection =
    selection &&
    data &&
    selection.startIndex >= 0 &&
    selection.endIndex < data.slots.length &&
    isSelectionStillAvailable(data.slots, selection)
      ? selection
      : null;

  // 즉시 예약 확정 뮤테이션(AC3). selectedDate는 성공 후 invalidate 대상 슬롯 키에 쓴다.
  const createReservation = useCreateReservation(roomId);

  // 성공/실패 배너는 다음 조작(날짜·슬롯 변경) 시 리셋한다 — 이벤트 핸들러에서 reset()(렌더 중 reset 아님).
  function resetSubmitFeedback() {
    if (createReservation.isSuccess || createReservation.isError) {
      createReservation.reset();
    }
  }

  function handleDateChange(next: string) {
    resetSubmitFeedback();
    setSelectedDate(next);
  }

  function handleSelect(next: SlotSelection | null) {
    resetSubmitFeedback();
    setSelection(next);
  }

  // 단절 일관성(AC8) — 단절을 서버 에러로 오인 표시하지 않는다(NetworkNotice가 단절을 우선 처리).
  const showSubmitError = isOnline && createReservation.isError;
  // 실패를 두 갈래로 분기(렌더 중 파생): SLOT_CONFLICT(409) 특화 / 그 외 generic.
  const showSlotConflict = showSubmitError && isSlotConflict(createReservation.error);
  const showGenericError = showSubmitError && !showSlotConflict;

  // stale 선택 무효화 안내(AC2). 선택이 있었는데 재조회로 더는 available이 아니게 되면 표시.
  // conflict 카피와 동시 표출 금지(!showSlotConflict).
  const selectionInvalidated =
    selection !== null && safeSelection === null && data !== undefined && !showSlotConflict;

  // 예약 확정 제출(AC3) — 선택 구간을 slot_start[]로 추출해 POST. 이중 제출은 isPending 가드.
  function handleSubmit() {
    if (!safeSelection || !data) return;
    const slotStarts = selectionSlotStarts(data.slots, safeSelection);
    createReservation.mutate(
      { slotStarts, selectedDate },
      {
        onSuccess: () => setSelection(null),
        onError: (error) => {
          if (isSlotConflict(error)) setSelection(null);
        },
      },
    );
  }

  return (
    <View style={styles.wrap}>
      {/* 단절: 에러보다 우선 — 배너 + 읽기 캐시 유지. */}
      {!isOnline ? <NetworkNotice /> : null}

      {/* 달력은 즉시·항상 표시(클라 계산 — 막다른 화면 금지). */}
      <View style={styles.section}>
        <ThemedText type="label" themeColor="text">
          날짜 선택
        </ThemedText>
        <Calendar value={selectedDate} onChange={handleDateChange} today={today} />
      </View>

      {/* 슬롯 영역(부분 degrade — 실패/로딩/단절은 이 영역만). */}
      <View style={styles.section}>
        <ThemedText type="label" themeColor="text">
          시간 선택
        </ThemedText>
        {showError ? (
          // 비-2xx 실패 — 슬롯 영역만 안내 + 다시 시도(달력·상세는 정상).
          <View style={styles.noticeBox}>
            <ThemedText type="bodySm" themeColor="text">
              시간표를 못 불러왔어요.
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
        ) : data !== undefined ? (
          isEmptyDay ? (
            // AC3: 빈 날 안내 + 다음 빈 날짜 제안(막다른 화면 금지 — 달력은 계속 조작 가능).
            <View accessibilityRole="alert" style={styles.noticeBox}>
              <ThemedText type="bodySm" themeColor="text">
                이 날은 다 찼어요. 다른 날을 골라보세요.
              </ThemedText>
              {nextAvailableDate ? (
                <Pressable
                  onPress={() => handleDateChange(nextAvailableDate)}
                  accessibilityRole="button"
                  style={styles.outlineButton}
                >
                  <ThemedText type="label" themeColor="cardForeground">
                    {formatDateKorean(nextAvailableDate)}은 자리가 있어요
                  </ThemedText>
                </Pressable>
              ) : null}
            </View>
          ) : (
            // 정상 — 슬롯 그리드 + 하단 선택 요약(선택 시에만).
            <View style={styles.slotArea}>
              <SlotGrid
                slots={data.slots}
                date={selectedDate}
                selection={safeSelection}
                onSelect={handleSelect}
              />

              {/* SLOT_CONFLICT 특화 안내(AC3) — selection 무관하게 슬롯 영역에서 보인다(요약 밖). */}
              {showSlotConflict ? (
                <ThemedText accessibilityRole="alert" type="bodySm" themeColor="text">
                  앗, 방금 다른 분이 먼저 잡았어요. 가까운 빈 시간을 다시 보여드릴게요.
                </ThemedText>
              ) : null}

              {createReservation.isSuccess ? (
                // 즉시예약 성공 직후 카카오 공유 진입점(AC7). 공유 데이터는 방금 받은 응답 + roomName.
                <View accessibilityLiveRegion="polite" style={styles.successBanner}>
                  <ThemedText type="label" themeColor="secondaryForeground">
                    예약이 완료됐어요!
                  </ThemedText>
                  {createReservation.data ? (
                    <ShareButton
                      roomName={roomName}
                      slotStarts={createReservation.data.slot_starts}
                      roomId={roomId}
                    />
                  ) : null}
                </View>
              ) : safeSelection ? (
                (() => {
                  const labels = selectionLabels(data.slots, safeSelection);
                  const total = selectionTotalPrice(safeSelection, pricePerHour);
                  return (
                    <View style={styles.summaryArea}>
                      <View
                        accessibilityLiveRegion="polite"
                        accessibilityLabel={labels.announcement}
                        style={styles.summaryBox}
                      >
                        <ThemedText type="label" themeColor="text">
                          {`${labels.rangeLabel} · ${formatDateKorean(selectedDate)} · ${labels.durationHours}시간 · ${formatPrice(total)}`}
                        </ThemedText>
                      </View>
                      {/* generic 실패 안내(404·5xx 등 — 에러코드 노출 금지) — selection 유지 → "다시 시도". */}
                      {showGenericError ? (
                        <ThemedText accessibilityRole="alert" type="bodySm" themeColor="destructive">
                          예약을 완료하지 못했어요. 다시 시도해 주세요.
                        </ThemedText>
                      ) : null}
                      {/* 예약 확정 CTA(AC3) — 선택 있을 때만. 제출 중 disabled + "예약 중…"(이중 제출 방지). */}
                      <Pressable
                        onPress={handleSubmit}
                        disabled={createReservation.isPending}
                        accessibilityRole="button"
                        accessibilityState={{ disabled: createReservation.isPending }}
                        style={[styles.primaryButtonWide, createReservation.isPending && styles.disabled]}
                      >
                        <ThemedText type="label" themeColor="primaryForeground">
                          {createReservation.isPending
                            ? '예약 중…'
                            : showGenericError
                              ? '다시 시도'
                              : '예약하기'}
                        </ThemedText>
                      </Pressable>
                    </View>
                  );
                })()
              ) : selectionInvalidated ? (
                // stale 선택 무효화 안내(AC2) — 선택이 방금 예약됨 등으로 비워졌음을 알리고 재선택 유도.
                <ThemedText accessibilityRole="alert" type="bodySm" themeColor="text">
                  선택한 시간 중 일부가 방금 예약됐어요. 다시 선택해 주세요.
                </ThemedText>
              ) : (
                <ThemedText type="bodySm" themeColor="textSecondary">
                  시간을 선택해 주세요.
                </ThemedText>
              )}
            </View>
          )
        ) : isOnline ? (
          // 로딩 — 슬롯 그리드 스켈레톤 6칸(달력은 위에서 이미 표시).
          <View style={styles.skeletonGrid} accessibilityLabel="시간표 불러오는 중">
            {Array.from({ length: 6 }, (_unused, index) => (
              <View key={index} style={styles.skeletonCell} />
            ))}
          </View>
        ) : (
          // 단절 + 캐시 없음(콜드): 배너(위)만 두고 막다른 화면을 만들지 않는다.
          <ThemedText type="bodySm" themeColor="textSecondary">
            연결되면 시간표를 보여드릴게요.
          </ThemedText>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: Spacing[5] },
  section: { gap: Spacing[2] },
  slotArea: { gap: Spacing[4] },
  summaryArea: { gap: Spacing[3] },
  noticeBox: {
    gap: Spacing[2],
    alignItems: 'flex-start',
    padding: Spacing[4],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.backgroundElement,
  },
  summaryBox: {
    padding: Spacing[4],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  successBanner: {
    gap: Spacing[3],
    alignItems: 'flex-start',
    padding: Spacing[4],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.secondary,
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
  primaryButtonWide: {
    minHeight: 44,
    alignSelf: 'stretch',
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  outlineButton: {
    minHeight: 44,
    alignSelf: 'flex-start',
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  disabled: { opacity: 0.6 },
  skeletonGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing[2] },
  skeletonCell: {
    height: 48,
    width: '31%',
    borderRadius: Radius.md,
    backgroundColor: Colors.light.backgroundElement,
  },
});
