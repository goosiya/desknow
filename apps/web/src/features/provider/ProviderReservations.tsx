"use client";

// provider 예약자 현황 (idea.md L38). 내 스터디룸의 확정 예약을 보고, 예외 예약을 거부한다(거부 시
// 해당 시간이 다시 열리고 예약자에게 통지 — 백엔드 처리). 예약자는 익명 라벨로만 보인다(타인-facing
// 표면 — 메모리 anonymous-booker-label). 백엔드 호출은 생성 SDK 경유 훅만.
import { useState } from "react";

import type { ProviderReservationItem } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { InfiniteScrollSentinel } from "@/components/InfiniteScrollSentinel";
import {
  useProviderReservations,
  useRejectReservation,
} from "./useProviderReservations";

/** slot_starts(시간당 UTC 시작들) → KST "M월 D일 HH:MM–HH:MM"(첫 시작~마지막 시작+1h). */
function formatSlots(slotStarts: string[]): string {
  if (slotStarts.length === 0) return "";
  const sorted = [...slotStarts].sort();
  const start = new Date(sorted[0]);
  const lastStart = new Date(sorted[sorted.length - 1]);
  const end = new Date(lastStart.getTime() + 60 * 60 * 1000); // 마지막 슬롯 끝 = 시작+1h
  const date = new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    timeZone: "Asia/Seoul",
  }).format(start);
  const hhmm = (d: Date) =>
    new Intl.DateTimeFormat("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Seoul",
    }).format(d);
  return `${date} ${hhmm(start)}–${hhmm(end)}`;
}

function ReservationRow({ item }: { item: ProviderReservationItem }) {
  const reject = useRejectReservation();
  const [confirming, setConfirming] = useState(false);
  const isConfirmed = item.status === "confirmed";

  return (
    <li className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-sm font-medium text-card-foreground">{item.room_name}</span>
          <span className="text-sm text-muted-foreground">{formatSlots(item.slot_starts)}</span>
          <span className="text-xs text-muted-foreground">{item.booker_label}</span>
        </div>
        {isConfirmed ? (
          <span className="shrink-0 rounded-full bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground">
            확정
          </span>
        ) : (
          <span className="shrink-0 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
            {item.status === "rejected" ? "거부됨" : "취소됨"}
          </span>
        )}
      </div>

      {isConfirmed ? (
        confirming ? (
          <div className="flex flex-col gap-2 rounded-md bg-muted/60 p-3">
            <p className="text-sm leading-[1.6] text-muted-foreground">
              이 예약을 거부하면 해당 시간이 다시 열리고 예약자에게 통지돼요. 거부할까요?
            </p>
            <div className="flex gap-2">
              <Button
                variant="destructive"
                size="sm"
                disabled={reject.isPending}
                onClick={() => reject.mutate(item.id, { onSuccess: () => setConfirming(false) })}
              >
                {reject.isPending ? "처리 중…" : "거부"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={reject.isPending}
                onClick={() => setConfirming(false)}
              >
                취소
              </Button>
            </div>
          </div>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() => setConfirming(true)}
          >
            예약 거부
          </Button>
        )
      ) : null}

      {reject.isError ? (
        <p className="text-sm text-destructive">거부에 실패했어요. 잠시 후 다시 시도해 주세요.</p>
      ) : null}
    </li>
  );
}

export function ProviderReservations() {
  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useProviderReservations();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">예약자 현황</h1>
        <p className="text-sm leading-[1.6] text-muted-foreground">
          내 스터디룸의 확정 예약이에요. 예외 상황이면 예약을 거부할 수 있어요(해당 시간이 다시 열려요).
        </p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">불러오는 중…</p>
      ) : isError ? (
        <p className="text-sm text-pin-full">
          예약을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.
        </p>
      ) : !data || data.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
          아직 들어온 예약이 없어요.
        </p>
      ) : (
        <>
          <ul className="flex flex-col gap-2">
            {data.map((item) => (
              <ReservationRow key={item.id} item={item} />
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
