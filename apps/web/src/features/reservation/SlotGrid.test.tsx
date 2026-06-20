// SlotGrid 상호작용 테스트 (Story 4.4 — AC1·AC2·AC4). 탭·키보드가 1급 경로, 드래그는 인프라
// 가능 범위(jsdom PointerEvent)에서 검증한다. selection 은 controlled prop 이라 작은 상태 harness
// 로 감싸 실제 탭→상태→재탭(확장/해제) 흐름을 그대로 흐르게 한다.
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { RoomSlot } from "@/lib/api-client";

import { SlotGrid } from "./SlotGrid";
import { type SlotSelection } from "./slots";

// 14:00 KST(05:00Z) 부터 1시간 간격 슬롯을 인덱스별 상태로 만든다.
function makeSlots(statuses: RoomSlot["status"][]): RoomSlot[] {
  return statuses.map((status, i) => ({
    slot_start: new Date(Date.UTC(2026, 5, 15, 5 + i, 0, 0)).toISOString(),
    status,
  }));
}

// controlled selection 을 보유하는 테스트 harness — onSelect 를 state setter 로 연결한다.
function Harness({
  slots,
  onChange,
}: {
  slots: RoomSlot[];
  onChange?: (sel: SlotSelection | null) => void;
}) {
  const [selection, setSelection] = useState<SlotSelection | null>(null);
  return (
    <SlotGrid
      slots={slots}
      date="2026-06-15"
      selection={selection}
      onSelect={(sel) => {
        setSelection(sel);
        onChange?.(sel);
      }}
    />
  );
}

// available 버튼만 라벨 텍스트로 조회(past/reserved 는 span 이라 button 으로 안 잡힘).
function slotButton(label: string): HTMLButtonElement {
  return screen.getByRole("button", { name: label });
}

describe("SlotGrid 탭 선택 (AC1)", () => {
  it("available 탭 → 그 슬롯 1칸 선택(aria-pressed) + onSelect 호출", () => {
    const onChange = vi.fn();
    render(<Harness slots={makeSlots(["available", "available", "available"])} onChange={onChange} />);

    fireEvent.click(slotButton("14:00"));
    expect(slotButton("14:00")).toHaveAttribute("aria-pressed", "true");
    expect(slotButton("15:00")).toHaveAttribute("aria-pressed", "false");
    expect(onChange).toHaveBeenLastCalledWith({ startIndex: 0, endIndex: 0 });
  });

  it("둘째 available 탭 → 앵커~대상 연속 구간으로 확장", () => {
    render(<Harness slots={makeSlots(["available", "available", "available"])} />);

    fireEvent.click(slotButton("14:00")); // 앵커
    fireEvent.click(slotButton("16:00")); // 확장 → 14·15·16

    expect(slotButton("14:00")).toHaveAttribute("aria-pressed", "true");
    expect(slotButton("15:00")).toHaveAttribute("aria-pressed", "true");
    expect(slotButton("16:00")).toHaveAttribute("aria-pressed", "true");
  });

  it("점유를 가로지르는 둘째 탭 → 확장 무시(선택 불변, D1)", () => {
    // [14 avail, 15 reserved, 16 avail] — 14 앵커 후 16 탭은 15(reserved)에 막혀 무시.
    render(<Harness slots={makeSlots(["available", "reserved", "available"])} />);

    fireEvent.click(slotButton("14:00"));
    fireEvent.click(slotButton("16:00"));

    expect(slotButton("14:00")).toHaveAttribute("aria-pressed", "true");
    expect(slotButton("16:00")).toHaveAttribute("aria-pressed", "false"); // 확장 안 됨.
  });

  it("단일 선택 슬롯 재탭 → 해제(onSelect(null))", () => {
    const onChange = vi.fn();
    render(<Harness slots={makeSlots(["available", "available"])} onChange={onChange} />);

    fireEvent.click(slotButton("14:00"));
    fireEvent.click(slotButton("14:00")); // 재탭 → 해제

    expect(slotButton("14:00")).toHaveAttribute("aria-pressed", "false");
    expect(onChange).toHaveBeenLastCalledWith(null);
  });
});

describe("SlotGrid 점유/표시 전용 회귀 (AC4 — 4.3 경계 보존)", () => {
  it("past/reserved 는 button 아님 · 클릭/포커스 불가 · aria-disabled · 취소선+sr-only 병행", () => {
    const { container } = render(
      <Harness slots={makeSlots(["available", "reserved", "past"])} />,
    );

    // available 만 button(1개), past/reserved 는 span 으로 표시 전용 유지.
    expect(container.querySelectorAll('[data-status="available"]')[0]?.tagName).toBe("BUTTON");
    const reserved = container.querySelector('[data-status="reserved"]');
    const past = container.querySelector('[data-status="past"]');
    expect(reserved?.tagName).toBe("SPAN");
    expect(reserved).toHaveAttribute("aria-disabled", "true");
    expect(reserved?.textContent).toContain("예약됨"); // 색 단독 금지 — sr-only 텍스트.
    expect(reserved?.className).toContain("line-through");
    expect(past?.textContent).toContain("지난 시간");
    expect(screen.queryByRole("button", { name: "15:00" })).not.toBeInTheDocument();
  });
});

