// 지역 콤보 순수 로직 — 웹 regions.ts 복사 (Story 9.1 — 콤보 상태 도출 단일 출처).
//
// SDK 타입(RegionGroup/Region)만 의존하는 순수 함수다. 콤보 2단(시군구→지역)의 옵션 도출과 조회
// 트리거용 region_code 해석을 담당한다. 용어는 "지역"으로 통일([[region-code-legal-not-admin-dong]]).
import type { Region, RegionGroup } from "@/lib/api-client";

/**
 * 선택된 시군구의 지역(동/읍/면) 옵션을 돌려준다(미선택·미존재 시군구면 빈 배열).
 * 2차 콤보는 1차(시군구) 선택에 종속된다.
 */
export function dongsFor(
  groups: RegionGroup[],
  sigunguCode: string | undefined,
): Region[] {
  if (!sigunguCode) return [];
  return groups.find((g) => g.code === sigunguCode)?.dongs ?? [];
}

/**
 * 조회 트리거용 region_code를 해석한다 — 지역을 골랐으면 지역 코드(그 지역만), 시군구만 골랐으면
 * 시군구 코드(그 구 전체), 둘 다 미선택이면 undefined(조회 비활성 — 무제한 초기 스캔 방지).
 */
export function resolveRegionCode(
  sigunguCode: string | undefined,
  dongCode: string | undefined,
): string | undefined {
  if (dongCode) return dongCode;
  if (sigunguCode) return sigunguCode;
  return undefined;
}
