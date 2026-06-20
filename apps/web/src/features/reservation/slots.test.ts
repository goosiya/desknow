// 예약 날짜·시간 순수 로직 테스트 (Story 4.3 — slots.ts). 결정성을 위해 now 를 주입한다.
import { describe, expect, it } from "vitest";

import type { RoomSlot } from "@/lib/api-client";

import {
  addDays,
  clampContiguousAvailable,
  formatDateAriaLabel,
  formatDateKorean,
  formatHourKorean,
  formatSlotLabel,
  isAvailableIndex,
  isSelectableDate,
  isSelectionStillAvailable,
  kstToday,
  monthGrid,
  selectionLabels,
  selectionSlotStarts,
  selectionTotalPrice,
  shiftMonth,
} from "./slots";

describe("kstToday (ROOM_TZ 오늘)", () => {
  it("Asia/Seoul 벽시계 날짜를 YYYY-MM-DD 로 준다 (UTC 날짜와 다른 경계)", () => {
    // UTC 16:00 → KST 익일 01:00 → 날짜가 하루 넘어간다(UTC+9 경계).
    expect(kstToday(new Date("2026-06-14T16:00:00Z"))).toBe("2026-06-15");
    // UTC 14:00 → KST 23:00(같은 날) → UTC 날짜와 동일.
    expect(kstToday(new Date("2026-06-14T14:00:00Z"))).toBe("2026-06-14");
  });
});

describe("monthGrid (7열 월 그리드)", () => {
  it("앞쪽 빈칸(요일 정렬) + 날짜 셀을 준다 (2026-06: 1일=월요일)", () => {
    const cells = monthGrid(2026, 6);
    // 6월 1일은 월요일(일=0…) → 앞 빈칸 1개(일요일 자리).
    expect(cells[0]).toBeNull();
    expect(cells[1]).toBe("2026-06-01");
    expect(cells.at(-1)).toBe("2026-06-30");
    expect(cells.filter((c) => c !== null)).toHaveLength(30);
  });
});

describe("isSelectableDate (과거·30일 초과 비활성)", () => {
  const today = "2026-06-15";
  it("오늘 이전은 비활성, 오늘~오늘+29 는 선택 가능, 30일 초과는 비활성", () => {
    expect(isSelectableDate("2026-06-14", today)).toBe(false); // 과거
    expect(isSelectableDate("2026-06-15", today)).toBe(true); // 오늘(하한 포함)
    expect(isSelectableDate(addDays(today, 29), today)).toBe(true); // 2026-07-14(상한 포함)
    expect(isSelectableDate(addDays(today, 30), today)).toBe(false); // 2026-07-15(초과)
  });
});

describe("formatSlotLabel (UTC → KST 벽시계 표시)", () => {
  it("서버 UTC 인스턴트를 Asia/Seoul 24시간 벽시계로 포맷한다", () => {
    expect(formatSlotLabel("2026-06-15T00:00:00Z")).toBe("09:00"); // 00:00 UTC = 09:00 KST
    expect(formatSlotLabel("2026-06-15T05:00:00Z")).toBe("14:00"); // 05:00 UTC = 14:00 KST
  });
});

describe("formatDateKorean / formatDateAriaLabel", () => {
  it("한국어 날짜 라벨을 만든다", () => {
    expect(formatDateKorean("2026-06-18")).toBe("6월 18일");
    expect(formatDateAriaLabel("2026-06-18")).toBe("2026년 6월 18일");
  });
});

describe("addDays / shiftMonth (달력 산술)", () => {
  it("월·연 경계를 안전하게 넘긴다", () => {
    expect(addDays("2026-06-30", 1)).toBe("2026-07-01");
    expect(addDays("2026-01-01", -1)).toBe("2025-12-31");
    expect(shiftMonth(2026, 12, 1)).toEqual([2027, 1]);
    expect(shiftMonth(2026, 1, -1)).toEqual([2025, 12]);
  });
});

