// 커서 페이징 공용 유틸 (F — 목록 무한스크롤). 6개 목록 표면(예약·즐겨찾기·후기·제공자예약·
// 탐색·룸검색)이 동일한 useInfiniteQuery 패턴을 쓰도록 봉투 타입·페이지 파라미터 도출·평탄화를
// 한 곳에서 제공한다.
//
// 백엔드 봉투(CursorPage): 목록 응답은 배열이 아니라 `{ items, next_cursor }` 객체다. `next_cursor`
// 는 다음 페이지 시작점을 가리키는 **불투명 토큰**으로, 클라이언트는 의미를 몰라도 다음 요청의
// `cursor` 쿼리에 그대로 echo한다(null/undefined=마지막 페이지). SDK가 생성한 `CursorPageXxx`
// 타입들이 모두 이 형태라, 제네릭 한 벌로 흡수한다.
import type { InfiniteData } from "@tanstack/react-query";

/** 커서 페이징 응답 봉투(SDK `CursorPageXxx`와 구조 동형 — 제네릭 흡수). */
export type CursorPage<T> = {
  items: T[];
  next_cursor?: string | null;
};

/** useInfiniteQuery 페이지 파라미터 = 불투명 커서(첫 페이지=null). */
export type CursorParam = string | null;

/** 첫 페이지 파라미터(커서 없음). useInfiniteQuery `initialPageParam`에 쓴다. */
export const INITIAL_CURSOR: CursorParam = null;

/**
 * 다음 페이지 파라미터 도출 — 봉투의 `next_cursor`(없으면 undefined=더 없음).
 * useInfiniteQuery `getNextPageParam`에 그대로 전달한다. react-query는 undefined를
 * "다음 페이지 없음"으로 해석해 `hasNextPage=false`로 만든다.
 */
export function getNextCursorParam<T>(lastPage: CursorPage<T>): CursorParam | undefined {
  return lastPage.next_cursor ?? undefined;
}

/**
 * 페이지들을 평탄화해 단일 아이템 배열로 만든다(소비 컴포넌트가 기존 `data: T[]`처럼 쓰도록).
 * 데이터 미적재(undefined)면 빈 배열.
 */
export function flattenPages<T>(
  data: InfiniteData<CursorPage<T>> | undefined,
): T[] {
  return data?.pages.flatMap((page) => page.items) ?? [];
}
