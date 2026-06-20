"use client";

// 단건 인앱 배너 (Story 5.1·5.2 — UX-DR5 · AC3·AC4). 면 위 플랫 배너 + 닫기.
//
// ⚠️ 색 단독 금지(architecture.md L300): 배경(색) + 아이콘(Bell) + 텍스트 3중 신호.
// ⚠️ 카피는 type/reason/room_name/slot_start 로 render-time 파생한다(effect→setState 금지,
//    반복함정 #2). status_change·reminder 양쪽 slot_start 정밀 카피(룸+KST 일시) — 5.3.
// ⚠️ 닫기 = 실제 dismiss 호출(dead 버튼 금지 — 반복함정 #7). **type별 분기**(5.2): 도래 리마인드는
//    '다시 보지 않기'(useDismissReminder·reservation_id 키) / status_change 등은 '확인'
//    (useDismissNotification·id 키) — 독립 트리거(서로 안 건드림). 토큰 스타일은 NetworkNotice 미러.
// ⚠️ KST 절대 날짜·시각 포맷은 reservation slots 헬퍼(formatDateKorean·kstToday·formatSlotLabel)를
//    재사용한다(중복 금지). 상대일("내일/오늘") 클라 KST 경계 재판정은 지양(deferred L207 트랩 —
//    절대 날짜·시각 표기).
// ⚠️ a11y: 배너에 role="status"를 두지 않는다 — 부모 InAppBannerSlot 컨테이너가 이미
//    aria-live="polite"(슬롯 계약)라 출현을 안내한다. 배너마다 live region 중첩 금지(이중 낭독 —
//    code review 2026-06-17).
import { Bell } from "lucide-react";

import type { NotificationItem } from "@/lib/api-client";
import {
  formatDateKorean,
  formatSlotLabel,
  kstToday,
} from "@/features/reservation/slots";

import { useDismissNotification, useDismissReminder } from "./useNotifications";

/**
 * slot_start(서버 UTC ISO) → "6월 17일 14:00"(KST 절대 날짜·시각) 또는 손상 시 ``null``.
 *
 * **L6 손상-데이터 가드(deferred-work.md L6 회수·reminder·status_change 공유):** 비-ISO/손상
 * slot_start면 ``new Date(...)``=Invalid Date → ``Intl.DateTimeFormat.format()``이 ``RangeError``를
 * throw해 render-time 파생인 ``InAppBannerSlot.map()`` 전체가 깨진다(정상 통지까지 소실). 포맷 전
 * ``Number.isNaN`` 검사로 손상을 잡아 ``null``을 반환 → 호출처가 시각 없는 generic 카피로 폴백한다
 * (throw 금지·room_name=null 폴백과 동일 정신). KST 절대 표기(상대일 재판정 회피 — deferred L207).
 *
 * **tz 지정자(무-Z) 가드(코드리뷰 2026-06-17 KTH 결정·BE earliest_slot_start와 대칭):** 와이어
 * 계약은 항상 UTC ``...Z``(또는 오프셋)다. tz 지정자 없는 naive ISO("2026-06-17T10:00:00")는
 * ``new Date``가 **host-local**로 해석해 NaN이 아니므로 위 가드를 통과하지만, 표시 시각이
 * host-tz에 따라 달라지는 조용한 오시각이 된다(BE와 동일 손상 클래스). tz 지정자 부재도 손상으로
 * 보아 ``null`` 폴백 → 시각 없는 generic 카피로 통일한다.
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
 * - status_change: reason 별 정밀 카피(5.3). slot_start 있고 유효하면 "{room} {KST 날짜} {시각}
 *   예약이 거절/취소됐어요.", 없거나 손상이면 generic "{room} 예약이 거절/취소됐어요."(L6 폴백).
 *   미지 reason은 "{room} 예약 상태가 변경됐어요.". **재탐색 CTA 없음**(KTH 확정 ② — 정보 카피만).
 * - reservation_reminder: slot_start 유효하면 "{room} 예약이 곧 다가와요. {KST 날짜} {시각}에
 *   만나요.", 없거나 손상이면 generic "{room} 예약이 곧 다가와요."(L6 폴백·status_change와 가드 공유).
 *
 * 룸 이름 누락(room_name=null·합성 폴백)·손상 slot_start도 막다른 화면 없이 카피한다(반복함정 #6·#7).
 */
export function bannerMessage(notification: NotificationItem): string {
  const room = notification.room_name?.trim();
  const prefix = room ? `${room} ` : "";
  // 손상 slot_start는 null → 시각 없는 generic 폴백(L6 가드를 두 분기가 공유).
  const when = notification.slot_start
    ? formatKstDateTime(notification.slot_start)
    : null;
  if (notification.type === "status_change") {
    const verb =
      notification.reason === "rejected"
        ? "거절"
        : notification.reason === "cancelled"
          ? "취소"
          : null;
    if (verb === null) return `${prefix}예약 상태가 변경됐어요.`; // 미지 reason 폴백
    if (when) return `${prefix}${when} 예약이 ${verb}됐어요.`; // 룸+KST 일시+사유(정밀)
    return `${prefix}예약이 ${verb}됐어요.`; // slot_start 없음/손상 generic 폴백
  }
  if (notification.type === "reservation_reminder") {
    if (when) return `${prefix}예약이 곧 다가와요. ${when}에 만나요.`;
    return `${prefix}예약이 곧 다가와요.`;
  }
  return "예약 알림이 있어요."; // 알 수 없는 종류 폴백(막다른 화면 금지)
}

export function NotificationBanner({
  notification,
}: {
  notification: NotificationItem;
}) {
  // 두 hook 모두 무조건 호출(hooks 규칙) — type 으로 동작·라벨만 분기한다(독립 트리거).
  const dismissReminder = useDismissReminder();
  const dismissNotification = useDismissNotification();
  const isReminder = notification.type === "reservation_reminder";

  const message = bannerMessage(notification);
  // 도래 리마인드 = '다시 보지 않기'(영속 억제), status_change 등 = '확인'(5.1 기본).
  const closeLabel = isReminder ? "다시 보지 않기" : "확인";
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
    <div className="flex items-center gap-2 rounded-md border border-border bg-secondary px-4 py-2 text-sm leading-[1.6] text-secondary-foreground">
      {/* 아이콘 — 색 단독 신호 회피(aria-hidden, 의미는 텍스트가 전달). */}
      <Bell aria-hidden="true" className="size-4 shrink-0" />
      <span className="flex-1">{message}</span>
      {/* 닫기 — 실제 dismiss 호출(≥44px tap-target·aria-label). type별 라벨·동작 분기. */}
      <button
        type="button"
        onClick={handleDismiss}
        disabled={isPending}
        aria-label="알림 닫기"
        className="tap-target inline-flex shrink-0 items-center justify-center rounded-md px-2 text-sm font-medium text-secondary-foreground hover:bg-muted disabled:opacity-60"
      >
        {closeLabel}
      </button>
    </div>
  );
}
