// 후기 작성 폼 테스트 (Story 5.5 — AC1·AC5). reviewsCreateReview SDK 를 모킹해 별점/텍스트 입력
// a11y·글자수·필수 검증·제출 인자·409 안내 카피를 검증한다.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { reviewsCreateReview } from "@/lib/api-client";
import { ReviewForm } from "./ReviewForm";

vi.mock("@/lib/api-client", () => ({
  reviewsCreateReview: vi.fn(),
  // useCreateReview → useRoomReviews 모듈이 import 하므로(키 함수만 사용) 대역 제공.
  reviewsListRoomReviews: vi.fn(),
}));

const mockCreate = vi.mocked(reviewsCreateReview);

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(<ReviewForm reservationId="r1" roomId="room-1" />, { wrapper });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ReviewForm (AC1·AC5)", () => {
  it("별점 라디오·텍스트 입력이 접근 가능한 이름을 갖는다(a11y)", () => {
    setup();
    // 별점 = 1~5 라디오, 각 aria-label "별점 N점"(키보드·SR 접근).
    for (let n = 1; n <= 5; n += 1) {
      expect(screen.getByRole("radio", { name: `별점 ${n}점` })).toBeInTheDocument();
    }
    // 텍스트 = 가시 라벨로 연결된 입력.
    expect(screen.getByLabelText(/후기/)).toBeInTheDocument();
  });

  it("글자수 카운터가 입력에 따라 갱신된다", () => {
    setup();
    expect(screen.getByText("0/500")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/후기/), { target: { value: "좋아요" } });
    expect(screen.getByText("3/500")).toBeInTheDocument();
  });

  it("별점 미선택 또는 텍스트 공백이면 제출 버튼이 비활성(필수)", () => {
    setup();
    const submit = screen.getByRole("button", { name: "후기 남기기" });
    expect(submit).toBeDisabled(); // 초기: 별점 0 + 텍스트 빈

    // 별점만 선택 → 여전히 비활성(텍스트 필수).
    fireEvent.click(screen.getByRole("radio", { name: "별점 4점" }));
    expect(submit).toBeDisabled();

    // 텍스트까지 입력 → 활성.
    fireEvent.change(screen.getByLabelText(/후기/), { target: { value: "조용했어요" } });
    expect(submit).toBeEnabled();
  });

  it("공백만 텍스트는 제출 비활성(빈 후기 금지)", () => {
    setup();
    fireEvent.click(screen.getByRole("radio", { name: "별점 5점" }));
    fireEvent.change(screen.getByLabelText(/후기/), { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "후기 남기기" })).toBeDisabled();
  });

  it("제출 시 경로 reservation_id·본문 rating/text(trim)로 SDK 를 호출한다", async () => {
    mockCreate.mockResolvedValue({ data: { id: "rev-1" } } as never);
    setup();
    fireEvent.click(screen.getByRole("radio", { name: "별점 4점" }));
    fireEvent.change(screen.getByLabelText(/후기/), {
      target: { value: "  조용하고 좋았어요  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "후기 남기기" }));

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          path: { reservation_id: "r1" },
          body: { rating: 4, text: "조용하고 좋았어요" }, // trim 적용
          throwOnError: true,
        }),
      ),
    );
  });

  it("이미 작성됨(409 REVIEW_ALREADY_EXISTS) → 친근 카피·코드 미노출", async () => {
    mockCreate.mockRejectedValue({
      detail: { code: "REVIEW_ALREADY_EXISTS", message: "이미 후기를 작성한 예약이에요." },
    });
    setup();
    fireEvent.click(screen.getByRole("radio", { name: "별점 3점" }));
    fireEvent.change(screen.getByLabelText(/후기/), { target: { value: "좋아요" } });
    fireEvent.click(screen.getByRole("button", { name: "후기 남기기" }));

    await waitFor(() =>
      expect(screen.getByText("이미 후기를 남기셨어요.")).toBeInTheDocument(),
    );
    // 에러코드 문자열은 화면에 노출하지 않는다(UX-DR10).
    expect(screen.queryByText(/REVIEW_ALREADY_EXISTS/)).not.toBeInTheDocument();
  });
});
