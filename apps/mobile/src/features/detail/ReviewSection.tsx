import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';
import type { ReviewListItem } from '@/lib/api-client';

import { StarRating } from './StarRating';
import { useRoomReviews } from './useRoomReviews';

// 룸 상세 후기 섹션(읽기) — 웹 detail/ReviewSection.tsx RN 포팅 (Story 9.2 — AC1 · 범위 결정 #4).
// 후기 목록을 노출하고, 후기에 제공자 답글이 있으면 후기 카드 안에 익명("제공자 답글" 라벨)으로 중첩
// 표시한다. **후기 답글 작성(useReplyToReview)은 9.3 소유** — 9.2는 read-only 표시만.
//
// ⚠️ 익명(KTH 결정): 각 후기는 별점·텍스트·작성일만 표시(작성자 식별 정보 비노출 — 서버 응답에
//    작성자 필드 없음).
// ⚠️ 막다른 화면 금지: 0건=빈 카피, 로딩=조용한 자리, 실패=안내. 상세 섹션이라 전체 화면을 막지 않음.
// ⚠️ 무한스크롤 — 룸 상세는 ScrollView라 세로 FlatList 중첩 불가(VirtualizedList 경고) → 누적 .map()
//    + "후기 더 보기" 버튼으로 fetchNextPage 구동(웹 IntersectionObserver의 RN 등가·예약현황 탭은
//    최상위 스크롤러라 FlatList onEndReached 사용). 작성일=절대 표기(상대일 클라 재판정 금지).

/** 후기·답글 작성일 — 서버 UTC(...Z) → Asia/Seoul "2026년 6월 17일"(절대 표기). 손상 입력은 빈 문자열. */
function formatReviewDate(createdAtUtc: string): string {
  const date = new Date(createdAtUtc);
  if (Number.isNaN(date.getTime())) {
    return ''; // 손상 입력 — 날짜 미표시로 안전 degrade(예외/NaN 노출 금지)
  }
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(date);
}

/** 제공자 답글(익명) — "제공자 답글" 라벨 + 텍스트 + 작성일. 후기 카드 안에 좌측 보더로 시각 구분. */
function ProviderReply({ reply }: { reply: NonNullable<ReviewListItem['reply']> }) {
  return (
    <View accessibilityLabel="제공자 답글" style={styles.reply}>
      <View style={styles.rowBetween}>
        <ThemedText type="caption" themeColor="text" style={styles.bold}>
          제공자 답글
        </ThemedText>
        <ThemedText type="caption" themeColor="textSecondary">
          {formatReviewDate(reply.created_at)}
        </ThemedText>
      </View>
      <ThemedText type="bodySm" themeColor="cardForeground">
        {reply.text}
      </ThemedText>
    </View>
  );
}

/** 후기 한 건(익명) — 별점 + 작성일 + 텍스트 + (있으면) 제공자 답글. 작성자 미표시. */
function ReviewItem({ review }: { review: ReviewListItem }) {
  return (
    <View style={styles.card}>
      <View style={styles.rowBetween}>
        <StarRating rating={review.rating} />
        <ThemedText type="caption" themeColor="textSecondary">
          {formatReviewDate(review.created_at)}
        </ThemedText>
      </View>
      <ThemedText type="bodySm" themeColor="cardForeground">
        {review.text}
      </ThemedText>
      {review.reply ? <ProviderReply reply={review.reply} /> : null}
    </View>
  );
}

export function ReviewSection({ roomId }: { roomId: string }) {
  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useRoomReviews(roomId);

  return (
    <View style={styles.section}>
      <ThemedText type="h3" themeColor="text">
        후기
      </ThemedText>

      {isLoading ? (
        // 로딩 — 조용한 자리(섹션 내부, 막다른 화면 금지).
        <View style={styles.skeleton} accessibilityLabel="후기 불러오는 중" />
      ) : isError ? (
        // 실패 — 섹션 내부 안내(전체 화면을 막지 않음).
        <View style={styles.noticeBox}>
          <ThemedText type="bodySm" themeColor="textSecondary">
            후기를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.
          </ThemedText>
        </View>
      ) : !data || data.length === 0 ? (
        // 빈 상태(0건) — 막다른 화면 금지 카피(작성 유도는 예약현황 진입점이 담당).
        <View style={styles.noticeBox}>
          <ThemedText type="bodySm" themeColor="textSecondary">
            아직 후기가 없어요. 첫 후기를 남겨보세요.
          </ThemedText>
        </View>
      ) : (
        <View style={styles.list}>
          {data.map((review) => (
            <ReviewItem key={review.id} review={review} />
          ))}
          {hasNextPage ? (
            <Pressable
              onPress={() => {
                if (!isFetchingNextPage) void fetchNextPage();
              }}
              disabled={isFetchingNextPage}
              accessibilityRole="button"
              style={styles.moreButton}
            >
              <ThemedText type="label" themeColor="cardForeground">
                {isFetchingNextPage ? '불러오는 중…' : '후기 더 보기'}
              </ThemedText>
            </Pressable>
          ) : null}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: Spacing[3] },
  list: { gap: Spacing[2] },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing[2],
  },
  bold: { fontWeight: '600' },
  card: {
    gap: Spacing[2],
    padding: Spacing[4],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
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
    backgroundColor: Colors.light.backgroundElement,
  },
  noticeBox: {
    padding: Spacing[4],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.backgroundElement,
  },
  skeleton: {
    height: 80,
    borderRadius: Radius.lg,
    backgroundColor: Colors.light.backgroundElement,
  },
  moreButton: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
});
