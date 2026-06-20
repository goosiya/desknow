import { useState } from "react";
import { FlatList, Pressable, StyleSheet, TextInput, View } from "react-native";

import { NetworkNotice } from "@/components/NetworkNotice";
import { ThemedText } from "@/components/themed-text";
import { Colors, Radius, Spacing } from "@/constants/theme";
import { useOnlineStatus } from "@/lib/useOnlineStatus";
import { InfoCard } from "@/features/list/ListStates";
import { StarRating } from "@/features/detail/StarRating";
import type { ReviewListItem } from "@/lib/api-client";

import { formatDate } from "./format";
import { useProviderReviews, useReplyToReview } from "./useProviderReviews";

// provider 후기 보기 + 답글 — 웹 ProviderReviews.tsx RN 포팅 (Story 9.3 — AC3). 내 스터디룸 후기를
// 보고 답글을 단다. 답글이 이미 있으면 "사장님 답글" read-only(9.2 ReviewSection 답글 렌더와 일관),
// 없으면 작성 폼. 후기 키는 룸 상세와 공유(roomReviewsKey) — 작성 후 양쪽 갱신. 별점은 9.2 StarRating.

/** 답글 작성 폼 — RN TextInput multiline(웹 textarea 대체)·최대 500자. */
function ReviewReplyForm({ reviewId, roomId }: { reviewId: string; roomId: string }) {
  const reply = useReplyToReview(roomId);
  const [text, setText] = useState("");
  const canSubmit = !reply.isPending && text.trim().length > 0;

  return (
    <View style={styles.form}>
      <TextInput
        value={text}
        onChangeText={setText}
        multiline
        maxLength={500}
        placeholder="답글을 남겨보세요(최대 500자)"
        placeholderTextColor={Colors.light.textSecondary}
        accessibilityLabel="답글 입력"
        style={styles.input}
      />
      <View style={styles.formActions}>
        <Pressable
          onPress={() => reply.mutate({ reviewId, text: text.trim() })}
          disabled={!canSubmit}
          accessibilityRole="button"
          style={[styles.primaryButton, !canSubmit && styles.disabled]}
        >
          <ThemedText type="label" themeColor="primaryForeground">
            {reply.isPending ? "등록 중…" : "답글 등록"}
          </ThemedText>
        </Pressable>
        {reply.isError ? (
          <ThemedText type="bodySm" themeColor="destructive">
            등록에 실패했어요.
          </ThemedText>
        ) : null}
      </View>
    </View>
  );
}

/** 후기 한 건 — 별점 + 작성일 + 텍스트 + (있으면) 사장님 답글 read-only / (없으면) 작성 폼. */
function ReviewCard({ review, roomId }: { review: ReviewListItem; roomId: string }) {
  return (
    <View style={styles.card}>
      <View style={styles.rowBetween}>
        <StarRating rating={review.rating} />
        <ThemedText type="caption" themeColor="textSecondary">
          {formatDate(review.created_at)}
        </ThemedText>
      </View>
      <ThemedText type="bodySm" themeColor="cardForeground">
        {review.text}
      </ThemedText>

      {review.reply ? (
        // 이미 답글 있음 — read-only(9.2 ReviewSection 답글 렌더와 일관).
        <View style={styles.reply}>
          <ThemedText type="caption" themeColor="text" style={styles.bold}>
            사장님 답글
          </ThemedText>
          <ThemedText type="bodySm" themeColor="cardForeground">
            {review.reply.text}
          </ThemedText>
        </View>
      ) : (
        <ReviewReplyForm reviewId={review.id} roomId={roomId} />
      )}
    </View>
  );
}

/** 화면 헤더(제목 + 설명). */
function Header() {
  return (
    <View style={styles.header}>
      <ThemedText type="h2" themeColor="text">
        후기
      </ThemedText>
      <ThemedText type="bodySm" themeColor="textSecondary">
        내 스터디룸에 달린 후기를 보고 답글을 남길 수 있어요.
      </ThemedText>
    </View>
  );
}

export function ProviderReviews() {
  const {
    roomId,
    hasRoom,
    isLoading,
    isError,
    reviews,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useProviderReviews();
  const isOnline = useOnlineStatus();

  if (!isOnline && reviews.length === 0) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <NetworkNotice />
      </View>
    );
  }

  if (isLoading) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <ThemedText type="bodySm" themeColor="textSecondary">
          불러오는 중…
        </ThemedText>
      </View>
    );
  }

  if (isError) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <ThemedText type="bodySm" themeColor="destructive">
          후기를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.
        </ThemedText>
      </View>
    );
  }

  if (!hasRoom) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <InfoCard text="먼저 스터디룸을 등록하면 후기를 받을 수 있어요." />
      </View>
    );
  }

  if (reviews.length === 0) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <InfoCard text="아직 후기가 없어요." />
      </View>
    );
  }

  return (
    <FlatList
      data={reviews}
      keyExtractor={(r) => r.id}
      renderItem={({ item }) => <ReviewCard review={item} roomId={roomId} />}
      ListHeaderComponent={
        <View>
          <Header />
          {!isOnline ? <NetworkNotice style={styles.notice} /> : null}
        </View>
      }
      contentContainerStyle={styles.listContent}
      keyboardShouldPersistTaps="handled"
      onEndReachedThreshold={0.5}
      onEndReached={() => {
        if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
      }}
      ListFooterComponent={
        isFetchingNextPage ? (
          <ThemedText type="bodySm" themeColor="textSecondary" style={styles.footer}>
            불러오는 중…
          </ThemedText>
        ) : null
      }
    />
  );
}

const styles = StyleSheet.create({
  stateWrap: { gap: Spacing[3] },
  header: { gap: Spacing[1] },
  listContent: { gap: Spacing[2], paddingBottom: Spacing[6] },
  notice: { marginTop: Spacing[2] },
  footer: { textAlign: "center", paddingVertical: Spacing[3] },
  card: {
    gap: Spacing[3],
    padding: Spacing[4],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  rowBetween: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: Spacing[2],
  },
  bold: { fontWeight: "600" },
  reply: {
    gap: Spacing[1],
    marginLeft: Spacing[3],
    paddingVertical: Spacing[2],
    paddingLeft: Spacing[3],
    paddingRight: Spacing[2],
    borderLeftWidth: 2,
    borderLeftColor: Colors.light.primary,
    borderRadius: Radius.md,
    // "사장님 답글" 박스 틴트 = secondary(만다린 복숭아빛) — 웹 PREV-2 정본(기존 베이지/회색에서 정정).
    backgroundColor: Colors.light.secondary,
  },
  form: { gap: Spacing[2] },
  input: {
    minHeight: 64,
    borderWidth: 1,
    borderColor: Colors.light.border,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
    fontSize: 14,
    lineHeight: 22,
    color: Colors.light.cardForeground,
    backgroundColor: Colors.light.background,
    textAlignVertical: "top",
  },
  formActions: { flexDirection: "row", alignItems: "center", gap: Spacing[2] },
  primaryButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  disabled: { opacity: 0.5 },
});
