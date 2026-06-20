"use client";

// 슬롯 그리드 — 연속 선택 인터랙티브 (Story 4.4 — AC1·AC2·AC4). 3열 그리드(목업 `.slots`).
//
// Story 4.3 가 남긴 "4.4 SEAM"(표시 전용 → 선택 상호작용 배선)을 채운다. `available` 슬롯을
// `<span>` → `<button>` 으로 승격하고 **탭·드래그·키보드**로 연속 구간을 선택한다. 선택 구간은
// `primary` 로 강조하고, **비연속·점유 가로지르기는 구조적으로 막는다**(D1). `selection` 은
// controlled prop(상태 출처 = `ReservationPanel`) — 본 컴포넌트는 상호작용만 담당한다.
//
// ⚠️ 연속-가용 단일 규칙(slots.ts `clampContiguousAvailable`): 앵커에서 인접 `available` 로만
//    구간이 자라고 첫 점유에서 멈춘다 → 비연속/점유 가로지르기 불가(D1 + 구간 점유 차단 동시 충족).
//    - 탭/Enter: 점유를 가로지르면 **무시**(앵커 유지). 드래그: 첫 점유에서 **클램프**(멈춤).
// ⚠️ 색 단독 금지(DESIGN L193·L273): 선택은 `aria-pressed`(스크린리더)+`primary` 토큰(시각) 병행.
//    비활성 슬롯은 취소선(시각)+sr-only(스크린리더)+범례로 신호한다. 색 hex 직접 작성 금지 —
//    Tailwind 토큰 클래스만. ≥44×44px 터치 타깃(EXPERIENCE L166 — `tap-target`/`h-12`).
//    SR 구간 피드백("14시부터 17시까지 선택됨")은 `ReservationPanel` 의 선택 요약(aria-live)이 담당.
import { useRef, type KeyboardEvent, type PointerEvent } from "react";

import type { RoomSlot } from "@/lib/api-client";

import { cn } from "@/lib/utils";
import {
  clampContiguousAvailable,
  formatDateKorean,
  formatSlotLabel,
  isAvailableIndex,
  type SlotSelection,
} from "./slots";

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
  past: "지난 시간",
  reserved: "예약됨",
};

// 키보드 방향키 → 인덱스 이동량(←/→ ±1, ↑/↓ ±3 — 3열 그리드 행 이동).
const ARROW_DELTAS: Record<string, number> = {
  ArrowLeft: -1,
  ArrowRight: 1,
  ArrowUp: -3,
  ArrowDown: 3,
};

