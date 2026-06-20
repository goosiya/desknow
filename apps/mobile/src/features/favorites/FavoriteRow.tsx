import { Pressable, StyleSheet, View } from 'react-native';
import { router, type Href } from 'expo-router';

import type { FavoriteRoomItem } from '@/lib/api-client';
import { StatusBadge } from '@/features/map/StatusBadge';
import { pinStatus } from '@/features/map/pin';
import {
  AMENITY_LABELS,
  ROOM_TYPE_LABELS,
  formatPrice,
  labelFor,
} from '@/features/map/roomSummary';
import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

import { FavoriteButton } from './FavoriteButton';

// 즐겨찾기 목록 한 행 — 웹 FavoriteRow RN 포팅 (Story 9.1 — AC4). 이름·예약 배지·가격·룸형태·부대시설
// + 하트. 비활성 룸(is_active=false)은 '비활성' 라벨 + 상세 진입 차단(막다른 화면 금지 — 라벨로 안내).
//
// ⚠️ 슬롯 anti-pattern 회피: 배지는 서버 신선 remaining_slots(pinStatus 자명 분기)로 도출.

/** 비활성 룸 라벨 — 색 + 텍스트(상세 진입 차단 안내). */
function InactiveBadge() {
  return (
    <View style={styles.inactiveBadge}>
      <ThemedText type="label" themeColor="textSecondary">
        ⊘ 비활성
      </ThemedText>
    </View>
  );
}

function RowBody({ favorite }: { favorite: FavoriteRoomItem }) {
  const status = pinStatus(favorite.remaining_slots);
  return (
    <>
      <ThemedText type="h3" themeColor="cardForeground">
        {favorite.name || '이름 없음'}
      </ThemedText>
      <View style={styles.metaRow}>
        {favorite.is_active ? <StatusBadge status={status} /> : <InactiveBadge />}
        <ThemedText type="bodySm" themeColor="cardForeground">
          <ThemedText type="bodySm">{formatPrice(favorite.price_per_hour)}</ThemedText>
          <ThemedText type="bodySm" themeColor="textSecondary">
            /시간
          </ThemedText>
        </ThemedText>
        <ThemedText type="caption" themeColor="textSecondary">
          {labelFor(favorite.room_type, ROOM_TYPE_LABELS)}
        </ThemedText>
      </View>
      {favorite.amenities.length > 0 ? (
        <View style={styles.chips}>
          {favorite.amenities.map((code) => (
            <View key={code} style={styles.chip}>
              <ThemedText type="caption" themeColor="secondaryForeground">
                {labelFor(code, AMENITY_LABELS)}
              </ThemedText>
            </View>
          ))}
        </View>
      ) : null}
    </>
  );
}

export function FavoriteRow({ favorite }: { favorite: FavoriteRoomItem }) {
  return (
    <View style={styles.row}>
      {favorite.is_active ? (
        // 활성 — 상세(9.2 스텁) 진입 가능. 하트와 분리된 형제(중첩 인터랙티브 금지).
        <Pressable
          onPress={() => router.push(`/rooms/${favorite.room_id}` as Href)}
          accessibilityRole="button"
          style={styles.body}
        >
          <RowBody favorite={favorite} />
        </Pressable>
      ) : (
        // 비활성 — 상세 진입 차단(비대화형). 라벨로 상태 안내(막다른 화면 금지).
        <View style={styles.body}>
          <RowBody favorite={favorite} />
        </View>
      )}
      <FavoriteButton roomId={favorite.room_id} />
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing[2],
    padding: Spacing[3],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  body: { flex: 1, gap: Spacing[2] },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: Spacing[2] },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing[1] },
  chip: {
    borderRadius: Radius.full,
    backgroundColor: Colors.light.secondary,
    paddingHorizontal: Spacing[2],
    paddingVertical: 2,
  },
  inactiveBadge: {
    alignSelf: 'flex-start',
    borderRadius: Radius.full,
    backgroundColor: Colors.light.backgroundElement,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[1],
  },
});
