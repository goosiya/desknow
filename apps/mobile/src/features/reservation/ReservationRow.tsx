import { Pressable, StyleSheet, View } from 'react-native';
import { router, type Href } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing, type ThemeColor } from '@/constants/theme';
import { StarRating } from '@/features/detail/StarRating';
import type { ReservationListItem } from '@/lib/api-client';

import { isCancelWindowPassed } from './errors';
import {
  isCancellable,
  isUpcoming,
  reservationDateLabel,
  reservationTimeRangeLabel,
} from './reservations';
import { ReviewForm } from './ReviewForm';
import { ShareButton } from './ShareButton';
import { useCancelReservation } from './useCancelReservation';

// 예약현황 목록 한 행 — 웹 reservation/ReservationRow.tsx RN 포팅 (Story 9.2 — AC4·AC5·AC7).
// 룸 이름·시간·상태 배지 + 상세 이동 + 취소 + 후기 + 공유.
//
// ⚠️ a11y: 활성 룸=상세 이동 Pressable, 비활성 룸=비대화형 View(막다른 화면 금지·진입 차단). 상세
//    이동과 취소/공유 버튼은 **형제**(중첩 인터랙티브 금지). 시간·분류는 전부 render-time 순수 계산
//    (reservations.ts)에서 온다. status 배지는 색 단독 금지(아이콘 + 텍스트 동반 — 3중 신호).

/** 6h 미만 남은 confirmed 예약의 취소 비활성 안내. */
const CANCEL_LEAD_NOTICE = '이제 6시간이 안 남아서 취소가 어려워요.';

type BadgeMeta = { label: string; icon: string; bg: ThemeColor; fg: ThemeColor };

/** 상태 배지 메타 — 확정/이용 완료/취소됨/거절됨(색 + 아이콘 + 텍스트 3중 신호). */
function statusBadge(item: ReservationListItem, now: Date): BadgeMeta {
  if (item.status === 'cancelled') {
    return { label: '취소됨', icon: '✕', bg: 'backgroundElement', fg: 'pinFull' };
  }
  if (item.status === 'rejected') {
    return { label: '거절됨', icon: '✕', bg: 'backgroundElement', fg: 'pinFull' };
  }
  // confirmed — 다가오면 '확정', 모든 슬롯이 지났으면 '이용 완료'.
  if (isUpcoming(item, now)) {
    return { label: '확정', icon: '✓', bg: 'secondary', fg: 'success' };
  }
  return { label: '이용 완료', icon: '✓', bg: 'backgroundElement', fg: 'textSecondary' };
}

function ReservationStatusBadge({ meta }: { meta: BadgeMeta }) {
  return (
    <View style={[styles.badge, { backgroundColor: Colors.light[meta.bg] }]}>
      <ThemedText type="caption" themeColor={meta.fg}>
        {meta.icon} {meta.label}
      </ThemedText>
    </View>
  );
}

/** 행 본문(룸 이름·상태 배지·날짜·시간). 활성=Pressable, 비활성=View 가 감싼다(호출처에서 분기). */
function RowBody({ item, now }: { item: ReservationListItem; now: Date }) {
  const dateLabel = reservationDateLabel(item);
  const timeLabel = reservationTimeRangeLabel(item);
  return (
    <>
      <View style={styles.nameRow}>
        <ThemedText type="h3" themeColor="cardForeground" style={styles.name}>
          {item.room_name || '이름 없음'}
        </ThemedText>
        <ReservationStatusBadge meta={statusBadge(item, now)} />
      </View>
      {dateLabel && timeLabel ? (
        <ThemedText type="bodySm" themeColor="textSecondary">
          {dateLabel} {timeLabel}
        </ThemedText>
      ) : null}
    </>
  );
}

