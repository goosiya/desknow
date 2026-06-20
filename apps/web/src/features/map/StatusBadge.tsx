// 예약 가능/마감 배지 — 색 + 아이콘 + 텍스트 3중 신호 (색 단독 금지, architecture.md L300).
//
// RoomSheet(바텀시트 3.3)·RoomDetail(상세 4.2)가 **공유**한다(단일 출처 — 재발명 금지). 신선
// remaining_slots 에서 도출한 PinStatus(summaryStatus)를 받아 배지를 렌더한다. 시각은 토큰
// 클래스만 사용한다(하드코딩 색 hex 0) — 가능=success, 마감=pin-full.
import type { PinStatus } from "./pin";

/** 예약 가능/마감 배지 — 색 + 아이콘 + 텍스트 3중 신호(색 단독 금지, 4.2 AC1 · architecture.md L300). */
export function StatusBadge({ status }: { status: PinStatus }) {
  if (status === "available") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-3 py-1 text-sm font-medium text-success">
        <span aria-hidden="true">✓</span> 예약 가능
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-sm font-medium text-pin-full">
      {/* "마감"은 룸 폐업이 아니라 **오늘 자리 마감**(remaining_slots=0)이라 명확히 표기(KTH 2026-06-18). */}
      <span aria-hidden="true">✕</span> 오늘 마감
    </span>
  );
}
