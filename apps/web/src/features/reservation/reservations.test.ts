// 예약현황 분류·표시 순수 헬퍼 테스트 (Story 4.8 — AC1·AC2). 경계 + 포맷.
import { describe, expect, it } from "vitest";

import type { ReservationListItem } from "@/lib/api-client";
import {
  isCancellable,
  isUpcoming,
  reservationDateLabel,
  reservationTimeRangeLabel,
} from "./reservations";

function item(overrides: Partial<ReservationListItem>): ReservationListItem {
  return {
    id: "r1",
    room_id: "room-1",
    room_name: "강남룸",
    status: "confirmed",
    slot_starts: ["2026-06-20T05:00:00Z"], // KST 14:00
    created_at: "2026-06-17T00:00:00Z",
    is_active: true,
    has_review: false,
    ...overrides,
  };
}

// 기준 now — KST 2026-06-20 의 한참 전(예약 시작까지 6h 이상 남는 시점).
const NOW_FAR = new Date("2026-06-19T00:00:00Z");

describe("isUpcoming (AC1)", () => {
  it("confirmed + 종료 시각이 미래면 다가오는 예약이다", () => {
    expect(isUpcoming(item({}), NOW_FAR)).toBe(true);
  });

  it("confirmed + 모든 슬롯이 과거면 지난 예약이다(미upcoming)", () => {
    // 슬롯 05Z+1h=06Z 가 now 보다 과거.
    const now = new Date("2026-06-20T10:00:00Z");
    expect(isUpcoming(item({}), now)).toBe(false);
  });

  it("취소/거절은 항상 미upcoming(지난 섹션)", () => {
    expect(isUpcoming(item({ status: "cancelled" }), NOW_FAR)).toBe(false);
    expect(isUpcoming(item({ status: "rejected" }), NOW_FAR)).toBe(false);
  });

  it("슬롯 0건(레거시)은 미upcoming", () => {
    expect(isUpcoming(item({ slot_starts: [] }), NOW_FAR)).toBe(false);
  });
});

describe("isCancellable (AC2 — 6h 경계)", () => {
  it("6h 이상 남으면 취소 가능", () => {
    expect(isCancellable(item({}), NOW_FAR)).toBe(true);
  });

  it("정확히 6h 남은 시점은 취소 가능(>= 경계 포함)", () => {
    // earliest = 05Z. now = 05Z - 6h = 2026-06-19T23:00:00Z.
    const now = new Date("2026-06-19T23:00:00Z");
    expect(isCancellable(item({}), now)).toBe(true);
  });

  it("6h 미만(6h-1s)이면 취소 불가", () => {
    const now = new Date("2026-06-19T23:00:01Z"); // 5h59m59s 남음
    expect(isCancellable(item({}), now)).toBe(false);
  });

  it("취소/거절/슬롯0건은 미cancellable", () => {
    expect(isCancellable(item({ status: "cancelled" }), NOW_FAR)).toBe(false);
    expect(isCancellable(item({ status: "rejected" }), NOW_FAR)).toBe(false);
    expect(isCancellable(item({ slot_starts: [] }), NOW_FAR)).toBe(false);
  });
});

describe("표시 포맷 (AC1)", () => {
  it("날짜 = KST '6월 20일'", () => {
    expect(reservationDateLabel(item({}))).toBe("6월 20일");
  });

  it("시간 범위 = 첫 슬롯 ~ 마지막 슬롯 +1h (KST '14:00–17:00')", () => {
    const multi = item({
      slot_starts: [
        "2026-06-20T05:00:00Z", // 14:00
        "2026-06-20T06:00:00Z", // 15:00
        "2026-06-20T07:00:00Z", // 16:00 (+1h = 17:00)
      ],
    });
    expect(reservationTimeRangeLabel(multi)).toBe("14:00–17:00");
  });

  it("단일 슬롯 = 1시간 범위 '14:00–15:00'", () => {
    expect(reservationTimeRangeLabel(item({}))).toBe("14:00–15:00");
  });

  it("슬롯 0건(레거시)이면 날짜·시간 null(미표시)", () => {
    expect(reservationDateLabel(item({ slot_starts: [] }))).toBeNull();
    expect(reservationTimeRangeLabel(item({ slot_starts: [] }))).toBeNull();
  });
});
