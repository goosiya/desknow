import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NetworkNotice } from "./NetworkNotice";

// NetworkNotice 테스트 (Story 3.8 — AC1·AC2·AC3). 확정 카피·role=status·className 오버라이드.

describe("NetworkNotice (AC1·AC2·AC3)", () => {
  it("확정 카피를 role=status 로 렌더한다(스크린리더 공지)", () => {
    render(<NetworkNotice />);
    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent(
      "네트워크 연결이 끊겼어요. 연결되면 다시 보여드릴게요.",
    );
    expect(notice).toHaveAttribute("aria-live", "polite");
  });

  it("className 으로 배치를 오버라이드할 수 있다", () => {
    render(<NetworkNotice className="absolute top-0" />);
    expect(screen.getByRole("status")).toHaveClass("absolute", "top-0");
  });
});
