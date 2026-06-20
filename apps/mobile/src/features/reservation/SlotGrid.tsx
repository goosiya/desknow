import { useRef } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';
import type { RoomSlot } from '@/lib/api-client';

import {
  clampContiguousAvailable,
  formatDateKorean,
  formatSlotLabel,
  type SlotSelection,
} from './slots';

// 슬롯 그리드 — 웹 reservation/SlotGrid.tsx RN 포팅 (Story 9.2 — AC2). 3열 그리드.
//
// **연속 선택 인터랙션 = 탭-확장**(anchor 탭 → 끝 탭 — 범위 결정 #3, 드래그는 선택 폴리시·미구현):
// 탭 시 `clampContiguousAvailable(slots, anchor, target)`로 클램프하고, 점유/지난을 가로지르면
// **무시**(앵커 유지 — expandOrIgnore). `selection`은 controlled prop(상태 출처 = ReservationPanel).
//
// ⚠️ 색 단독 금지: 선택은 accessibilityState.selected(SR) + primary 토큰(시각) 병행. 비활성 슬롯은
//    취소선(시각) + a11y 라벨(SR) + 범례로 신호한다. ≥44 터치 타깃(h-48 → 48px).
// ⚠️ 슬롯 색·상태는 서버 `slot.status`만(클라 재계산 금지 — architecture.md L367).
type SlotGridProps = {
  slots: RoomSlot[];
  /** 선택된 날짜 "YYYY-MM-DD"(부제 표기). */
  date: string;
  /** 현재 선택 구간(상태 출처 = ReservationPanel). 선택 없음 = null. */
  selection: SlotSelection | null;
  /** 선택 변경 콜백(확장·해제 포함). */
  onSelect: (selection: SlotSelection | null) => void;
};

// 비활성 상태별 스크린리더 라벨(색 단독 금지 — 시각 취소선과 병행).
const UNAVAILABLE_LABEL: Record<string, string> = {
  past: '지난 시간',
  reserved: '예약됨',
};

/** 평평한 슬롯 배열을 3개씩 행으로 자른다(레이아웃 정렬 — 마지막 행은 빈 칸 패딩). */
function toRows<T>(items: T[]): (T | null)[][] {
  const rows: (T | null)[][] = [];
  for (let i = 0; i < items.length; i += 3) {
    const row: (T | null)[] = items.slice(i, i + 3);
    while (row.length < 3) row.push(null);
    rows.push(row);
  }
  return rows;
}

export function SlotGrid({ slots, date, selection, onSelect }: SlotGridProps) {
  // 앵커 = 구간 확장의 기준점(마지막 단일 선택 인덱스). 렌더 상태 아님(ref).
  const anchorRef = useRef<number | null>(null);

  function isSelected(i: number): boolean {
    return selection !== null && i >= selection.startIndex && i <= selection.endIndex;
  }

  // 탭 확장 — 점유를 가로지르면 무시(null). 앵커~대상 사이에 점유가 끼면 대상까지 못 미친다.
  function expandOrIgnore(anchor: number, target: number): SlotSelection | null {
    const next = clampContiguousAvailable(slots, anchor, target);
    if (next && target >= next.startIndex && target <= next.endIndex) return next;
    return null;
  }

  // 탭 공통 선택 로직: 없으면 1칸(앵커) · 단일 재선택이면 해제 · 아니면 앵커~대상 확장.
  function selectAt(i: number) {
    if (selection === null) {
      anchorRef.current = i;
      onSelect({ startIndex: i, endIndex: i });
      return;
    }
    if (selection.startIndex === selection.endIndex && selection.startIndex === i) {
      anchorRef.current = null;
      onSelect(null); // 단일 선택 슬롯 재선택 → 해제.
      return;
    }
    const anchor = anchorRef.current ?? selection.startIndex;
    const next = expandOrIgnore(anchor, i);
    if (next) onSelect(next); // 점유 가로지르면 null → 무시(앵커 유지).
  }

  const rows = toRows(slots.map((slot, index) => ({ slot, index })));

  return (
    <View style={styles.wrap}>
      {/* 부제 — 선택한 날짜 + "연속된 시간만 고를 수 있어요". */}
      <ThemedText type="caption" themeColor="textSecondary">
        {formatDateKorean(date)} · 연속된 시간만 고를 수 있어요
      </ThemedText>

      <View style={styles.grid}>
        {rows.map((row, rowIndex) => (
          <View key={rowIndex} style={styles.row}>
            {row.map((entry, colIndex) => {
              if (entry === null) {
                return <View key={`empty-${rowIndex}-${colIndex}`} style={styles.cell} />;
              }
              const { slot, index } = entry;
              const label = formatSlotLabel(slot.slot_start);
              if (slot.status === 'available') {
                const selected = isSelected(index);
                return (
                  <Pressable
                    key={slot.slot_start}
                    onPress={() => selectAt(index)}
                    accessibilityRole="button"
                    accessibilityState={{ selected }}
                    accessibilityLabel={`${label}${selected ? ', 선택됨' : ''}`}
                    style={[styles.cell, styles.slot, selected && styles.slotSelected]}
                  >
                    <ThemedText
                      type="label"
                      themeColor={selected ? 'primaryForeground' : 'text'}
                    >
                      {label}
                    </ThemedText>
                  </Pressable>
                );
              }
              // past·reserved = 비활성(표시 전용). muted + 취소선 + a11y 라벨. 선택/탭 불가(View).
              return (
                <View
                  key={slot.slot_start}
                  accessibilityLabel={`${label} (${UNAVAILABLE_LABEL[slot.status]})`}
                  style={[styles.cell, styles.slotDisabled]}
                >
                  <ThemedText type="label" themeColor="textSecondary" style={styles.strike}>
                    {label}
                  </ThemedText>
                </View>
              );
            })}
          </View>
        ))}
      </View>

      {/* 범례 — 색 단독 금지 보완(텍스트로 의미 고정). */}
      <View style={styles.legend}>
        <View style={styles.legendItem}>
          <View style={[styles.legendSwatch, styles.legendAvailable]} />
          <ThemedText type="caption" themeColor="textSecondary">
            가능
          </ThemedText>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.legendSwatch, styles.legendFull]} />
          <ThemedText type="caption" themeColor="textSecondary">
            마감 · 지난 시간
          </ThemedText>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: Spacing[3] },
  grid: { gap: Spacing[2] },
  row: { flexDirection: 'row', gap: Spacing[2] },
  cell: { flex: 1 },
  slot: {
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  slotSelected: {
    borderColor: Colors.light.primary,
    backgroundColor: Colors.light.primary,
  },
  slotDisabled: {
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.backgroundElement,
    backgroundColor: Colors.light.backgroundElement,
  },
  strike: { textDecorationLine: 'line-through' },
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing[4] },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: Spacing[2] },
  legendSwatch: { width: 12, height: 12, borderRadius: Radius.sm },
  legendAvailable: {
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  legendFull: { backgroundColor: Colors.light.backgroundElement },
});
