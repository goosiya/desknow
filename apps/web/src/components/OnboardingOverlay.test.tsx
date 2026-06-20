import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingOverlay } from "./OnboardingOverlay";

// OnboardingOverlay 테스트 (Story 3.9 — AC1·AC2·AC4). 첫 방문 캐러셀 렌더·페이지 이동·
// 닫기 정책: "다시 보지 않기"만 영속(재방문 무노출), "시작하기"·우상단 X는 영속 없이 닫기(재노출).
//
// 쿼리 0이라 QueryClient 래퍼 불필요. localStorage 누수 방지 위해 beforeEach 에서 clear().
const ONBOARDING_SEEN_KEY = "desknow:onboarding:seen";

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OnboardingOverlay (AC1·AC2·AC4)", () => {
  it("플래그 없으면 첫 슬라이드(환영)와 내비게이션을 모달로 렌더한다(AC1)", async () => {
    render(<OnboardingOverlay />);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "DeskNow에 오신 걸 환영해요" }),
    ).toBeInTheDocument();
    // 첫 페이지엔 이전 없음, 다음·다시 보지 않기 있음.
    expect(screen.getByRole("button", { name: "다음" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 보지 않기" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "이전" })).not.toBeInTheDocument();
  });

  it("다음으로 페이지를 넘기면 다음 안내가 보인다", async () => {
    const user = userEvent.setup();
    render(<OnboardingOverlay />);

    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "다음" }));

    expect(
      screen.getByRole("heading", { name: "지도와 목록으로 찾기" }),
    ).toBeInTheDocument();
    // 2페이지부터는 이전 버튼이 생긴다.
    expect(screen.getByRole("button", { name: "이전" })).toBeInTheDocument();
  });

  it("페이지 점으로 마지막 슬라이드 이동 시 시작하기가 나오고, 누르면 영속 없이 닫힌다(재방문 재노출)", async () => {
    const user = userEvent.setup();
    render(<OnboardingOverlay />);

    await screen.findByRole("dialog");
    // 마지막 안내 점(4번째)으로 점프.
    await user.click(screen.getByRole("tab", { name: "4번째 안내" }));

    const start = screen.getByRole("button", { name: "시작하기" });
    expect(start).toBeInTheDocument();
    await user.click(start);

    // 시작하기는 영속하지 않는다 — 플래그 미설정(다음 방문 시 다시 노출).
    expect(localStorage.getItem(ONBOARDING_SEEN_KEY)).toBeNull();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("우상단 X 클릭 시 영속 없이 닫힌다(재방문 재노출)", async () => {
    const user = userEvent.setup();
    render(<OnboardingOverlay />);

    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "닫기" }));

    // X도 영속하지 않는다 — 플래그 미설정.
    expect(localStorage.getItem(ONBOARDING_SEEN_KEY)).toBeNull();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it('"다시 보지 않기" 클릭 시 플래그 영속 + 다이얼로그 닫힘(AC2)', async () => {
    const user = userEvent.setup();
    render(<OnboardingOverlay />);

    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "다시 보지 않기" }));

    expect(localStorage.getItem(ONBOARDING_SEEN_KEY)).toBe("1");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("플래그 있으면 렌더되지 않는다(AC3 재방문 무노출)", () => {
    localStorage.setItem(ONBOARDING_SEEN_KEY, "1");
    render(<OnboardingOverlay />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