describe("SlotGrid 키보드 대안 (AC2 — 방향키 + Enter 시작/끝)", () => {
  it("Enter 로 시작 → 방향키로 이동 → Enter 로 끝 지정해 연속 구간 확정", async () => {
    const user = userEvent.setup();
    render(<Harness slots={makeSlots(["available", "available", "available"])} />);

    slotButton("14:00").focus();
    await user.keyboard("{Enter}"); // 시작(앵커) — 14 단일 선택
    expect(slotButton("14:00")).toHaveAttribute("aria-pressed", "true");

    fireEvent.keyDown(slotButton("14:00"), { key: "ArrowRight" }); // 포커스 15 로 이동
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "ArrowRight" }); // 16 으로
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: "Enter" }); // 끝 → 14·15·16

    expect(slotButton("14:00")).toHaveAttribute("aria-pressed", "true");
    expect(slotButton("15:00")).toHaveAttribute("aria-pressed", "true");
    expect(slotButton("16:00")).toHaveAttribute("aria-pressed", "true");
  });

  it("방향키 이동은 비활성(reserved) 슬롯을 스킵한다", () => {
    // [14 avail, 15 reserved, 16 avail] — 14 에서 ArrowRight → 15 스킵하고 16 포커스.
    render(<Harness slots={makeSlots(["available", "reserved", "available"])} />);

    slotButton("14:00").focus();
    fireEvent.keyDown(slotButton("14:00"), { key: "ArrowRight" });
    expect(document.activeElement).toBe(slotButton("16:00"));
  });

  it("Enter 끝 지정이 점유를 가로지르면 무시한다(앵커 유지)", () => {
    render(<Harness slots={makeSlots(["available", "reserved", "available"])} />);

    slotButton("14:00").focus();
    fireEvent.keyDown(slotButton("14:00"), { key: "Enter" }); // 앵커 14
    // 16 으로 직접 포커스 후 Enter → 15(reserved) 가로질러 확장 무시.
    slotButton("16:00").focus();
    fireEvent.keyDown(slotButton("16:00"), { key: "Enter" });

    expect(slotButton("14:00")).toHaveAttribute("aria-pressed", "true");
    expect(slotButton("16:00")).toHaveAttribute("aria-pressed", "false");
  });

  it("로빙 탭인덱스 — 첫 available 한 칸만 tabIndex=0", () => {
    render(<Harness slots={makeSlots(["available", "available"])} />);
    expect(slotButton("14:00")).toHaveAttribute("tabindex", "0");
    expect(slotButton("15:00")).toHaveAttribute("tabindex", "-1");
  });
});

describe("SlotGrid 드래그 (AC1 — Pointer Events, 인프라 가능 범위)", () => {
  it("pointerDown→pointerEnter→pointerUp 로 연속 확장한다", () => {
    render(<Harness slots={makeSlots(["available", "available", "available"])} />);

    fireEvent.pointerDown(slotButton("14:00"), { pointerId: 1 });
    fireEvent.pointerEnter(slotButton("16:00"), { pointerId: 1 }); // 14→16 연속 확장
    fireEvent.pointerUp(slotButton("16:00"), { pointerId: 1 });

    expect(slotButton("14:00")).toHaveAttribute("aria-pressed", "true");
    expect(slotButton("15:00")).toHaveAttribute("aria-pressed", "true");
    expect(slotButton("16:00")).toHaveAttribute("aria-pressed", "true");
  });

  it("드래그가 점유 슬롯에서 멈춘다(클램프 — 첫 점유 직전까지)", () => {
    // [14 avail, 15 avail, 16 reserved, 17 avail] — 14 에서 17 로 드래그해도 16 에서 멈춰 14·15 만.
    render(
      <Harness slots={makeSlots(["available", "available", "reserved", "available"])} />,
    );

    fireEvent.pointerDown(slotButton("14:00"), { pointerId: 1 });
    fireEvent.pointerEnter(slotButton("17:00"), { pointerId: 1 }); // 16(reserved) 가로지르기 시도
    fireEvent.pointerUp(slotButton("17:00"), { pointerId: 1 });

    expect(slotButton("14:00")).toHaveAttribute("aria-pressed", "true");
    expect(slotButton("15:00")).toHaveAttribute("aria-pressed", "true");
    expect(slotButton("17:00")).toHaveAttribute("aria-pressed", "false"); // 점유 못 넘음.
  });
});
