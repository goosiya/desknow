import { describe, expect, it } from "vitest";

import {
  AMENITY_LABELS,
  ROOM_TYPE_LABELS,
  formatHours,
  formatPrice,
  labelFor,
  summaryStatus,
  todayBusinessHours,
} from "./roomSummary";

// 바텀시트 요약 순수 로직 단위 테스트 (Story 3.3 — 카카오/DOM 불필요).
// 가격·영업시간 포맷, KST 오늘 요일 선택, 상태 도출, 라벨 매핑이 결정적으로 동작함을 단언한다.

describe("formatPrice", () => {
  it("천단위 콤마 + 원", () => {
    expect(formatPrice(8000)).toBe("8,000원");
    expect(formatPrice(12000)).toBe("12,000원");
  });
  it("0원도 자연스럽게 표기한다", () => {
    expect(formatPrice(0)).toBe("0원");
  });
});

describe("formatHours", () => {
  it('"HH:MM:SS" → "HH:MM" 절단 후 en-dash 로 연결', () => {
    expect(formatHours("09:00:00", "22:00:00")).toBe("09:00–22:00");
    expect(formatHours("10:30:00", "12:00:00")).toBe("10:30–12:00");
  });
});

describe("todayBusinessHours", () => {
  // 2026-06-15 = 월요일. 03:00Z = 12:00 KST(월), 16:00Z(전날 14일) = 01:00 KST 15일(월).
  const MON_NOON_UTC = new Date("2026-06-15T03:00:00Z");
  const hours = [
    { weekday: 0, open_time: "09:00:00", close_time: "22:00:00" }, // 월
    { weekday: 2, open_time: "10:00:00", close_time: "18:00:00" }, // 수
  ];

  it("KST 오늘 요일에 맞는 행을 고른다(슬롯 재계산 아님 — 단순 표시)", () => {
    const today = todayBusinessHours(hours, MON_NOON_UTC);
    expect(today?.weekday).toBe(0);
    expect(today?.open_time).toBe("09:00:00");
  });

  it("UTC→KST 날짜 경계: 14일 16:00Z 는 KST 15일(월)로 판정된다", () => {
    const boundary = new Date("2026-06-14T16:00:00Z"); // = 2026-06-15 01:00 KST(월)
    expect(todayBusinessHours(hours, boundary)?.weekday).toBe(0);
  });

  it("오늘 요일 영업행이 없으면 null(→ '오늘 휴무' 표시)", () => {
    const tueOnly = [{ weekday: 1, open_time: "09:00:00", close_time: "18:00:00" }];
    expect(todayBusinessHours(tueOnly, MON_NOON_UTC)).toBeNull();
  });
});

describe("summaryStatus", () => {
  it("0 → full, 1 → available (경계 — pinStatus 재사용)", () => {
    expect(summaryStatus(0)).toBe("full");
    expect(summaryStatus(1)).toBe("available");
    expect(summaryStatus(13)).toBe("available");
  });
});

describe("라벨 매핑", () => {
  it("부대시설 코드 → 한국어 라벨", () => {
    expect(AMENITY_LABELS.wifi).toBe("와이파이");
    expect(AMENITY_LABELS.projector_tv).toBe("빔프로젝터/TV");
    expect(labelFor("parking", AMENITY_LABELS)).toBe("주차");
  });
  it("룸 형태 코드 → 한국어 라벨", () => {
    expect(ROOM_TYPE_LABELS.open).toBe("개방형");
    expect(labelFor("private", ROOM_TYPE_LABELS)).toBe("독립룸");
  });
  it("미지정 코드는 코드 원문으로 폴백한다(방어)", () => {
    expect(labelFor("unknown_code", AMENITY_LABELS)).toBe("unknown_code");
    expect(labelFor("custom", ROOM_TYPE_LABELS)).toBe("custom");
  });
});
