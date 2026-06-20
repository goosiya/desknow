import { describe, expect, it } from "vitest";

import type { RegionGroup } from "@/lib/api-client";
import { dongsFor, resolveRegionCode } from "./regions";

// 콤보 순수 로직 테스트 (Story 3.4 — Task 10). pin/roomSummary 재사용분은 기존 테스트가 커버.

const GROUPS: RegionGroup[] = [
  {
    code: "1168000000",
    name: "서울특별시 강남구",
    room_count: 2,
    dongs: [
      { code: "1168010100", name: "역삼동", room_count: 1 },
      { code: "1168010300", name: "개포동", room_count: 1 },
    ],
  },
  {
    code: "1111000000",
    name: "서울특별시 종로구",
    room_count: 1,
    dongs: [{ code: "1111010100", name: "청운동", room_count: 1 }],
  },
];

describe("dongsFor", () => {
  it("선택 시군구의 동 옵션을 돌려준다", () => {
    expect(dongsFor(GROUPS, "1168000000").map((d) => d.name)).toEqual([
      "역삼동",
      "개포동",
    ]);
  });

  it("미선택(undefined) 시군구는 빈 배열", () => {
    expect(dongsFor(GROUPS, undefined)).toEqual([]);
  });

  it("존재하지 않는 시군구는 빈 배열", () => {
    expect(dongsFor(GROUPS, "9999900000")).toEqual([]);
  });
});

describe("resolveRegionCode", () => {
  it("동을 골랐으면 동 코드(그 동만)", () => {
    expect(resolveRegionCode("1168000000", "1168010100")).toBe("1168010100");
  });

  it("시군구만 골랐으면 시군구 코드(그 구 전체)", () => {
    expect(resolveRegionCode("1168000000", undefined)).toBe("1168000000");
  });

  it("둘 다 미선택이면 undefined(조회 비활성)", () => {
    expect(resolveRegionCode(undefined, undefined)).toBeUndefined();
  });
});
