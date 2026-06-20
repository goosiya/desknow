// 커서 페이징 유틸 테스트 (F — 목록 무한스크롤). 봉투(`{ items, next_cursor }`)에서 다음 페이지
// 파라미터 도출과 페이지 평탄화를 검증한다(useInfiniteQuery getNextPageParam·select 가 의존).
import type { InfiniteData } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import {
  type CursorPage,
  flattenPages,
  getNextCursorParam,
} from "./pagination";

describe("getNextCursorParam", () => {
  it("next_cursor 가 있으면 그 값을 그대로 돌려준다(다음 페이지 토큰)", () => {
    const lastPage: CursorPage<number> = { items: [1, 2], next_cursor: "cursor-2" };
    expect(getNextCursorParam(lastPage)).toBe("cursor-2");
  });

  it("next_cursor 가 null 이면 undefined 를 돌려준다(더 없음 — hasNextPage=false)", () => {
    const lastPage: CursorPage<number> = { items: [1], next_cursor: null };
    expect(getNextCursorParam(lastPage)).toBeUndefined();
  });

  it("next_cursor 가 부재(undefined)면 undefined 를 돌려준다(더 없음)", () => {
    const lastPage: CursorPage<number> = { items: [] };
    expect(getNextCursorParam(lastPage)).toBeUndefined();
  });
});

describe("flattenPages", () => {
  it("여러 페이지의 items 를 순서대로 병합한다", () => {
    const data: InfiniteData<CursorPage<number>> = {
      pages: [
        { items: [1, 2], next_cursor: "c1" },
        { items: [3, 4], next_cursor: null },
      ],
      pageParams: [null, "c1"],
    };
    expect(flattenPages(data)).toEqual([1, 2, 3, 4]);
  });

  it("단일 페이지면 그 페이지 items 를 그대로 돌려준다", () => {
    const data: InfiniteData<CursorPage<string>> = {
      pages: [{ items: ["a", "b"], next_cursor: null }],
      pageParams: [null],
    };
    expect(flattenPages(data)).toEqual(["a", "b"]);
  });

  it("데이터 미적재(undefined)면 빈 배열을 돌려준다", () => {
    expect(flattenPages<number>(undefined)).toEqual([]);
  });
});
