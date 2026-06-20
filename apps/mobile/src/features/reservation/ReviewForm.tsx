import { useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

import { isReservationNotCompleted, isReviewAlreadyExists } from './errors';
import { useCreateReview } from './useCreateReview';

// 후기 작성 폼 — 웹 reservation/ReviewForm.tsx RN 포팅 (Story 9.2 — AC5 · review-accessibility L61).
// 예약현황의 이용 완료·미작성 행에서 별점 + 텍스트 후기를 작성한다.
//
// ⚠️ a11y: 별점 = Pressable 별 5개(각 별 accessibilityLabel "별점 N점") · 텍스트 = maxLength 500 +
//    글자수 카운터 "{n}/500" · 에러 = 텍스트 안내(색 단독 금지). set-state-in-effect 금지(별점·텍스트
//    =로컬 state, 제출=탭 이벤트).
// ⚠️ 막다른 화면 금지: 409(이용 완료 안 됨/이미 작성)·기타 실패는 friendly 카피(코드 미노출 — 분기에만).

/** 후기 텍스트 최대 길이 — 백엔드 스키마(REVIEW_TEXT_MAX_LENGTH)와 정합(500). */
const TEXT_MAX_LENGTH = 500;

/** 후기 작성 실패 시 화면 카피(코드/숫자 미노출 — UX-DR10, detail.code 는 분기에만). */
function errorCopy(error: unknown): string {
  if (isReviewAlreadyExists(error)) {
    return '이미 후기를 남기셨어요.';
  }
  if (isReservationNotCompleted(error)) {
    return '아직 이용 완료 전이라 후기를 남길 수 없어요.';
  }
  return '후기를 남기지 못했어요. 잠시 후 다시 시도해 주세요.';
}

export function ReviewForm({
  reservationId,
  roomId,
}: {
  reservationId: string;
  roomId: string;
}) {
  const create = useCreateReview();
  const [rating, setRating] = useState(0); // 0 = 미선택
  const [text, setText] = useState('');

  // 제출 가능 = 별점 선택됨 + 텍스트 공백 아님 + 진행 중 아님(render-time 파생 — effect 아님).
  const trimmed = text.trim();
  const canSubmit = rating >= 1 && trimmed.length > 0 && !create.isPending;

  function handleSubmit() {
    if (!canSubmit) return; // 방어(버튼 disabled와 이중)
    create.mutate({ reservationId, roomId, rating, text: trimmed });
  }

  return (
    <View style={styles.wrap}>
      <ThemedText type="bodySm" themeColor="cardForeground" style={styles.bold}>
        이용은 어떠셨어요? 짧게 후기를 남겨주세요.
      </ThemedText>

      {/* ── 별점 입력(Pressable 별 5개 — a11y "별점 N점") ── */}
      <View style={styles.stars} accessibilityRole="radiogroup" accessibilityLabel="별점">
        {[1, 2, 3, 4, 5].map((n) => (
          <Pressable
            key={n}
            onPress={() => setRating(n)}
            accessibilityRole="radio"
            accessibilityLabel={`별점 ${n}점`}
            accessibilityState={{ selected: rating === n }}
            style={styles.starButton}
          >
            <ThemedText type="h2" themeColor={n <= rating ? 'primary' : 'border'}>
              {n <= rating ? '★' : '☆'}
            </ThemedText>
          </Pressable>
        ))}
      </View>

      {/* ── 텍스트 입력(maxLength 500 + 글자수 카운터) ── */}
      <View style={styles.field}>
        <TextInput
          value={text}
          onChangeText={(v) => setText(v.slice(0, TEXT_MAX_LENGTH))}
          maxLength={TEXT_MAX_LENGTH}
          multiline
          numberOfLines={3}
          accessibilityLabel="후기 내용"
          placeholder="공간은 어땠는지 다른 분께 알려주세요."
          placeholderTextColor={Colors.light.textSecondary}
          style={styles.input}
        />
        <ThemedText type="caption" themeColor="textSecondary" style={styles.counter}>
          {text.length}/{TEXT_MAX_LENGTH}
        </ThemedText>
      </View>

      {/* ── 에러 안내(텍스트 — 색 단독 금지) ── */}
      {create.isError ? (
        <ThemedText accessibilityRole="alert" type="caption" themeColor="destructive">
          {errorCopy(create.error)}
        </ThemedText>
      ) : null}

      <Pressable
        onPress={handleSubmit}
        disabled={!canSubmit}
        accessibilityRole="button"
        accessibilityState={{ disabled: !canSubmit }}
        style={[styles.submit, !canSubmit && styles.disabled]}
      >
        <ThemedText type="label" themeColor="primaryForeground">
          {create.isPending ? '남기는 중…' : '후기 남기기'}
        </ThemedText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: Spacing[3],
    padding: Spacing[3],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.backgroundElement,
  },
  bold: { fontWeight: '600' },
  stars: { flexDirection: 'row', gap: Spacing[1] },
  starButton: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  field: { gap: Spacing[1] },
  input: {
    minHeight: 72,
    padding: Spacing[2],
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
    color: Colors.light.cardForeground,
    textAlignVertical: 'top',
    fontSize: 14,
    lineHeight: 22,
  },
  counter: { alignSelf: 'flex-end' },
  submit: {
    minHeight: 44,
    alignSelf: 'flex-start',
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  disabled: { opacity: 0.5 },
});
