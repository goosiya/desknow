import { SegmentedControl } from '@/components/SegmentedControl';

// 반경 조정 컨트롤 — 웹 RadiusControl RN 포팅 (Story 9.1 — AC4). 프리셋 반경(km)을 고르는 radiogroup
// 세그먼트. 선택값(radiusKm)은 부모(ExploreView)가 보유한다(검색방식 전환 왕복 후에도 보존).

/** 프리셋 반경(km). 기본 3km(ExploreView가 초기값으로 보유). */
export const RADIUS_PRESETS_KM = [1, 2, 3, 5, 10] as const;

type RadiusControlProps = {
  radiusKm: number;
  onChange: (km: number) => void;
};

export function RadiusControl({ radiusKm, onChange }: RadiusControlProps) {
  return (
    <SegmentedControl
      variant="radio"
      accessibilityLabel="반경 선택"
      value={String(radiusKm)}
      onChange={(v) => onChange(Number(v))}
      options={RADIUS_PRESETS_KM.map((km) => ({
        value: String(km),
        label: `${km}km`,
        accessibilityLabel: `반경 ${km}km`,
      }))}
    />
  );
}
