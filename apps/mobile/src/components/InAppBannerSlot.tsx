import { useEffect, useRef } from 'react';
import { AccessibilityInfo, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { HEADER_CONTENT_HEIGHT } from '@/components/AppHeader';
import { Spacing } from '@/constants/theme';
import { NotificationBanner } from '@/features/notifications/NotificationBanner';
import { useNotifications } from '@/features/notifications/useNotifications';

// 인앱 배너 슬롯 (Story 1.6 자리 → 9.2 배선). 전역 상단 오버레이(배너<콘텐츠<FAB Z-순서). 9.1이
// 이미 마운트(_layout.tsx)했으므로 **내부만 채운다**(슬롯 계약·배치 보존).
//
// 미확인 통지(useNotifications)를 조회해 각 건을 NotificationBanner 로 render-time map 렌더한다
// (effect→setState 금지). 통지 0건/미로그인/로딩이면 null 반환 → 공간을 차지하지 않는다(AC6). 출현은
// AccessibilityInfo.announceForAccessibility 로 안내한다(웹 aria-live 등가 — 푸시 아님·접속 시점 GET).
//
// ⚠️ 절대 배치 + pointerEvents="box-none": 배너가 없는 영역의 터치는 아래 화면으로 통과시키고, 배너
//    카드(닫기 버튼)만 터치를 잡는다. top 인셋으로 상태바 아래에 둔다.
export function InAppBannerSlot() {
  const { data: notifications } = useNotifications();
  const insets = useSafeAreaInsets();

  // 통지 출현 안내(웹 aria-live 등가) — 통지 건수가 **늘 때만** 공지한다. dismiss로 줄 때는
  // 재낭독하지 않는다(폴링/푸시 없이 접속 시점 1회 GET이라 실질적으로 최초 출현 시 1회).
  const keySignature = (notifications ?? [])
    .map((n) => `${n.type}:${n.reservation_id}`)
    .join('|');
  const announcedCountRef = useRef(0);
  useEffect(() => {
    const count = keySignature ? keySignature.split('|').length : 0;
    if (count > announcedCountRef.current) {
      AccessibilityInfo.announceForAccessibility(`알림 ${count}건이 있어요.`);
    }
    announcedCountRef.current = count;
  }, [keySignature]);

  if (!notifications || notifications.length === 0) {
    return null; // 0건/미로그인/로딩 — 공간 미점유(슬롯 계약 보존).
  }

  return (
    <View
      pointerEvents="box-none"
      // 글로벌 헤더(9.4) 아래로 배너를 띄운다 — 헤더 높이(top 인셋 + 콘텐츠 56)만큼 내린다.
      style={[styles.slot, { top: insets.top + HEADER_CONTENT_HEIGHT + Spacing[2] }]}
    >
      <View style={styles.list}>
        {notifications.map((notification) => (
          // key = type:reservation_id (리마인드 id=null 대응 — 종류당 예약별 1건이라 유일).
          <NotificationBanner
            key={`${notification.type}:${notification.reservation_id}`}
            notification={notification}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  slot: {
    position: 'absolute',
    left: 0,
    right: 0,
    paddingHorizontal: Spacing[4],
    zIndex: 90,
  },
  list: { gap: Spacing[2] },
});
