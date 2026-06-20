// 반경 조정 컨트롤 (Story 3.5 — AC1·범위 결정 #6). 프리셋 반경(km)을 고르는 접근성 있는
// radiogroup 세그먼트 컨트롤. 연속 슬라이더(shadcn Slider=radix-ui Slider 추가)는 **비채택** —
// 신규 의존성 0 으로 토큰·기본 버튼만 쓴다(연속 슬라이더는 선택적 후속).
//
// 선택값(radiusKm)은 부모(ExploreView)가 보유한다 — 검색방식 전환 왕복 후에도 보존(AC2).
// UI 는 공용 SegmentedControl(variant="radio")로 그린다 — 지역/내 반경 토글과 톤·높이 동일
// (지역 콤보 36px 에 맞춘 프레임). 각 옵션은 접근 이름(`반경 N km`)·aria-checked 를 가진다(NFR-5).
import { SegmentedControl } from "@/components/ui/segmented-control";

/** 프리셋 반경(km). 기본 3km(범위 결정 #6 — ExploreView 가 초기값으로 보유). */
export const RADIUS_PRESETS_KM = [1, 2, 3, 5, 10] as const;

type RadiusControlProps = {
  radiusKm: number;
  onChange: (km: number) => void;
};

export function RadiusControl({ radiusKm, onChange }: RadiusControlProps) {
  return (
    <SegmentedControl
      variant="radio"
      ariaLabel="반경 선택"
      value={String(radiusKm)}
      onChange={(v) => onChange(Number(v))}
      options={RADIUS_PRESETS_KM.map((km) => ({
        value: String(km),
        label: `${km}km`,
        ariaLabel: `반경 ${km}km`,
      }))}
    />
  );
}
