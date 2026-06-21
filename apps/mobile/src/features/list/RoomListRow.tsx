import { Pressable, StyleSheet, View } from 'react-native';

import type { RoomListItem } from '@/lib/api-client';
import { FavoriteButton } from '@/features/favorites/FavoriteButton';
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

// 지역/반경 목록 한 행 — 웹 RoomListRow RN 포팅 (Story 9.1 — AC3·AC4). 이름·예약 배지·가격·룸형태·
// 부대시설 + 즐겨찾기. 행 본문 탭 → 부모가 바텀시트 오픈. 하트는 형제 버튼(중첩 인터랙티브 금지).
//
// ⚠️ 슬롯 anti-pattern 회피: 배지는 서버 신선 remaining_slots(pinStatus 자명 분기)로 도출(클라 재계산 0).
type RoomListRowProps = {
  room: RoomListItem;
  onSelect: (room: RoomListItem) => void;
};

export function RoomListRow({ room, onSelect }: RoomListRowProps) {
  const status = pinStatus(room.remaining_slots);
  return (
    <View style={styles.row}>
      <Pressable
        onPress={() => onSelect(room)}
        accessibilityRole="button"
        style={styles.body}
      >
        <ThemedText type="h3" themeColor="cardForeground">
          {room.name}
        </ThemedText>
        <View style={styles.metaRow}>
          <StatusBadge status={status} />
          <ThemedText type="bodySm" themeColor="cardForeground">
            <ThemedText type="bodySm">{formatPrice(room.price_per_hour)}</ThemedText>
            <ThemedText type="bodySm" themeColor="textSecondary">
              /시간
            </ThemedText>
          </ThemedText>
          <ThemedText type="caption" themeColor="textSecondary">
            {labelFor(room.room_type, ROOM_TYPE_LABELS)}
          </ThemedText>
        </View>
        {room.amenities.length > 0 ? (
          <View style={styles.chips}>
            {room.amenities.map((code) => (
              <View key={code} style={styles.chip}>
                <ThemedText type="caption" themeColor="secondaryForeground">
                  {labelFor(code, AMENITY_LABELS)}
                </ThemedText>
              </View>
            ))}
          </View>
        ) : null}
      </Pressable>
      {/* 목록 카드는 높이가 짧아 안내 팝오버를 하트 왼쪽(카드 안)으로 연다(아래로 열면 카드 밖 넘침). */}
      <FavoriteButton roomId={room.room_id} hintPlacement="left" />
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
});
