import { useEffect } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { ComboSelect } from '@/components/ComboSelect';
import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

import { dongsFor } from './regions';
import { useRegions } from './useRegions';

// 지역 콤보 — 웹 RegionCombos RN 포팅 (Story 9.1 — AC4). 시/군/구 → 동/읍/면 2단 선택.
// 데이터(useRegions)는 여기서 가져오되 **선택 상태는 부모(ExploreView)가 보유**한다(토글 왕복 시
// 보존). 시군구 변경 시 지역 선택을 리셋한다. 용어는 "지역"으로 통일(행정동/법정동 금지).

// 지역 콤보의 "전체"(시군구 전체) 센티넬 — 동 미선택(구 전체)을 명시 옵션으로 표현.
const DONG_ALL = '__all__';

type RegionCombosProps = {
  sigunguCode: string | undefined;
  dongCode: string | undefined;
  onSigunguChange: (code: string | undefined) => void;
  onDongChange: (code: string | undefined) => void;
};

export function RegionCombos({
  sigunguCode,
  dongCode,
  onSigunguChange,
  onDongChange,
}: RegionCombosProps) {
  const { data: groups = [], isLoading, isError, refetch } = useRegions();
  const dongs = dongsFor(groups, sigunguCode);

  // stale 선택 조정 — 데이터 리페치로 선택했던 시군구/지역이 사라지면 부모 상태를 정리한다(미정리 시
  // resolveRegionCode가 stale 코드로 조회 → 거짓 "등록된 곳이 없어요"). 데이터 준비 후에만 수행.
  useEffect(() => {
    if (isLoading || isError || groups.length === 0) return;
    if (sigunguCode && !groups.some((g) => g.code === sigunguCode)) {
      onSigunguChange(undefined);
      onDongChange(undefined);
      return;
    }
    const currentDongs = dongsFor(groups, sigunguCode);
    if (dongCode && !currentDongs.some((d) => d.code === dongCode)) {
      onDongChange(undefined);
    }
  }, [groups, sigunguCode, dongCode, isLoading, isError, onSigunguChange, onDongChange]);

  // 콤보 데이터 로드 실패 → 막다른 화면 금지(재시도 노출).
  if (isError) {
    return (
      <View style={styles.errorCard}>
        <ThemedText type="bodySm" themeColor="cardForeground">
          지역 목록을 못 불러왔어요.
        </ThemedText>
        <Pressable onPress={() => refetch()} accessibilityRole="button" style={styles.retry}>
          <ThemedText type="label" themeColor="primaryForeground">
            다시 시도
          </ThemedText>
        </Pressable>
      </View>
    );
  }

  const combosDisabled = isLoading || groups.length === 0;

  return (
    <View style={styles.combos}>
      <ComboSelect
        accessibilityLabel="시/군/구 선택"
        placeholder="시/군/구"
        value={sigunguCode}
        disabled={combosDisabled}
        options={groups.map((g) => ({ value: g.code, label: `${g.name} (${g.room_count})` }))}
        onChange={(code) => {
          onSigunguChange(code);
          onDongChange(undefined); // 시군구 변경 → 지역 리셋
        }}
      />
      <ComboSelect
        accessibilityLabel="동/읍/면 선택"
        placeholder="동/읍/면 전체"
        value={dongCode ?? DONG_ALL}
        disabled={combosDisabled || !sigunguCode}
        options={[
          { value: DONG_ALL, label: '동/읍/면 전체' },
          ...dongs.map((d) => ({ value: d.code, label: `${d.name} (${d.room_count})` })),
        ]}
        onChange={(code) => onDongChange(code === DONG_ALL ? undefined : code)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  combos: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing[2] },
  errorCard: {
    gap: Spacing[2],
    padding: Spacing[4],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
    alignItems: 'flex-start',
  },
  retry: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
});
