"use client";

// 인앱 배너 슬롯 (Story 1.6 자리 → Story 5.1 배선). 헤더 하단 Z-순서 자리(배너<콘텐츠<FAB).
//
// 미확인 통지(useNotifications)를 조회해 각 건을 NotificationBanner 로 render-time map 렌더한다
// (effect→setState 금지·반복함정 #2). 통지 0건/미로그인/로딩이면 빈 컨테이너 → `empty:hidden` 이
// 공간을 차지하지 않게 한다(AC4 — 기존 슬롯 계약 보존). 출현은 컨테이너 `aria-live="polite"` 가
// 자동 안내한다(푸시 아님 — 접속 시점 GET 조회로만 표시). AppShell.tsx 의 Z-순서·레이아웃·기존
// id/aria/className 은 그대로 유지한다(AppShell 자체 수정 불요 — 이 컴포넌트만 승격).
import { NotificationBanner } from "@/features/notifications/NotificationBanner";
import { useNotifications } from "@/features/notifications/useNotifications";

export function InAppBannerSlot() {
  const { data: notifications } = useNotifications();

  return (
    <div
      id="in-app-banner-slot"
      aria-live="polite"
      className="mx-auto w-full max-w-6xl px-4 empty:hidden"
    >
      {notifications && notifications.length > 0 ? (
        <div className="flex flex-col gap-2 py-2">
          {notifications.map((notification) => (
            // key = type:reservation_id (리마인드 id=null 대응 — 종류당 예약별 1건이라 유일, 5.2).
            <NotificationBanner
              key={`${notification.type}:${notification.reservation_id}`}
              notification={notification}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
