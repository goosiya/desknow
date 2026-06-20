// 인앱 통지 쿼리/소멸 뮤테이션 — 웹 notifications/useNotifications.ts 미러 (Story 9.2 — AC6).
//
// ⚠️ 키 프리픽스 = ["notifications"] (최상위 독립). ["rooms",...]/["reservations",...] 프리픽스
//    **금지** — useFavorites/useReservations 선례(deferred L153 정신): 지도/시트/예약현황이 그 키를
//    쓰므로 광역 무효화가 그 캐시까지 휩쓴다. 통지는 독립 키 + 정확 키 invalidate 만 한다.
//
// 미로그인 시 비활성(useSession `!!user`). 폴링/푸시 없음 — 접속 시점(컴포넌트 마운트) 1회 GET.
// 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드). 인증 헤더(Bearer)는 인터셉터가 주입.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  notificationsDismissNotification,
  notificationsDismissReminder,
  notificationsListNotifications,
  type NotificationItem,
} from "@/lib/api-client";
import { useSession } from "@/features/auth/useSession";

/** 통지 캐시 키 — 최상위 독립(절대 ["rooms"]/["reservations"] 프리픽스 금지, favorites 선례). */
export const NOTIFICATIONS_KEY = ["notifications"] as const;

/** 본인 미확인 통지 목록(미로그인 시 비활성 — enabled). InAppBannerSlot 이 소비. */
export function useNotifications() {
  const { data: user } = useSession();
  return useQuery({
    queryKey: NOTIFICATIONS_KEY,
    enabled: !!user,
    queryFn: async (): Promise<NotificationItem[]> => {
      const { data } = await notificationsListNotifications({ throwOnError: true });
      return data ?? [];
    },
  });
}

type DismissVars = { notificationId: string };
type DismissContext = { previous: NotificationItem[] | undefined };

/**
 * 통지 소멸 뮤테이션(옵티미스틱 — AC6). '확인'(status_change 등) 진입점.
 *
 * **옵티미스틱 패턴(useToggleFavorite 선례):**
 * - onMutate: cancelQueries → 스냅샷 previous → 해당 id 제거로 즉시 반영(배너 사라짐).
 * - onError: previous 로 롤백(서버 실패 시 배너 복원).
 * - onSettled: ["notifications"] **정확 키만** invalidate(절대 ["rooms"]/["reservations"] 광역 금지).
 *
 * 소멸은 서버에 영속(dismissed_at)되므로 재접속 시 다시 뜨지 않는다(AC6). 멱등(서버 보장)이라
 * 중복 클릭·재시도에도 안전하다.
 */
export function useDismissNotification() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, DismissVars, DismissContext>({
    mutationFn: async ({ notificationId }) => {
      await notificationsDismissNotification({
        path: { notification_id: notificationId },
        throwOnError: true,
      });
    },
    onMutate: async ({ notificationId }) => {
      await queryClient.cancelQueries({ queryKey: NOTIFICATIONS_KEY });
      const previous =
        queryClient.getQueryData<NotificationItem[]>(NOTIFICATIONS_KEY);
      queryClient.setQueryData<NotificationItem[]>(NOTIFICATIONS_KEY, (old) =>
        (old ?? []).filter((item) => item.id !== notificationId),
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(NOTIFICATIONS_KEY, context.previous);
      }
    },
    onSettled: () => {
      // 정확 키만 — ["rooms"]/["reservations"] 프리픽스 광역 무효화 절대 금지(favorites 선례).
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
  });
}

type DismissReminderVars = { reservationId: string };

/**
 * 도래 리마인드 '다시 보지 않기' 뮤테이션(옵티미스틱 — AC6).
 *
 * status_change '확인'(useDismissNotification)과 **독립 트리거**다(서로의 dismiss를 건드리지
 * 않음 — 키·엔드포인트 분리). 도래 리마인드는 도출(행 없음)이라 notification id가 없어
 * `reservation_id` 키 엔드포인트(`notificationsDismissReminder`)를 호출하고, 서버가 born-dismissed
 * 억제행을 생성해 사용자별로 영속한다(재접속 시 그 예약 리마인드 미도출).
 *
 * **옵티미스틱(useDismissNotification 미러):** onMutate가 **해당 reservation_id의
 * reservation_reminder 항목만** 제거한다(같은 예약 status_change·타 예약 리마인드 불변 — 독립
 * 트리거). onError 롤백. onSettled는 ["notifications"] **정확 키만** invalidate. 멱등이라 재클릭 안전.
 */
export function useDismissReminder() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, DismissReminderVars, DismissContext>({
    mutationFn: async ({ reservationId }) => {
      await notificationsDismissReminder({
        path: { reservation_id: reservationId },
        throwOnError: true,
      });
    },
    onMutate: async ({ reservationId }) => {
      await queryClient.cancelQueries({ queryKey: NOTIFICATIONS_KEY });
      const previous =
        queryClient.getQueryData<NotificationItem[]>(NOTIFICATIONS_KEY);
      queryClient.setQueryData<NotificationItem[]>(NOTIFICATIONS_KEY, (old) =>
        // 해당 예약의 리마인드 항목만 제거 — type+reservation_id 매칭(status_change·타 예약 불변).
        (old ?? []).filter(
          (item) =>
            !(
              item.type === "reservation_reminder" &&
              item.reservation_id === reservationId
            ),
        ),
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(NOTIFICATIONS_KEY, context.previous);
      }
    },
    onSettled: () => {
      // 정확 키만 — ["rooms"]/["reservations"] 프리픽스 광역 무효화 절대 금지(favorites 선례).
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
    },
  });
}