export function ReservationRow({
  item,
  now,
}: {
  item: ReservationListItem;
  now: Date;
}) {
  const cancel = useCancelReservation();

  // 취소 버튼은 **다가오는 confirmed** 에만 노출(취소/거절/이용 완료엔 미노출 — AC4).
  const showCancel = item.status === 'confirmed' && isUpcoming(item, now);
  const cancellable = isCancellable(item, now);
  // 공유 버튼은 **다가오는 confirmed(활성 룸)** 에만 노출(이미 종료된 예약 공유 무의미·죽은 링크 방지).
  const showShare = item.status === 'confirmed' && item.is_active && isUpcoming(item, now);

  // 후기 게이팅(AC5). 이용 완료 = confirmed + 다가오지 않음(모든 슬롯 종료). 미작성 → 폼, 작성됨 → 표시.
  const isCompleted = item.status === 'confirmed' && !isUpcoming(item, now);
  const showReviewForm = isCompleted && !item.has_review;
  const showReviewDone = isCompleted && item.has_review;

  return (
    <View style={styles.row}>
      <View style={styles.topRow}>
        {item.is_active ? (
          // 활성 — 상세(/rooms/{id}) 진입 가능. 취소/공유 버튼과 분리된 형제(중첩 인터랙티브 금지).
          <Pressable
            onPress={() => router.push(`/rooms/${item.room_id}` as Href)}
            accessibilityRole="button"
            accessibilityLabel={`${item.room_name || '이름 없음'} 상세 보기`}
            style={styles.body}
          >
            <RowBody item={item} now={now} />
          </Pressable>
        ) : (
          // 비활성 — 상세 진입 차단. 이름·히스토리는 표시(막다른 화면 금지).
          <View style={styles.body}>
            <RowBody item={item} now={now} />
          </View>
        )}
        <View style={styles.actions}>
          {showShare ? (
            <ShareButton
              roomName={item.room_name}
              slotStarts={item.slot_starts}
              roomId={item.room_id}
            />
          ) : null}
          {showCancel ? (
            <Pressable
              onPress={() => cancel.mutate({ roomId: item.room_id, reservationId: item.id })}
              disabled={!cancellable || cancel.isPending}
              accessibilityRole="button"
              accessibilityLabel="예약 취소"
              accessibilityState={{ disabled: !cancellable || cancel.isPending }}
              style={[styles.cancelButton, (!cancellable || cancel.isPending) && styles.disabled]}
            >
              <ThemedText type="label" themeColor="cardForeground">
                {cancel.isPending ? '취소 중…' : '취소'}
              </ThemedText>
            </Pressable>
          ) : null}
        </View>
      </View>

      {/* 6h 미만 — 취소 비활성 안내(AC4). 버튼이 노출되고 비활성일 때만. */}
      {showCancel && !cancellable ? (
        <ThemedText type="caption" themeColor="textSecondary">
          {CANCEL_LEAD_NOTICE}
        </ThemedText>
      ) : null}

      {/* 취소 실패 안내: 클럭 스큐 409 는 친절 안내(목록 재조회는 훅이 처리), 그 외 generic 재시도. */}
      {cancel.isError ? (
        isCancelWindowPassed(cancel.error) ? (
          <ThemedText accessibilityRole="alert" type="caption" themeColor="textSecondary">
            방금 취소 가능 시간이 지났어요. 목록을 새로고침했어요.
          </ThemedText>
        ) : (
          <ThemedText accessibilityRole="alert" type="caption" themeColor="pinFull">
            취소하지 못했어요. 잠시 후 다시 시도해 주세요.
          </ThemedText>
        )
      ) : null}

      {/* 후기(AC5): 이용 완료·미작성=작성 폼 / 작성됨=내 후기(별점·내용)+사장님 답글 read-only. */}
      {showReviewForm ? (
        <ReviewForm reservationId={item.id} roomId={item.room_id} />
      ) : showReviewDone && item.review ? (
        <View style={styles.myReview}>
          <View style={styles.nameRow}>
            <ThemedText type="caption" themeColor="success" style={styles.bold}>
              내 후기
            </ThemedText>
            <StarRating rating={item.review.rating} />
          </View>
          <ThemedText type="bodySm" themeColor="cardForeground">
            {item.review.text}
          </ThemedText>
          {/* 사장님 답글 — 있으면 내 후기 아래 중첩(좌측 보더로 시각 구분). */}
          {item.review.reply ? (
            <View accessibilityLabel="사장님 답글" style={styles.reply}>
              <ThemedText type="caption" themeColor="text" style={styles.bold}>
                사장님 답글
              </ThemedText>
              <ThemedText type="bodySm" themeColor="cardForeground">
                {item.review.reply.text}
              </ThemedText>
            </View>
          ) : null}
        </View>
      ) : showReviewDone ? (
        // review 누락 방어(정상 경로엔 has_review면 review 동반) — 안전 degrade.
        <ThemedText type="caption" themeColor="success" style={styles.bold}>
          후기 완료
        </ThemedText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: Spacing[2],
    padding: Spacing[3],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  topRow: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing[2] },
  body: { flex: 1, gap: Spacing[1] },
  nameRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: Spacing[2] },
  name: { flexShrink: 1 },
  // 공유·취소는 본문 우측에 **가로로 나란히**(웹 ReservationRow의 flex items-center 미러).
  // 세로 스택이면 '취소'가 '공유' 아래로 처져 날짜보다 낮게 보였다(KTH 2026-06-20 실기기 지적).
  actions: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing[2] },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: Radius.full,
    paddingHorizontal: Spacing[2],
    paddingVertical: Spacing[1],
  },
  cancelButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[3],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  disabled: { opacity: 0.5 },
  bold: { fontWeight: '600' },
  myReview: {
    gap: Spacing[2],
    padding: Spacing[3],
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.backgroundElement,
  },
  reply: {
    gap: Spacing[1],
    marginLeft: Spacing[3],
    paddingVertical: Spacing[2],
    paddingLeft: Spacing[3],
    paddingRight: Spacing[2],
    borderLeftWidth: 2,
    borderLeftColor: Colors.light.border,
    borderRadius: Radius.md,
    backgroundColor: Colors.light.card,
  },
});
