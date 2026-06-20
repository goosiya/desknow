import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';
import type { NotificationItem } from '@/lib/api-client';
import {
  formatDateKorean,
  formatSlotLabel,
  kstToday,
} from '@/features/reservation/slots';

import { useDismissNotification, useDismissReminder } from './useNotifications';

// 단건 인앱 배너 — 웹 notifications/NotificationBanner.tsx RN 포팅 (Story 9.2 — AC6). 면 위 플랫 배너
// + 닫기.
//
// ⚠️ 색 단독 금지: 배경(색) + 아이콘(🔔) + 텍스트 3중 신호.
// ⚠️ 카피는 type/reason/room_name/slot_start 로 render-time 파생한다(effect→setState 금지).
// ⚠️ 닫기 = 실제 dismiss 호출(dead 버튼 금지). **type별 분기**: 도래 리마인드는 '다시 보지 않기'
//    (useDismissReminder·reservation_id 키) / status_change 등은 '확인'(useDismissNotification·id 키)
//    — 독립 트리거(서로 안 건드림).
// ⚠️ KST 절대 날짜·시각 포맷은 slots 헬퍼(formatDateKorean·kstToday·formatSlotLabel)를 재사용한다.

/**
 * slot_start(서버 UTC ISO) → "6월 17일 14:00"(KST 절대 날짜·시각) 또는 손상 시 ``null``.
 *
 * 손상-데이터 가드: 비-ISO/손상 slot_start면 시각 없는 generic 카피로 폴백(throw 금지). tz 지정자
 * 없는 naive ISO도 host-local 오시각이 되므로 손상으로 보아 null 폴백(BE earliest_slot_start 대칭).
 */
function formatKstDateTime(slotStart: string): string | null {
  const hasTz = /(Z|[+-]\d{2}:?\d{2})$/.test(slotStart.trim()); // ...Z 또는 ±HH:MM 오프셋 필수
  if (!hasTz || Number.isNaN(new Date(slotStart).getTime())) return null; // 손상/무-Z → 시각 없는 폴백
  const date = formatDateKorean(kstToday(new Date(slotStart))); // "6월 17일"
  const time = formatSlotLabel(slotStart); // "14:00"
  return `${date} ${time}`;
}

/**
 * 통지 한 건의 배너 카피를 type/reason/room_name/slot_start 로 만든다(render-time 파생·정보 전용).
 *
 * - status_change: reason 별 정밀 카피. slot_start 유효하면 "{room} {KST 날짜} {시각} 예약이 거절/
 *   취소됐어요.", 없거나 손상이면 generic "{room} 예약이 거절/취소됐어요.".
 * - reservation_reminder: slot_start 유효하면 "{room} 예약이 곧 다가와요. {KST 날짜} {시각}에 만나요.",
 *   없거나 손상이면 generic "{room} 예약이 곧 다가와요.".
 */
export function bannerMessage(notification: NotificationItem): string {
  const room = notification.room_name?.trim();
  const prefix = room ? `${room} ` : '';
  const when = notification.slot_start
    ? formatKstDateTime(notification.slot_start)
    : null;
  if (notification.type === 'status_change') {
    const verb =
      notification.reason === 'rejected'
        ? '거절'
        : notification.reason === 'cancelled'
          ? '취소'
          : null;
    if (verb === null) return `${prefix}예약 상태가 변경됐어요.`; // 미지 reason 폴백
    if (when) return `${prefix}${when} 예약이 ${verb}됐어요.`; // 룸+KST 일시+사유(정밀)
    return `${prefix}예약이 ${verb}됐어요.`; // slot_start 없음/손상 generic 폴백
  }
  if (notification.type === 'reservation_reminder') {
    if (when) return `${prefix}예약이 곧 다가와요. ${when}에 만나요.`;
    return `${prefix}예약이 곧 다가와요.`;
  }
  return '예약 알림이 있어요.'; // 알 수 없는 종류 폴백(막다른 화면 금지)
}

export function NotificationBanner({
  notification,
}: {
  notification: NotificationItem;
}) {
  // 두 hook 모두 무조건 호출(hooks 규칙) — type 으로 동작·라벨만 분기한다(독립 트리거).
  const dismissReminder = useDismissReminder();
  const dismissNotification = useDismissNotification();
  const isReminder = notification.type === 'reservation_reminder';

  const message = bannerMessage(notification);
  // 도래 리마인드 = '다시 보지 않기'(영속 억제), status_change 등 = '확인'.
  const closeLabel = isReminder ? '다시 보지 않기' : '확인';
  const isPending = isReminder
    ? dismissReminder.isPending
    : dismissNotification.isPending;

  const handleDismiss = () => {
    if (isReminder) {
      // 리마인드는 도출(행 없음)이라 reservation_id 키로 억제(born-dismissed).
      dismissReminder.mutate({ reservationId: notification.reservation_id });
    } else if (notification.id) {
      // status_change 는 행 id 로 소멸(id 존재 타입가드 — reminder 만 id=null).
      dismissNotification.mutate({ notificationId: notification.id });
    }
  };

  return (
    <View style={styles.banner}>
      {/* 아이콘 — 색 단독 신호 회피(장식, 의미는 텍스트가 전달). */}
      <ThemedText type="bodySm" importantForAccessibility="no">
        🔔
      </ThemedText>
      <ThemedText type="bodySm" themeColor="secondaryForeground" style={styles.message}>
        {message}
      </ThemedText>
      {/* 닫기 — 실제 dismiss 호출(≥44 tap-target·a11y 라벨). type별 라벨·동작 분기. */}
      <Pressable
        onPress={handleDismiss}
        disabled={isPending}
        accessibilityRole="button"
        accessibilityLabel="알림 닫기"
        accessibilityState={{ disabled: isPending }}
        style={[styles.closeButton, isPending && styles.disabled]}
      >
        <ThemedText type="label" themeColor="secondaryForeground">
          {closeLabel}
        </ThemedText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing[2],
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.secondary,
    paddingHorizontal: Spacing[4],
    paddingVertical: Spacing[2],
  },
  message: { flex: 1 },
  closeButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[2],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
  },
  disabled: { opacity: 0.6 },
});
