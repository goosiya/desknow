import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

import { shareReservation } from './shareReservation';

// 예약 공유 버튼 — 웹 KakaoShareButton RN 포팅 (Story 9.2 — AC7 · 범위 결정 #3). 확정 예약을 한 번의
// 탭으로 OS 공유 시트에 올린다. 즉시예약 성공 배너(ReservationPanel) + 예약현황 행(ReservationRow)
// 두 진입점이 같은 컴포넌트를 쓴다(추가 API 조회 0 — 공유 데이터는 호출처가 이미 보유한 필드에서 합성).
//
// ⚠️ graceful degrade(AC7): 공유 실패는 친근한 안내(role=status) + 로컬 state로 처리하고 throw를
//    전파하지 않는다(예약 행/화면 크래시 금지 — 웹 KakaoShareButton AC4 동형).
// ⚠️ set-state-in-effect 금지: 공유는 **탭 이벤트**에서 호출(effect 아님)·실패 state도 핸들러에서만 갱신.
// ⚠️ 색 단독 금지: 버튼 = 공유 아이콘 + 가시 텍스트("공유") + a11y 라벨("카카오톡으로 공유"). tap-target(≥44px).

// 공유 아이콘 — 웹 KakaoShareButton의 lucide Share2(점 3개 + 연결선 2개) 등가를 순수 RN View로 그린다
// (신규 의존성 0 — ChatbotFabSlot가 lucide를 View로 그린 선례). 16px 박스에 채움 점 3개 + 회전 막대 2개.
function ShareIcon() {
  return (
    <View style={styles.icon}>
      <View style={[styles.iconLine, styles.iconLineTop]} />
      <View style={[styles.iconLine, styles.iconLineBottom]} />
      <View style={[styles.iconDot, styles.iconDotA]} />
      <View style={[styles.iconDot, styles.iconDotB]} />
      <View style={[styles.iconDot, styles.iconDotC]} />
    </View>
  );
}

export function ShareButton({
  roomName,
  slotStarts,
  roomId,
}: {
  roomName: string;
  slotStarts: string[];
  roomId: string;
}) {
  // 공유 실패 안내 표시 여부(로컬 — 탭 핸들러에서만 갱신). 진행 중 이중 탭은 isSharing 가드.
  const [failed, setFailed] = useState(false);
  const [isSharing, setIsSharing] = useState(false);

  async function handleShare() {
    if (isSharing) return;
    setIsSharing(true);
    setFailed(false);
    try {
      await shareReservation({ roomName, slotStarts, roomId });
    } catch {
      // AC7 — 조용한 실패 금지: 친근한 안내(throw 전파 금지·예약 행 크래시 금지).
      setFailed(true);
    } finally {
      setIsSharing(false);
    }
  }

  return (
    <View style={styles.wrapper}>
      <Pressable
        onPress={handleShare}
        disabled={isSharing}
        accessibilityRole="button"
        accessibilityLabel="카카오톡으로 공유"
        accessibilityState={{ disabled: isSharing }}
        style={[styles.button, isSharing && styles.buttonDisabled]}
      >
        <ShareIcon />
        <ThemedText type="label" themeColor="cardForeground">
          공유
        </ThemedText>
      </Pressable>
      {failed ? (
        // 절대배치(흐름 밖) — 버튼 행 높이를 안 늘려 형제 취소 버튼이 안 밀리고 카드 안에 머문다
        // (즐겨찾기 안내 팝오버와 동일 패턴). 왼쪽으로 열어 본문 위에 겹친다(좁은 카드 밖으로 안 넘침).
        <View accessibilityRole="alert" style={styles.failHint}>
          <ThemedText type="caption" themeColor="textSecondary">
            지금은 공유를 할 수 없어요. 잠시 후 다시 해주세요.
          </ThemedText>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { alignItems: 'flex-start', gap: Spacing[1] },
  button: {
    flexDirection: 'row',
    gap: Spacing[1],
    minHeight: 44,
    paddingHorizontal: Spacing[3],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  buttonDisabled: { opacity: 0.5 },
  // 공유 실패 안내 — 절대배치(왼쪽·상단정렬). 흐름 밖이라 버튼 행을 안 늘리고, 본문 위에 겹쳐 카드
  // 안에 머문다(즐겨찾기 hintLeft 동형). 좁은 카드 밖으로 넘치지 않게 폭 고정.
  failHint: {
    position: 'absolute',
    right: '100%',
    top: 0,
    marginRight: Spacing[1],
    width: 180,
    zIndex: 50,
    padding: Spacing[2],
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  // 공유 아이콘(Share2 등가) — 16px 박스 좌표는 lucide 24그리드를 16으로 스케일한 값(점 r2, 선 2획).
  icon: { width: 16, height: 16, position: 'relative' },
  iconDot: {
    position: 'absolute',
    width: 4.5,
    height: 4.5,
    borderRadius: 2.25,
    backgroundColor: Colors.light.cardForeground,
  },
  iconDotA: { top: 1, left: 9.75 },
  iconDotB: { top: 5.75, left: 1.75 },
  iconDotC: { top: 10.4, left: 9.75 },
  iconLine: {
    position: 'absolute',
    width: 5.3,
    height: 1.5,
    borderRadius: 1,
    backgroundColor: Colors.light.cardForeground,
  },
  iconLineTop: { top: 4.9, left: 5.4, transform: [{ rotate: '-30deg' }] },
  iconLineBottom: { top: 9.6, left: 5.4, transform: [{ rotate: '30deg' }] },
});
