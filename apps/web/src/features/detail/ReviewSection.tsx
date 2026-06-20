"use client";

// 룸 상세 후기 섹션 (Story 5.5 — AC4 · Story 5.6 — AC5). RoomDetail 3차 섹션에서 후기 목록을
// 노출하고, 후기에 제공자 답글이 있으면 후기 카드 안에 익명("제공자 답글" 라벨)으로 중첩 표시한다.
//
// ⚠️ 익명(KTH 결정 1): 각 후기는 **별점·텍스트·작성일만** 표시 — 작성자 식별 정보는 노출하지 않는다
//    (users엔 email만 있어 표시 이름 부재·프라이버시). 서버 응답(ReviewListItem)에 작성자 필드가
//    애초에 없다.
// ⚠️ 막다른 화면 금지(NFR-5): 0건=빈 상태 카피("아직 후기가 없어요"), 로딩=조용한 자리, 실패=재시도.
//    상세 화면 안의 섹션이라 전체 화면을 막지 않고 섹션 내부에서만 상태를 표현한다.
// ⚠️ 별점 색 단독 금지: StarRating(채움/빈 별 + 숫자 + aria-label) 재사용(review-accessibility L61).
//
// 백엔드 호출은 useRoomReviews(SDK 경유) — 직접 fetch 0. 작성일은 절대 표기(상대일 클라 재판정 금지).
import { InfiniteScrollSentinel } from "@/components/InfiniteScrollSentinel";
import type { ReviewListItem } from "@/lib/api-client";

import { StarRating } from "./StarRating";
import { useRoomReviews } from "./useRoomReviews";

/**
 * 후기·답글 작성일 — 서버 UTC(...Z) → Asia/Seoul "2026년 6월 17일"(절대 표기, 상대일 재판정 금지).
 *
 * ⚠️ malformed 가드(5.5 review defer 회수): 손상된 created_at(파싱 불가)이면 Intl 포맷이 "Invalid
 *    Date"/NaN을 내므로, Date가 유효하지 않으면 빈 문자열로 안전 폴백한다(후기·답글 양쪽 날짜에 동일
 *    적용 — StarRating 클램프와 대칭, 깨진 입력에 화면이 무너지지 않게 degrade).
 */
function formatReviewDate(createdAtUtc: string): string {
  const date = new Date(createdAtUtc);
  if (Number.isNaN(date.getTime())) {
    return ""; // 손상 입력 — 날짜 미표시로 안전 degrade(예외/NaN 노출 금지)
  }
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
}

/** 제공자 답글(익명) — "제공자 답글" 라벨 + 텍스트 + 작성일. 후기 카드 안에 시각 구분 중첩. */
function ProviderReply({ reply }: { reply: NonNullable<ReviewListItem["reply"]> }) {
  return (
    // 시각 구분 — 좌측 보더 + muted 배경 + 들여쓰기(후기 본문과 구별). 의미 라벨로 a11y 보강.
    <div
      aria-label="제공자 답글"
      className="ml-3 flex flex-col gap-1 rounded-md border-l-2 border-border bg-muted/50 py-2 pl-3 pr-2"
    >
      <div className="flex items-center justify-between gap-2">
        {/* 제공자명 미노출(익명) — 고정 라벨만. */}
        <span className="text-xs font-medium text-foreground">제공자 답글</span>
        <span className="text-xs text-muted-foreground">
          {formatReviewDate(reply.created_at)}
        </span>
      </div>
      {/* 줄바꿈 보존 — 후기 본문과 동일(whitespace-pre-line). */}
      <p className="whitespace-pre-line text-sm leading-[1.6] text-card-foreground">
        {reply.text}
      </p>
    </div>
  );
}

/** 후기 한 건(익명) — 별점 + 작성일 + 텍스트 + (있으면) 제공자 답글. 작성자 미표시. */
function ReviewItem({ review }: { review: ReviewListItem }) {
  return (
    <li className="flex flex-col gap-1.5 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <StarRating rating={review.rating} />
        <span className="text-xs text-muted-foreground">
          {formatReviewDate(review.created_at)}
        </span>
      </div>
      {/* 줄바꿈 보존 — 사용자가 입력한 줄바꿈을 그대로 표시(whitespace-pre-line). */}
      <p className="whitespace-pre-line text-sm leading-[1.6] text-card-foreground">
        {review.text}
      </p>
      {/* 제공자 답글 — 있으면 후기 카드 안에 중첩 표시(5.6). 없으면 미표시(선택적·빈 상태 카피 불요). */}
      {review.reply ? <ProviderReply reply={review.reply} /> : null}
    </li>
  );
}

export function ReviewSection({ roomId }: { roomId: string }) {
  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useRoomReviews(roomId);

  return (
    <section aria-label="후기" className="flex flex-col gap-3">
      <h2 className="text-base font-semibold text-foreground">후기</h2>

      {isLoading ? (
        // 로딩 — 조용한 자리(섹션 내부, 막다른 화면 금지).
        <div
          data-testid="reviews-skeleton"
          className="h-20 w-full animate-pulse rounded-lg bg-muted"
        />
      ) : isError ? (
        // 실패 — 섹션 내부 안내(전체 화면을 막지 않음). 상세 본문은 위에서 이미 표시됨.
        <p className="rounded-lg border border-border bg-muted/50 p-4 text-sm text-muted-foreground">
          후기를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.
        </p>
      ) : !data || data.length === 0 ? (
        // 빈 상태(0건) — 막다른 화면 금지 카피(작성 유도는 예약현황 진입점이 담당).
        <div className="rounded-lg border border-border bg-muted/50 p-6 text-sm text-muted-foreground">
          아직 후기가 없어요. 첫 후기를 남겨보세요.
        </div>
      ) : (
        // 목록 — 최신순(서버 created_at desc 보장). 각 행 익명(별점·텍스트·작성일).
        <>
          <ul className="flex flex-col gap-2">
            {data.map((review) => (
              <ReviewItem key={review.id} review={review} />
            ))}
          </ul>
          <InfiniteScrollSentinel
            hasNextPage={hasNextPage}
            isFetchingNextPage={isFetchingNextPage}
            fetchNextPage={fetchNextPage}
          />
        </>
      )}
    </section>
  );
}
