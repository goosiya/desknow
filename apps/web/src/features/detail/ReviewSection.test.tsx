// 룸 상세 후기 섹션 테스트 (Story 5.5 — AC4). reviewsListRoomReviews SDK 를 모킹해 별점 a11y·
// 익명(작성자 미표시)·0건 빈 상태·목록 렌더를 라이브 백엔드 없이 검증한다.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { reviewsListRoomReviews } from "@/lib/api-client";
import { ReviewSection } from "./ReviewSection";

vi.mock("@/lib/api-client", () => ({ reviewsListRoomReviews: vi.fn() }));

const mockList = vi.mocked(reviewsListRoomReviews);

// 목록 응답 봉투 헬퍼 — 커서 페이징(F) 전환으로 SDK 응답이 배열이 아니라 `{ items, next_cursor }` 봉투다.
function page(items: unknown[], nextCursor: string | null = null) {
  return { data: { items, next_cursor: nextCursor } };
}

function renderSection(roomId = "room-1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<ReviewSection roomId={roomId} />, { wrapper });
}

function review(overrides: Record<string, unknown> = {}) {
  return {
    id: "rev-1",
    rating: 4,
    text: "조용하고 좋았어요",
    created_at: "2026-06-17T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ReviewSection (AC4)", () => {
  it("후기 목록을 별점 aria-label·텍스트로 렌더한다(별점 색 단독 금지·SR 읽기 가능)", async () => {
    mockList.mockResolvedValue(page([review({ rating: 5 })]) as never);
    renderSection();

    await waitFor(() =>
      expect(screen.getByText("조용하고 좋았어요")).toBeInTheDocument(),
    );
    // 별점은 색 단독 금지 — aria-label("별점 5점 만점에 5점") + 숫자("5/5") 병행.
    expect(screen.getByLabelText("별점 5점 만점에 5점")).toBeInTheDocument();
    expect(screen.getByText("5/5")).toBeInTheDocument();
  });

  it("작성자 식별 정보를 노출하지 않는다(익명 — KTH 결정 1)", async () => {
    // 서버 응답엔 작성자 필드가 없다. 혹시 텍스트에 우연히 안 들어가도 booker/이메일류 미표시 확인.
    mockList.mockResolvedValue(page([review()]) as never);
    renderSection();

    await waitFor(() =>
      expect(screen.getByText("조용하고 좋았어요")).toBeInTheDocument(),
    );
    expect(screen.queryByText(/@/)).not.toBeInTheDocument(); // 이메일류 미노출
    expect(screen.queryByText(/booker/i)).not.toBeInTheDocument();
  });

  it("0건이면 빈 상태 카피를 보인다(막다른 화면 금지)", async () => {
    mockList.mockResolvedValue(page([]) as never);
    renderSection();

    await waitFor(() =>
      expect(screen.getByText(/아직 후기가 없어요/)).toBeInTheDocument(),
    );
  });

  it("여러 후기를 서버 순서(최신순)대로 렌더한다", async () => {
    mockList.mockResolvedValue(page([
        review({ id: "rev-new", text: "최근 후기", created_at: "2026-06-17T00:00:00Z" }),
        review({ id: "rev-old", text: "오래된 후기", created_at: "2026-06-10T00:00:00Z" }),
      ]) as never);
    renderSection();

    await waitFor(() => expect(screen.getByText("최근 후기")).toBeInTheDocument());
    // 서버가 준 순서(최신 먼저)를 그대로 렌더 — 클라 재정렬 안 함. DOM 위치로 순서 확인.
    const recent = screen.getByText("최근 후기");
    const old = screen.getByText("오래된 후기");
    expect(
      recent.compareDocumentPosition(old) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy(); // 최근 후기가 오래된 후기보다 앞(먼저)
  });

  it("실패 시 막다른 화면 대신 재시도 안내를 보인다", async () => {
    mockList.mockRejectedValue(new Error("boom"));
    renderSection();

    await waitFor(() =>
      expect(screen.getByText(/후기를 불러오지 못했어요/)).toBeInTheDocument(),
    );
  });
});

describe("ReviewSection 제공자 답글 (5.6 AC5)", () => {
  it("답글이 있는 후기는 '제공자 답글' 라벨·텍스트·날짜를 익명으로 중첩 표시한다", async () => {
    mockList.mockResolvedValue(page([
        review({
          text: "조용하고 좋았어요",
          reply: {
            text: "이용해 주셔서 감사합니다",
            created_at: "2026-06-18T00:00:00Z",
          },
        }),
      ]) as never);
    renderSection();

    await waitFor(() =>
      expect(screen.getByText("이용해 주셔서 감사합니다")).toBeInTheDocument(),
    );
    // "제공자 답글" 고정 라벨(제공자명 미노출 — 익명).
    expect(screen.getByText("제공자 답글")).toBeInTheDocument();
    // 답글 블록은 의미 라벨(aria-label)로 구분된다(a11y).
    expect(screen.getByLabelText("제공자 답글")).toBeInTheDocument();
    // 답글 작성일이 절대 표기(KST)로 보인다.
    expect(screen.getByText(/2026년 6월 18일/)).toBeInTheDocument();
    // 제공자 식별 정보 미노출(익명) — 이메일류 없음.
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();
  });

  it("답글이 없는 후기는 답글 영역을 표시하지 않는다(선택적·빈 상태 카피 불요)", async () => {
    mockList.mockResolvedValue(page([review({ text: "조용해요", reply: null })]) as never);
    renderSection();

    await waitFor(() =>
      expect(screen.getByText("조용해요")).toBeInTheDocument(),
    );
    expect(screen.queryByText("제공자 답글")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("제공자 답글")).not.toBeInTheDocument();
  });

  it("손상된 작성일(malformed)이면 'Invalid Date'/NaN 대신 안전 폴백한다(가드 회수)", async () => {
    // 후기·답글 양쪽 날짜에 손상 입력 — formatReviewDate 가드가 빈 문자열로 degrade.
    mockList.mockResolvedValue(page([
        review({
          text: "본문은 정상",
          created_at: "not-a-date",
          reply: { text: "답글도 정상", created_at: "garbage" },
        }),
      ]) as never);
    renderSection();

    await waitFor(() =>
      expect(screen.getByText("본문은 정상")).toBeInTheDocument(),
    );
    // 깨진 날짜가 "Invalid Date"/"NaN"으로 새지 않는다 — 본문·답글 텍스트는 정상 렌더.
    expect(screen.getByText("답글도 정상")).toBeInTheDocument();
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });
});
