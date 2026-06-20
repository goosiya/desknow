import { colors } from "@desknow/ui";
import { describe, expect, it } from "vitest";

import {
  joinAvailability,
  pinAriaLabel,
  pinStatus,
  pinVisual,
} from "./pin";

// 핀 순수 로직 단위 테스트 (Story 3.2 — AC2·AC4 anti-pattern 회피의 단일 출처).
// 조인·상태/색/아이콘 도출·aria 라벨이 DOM·카카오 없이 결정적으로 동작함을 단언한다.

const ROOM_A = { room_id: "a", name: "강남", lat: 37.5, lng: 127.0 };
const ROOM_B = { room_id: "b", name: "홍대", lat: 37.55, lng: 126.92 };

describe("joinAvailability", () => {
  it("room_id 로 가용성을 조인해 remaining_slots 를 붙인다", () => {
    const pins = joinAvailability(
      [ROOM_A, ROOM_B],
      [
        { room_id: "a", remaining_slots: 3 },
        { room_id: "b", remaining_slots: 0 },
      ],
    );
    const byId = Object.fromEntries(pins.map((p) => [p.room_id, p]));
    expect(byId.a.remaining_slots).toBe(3);
    expect(byId.a.status).toBe("available");
    expect(byId.b.remaining_slots).toBe(0);
    expect(byId.b.status).toBe("full");
    // 좌표·이름이 보존된다.
    expect(byId.a.name).toBe("강남");
    expect(byId.a.lat).toBe(37.5);
  });

  it("가용성에 없는 룸은 마감(remaining_slots=0)으로 취급한다", () => {
    const pins = joinAvailability([ROOM_A], []); // 가용성 비어있음
    expect(pins).toHaveLength(1);
    expect(pins[0].remaining_slots).toBe(0);
    expect(pins[0].status).toBe("full");
  });
});

describe("pinStatus", () => {
  it(">= 1 이면 available, 0 이면 full (유일한 클라 분기 — 슬롯 재계산 아님)", () => {
    expect(pinStatus(1)).toBe("available");
    expect(pinStatus(13)).toBe("available");
    expect(pinStatus(0)).toBe("full");
  });
});

describe("pinVisual", () => {
  it("available → pinAvailable 토큰 hex + check 아이콘", () => {
    const v = pinVisual("available");
    expect(v.colorToken).toBe("pinAvailable");
    expect(v.hex).toBe(colors.pinAvailable); // 토큰 단일 출처(하드코딩 금지)
    expect(v.hex).toBe("#157F45");
    expect(v.icon).toBe("check");
  });

  it("full → pinFull 토큰 hex + x 아이콘", () => {
    const v = pinVisual("full");
    expect(v.colorToken).toBe("pinFull");
    expect(v.hex).toBe(colors.pinFull);
    expect(v.hex).toBe("#7E7466");
    expect(v.icon).toBe("x");
  });

  it("색 외에 아이콘이 항상 동반된다(색 단독 신호 금지 — AC2)", () => {
    // available/full 모두 icon 이 비어있지 않다(색-독립 신호 존재).
    expect(pinVisual("available").icon).toBeTruthy();
    expect(pinVisual("full").icon).toBeTruthy();
    // 두 상태의 아이콘이 서로 다르다(아이콘만으로도 구분 가능).
    expect(pinVisual("available").icon).not.toBe(pinVisual("full").icon);
  });
});

describe("pinAriaLabel", () => {
  it("가용 → '{이름} 스터디룸, 예약 가능' (AC4 정확 문구)", () => {
    expect(pinAriaLabel("강남", "available")).toBe("강남 스터디룸, 예약 가능");
  });

  it("마감 → '{이름} 스터디룸, 마감'", () => {
    expect(pinAriaLabel("홍대", "full")).toBe("홍대 스터디룸, 오늘 마감");
  });
});
