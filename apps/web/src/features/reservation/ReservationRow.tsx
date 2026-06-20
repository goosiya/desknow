// 예약현황 목록 한 행 (Story 4.8 — AC1·AC2). 룸 이름·시간·상태 배지 + 상세 이동 + 취소 버튼.
//
// ⚠️ a11y(FavoriteRow 선례): 활성 룸=상세 Link, 비활성 룸=비대화형 div(막다른 화면 금지·진입 차단).
//    상세 Link 와 취소 버튼은 **형제**(Link 안에 button 중첩 금지 — 중첩 인터랙티브 a11y 위반).
// ⚠️ 시간·분류는 전부 render-time 순수 계산(reservations.ts)에서 온다(set-state-in-effect 금지,
//    3.5/3.6 함정). status 배지는 색 단독 금지(아이콘 + 텍스트 동반 — 3중 신호).
import Link from "next/link";

import type { ReservationListItem } from "@/lib/api-client";
import { StarRating } from "@/features/detail/StarRating";

import { KakaoShareButton } from "./KakaoShareButton";
import { ReviewForm } from "./ReviewForm";
import { useCancelReservation } from "./useCancelReservation";
import { isCancelWindowPassed } from "./errors";
import {
  isCancellable,
  isUpcoming,
  reservationDateLabel,
  reservationTimeRangeLabel,
} from "./reservations";

/** 6h 미만 남은 confirmed 예약의 취소 비활성 안내(에픽 4.7 AC1 카피와 동일 — UTF-8). */
const CANCEL_LEAD_NOTICE = "이제 6시간이 안 남아서 취소가 어려워요.";

type BadgeMeta = { label: string; icon: string; className: string };

/** 상태 배지 메타 — 확정/이용 완료/취소됨/거절됨(색 + 아이콘 + 텍스트 3중 신호). */
function statusBadge(item: ReservationListItem, now: Date): BadgeMeta {
  if (item.status === "cancelled") {
    return { label: "취소됨", icon: "✕", className: "bg-muted text-pin-full" };
  }
  if (item.status === "rejected") {
    return { label: "거절됨", icon: "✕", className: "bg-muted text-pin-full" };
  }
  // confirmed — 다가오면 '확정', 모든 슬롯이 지났으면 '이용 완료'(AC1).
  if (isUpcoming(item, now)) {
    return { label: "확정", icon: "✓", className: "bg-secondary text-success" };
  }
  return { label: "이용 완료", icon: "✓", className: "bg-muted text-muted-foreground" };
}

