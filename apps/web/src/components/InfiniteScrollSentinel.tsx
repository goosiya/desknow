// 무한스크롤 sentinel (F — 목록 무한스크롤). 목록 하단에 두는 감지 표식 — 뷰포트에 들어오면
// 다음 페이지를 자동 로드한다(IntersectionObserver). 6개 목록 표면이 공유한다.
//
// **접근성·견고성:** 관찰자가 없는 환경(IntersectionObserver 미지원·jsdom 테스트)이나 자동 로드가
// 안 잡히는 경우를 위해 **"더 보기" 버튼**을 항상 함께 렌더한다(자동+수동 이중 트리거). 마지막
// 페이지(hasNextPage=false)면 아무것도 렌더하지 않는다(막다른 표식 없음 — 자연 종료).
"use client";

import { useEffect, useRef } from "react";

type InfiniteScrollSentinelProps = {
  /** 더 가져올 페이지가 있는지(useInfiniteQuery `hasNextPage`). */
  hasNextPage: boolean;
  /** 다음 페이지 로딩 중인지(중복 트리거 방지·스피너 표시). */
  isFetchingNextPage: boolean;
  /** 다음 페이지 로드 트리거(useInfiniteQuery `fetchNextPage`). */
  fetchNextPage: () => void;
};

export function InfiniteScrollSentinel({
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
}: InfiniteScrollSentinelProps) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // 더 없으면 관찰 불필요. IntersectionObserver 미지원 환경(구형·테스트)은 수동 버튼으로 폴백.
    if (!hasNextPage) return;
    if (typeof IntersectionObserver === "undefined") return;
    const node = sentinelRef.current;
    if (node === null) return;

    const observer = new IntersectionObserver(
      (entries) => {
        // 교차(뷰포트 진입) + 더 있음 + 로딩 중 아님 → 다음 페이지 로드(중복 방지).
        if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      // 하단 200px 여유로 미리 로드(끝까지 스크롤 전에 매끄럽게 이어짐).
      { rootMargin: "200px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  // 마지막 페이지면 자연 종료(막다른 표식 없음).
  if (!hasNextPage) return null;

  return (
    <div
      ref={sentinelRef}
      className="flex justify-center py-4"
      data-testid="infinite-scroll-sentinel"
    >
      <button
        type="button"
        onClick={() => fetchNextPage()}
        disabled={isFetchingNextPage}
        className="tap-target inline-flex items-center justify-center rounded-md border border-border bg-card px-4 text-sm font-medium text-card-foreground disabled:opacity-60"
      >
        {isFetchingNextPage ? "불러오는 중…" : "더 보기"}
      </button>
    </div>
  );
}