export function SlotGrid({ slots, date, selection, onSelect }: SlotGridProps) {
  // 앵커 = 구간 확장의 기준점(마지막 단일 선택/드래그 시작 인덱스). 렌더 상태 아님(ref).
  const anchorRef = useRef<number | null>(null);
  // 드래그 진행 여부 + 실제 이동 발생 여부(드래그 직후 따라오는 click 을 무시하기 위함).
  const draggingRef = useRef(false);
  const draggedRef = useRef(false);
  // 로빙 탭인덱스 + 방향키 동기 포커스용 버튼 DOM 참조(Calendar dayRefs 패턴 미러).
  const slotRefs = useRef(new Map<number, HTMLButtonElement>());

  // 로빙 대상 = 선택 시작 슬롯(있으면) 아니면 첫 available 슬롯 한 칸만 tabbable.
  const firstAvailable = slots.findIndex((slot) => slot.status === "available");
  const tabbableIndex =
    selection && isAvailableIndex(slots, selection.startIndex)
      ? selection.startIndex
      : firstAvailable;

  function isSelected(i: number): boolean {
    return selection !== null && i >= selection.startIndex && i <= selection.endIndex;
  }

  // 탭/Enter 확장 — 점유를 가로지르면 무시(null). 드래그(클램프)와 다른 의미라 분리한다.
  function expandOrIgnore(anchor: number, target: number): SlotSelection | null {
    const next = clampContiguousAvailable(slots, anchor, target);
    // 대상까지 못 미치면(중간 점유) 무시 — 앵커 유지.
    if (next && target >= next.startIndex && target <= next.endIndex) return next;
    return null;
  }

  // 탭/Enter 공통 선택 로직: 없으면 1칸(앵커) · 단일 재선택이면 해제 · 아니면 앵커~대상 확장.
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

  function handleClick(i: number) {
    if (draggedRef.current) {
      draggedRef.current = false; // 드래그가 이미 선택을 확정 — 뒤따르는 click 무시.
      return;
    }
    selectAt(i);
  }

  function handlePointerDown(event: PointerEvent<HTMLButtonElement>, i: number) {
    anchorRef.current = i;
    draggingRef.current = true;
    draggedRef.current = false;
    // 포인터 캡처 — 드래그가 슬롯 밖으로 나가도 up 을 받는다(jsdom 은 no-op 폴리필).
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function handlePointerEnter(i: number) {
    if (!draggingRef.current || anchorRef.current === null) return;
    draggedRef.current = true;
    // 드래그 = 첫 점유에서 클램프(멈춤). 점유 슬롯엔 핸들러가 없어 enter 가 안 와도 마지막
    // available 에서 자연히 멈춘다.
    const next = clampContiguousAvailable(slots, anchorRef.current, i);
    if (next) onSelect(next);
  }

  function endDrag() {
    draggingRef.current = false;
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, i: number) {
    if (event.key === "Enter" || event.key === " ") {
      // 버튼 기본 동작(click)을 막아 키보드 경로를 onKeyDown 단일 처리로 둔다(click 중복 회피).
      event.preventDefault();
      selectAt(i);
      return;
    }
    const delta = ARROW_DELTAS[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    // 다음 available 슬롯으로 동기 포커스(비활성 past/reserved 는 스킵).
    const dir = delta > 0 ? 1 : -1;
    let target = i + delta;
    while (target >= 0 && target < slots.length && !isAvailableIndex(slots, target)) {
      target += dir;
    }
    if (target >= 0 && target < slots.length) slotRefs.current.get(target)?.focus();
  }

  return (
    <div className="flex flex-col gap-3">
      {/* 부제 — 선택한 날짜 + "연속된 시간만 고를 수 있어요"(목업 `.slot-sub` — 4.4 소유). */}
      <p className="text-xs text-muted-foreground">
        {formatDateKorean(date)} · 연속된 시간만 고를 수 있어요
      </p>

      <div className="grid grid-cols-3 gap-2">
        {slots.map((slot, index) => {
          const label = formatSlotLabel(slot.slot_start);
          if (slot.status === "available") {
            const selected = isSelected(index);
            // available = 선택 가능 버튼(목업 `.slot`/`.slot.sel`). 탭·드래그·키보드 배선.
            return (
              <button
                key={slot.slot_start}
                type="button"
                data-status="available"
                aria-pressed={selected}
                tabIndex={index === tabbableIndex ? 0 : -1}
                ref={(el) => {
                  if (el) slotRefs.current.set(index, el);
                  else slotRefs.current.delete(index);
                }}
                onClick={() => handleClick(index)}
                onPointerDown={(event) => handlePointerDown(event, index)}
                onPointerEnter={() => handlePointerEnter(index)}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
                onKeyDown={(event) => handleKeyDown(event, index)}
                className={cn(
                  // touch-none/select-none — 드래그 중 스크롤·텍스트 선택 방지.
                  "tap-target flex h-12 touch-none select-none items-center justify-center rounded-md border text-sm font-semibold",
                  selected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card text-foreground",
                )}
              >
                {label}
              </button>
            );
          }
          // past·reserved = 비활성(목업 `.slot.disabled`/`.booked`). 표시 전용 유지(4.3 보존) —
          // muted + 취소선 + sr-only 텍스트. 선택/포커스 불가(`<span>` · aria-disabled).
          return (
            <span
              key={slot.slot_start}
              data-status={slot.status}
              aria-disabled="true"
              className={cn(
                "flex h-12 items-center justify-center rounded-md border border-muted bg-muted text-sm font-semibold text-muted-foreground line-through",
              )}
            >
              {label}
              <span className="sr-only"> ({UNAVAILABLE_LABEL[slot.status]})</span>
            </span>
          );
        })}
      </div>

      {/* 범례(목업 `.legend`) — 색 단독 금지 보완(텍스트로 의미 고정). */}
      <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block h-3 w-3 rounded-sm border border-border bg-card" />
          가능
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block h-3 w-3 rounded-sm bg-muted" />
          마감 · 지난 시간
        </span>
      </div>
    </div>
  );
}