function StatusBadge({ meta }: { meta: BadgeMeta }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.className}`}
    >
      <span aria-hidden="true">{meta.icon}</span> {meta.label}
    </span>
  );
}

/** 행 본문(룸 이름·상태 배지·날짜·시간). 활성=Link, 비활성=div 가 감싼다(호출처에서 분기). */
function RowBody({ item, now }: { item: ReservationListItem; now: Date }) {
  const dateLabel = reservationDateLabel(item);
  const timeLabel = reservationTimeRangeLabel(item);
  return (
    <>
      <span className="flex flex-wrap items-center gap-2">
        <span className="text-base font-semibold leading-[1.45] text-card-foreground">
          {item.room_name || "이름 없음"}
        </span>
        <StatusBadge meta={statusBadge(item, now)} />
      </span>
      {/* 스냅샷 시간(취소/거절 후에도 잔존). 슬롯 0건 레거시면 미표시(AC1 허용). */}
      {dateLabel && timeLabel ? (
        <span className="text-sm text-muted-foreground">
          {dateLabel} {timeLabel}
        </span>
      ) : null}
    </>
  );
}

export function ReservationRow({
  item,
  now,
}: {
  item: ReservationListItem;
  now: Date;
}) {
  const cancel = useCancelReservation();

  // 취소 버튼은 **다가오는 confirmed** 에만 노출(취소/거절/이용 완료엔 미노출 — AC2).
  const showCancel = item.status === "confirmed" && isUpcoming(item, now);
  const cancellable = isCancellable(item, now);
  // 공유 버튼은 **다가오는 confirmed(활성 룸)** 에만 노출한다(KTH 2026-06-18). 이미 종료된
  // '이용 완료' 예약은 같이 갈 사람에게 공유할 의미가 없어 제외한다(과거 슬롯 공유 = 무의미).
  // 취소/거절엔 미노출. 취소 버튼과 형제(중첩 인터랙티브 금지 — L3-4 a11y 규칙).
  // is_active 게이팅(코드리뷰 P3): 비활성 룸은 상세 Link 가 차단되는데(막다른 화면 방지) 공유로
  // 죽은 `/rooms/{id}` 링크(수신자 404)를 내보내는 비대칭을 막는다 — 행 차단과 정합.
  const showShare =
    item.status === "confirmed" && item.is_active && isUpcoming(item, now);

  // 후기 작성/완료 게이팅(Story 5.5 — AC5). 이용 완료 = confirmed + 다가오지 않음(모든 슬롯 종료).
  // 미작성(has_review===false) → 작성 폼, 작성됨 → "후기 완료" 표시(죽은 버튼 0). 취소/거절/다가오는
  // 확정엔 미노출. 후기 UI 는 상세 Link·버튼과 **형제**(중첩 인터랙티브 금지 — 행 하단 별도 블록).
  const isCompleted = item.status === "confirmed" && !isUpcoming(item, now);
  const showReviewForm = isCompleted && !item.has_review;
  const showReviewDone = isCompleted && item.has_review;

  return (
    <li className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3">
      <div className="flex items-center gap-2">
        {item.is_active ? (
          // 활성 — 상세(/rooms/{id}) 진입 가능. 취소 버튼과 분리된 형제(중첩 인터랙티브 금지).
          <Link
            href={`/rooms/${item.room_id}`}
            className="tap-target flex flex-1 flex-col items-start gap-1.5 text-left"
          >
            <RowBody item={item} now={now} />
          </Link>
        ) : (
          // 비활성 — 상세 진입 차단(Link 미노출). 이름·히스토리는 표시(막다른 화면 금지).
          <div className="flex flex-1 flex-col items-start gap-1.5 text-left">
            <RowBody item={item} now={now} />
          </div>
        )}
        {showShare ? (
          // 확정 예약 공유(5.4 AC3) — 상세 Link/취소 버튼과 형제(중첩 인터랙티브 금지). 추가 조회
          // 0(이미 보유한 스냅샷 필드에서 합성). graceful degrade·a11y 는 KakaoShareButton 내부.
          <KakaoShareButton
            roomName={item.room_name}
            slotStarts={item.slot_starts}
            roomId={item.room_id}
          />
        ) : null}
        {showCancel ? (
          <button
            type="button"
            disabled={!cancellable || cancel.isPending}
            onClick={() =>
              cancel.mutate({ roomId: item.room_id, reservationId: item.id })
            }
            className="tap-target inline-flex shrink-0 items-center justify-center rounded-md border border-border px-3 text-sm font-medium text-card-foreground disabled:opacity-50"
          >
            {cancel.isPending ? "취소 중…" : "취소"}
          </button>
        ) : null}
      </div>

      {/* 6h 미만 — 취소 비활성 안내(AC2). 버튼이 노출되고 비활성일 때만. */}
      {showCancel && !cancellable ? (
        <p className="text-xs leading-[1.6] text-muted-foreground">
          {CANCEL_LEAD_NOTICE}
        </p>
      ) : null}

      {/* 취소 실패 안내: 클럭 스큐 409 는 친절 안내(목록 재조회는 훅이 처리), 그 외 generic 재시도. */}
      {cancel.isError ? (
        isCancelWindowPassed(cancel.error) ? (
          <p role="status" className="text-xs leading-[1.6] text-muted-foreground">
            방금 취소 가능 시간이 지났어요. 목록을 새로고침했어요.
          </p>
        ) : (
          <p role="status" className="text-xs leading-[1.6] text-pin-full">
            취소하지 못했어요. 잠시 후 다시 시도해 주세요.
          </p>
        )
      ) : null}

      {/* 후기(Story 5.5 — AC5): 이용 완료·미작성=작성 폼 / 작성됨=내 후기(별점·내용)+사장님 답글
          표시(KTH 2026-06-19 — "후기 완료" 텍스트만 보여주던 것을 실제 내용까지). 상세 Link·취소·
          공유 버튼과 형제(행 하단 별도 블록 — 중첩 인터랙티브 금지). */}
      {showReviewForm ? (
        <ReviewForm reservationId={item.id} roomId={item.room_id} />
      ) : showReviewDone && item.review ? (
        <div className="flex flex-col gap-1.5 rounded-md border border-border bg-muted/40 p-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-success">내 후기</span>
            <StarRating rating={item.review.rating} />
          </div>
          {/* 줄바꿈 보존(ReviewSection 미러). */}
          <p className="whitespace-pre-line text-sm leading-[1.6] text-card-foreground">
            {item.review.text}
          </p>
          {/* 사장님 답글 — 있으면 내 후기 아래 중첩(좌측 보더로 시각 구분, ReviewSection 패턴). */}
          {item.review.reply ? (
            <div
              aria-label="사장님 답글"
              className="ml-3 flex flex-col gap-1 rounded-md border-l-2 border-border bg-muted/60 py-2 pl-3 pr-2"
            >
              <span className="text-xs font-medium text-foreground">사장님 답글</span>
              <p className="whitespace-pre-line text-sm leading-[1.6] text-card-foreground">
                {item.review.reply.text}
              </p>
            </div>
          ) : null}
        </div>
      ) : showReviewDone ? (
        // review 누락 방어(정상 경로엔 has_review면 review 동반) — 안전 degrade.
        <p className="text-xs font-medium text-success">후기 완료</p>
      ) : null}
    </li>
  );
}
