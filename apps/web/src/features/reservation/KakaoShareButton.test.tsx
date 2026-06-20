// KakaoShareButton 테스트 (Story 5.4 — AC1·AC3·AC4). 클릭 시 shareReservation 호출(인자 검증)·
// 로드 실패 graceful degrade(안내 + 크래시 없음 + 재시도)·a11y(role·aria-label·tap-target·아이콘+
// 텍스트)·카톡 외 SNS 진입점 부재. 실제 `<script>` 주입을 피하려 kakao-share 모듈을 모킹한다.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { shareReservation } from "@/lib/kakao-share";
import { KakaoShareButton } from "./KakaoShareButton";

vi.mock("@/lib/kakao-share", () => ({
  shareReservation: vi.fn(),
}));

const mockShare = vi.mocked(shareReservation);

const PROPS = {
  roomName: "강남 스터디라운지",
  slotStarts: ["2026-06-20T05:00:00Z"],
  roomId: "room-1",
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("KakaoShareButton (Story 5.4 — AC1·AC3·AC4)", () => {
  it("클릭하면 shareReservation 을 룸 이름·슬롯·룸 id 로 호출한다", async () => {
    mockShare.mockResolvedValue(undefined);
    render(<KakaoShareButton {...PROPS} />);

    fireEvent.click(screen.getByRole("button", { name: "카카오톡으로 공유" }));
    await waitFor(() =>
      expect(mockShare).toHaveBeenCalledWith({
        roomName: "강남 스터디라운지",
        slotStarts: ["2026-06-20T05:00:00Z"],
        roomId: "room-1",
      }),
    );
  });

  it("공유(로드) 실패 시 친근한 안내를 보이고 화면이 크래시하지 않는다(AC4)", async () => {
    mockShare.mockRejectedValue(new Error("SDK load failed"));
    render(<KakaoShareButton {...PROPS} />);

    fireEvent.click(screen.getByRole("button", { name: "카카오톡으로 공유" }));
    expect(
      await screen.findByText("지금은 공유를 할 수 없어요. 잠시 후 다시 해주세요."),
    ).toBeInTheDocument();
    // 버튼은 여전히 존재(재시도 가능) — 막다른 화면 금지.
    expect(screen.getByRole("button", { name: "카카오톡으로 공유" })).toBeInTheDocument();
  });

  it("실패 후 다시 클릭하면 안내가 사라지고 재호출된다(재시도 — AC4)", async () => {
    mockShare.mockRejectedValueOnce(new Error("fail")).mockResolvedValueOnce(undefined);
    render(<KakaoShareButton {...PROPS} />);

    const button = screen.getByRole("button", { name: "카카오톡으로 공유" });
    fireEvent.click(button);
    await screen.findByText("지금은 공유를 할 수 없어요. 잠시 후 다시 해주세요.");

    fireEvent.click(button);
    await waitFor(() =>
      expect(
        screen.queryByText("지금은 공유를 할 수 없어요. 잠시 후 다시 해주세요."),
      ).not.toBeInTheDocument(),
    );
    expect(mockShare).toHaveBeenCalledTimes(2);
  });

  it("접근성 — 버튼 role·aria-label·tap-target·아이콘+텍스트(색/아이콘 단독 금지)", () => {
    mockShare.mockResolvedValue(undefined);
    render(<KakaoShareButton {...PROPS} />);

    const button = screen.getByRole("button", { name: "카카오톡으로 공유" });
    expect(button).toHaveClass("tap-target");
    // 가시 텍스트 "공유" 동반(아이콘 단독 아님).
    expect(button).toHaveTextContent("공유");
  });

  it("카톡 외 SNS 진입점은 없다 — 단일 공유 버튼만(AC4·epics L958)", () => {
    mockShare.mockResolvedValue(undefined);
    render(<KakaoShareButton {...PROPS} />);
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });
});