// ── Story 4.4: 연속 슬롯 선택 헬퍼 ──
// 슬롯 빌더 — 인덱스별 상태를 받아 시간순 slots 배열(05:00Z=14:00 KST 부터 1시간 간격)을 만든다.
function makeSlots(statuses: RoomSlot["status"][]): RoomSlot[] {
  return statuses.map((status, i) => ({
    // 2026-06-15 05:00Z(=14:00 KST) + i시간 — 시간순 정렬된 슬롯.
    slot_start: new Date(Date.UTC(2026, 5, 15, 5 + i, 0, 0)).toISOString(),
    status,
  }));
}

describe("isAvailableIndex (경계·상태 가드)", () => {
  const slots = makeSlots(["available", "reserved"]);
  it("available 만 true, past/reserved·범위 밖은 false", () => {
    expect(isAvailableIndex(slots, 0)).toBe(true);
    expect(isAvailableIndex(slots, 1)).toBe(false); // reserved
    expect(isAvailableIndex(slots, -1)).toBe(false); // 범위 밖
    expect(isAvailableIndex(slots, 2)).toBe(false); // 범위 밖
  });
});

describe("isSelectionStillAvailable (Story 4.9 — stale 선택 무효화, AC5)", () => {
  it("구간 전체가 available 면 true", () => {
    const slots = makeSlots(["available", "available", "available"]);
    expect(isSelectionStillAvailable(slots, { startIndex: 0, endIndex: 2 })).toBe(true);
  });

  it("구간 내 하나라도 reserved 로 바뀌면 false(인덱스 안 밀린 stale — L224 케이스)", () => {
    // 동일 길이·다른 내용: 가운데가 방금 reserved 됨 → 선택 무효.
    const slots = makeSlots(["available", "reserved", "available"]);
    expect(isSelectionStillAvailable(slots, { startIndex: 0, endIndex: 2 })).toBe(false);
  });

  it("구간 내 past 도 무효 처리(available 아님)", () => {
    const slots = makeSlots(["past", "available"]);
    expect(isSelectionStillAvailable(slots, { startIndex: 0, endIndex: 1 })).toBe(false);
  });

  it("범위 밖 인덱스(배열 축소)도 false(bounds 이상도 stale 처리)", () => {
    const slots = makeSlots(["available"]);
    expect(isSelectionStillAvailable(slots, { startIndex: 0, endIndex: 2 })).toBe(false);
  });

  it("단일 슬롯이 여전히 available 면 true", () => {
    const slots = makeSlots(["available", "reserved"]);
    expect(isSelectionStillAvailable(slots, { startIndex: 0, endIndex: 0 })).toBe(true);
  });
});

describe("clampContiguousAvailable (앵커→연속-가용 확장, D1)", () => {
  it("① 전부 available → 앵커~대상 전체 구간", () => {
    const slots = makeSlots(["available", "available", "available", "available"]);
    expect(clampContiguousAvailable(slots, 0, 3)).toEqual({ startIndex: 0, endIndex: 3 });
  });

  it("② 사이에 reserved/past 가 끼면 그 직전까지만(점유 못 넘음 — D1)", () => {
    // [14 avail, 15 reserved, 16 avail] — 0→2 확장 시 1(reserved)에서 막혀 {0,0}.
    const reserved = makeSlots(["available", "reserved", "available"]);
    expect(clampContiguousAvailable(reserved, 0, 2)).toEqual({ startIndex: 0, endIndex: 0 });
    const past = makeSlots(["available", "available", "past", "available"]);
    expect(clampContiguousAvailable(past, 0, 3)).toEqual({ startIndex: 0, endIndex: 1 });
  });

  it("③ 역방향(대상<앵커)도 대칭으로 정규화한다", () => {
    const slots = makeSlots(["available", "available", "available"]);
    expect(clampContiguousAvailable(slots, 2, 0)).toEqual({ startIndex: 0, endIndex: 2 });
    // 역방향에 점유가 끼면 그 직전까지(2→0, 1이 reserved → {2,2}).
    const blocked = makeSlots(["available", "reserved", "available"]);
    expect(clampContiguousAvailable(blocked, 2, 0)).toEqual({ startIndex: 2, endIndex: 2 });
  });

  it("④ 앵커가 비-available 면 null(선택 시작 불가)", () => {
    const slots = makeSlots(["reserved", "available"]);
    expect(clampContiguousAvailable(slots, 0, 1)).toBeNull();
  });

  it("⑤ 단일 슬롯(앵커=대상)", () => {
    const slots = makeSlots(["available", "available"]);
    expect(clampContiguousAvailable(slots, 1, 1)).toEqual({ startIndex: 1, endIndex: 1 });
  });
});

