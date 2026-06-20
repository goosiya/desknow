import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

// 공용 세그먼트 컨트롤 — 웹 SegmentedControl RN 포팅 (Story 9.1). 지도/목록 토글·검색방식(지역/내
// 반경)·반경 프리셋이 같은 컴포넌트로 그려진다(톤·높이 통일). 선택값은 부모가 보유(controlled).
//
// a11y(NFR-5): 컨테이너는 radiogroup/tablist, 각 옵션은 radio/tab + selected 상태 + 접근 이름.
// 토큰만 사용(하드코딩 색/픽셀 0). 탭 타겟 ≥44px.
export type SegmentOption = {
  value: string;
  label: string;
  /** 접근 이름(미지정 시 label 사용). 예: 반경 프리셋 "1km" → "반경 1km". */
  accessibilityLabel?: string;
};

type SegmentedControlProps = {
  accessibilityLabel: string;
  value: string;
  onChange: (value: string) => void;
  options: SegmentOption[];
  /** radio=단일 선택 그룹(반경·검색방식), tab=뷰 전환. a11y role만 다르다. */
  variant?: 'radio' | 'tab';
};

export function SegmentedControl({
  accessibilityLabel,
  value,
  onChange,
  options,
  variant = 'tab',
}: SegmentedControlProps) {
  return (
    <View
      accessibilityRole={variant === 'radio' ? 'radiogroup' : 'tablist'}
      accessibilityLabel={accessibilityLabel}
      style={styles.group}
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <Pressable
            key={opt.value}
            onPress={() => onChange(opt.value)}
            accessibilityRole={variant === 'radio' ? 'radio' : 'tab'}
            accessibilityState={{ selected: active }}
            accessibilityLabel={opt.accessibilityLabel ?? opt.label}
            style={[styles.segment, active && styles.segmentActive]}
          >
            <ThemedText
              type="label"
              themeColor={active ? 'primaryForeground' : 'textSecondary'}
            >
              {opt.label}
            </ThemedText>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  group: {
    flexDirection: 'row',
    alignSelf: 'flex-start',
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    padding: 2,
    gap: 2,
  },
  segment: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.sm,
  },
  segmentActive: {
    backgroundColor: Colors.light.primary,
  },
});
