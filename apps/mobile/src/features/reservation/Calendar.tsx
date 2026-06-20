import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

import {
  addDays,
  firstOfMonth,
  formatDateAriaLabel,
  isSelectableDate,
  monthGrid,
  RESERVATION_HORIZON_DAYS,
  shiftMonth,
  yearMonthOf,
} from './slots';

// 경량 커스텀 달력 — 웹 reservation/Calendar.tsx RN 포팅 (Story 9.2 — AC2 · 범위 결정 #3). 7열(일~토)
// 월 그리드. 라이브러리 0(30일 짧은 범위 — monthGrid/isSelectableDate 순수함수로 충분).
//
// ⚠️ 경계: **날짜 선택만**. 슬롯 선택은 SlotGrid. 과거·30일 초과 날짜는 비활성, 선택일은 primary 강조.
// ⚠️ 웹은 키보드 방향키 이동이지만 RN은 **탭 중심**(각 셀 Pressable·탭 타겟 ≥44 — 범위 결정 #3).
//    색 단독 금지: 선택은 accessibilityState.selected(SR) + primary 토큰(시각) 병행.
type CalendarProps = {
  /** 선택된 날짜 "YYYY-MM-DD". */
  value: string;
  /** 날짜 선택 콜백. */
  onChange: (date: string) => void;
  /** ROOM_TZ "오늘" "YYYY-MM-DD"(선택 가능 하한·초기 보기 월). */
  today: string;
  /** 선택 가능 기간(일). 기본 30일(범위 결정 #2). */
  horizonDays?: number;
};

const DOW = ['일', '월', '화', '수', '목', '금', '토']; // 일요일 시작

/** 평평한 그리드 셀 배열을 7개씩 주 단위로 자른다(마지막 주는 null 패딩 — 레이아웃 정렬). */
function toWeeks(cells: (string | null)[]): (string | null)[][] {
  const weeks: (string | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) {
    const week = cells.slice(i, i + 7);
    while (week.length < 7) week.push(null);
    weeks.push(week);
  }
  return weeks;
}

export function Calendar({
  value,
  onChange,
  today,
  horizonDays = RESERVATION_HORIZON_DAYS,
}: CalendarProps) {
  // 보기 월 앵커("YYYY-MM-01"). 초기값은 선택일의 월(effect 없이 useState 초기값 — set-state-in-
  // effect 함정 회피).
  const [viewAnchor, setViewAnchor] = useState(() => {
    const [y, m] = yearMonthOf(value);
    return firstOfMonth(y, m);
  });
  // value 가 외부에서 다른 달로 점프하면(다음 빈 날짜 제안 클릭) 그 달로 따라간다. effect 아니라
  // **렌더 중 상태 조정**(이전 prop 보관 후 비교)으로 처리한다.
  const [prevValue, setPrevValue] = useState(value);
  if (value !== prevValue) {
    setPrevValue(value);
    const [vy, vm] = yearMonthOf(value);
    const [ay, am] = yearMonthOf(viewAnchor);
    if (vy !== ay || vm !== am) setViewAnchor(firstOfMonth(vy, vm));
  }

  const [year, month] = yearMonthOf(viewAnchor);
  const weeks = toWeeks(monthGrid(year, month));
  const lastSelectable = addDays(today, horizonDays - 1);

  // 월 이동 가능 여부 — 오늘 이전 달로는 못 가고, horizon 마지막 날의 달을 넘지 못한다.
  const [ty, tm] = yearMonthOf(today);
  const [ly, lm] = yearMonthOf(lastSelectable);
  const canPrev = year > ty || (year === ty && month > tm);
  const canNext = year < ly || (year === ly && month < lm);

  function goMonth(delta: number) {
    const [ny, nm] = shiftMonth(year, month, delta);
    setViewAnchor(firstOfMonth(ny, nm));
  }

  return (
    <View style={styles.wrap}>
      {/* 월 헤더 + 이전/다음 달 이동. */}
      <View style={styles.head}>
        <Pressable
          onPress={() => goMonth(-1)}
          disabled={!canPrev}
          accessibilityRole="button"
          accessibilityLabel="이전 달"
          accessibilityState={{ disabled: !canPrev }}
          style={styles.navButton}
        >
          <ThemedText
            type="h3"
            themeColor={canPrev ? 'textSecondary' : 'border'}
          >
            ‹
          </ThemedText>
        </Pressable>
        <ThemedText type="label" themeColor="text">
          {year}년 {month}월
        </ThemedText>
        <Pressable
          onPress={() => goMonth(1)}
          disabled={!canNext}
          accessibilityRole="button"
          accessibilityLabel="다음 달"
          accessibilityState={{ disabled: !canNext }}
          style={styles.navButton}
        >
          <ThemedText
            type="h3"
            themeColor={canNext ? 'textSecondary' : 'border'}
          >
            ›
          </ThemedText>
        </Pressable>
      </View>

      {/* 요일 헤더. */}
      <View style={styles.row}>
        {DOW.map((label) => (
          <View key={label} style={styles.cell}>
            <ThemedText type="caption" themeColor="textSecondary">
              {label}
            </ThemedText>
          </View>
        ))}
      </View>

      {/* 주 단위 행. */}
      {weeks.map((week, weekIndex) => (
        <View key={weekIndex} style={styles.row}>
          {week.map((date, dayIndex) => {
            if (date === null) {
              // 앞/뒤 빈칸 — 셀 자리만 차지(레이아웃 정렬).
              return <View key={`empty-${weekIndex}-${dayIndex}`} style={styles.cell} />;
            }
            const day = Number(date.slice(8, 10));
            const selectable = isSelectableDate(date, today, horizonDays);
            const selected = date === value;
            if (!selectable) {
              // 과거·30일 초과 = 비활성. 선택/탭 불가(View·텍스트 흐리게).
              return (
                <View key={date} style={styles.cell}>
                  <ThemedText type="bodySm" themeColor="border">
                    {day}
                  </ThemedText>
                </View>
              );
            }
            return (
              <Pressable
                key={date}
                onPress={() => onChange(date)}
                accessibilityRole="button"
                accessibilityLabel={formatDateAriaLabel(date)}
                accessibilityState={{ selected }}
                style={[styles.cell, styles.dayCell, selected && styles.daySelected]}
              >
                <ThemedText
                  type="bodySm"
                  themeColor={selected ? 'primaryForeground' : 'text'}
                  style={selected ? styles.daySelectedText : undefined}
                >
                  {day}
                </ThemedText>
              </Pressable>
            );
          })}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: Spacing[2] },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  navButton: {
    minWidth: 44,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
  },
  row: { flexDirection: 'row' },
  cell: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dayCell: { borderRadius: Radius.md, margin: 1 },
  daySelected: { backgroundColor: Colors.light.primary },
  daySelectedText: { fontWeight: '700' },
});
