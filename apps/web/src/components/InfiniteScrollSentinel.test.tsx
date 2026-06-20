// 무한스크롤 sentinel 테스트 (F — 목록 무한스크롤). jsdom 엔 IntersectionObserver 가 없으므로
// 버튼(수동 폴백) 경로만 검증한다 — hasNextPage 게이팅·클릭 시 fetchNextPage 호출·로딩 표시.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InfiniteScrollSentinel } from "./InfiniteScrollSentinel";

describe("InfiniteScrollSentinel", () => {
  it("hasNextPage=false 면 아무것도 렌더하지 않는다(자연 종료)", () => {
    const fetchNextPage = vi.fn();
    const { container } = render(
      <InfiniteScrollSentinel
        hasNextPage={false}
        isFetchingNextPage={false}
        fetchNextPage={fetchNextPage}
      />,
    );
    // 막다른 표식 없음 — sentinel·버튼 모두 미노출.
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("infinite-scroll-sentinel")).toBeNull();
    expect(screen.queryByRole("button", { name: "더 보기" })).toBeNull();
  });

  it("hasNextPage=true 면 '더 보기' 버튼을 보이고 클릭 시 fetchNextPage 를 호출한다", () => {
    const fetchNextPage = vi.fn();
    render(
      <InfiniteScrollSentinel
        hasNextPage={true}
        isFetchingNextPage={false}
        fetchNextPage={fetchNextPage}
      />,
    );

    expect(screen.getByTestId("infinite-scroll-sentinel")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "더 보기" });
    expect(button).toBeEnabled();

    fireEvent.click(button);
    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });

  it("isFetchingNextPage=true 면 '불러오는 중…' 표시 + 버튼 비활성(중복 트리거 방지)", () => {
    const fetchNextPage = vi.fn();
    render(
      <InfiniteScrollSentinel
        hasNextPage={true}
        isFetchingNextPage={true}
        fetchNextPage={fetchNextPage}
      />,
    );

    const button = screen.getByRole("button", { name: "불러오는 중…" });
    expect(button).toBeDisabled();
    expect(screen.queryByRole("button", { name: "더 보기" })).toBeNull();
  });
});
