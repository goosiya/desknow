// 지역 콤보 순수 로직 (Story 3.4 — 프레임워크 무관 · 콤보 상태 도출의 단일 출처).
//
// SDK 타입(RegionGroup/Region)만 의존하는 순수 함수다. 콤보 2단(시군구→동)의 옵션 도출과
// 조회 트리거용 region_code 해석을 담당한다. 슬롯·가용성·가격·라벨 포맷은 features/map 의
// pin.ts / roomSummary.ts 를 재사용한다(중복 금지 — RoomListRow 가 직접 import).
import type { Region, RegionGroup } from "@/lib/api-client";

/**
 * 선택된 시군구의 동/읍/면 옵션을 돌려준다(미선택·미존재 시군구면 빈 배열).
 * 2차 콤보(동)는 1차(시군구) 선택에 종속된다.
 */
export function dongsFor(
  groups: RegionGroup[],
  sigunguCode: string | undefined,
): Region[] {
  if (!sigunguCode) return [];
  return groups.find((g) => g.code === sigunguCode)?.dongs ?? [];
}

/**
 * 조회 트리거용 region_code 를 해석한다 — 동을 골랐으면 동 코드(그 동만), 시군구만 골랐으면
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