describe("selectionLabels (범위·시간·SR 구간 피드백)", () => {
  it("14·15·16 선택 → '14:00–17:00' · 3시간 · '14시부터 17시까지 선택됨'(끝=마지막+1h)", () => {
    const slots = makeSlots(["available", "available", "available"]); // 14·15·16 KST
    const labels = selectionLabels(slots, { startIndex: 0, endIndex: 2 });
    expect(labels.rangeLabel).toBe("14:00–17:00"); // 끝 슬롯(16:00) + 1h = 17:00 (off-by-one 회귀 방지)
    expect(labels.durationHours).toBe(3);
    expect(labels.announcement).toBe("14시부터 17시까지 선택됨");
  });

  it("단일 14 선택 → '14:00–15:00' · '14시부터 15시까지 선택됨'", () => {
    const slots = makeSlots(["available"]); // 14 KST
    const labels = selectionLabels(slots, { startIndex: 0, endIndex: 0 });
    expect(labels.rangeLabel).toBe("14:00–15:00");
    expect(labels.durationHours).toBe(1);
    expect(labels.announcement).toBe("14시부터 15시까지 선택됨");
  });

  it("끝 슬롯 +1h 가 자정 경계여도 라벨이 깨지지 않는다(23시 슬롯 끝=00:00, h23 산출 그대로)", () => {
    // 14:00Z = 23:00 KST 슬롯 → 끝 +1h = 15:00Z = 00:00 KST(h23 래핑). 영업은 같은 날 0~24시라
    // 실발현 없음(deferred) — 여기선 포맷이 throw 하지 않고 안정적으로 산출됨만 단언.
    const slot: RoomSlot = { slot_start: "2026-06-15T14:00:00Z", status: "available" };
    const labels = selectionLabels([slot], { startIndex: 0, endIndex: 0 });
    expect(labels.rangeLabel).toBe("23:00–00:00");
    expect(formatHourKorean("2026-06-15T14:00:00Z")).toBe("23시");
  });
});

describe("selectionTotalPrice (시간 × 시간당 가격)", () => {
  it("3시간 × 8000 = 24000", () => {
    expect(selectionTotalPrice({ startIndex: 0, endIndex: 2 }, 8000)).toBe(24000);
    expect(selectionTotalPrice({ startIndex: 0, endIndex: 0 }, 8000)).toBe(8000); // 단일 1시간
  });
});

// ── Story 4.5: 즉시 예약 제출용 슬롯 추출 ──
describe("selectionSlotStarts (선택 구간 → slot_start[] 추출)", () => {
  it("14·15·16 선택 → 해당 3개의 slot_start(서버 UTC ISO 그대로)", () => {
    const slots = makeSlots(["available", "available", "available", "available"]);
    expect(selectionSlotStarts(slots, { startIndex: 0, endIndex: 2 })).toEqual([
      slots[0].slot_start,
      slots[1].slot_start,
      slots[2].slot_start,
    ]);
  });

  it("단일 슬롯(앵커=대상) → 1개", () => {
    const slots = makeSlots(["available", "available"]);
    expect(selectionSlotStarts(slots, { startIndex: 1, endIndex: 1 })).toEqual([
      slots[1].slot_start,
    ]);
  });

  it("배열 끝까지의 구간(경계)도 안전하게 포함한다", () => {
    const slots = makeSlots(["available", "available", "available"]);
    expect(selectionSlotStarts(slots, { startIndex: 1, endIndex: 2 })).toEqual([
      slots[1].slot_start,
      slots[2].slot_start,
    ]);
  });
});
