"use client";

// 경량 커스텀 달력 (Story 4.3 — AC2, 범위 결정 #3). 7열(일~토) 월 그리드.
//
// react-day-picker/date-fns 등 라이브러리 미도입(신규 의존성 0) — 30일 짧은 범위라 커스텀이
// 충분하다. 접근성(role=grid·gridcell·aria-selected/disabled·키보드 방향키·한국어 aria-label)을
// 직접 작성한다(이 부담 수용이 본 결정의 트레이드오프).
//
// ⚠️ 경계: **날짜 선택만 4.3 소유**(키보드 포함). 슬롯 선택은 4.4. 과거·30일 초과 날짜는 비활성
//    (목업 `.day.past`), 선택일은 primary 강조(목업 `.day.sel`). 색 hex 직접 작성 금지 —
//    Tailwind 토큰 클래스만(3.3/4.2 선례). prefers-reduced-motion 존중(전환 모션 없음).
import { useRef, useState, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";
import {
  addDays,
  firstOfMonth,
  formatDateAriaLabel,
  isSelectableDate,
  monthGrid,
  RESERVATION_HORIZON_DAYS,
  shiftMonth,
  yearMonthOf,
} from "./slots";

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

const DOW = ["일", "월", "화", "수", "목", "금", "토"]; // 일요일 시작(목업 `.dow`)

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
  // effect 함정 회피, 3.5/3.6).
  const [viewAnchor, setViewAnchor] = useState(() => {
    const [y, m] = yearMonthOf(value);
    return firstOfMonth(y, m);
  });
  // value 가 외부에서 다른 달로 점프하면(다음 빈 날짜 제안 클릭) 그 달로 따라간다. effect 아니라
  // **렌더 중 상태 조정**(React 공식 패턴 — 이전 prop 보관 후 비교)으로 처리해 lint 함정을 피한다.
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

  // 로빙 탭인덱스 — 선택일이 이 달에 있으면 그 셀, 아니면 이 달 첫 선택 가능 셀이 tabbable.
  const visibleSelectable = weeks
    .flat()
    .filter((d): d is string => d !== null && isSelectableDate(d, today, horizonDays));
  const tabbableDate = visibleSelectable.includes(value)
    ? value
    : (visibleSelectable[0] ?? "");

  // 같은 달 안의 날짜 셀 DOM 참조(키보드 방향키 이동 시 동기 포커스 — 월 횡단은 prev/next 버튼).
  const dayRefs = useRef(new Map<string, HTMLButtonElement>());

  function goMonth(delta: number) {
    const [ny, nm] = shiftMonth(year, month, delta);
    setViewAnchor(firstOfMonth(ny, nm));
  }

  function handleDayKeyDown(event: KeyboardEvent<HTMLButtonElement>, date: string) {
    const deltas: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -7,
      ArrowDown: 7,
    };
    const delta = deltas[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    // 같은 달 안에서만 이동(셀이 렌더돼 있어 동기 포커스 가능). 월 횡단은 prev/next 버튼이 담당.
    const target = addDays(date, delta);
    const targetEl = dayRefs.current.get(target);
    if (targetEl && isSelectableDate(target, today, horizonDays)) {
      targetEl.focus();
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {/* 월 헤더 + 이전/다음 달 이동(목업 `.cal-head`). */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => goMonth(-1)}
          disabled={!canPrev}
          aria-label="이전 달"
          className="tap-target inline-flex items-center justify-center rounded-md px-2 text-muted-foreground disabled:opacity-40"
        >
          ‹
        </button>
        <span className="text-sm font-semibold text-foreground">
          {year}년 {month}월
        </span>
        <button
          type="button"
          onClick={() => goMonth(1)}
          disabled={!canNext}
          aria-label="다음 달"
          className="tap-target inline-flex items-center justify-center rounded-md px-2 text-muted-foreground disabled:opacity-40"
        >
          ›
        </button>
      </div>

      <div role="grid" aria-label="날짜 선택" className="flex flex-col gap-1.5">
        {/* 요일 헤더(목업 `.dow`). */}
        <div role="row" className="grid grid-cols-7 text-center">
          {DOW.map((label) => (
            <span
              key={label}
              role="columnheader"
              className="text-xs text-muted-foreground"
            >
              {label}
            </span>
          ))}
        </div>

        {/* 주 단위 행. */}
        {weeks.map((week, weekIndex) => (
          <div role="row" key={weekIndex} className="grid grid-cols-7 gap-1">
            {week.map((date, dayIndex) => {
              if (date === null) {
                // 앞/뒤 빈칸 — 셀 자리만 차지(레이아웃 정렬).
                return (
                  <span
                    key={`empty-${weekIndex}-${dayIndex}`}
                    role="gridcell"
                    aria-hidden="true"
                  />
                );
              }
              const day = Number(date.slice(8, 10));
              const selectable = isSelectableDate(date, today, horizonDays);
              const selected = date === value;
              if (!selectable) {
                // 과거·30일 초과 = 비활성(목업 `.day.past`). 포커스 스킵(aria-disabled).
                return (
                  <span
                    key={date}
                    role="gridcell"
                    aria-disabled="true"
                    aria-label={formatDateAriaLabel(date)}
                    className="flex aspect-square items-center justify-center rounded-md text-sm text-muted-foreground/50"
                  >
                    {day}
                  </span>
                );
              }
              return (
                <button
                  key={date}
                  type="button"
                  role="gridcell"
                  aria-selected={selected}
                  aria-label={formatDateAriaLabel(date)}
                  tabIndex={date === tabbableDate ? 0 : -1}
                  ref={(el) => {
                    if (el) dayRefs.current.set(date, el);
                    else dayRefs.current.delete(date);
                  }}
                  onClick={() => onChange(date)}
                  onKeyDown={(event) => handleDayKeyDown(event, date)}
                  className={cn(
                    "tap-target flex aspect-square items-center justify-center rounded-md text-sm",
                    selected
                      ? "bg-primary font-bold text-primary-foreground"
                      : "text-foreground hover:bg-muted",
                  )}
                >
                  {day}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
