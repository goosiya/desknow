"use client";

// provider 후기 보기 + 답글 (idea.md L39). 내 스터디룸 후기를 보고 답글을 단다. 답글이 이미 있으면
// 표시만 하고(수정/삭제는 범위 밖), 없으면 작성 폼을 보인다. 백엔드 호출은 생성 SDK 경유 훅만.
import { useState } from "react";

import type { ReviewListItem } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { InfiniteScrollSentinel } from "@/components/InfiniteScrollSentinel";
import { StarRating } from "@/features/detail/StarRating";
import { useProviderReviews, useReplyToReview } from "./useProviderReviews";

/** KST 날짜(YYYY년 M월 D일). */
function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "Asia/Seoul",
  }).format(new Date(iso));
}

function ReviewCard({ review, roomId }: { review: ReviewListItem; roomId: string }) {
  const reply = useReplyToReview(roomId);
  const [text, setText] = useState("");

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <StarRating rating={review.rating} />
        <span className="text-xs text-muted-foreground">{formatDate(review.created_at)}</span>
      </div>
      <p className="text-sm leading-[1.6] text-card-foreground">{review.text}</p>

      {review.reply ? (
        // 이미 답글 있음 — 표시만(들여쓰기 + 보조 톤).
        <div className="rounded-md border-l-2 border-primary bg-secondary/50 px-3 py-2">
          <p className="text-xs font-medium text-muted-foreground">사장님 답글</p>
          <p className="mt-0.5 text-sm leading-[1.6] text-card-foreground">{review.reply.text}</p>
        </div>
      ) : (
        // 답글 작성 폼.
        <div className="flex flex-col gap-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={2}
            maxLength={500}
            placeholder="답글을 남겨보세요(최대 500자)"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm leading-[1.6] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
          />
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              disabled={reply.isPending || text.trim().length === 0}
              onClick={() => reply.mutate({ reviewId: review.id, text: text.trim() })}
            >
              {reply.isPending ? "등록 중…" : "답글 등록"}
            </Button>
            {reply.isError ? (
              <span className="text-sm text-destructive">등록에 실패했어요.</span>
            ) : null}
          </div>
        </div>
      )}
    </li>
  );
}

export function ProviderReviews() {
  const {
    roomId,
    hasRoom,
    isLoading,
    isError,
    reviews,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useProviderReviews();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">후기</h1>
        <p className="text-sm leading-[1.6] text-muted-foreground">
          내 스터디룸에 달린 후기를 보고 답글을 남길 수 있어요.
        </p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">불러오는 중…</p>
      ) : isError ? (
        <p className="text-sm text-pin-full">후기를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.</p>
      ) : !hasRoom ? (
        <p className="rounded-lg border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
          먼저 스터디룸을 등록하면 후기를 받을 수 있어요.
        </p>
      ) : reviews.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
          아직 후기가 없어요.
        </p>
      ) : (
        <>
          <ul className="flex flex-col gap-2">
            {reviews.map((r) => (
              <ReviewCard key={r.id} review={r} roomId={roomId} />
            ))}
          </ul>
          <InfiniteScrollSentinel
            hasNextPage={hasNextPage}
            isFetchingNextPage={isFetchingNextPage}
            fetchNextPage={fetchNextPage}
          />
        </>
      )}
    </div>
  );
}
