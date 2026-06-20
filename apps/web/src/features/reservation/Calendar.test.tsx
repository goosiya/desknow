// 경량 커스텀 달력 테스트 (Story 4.3 — AC2). 날짜 선택·과거/30일 초과 비활성·키보드 이동·월 이동.
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Calendar } from "./Calendar";

const TODAY = "2026-06-15"; // 월요일

function renderCalendar(value = TODAY) {
  const onChange = vi.fn();
  render(<Calendar value={value} onChange={onChange} today={TODAY} />);
  return { onChange };
}

describe("Calendar 날짜 선택 (AC2)", () => {
  it("선택 가능한 날짜를 누르면 onChange 로 그 날짜를 알린다", () => {
    const { onChange } = renderCalendar();
    // 6월 17일(선택 가능) 셀 클릭 — aria-label 로 찾는다.
    fireEvent.click(screen.getByRole("gridcell", { name: "2026년 6월 17일" }));
    expect(onChange).toHaveBeenCalledWith("2026-06-17");
  });

  it("선택일은 aria-selected=true 로 강조된다", () => {
    renderCalendar("2026-06-16");
    expect(screen.getByRole("gridcell", { name: "2026년 6월 16일" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});

describe("Calendar 비활성 경계 (AC2)", () => {
  it("과거 날짜는 비활성(aria-disabled)이라 버튼이 아니다 — 클릭 불가", () => {
    renderCalendar();
    // 6월 14일(어제) — gridcell 이지만 button 이 아니라 비활성 span.
    const past = screen.getByRole("gridcell", { name: "2026년 6월 14일" });
    expect(past).toHaveAttribute("aria-disabled", "true");
    expect(past.tagName).not.toBe("BUTTON");
  });

  it("30일 초과 날짜는 다음 달에서 비활성이다", () => {
    // 다음 달(7월)로 이동 후 7/15(today+30=초과)는 비활성.
    renderCalendar();
    fireEvent.click(screen.getByRole("button", { name: "다음 달" }));
    const beyond = screen.getByRole("gridcell", { name: "2026년 7월 15일" });
    expect(beyond).toHaveAttribute("aria-disabled", "true");
    // 7/14(today+29=상한 포함)는 선택 가능(버튼).
    const lastSelectable = screen.getByRole("gridcell", { name: "2026년 7월 14일" });
    expect(lastSelectable.tagName).toBe("BUTTON");
  });
});

describe("Calendar 키보드 이동 (AC2 — 날짜 선택은 4.3 책임)", () => {
  it("방향키로 날짜 포커스를 옮기고 Enter/클릭으로 선택한다", () => {
    const { onChange } = renderCalendar();
    const start = screen.getByRole("gridcell", { name: "2026년 6월 16일" });
    (start as HTMLButtonElement).focus();
    // ArrowRight → 6/17 로 포커스 이동(같은 달).
    fireEvent.keyDown(start, { key: "ArrowRight" });
    expect(screen.getByRole("gridcell", { name: "2026년 6월 17일" })).toHaveFocus();
    // ArrowDown → +7일(6/24)로 이동.
    fireEvent.keyDown(screen.getByRole("gridcell", { name: "2026년 6월 17일" }), {
      key: "ArrowDown",
    });
    expect(screen.getByRole("gridcell", { name: "2026년 6월 24일" })).toHaveFocus();
    // 클릭(=Enter 와 동일 활성화)로 선택.
    fireEvent.click(screen.getByRole("gridcell", { name: "2026년 6월 24일" }));
    expect(onChange).toHaveBeenCalledWith("2026-06-24");
  });

  it("포커스된 날짜에서 Enter 로 선택한다(네이티브 button 활성화 — Task 11 ⑧)", async () => {
    const user = userEvent.setup();
    const { onChange } = renderCalendar();
    // 6/17(선택 가능) 셀에 포커스 후 Enter — 셀이 <button> 이라 네이티브 활성화로 onClick 발화.
    const cell = screen.getByRole("gridcell", { name: "2026년 6월 17일" });
    (cell as HTMLButtonElement).focus();
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledWith("2026-06-17");
  });

  it("포커스된 날짜에서 Space 로 선택한다(네이티브 button 활성화)", async () => {
    const user = userEvent.setup();
    const { onChange } = renderCalendar();
    const cell = screen.getByRole("gridcell", { name: "2026년 6월 18일" });
    (cell as HTMLButtonElement).focus();
    await user.keyboard("[Space]");
    expect(onChange).toHaveBeenCalledWith("2026-06-18");
  });

  it("이전 달 버튼은 오늘 달에서 비활성이다(과거 달로 못 감)", () => {
    renderCalendar();
    expect(screen.getByRole("button", { name: "이전 달" })).toBeDisabled();
  });
});
