"use client";

// 후기 작성 폼 (Story 5.5 — AC1·AC5 · review-accessibility.md L61). 예약현황의 이용 완료·미작성
// 행에서 별점+텍스트 후기를 작성한다.
//
// ⚠️ a11y(review-accessibility L61): ① 별점 입력=키보드·SR 접근(네이티브 라디오 그룹 — 화살표/탭
//    이동, 각 별 aria-label="별점 N점") ② 텍스트=가시 라벨 for/id 연결·글자수 카운터 "n/500"·필수
//    별표+'필수' 텍스트 ③ 에러=색+아이콘+텍스트(색 단독 금지).
// ⚠️ set-state-in-effect 금지(반복 함정 #7): 별점·텍스트=로컬 state, 제출=클릭 이벤트(effect 아님).
// ⚠️ 막다른 화면 금지: 409(이용 완료 안 됨/이미 작성)·기타 실패는 friendly 카피 + 재시도(코드 미노출).
import { useId, useState } from "react";
import { AlertCircle, Star } from "lucide-react";

import { isReservationNotCompleted, isReviewAlreadyExists } from "./errors";
import { useCreateReview } from "./useCreateReview";

/** 후기 텍스트 최대 길이 — 백엔드 스키마(REVIEW_TEXT_MAX_LENGTH)와 정합(500). */
const TEXT_MAX_LENGTH = 500;

/** 별점 입력 실패 시 화면 카피(코드/숫자 미노출 — UX-DR10, detail.code 는 분기에만). */
function errorCopy(error: unknown): string {
  if (isReviewAlreadyExists(error)) {
    return "이미 후기를 남기셨어요.";
  }
  if (isReservationNotCompleted(error)) {
    return "아직 이용 완료 전이라 후기를 남길 수 없어요.";
  }
  return "후기를 남기지 못했어요. 잠시 후 다시 시도해 주세요.";
}

export function ReviewForm({
  reservationId,
  roomId,
}: {
  reservationId: string;
  roomId: string;
}) {
  const create = useCreateReview();
  const [rating, setRating] = useState(0); // 0 = 미선택
  const [text, setText] = useState("");
  const textId = useId();
  const counterId = useId();

  // 제출 가능 = 별점 선택됨 + 텍스트 공백 아님 + 진행 중 아님(render-time 파생 — effect 아님).
  const trimmed = text.trim();
  const canSubmit = rating >= 1 && trimmed.length > 0 && !create.isPending;

  function handleSubmit() {
    if (!canSubmit) return; // 방어(버튼 disabled와 이중)
    create.mutate({ reservationId, roomId, rating, text: trimmed });
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/40 p-3">
      <p className="text-sm font-medium text-card-foreground">
        이용은 어떠셨어요? 짧게 후기를 남겨주세요.
      </p>

      {/* ── 별점 입력(네이티브 라디오 그룹 — 키보드 화살표·탭 이동·SR 라벨) ── */}
      <fieldset className="flex flex-col gap-1">
        <legend className="text-xs font-medium text-card-foreground">
          별점 <span aria-hidden="true" className="text-destructive">*</span>
          <span className="sr-only">필수</span>
        </legend>
        <div className="flex items-center gap-0.5">
          {[1, 2, 3, 4, 5].map((n) => (
            <label
              key={n}
              className="tap-target inline-flex cursor-pointer items-center justify-center"
            >
              <input
                type="radio"
                name={`rating-${reservationId}`}
                value={n}
                checked={rating === n}
                onChange={() => setRating(n)}
                aria-label={`별점 ${n}점`}
                className="sr-only peer"
              />
              {/* 채움(형태) + 색 + 라벨 3중 신호. 포커스 시 별에 링(키보드 가시성). */}
              <Star
                aria-hidden="true"
                className={
                  (n <= rating
                    ? "fill-current text-accent"
                    : "text-muted-foreground") +
                  " size-7 rounded peer-focus-visible:ring-2 peer-focus-visible:ring-ring"
                }
              />
            </label>
          ))}
        </div>
      </fieldset>

      {/* ── 텍스트 입력(가시 라벨 for/id·글자수 카운터·필수) ── */}
      <div className="flex flex-col gap-1">
        <label htmlFor={textId} className="text-xs font-medium text-card-foreground">
          후기 <span aria-hidden="true" className="text-destructive">*</span>
          <span className="sr-only">필수</span>
        </label>
        <textarea
          id={textId}
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, TEXT_MAX_LENGTH))}
          maxLength={TEXT_MAX_LENGTH}
          rows={3}
          aria-describedby={counterId}
          placeholder="공간은 어땠는지 다른 분께 알려주세요."
          className="w-full resize-y rounded-md border border-input bg-card p-2 text-sm leading-[1.6] text-card-foreground"
        />
        <span id={counterId} className="self-end text-xs text-muted-foreground">
          {text.length}/{TEXT_MAX_LENGTH}
        </span>
      </div>

      {/* ── 에러 안내(색 + 아이콘 + 텍스트 — 색 단독 금지) ── */}
      {create.isError ? (
        <p
          role="status"
          className="flex items-center gap-1.5 text-xs leading-[1.6] text-destructive"
        >
          <AlertCircle aria-hidden="true" className="size-4 shrink-0" />
          {errorCopy(create.error)}
        </p>
      ) : null}

      <button
        type="button"
        onClick={handleSubmit}
        disabled={!canSubmit}
        className="tap-target inline-flex items-center justify-center self-start rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
      >
        {create.isPending ? "남기는 중…" : "후기 남기기"}
      </button>
    </div>
  );
}
