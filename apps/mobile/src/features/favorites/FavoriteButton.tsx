import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { router, type Href } from 'expo-router';

import { useSession } from '@/features/auth/useSession';
import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

import { useFavoriteIds, useToggleFavorite } from './useFavorites';

// 공유 즐겨찾기 하트 — 웹 FavoriteButton RN 포팅 (Story 9.1 — AC4). 바텀시트·목록·즐겨찾기 페이지가
// 같은 컴포넌트로 토글을 배선한다.
//
// ⚠️ 색 단독 금지: 채움(♥)/외곽선(♡) 형태 + 색 + a11y selected 3중 신호.
// ⚠️ 미로그인 게이팅(AC4): 하트는 보이되 클릭 시 토글하지 않고 "로그인하면 저장돼요" 안내(옵티미스틱
//    호출 안 함). 막다른 화면 금지 — 안내에 로그인 링크 + 닫기를 둔다.
// hintPlacement: 안내 팝오버 배치. 기본 "below"(하트 아래 — 시트/상세). 목록 카드는 높이가 짧아
// 아래로 열면 카드 밖으로 넘치므로 "left"(하트 왼쪽·수직중앙 — 카드 안)로 연다.
export function FavoriteButton({
  roomId,
  hintPlacement = 'below',
}: {
  roomId: string;
  hintPlacement?: 'below' | 'left';
}) {
  const { data: user, isError: sessionError } = useSession();
  const isLoggedIn = !!user;
  const { data: favoriteIds } = useFavoriteIds();
  const isFavorited = favoriteIds?.has(roomId) ?? false;
  const toggle = useToggleFavorite();
  const [showLoginHint, setShowLoginHint] = useState(false);

  // 로그인되면 잔존 hint 초기화("렌더 중 파생 상태 조정" — 미로그인 클릭으로 켜둔 뒤 로그인하면 세션이
  // 다시 null로 깜빡일 때 유령 재노출 방지).
  const [prevLoggedIn, setPrevLoggedIn] = useState(isLoggedIn);
  if (prevLoggedIn !== isLoggedIn) {
    setPrevLoggedIn(isLoggedIn);
    if (isLoggedIn && showLoginHint) setShowLoginHint(false);
  }

  function handleClick() {
    if (!roomId) return; // 빈 roomId 방어(닫히는 시트 등 — 유령 토글/422 방지)
    if (sessionError) return; // 세션 판별 실패 — 미로그인 오인 금지(상위 화면이 안내)
    if (!isLoggedIn) {
      setShowLoginHint(true); // AC4: 토글 대신 로그인 유도(옵티미스틱 호출 안 함)
      return;
    }
    toggle.mutate({ roomId, next: !isFavorited });
  }

  return (
    <View style={styles.wrapper}>
      <Pressable
        onPress={handleClick}
        accessibilityRole="button"
        accessibilityState={{ selected: isFavorited }}
        accessibilityLabel={isFavorited ? '즐겨찾기 해제' : '즐겨찾기 추가'}
        style={styles.button}
      >
        <ThemedText
          type="h3"
          themeColor={isFavorited ? 'destructive' : 'textSecondary'}
        >
          {isFavorited ? '♥' : '♡'}
        </ThemedText>
      </Pressable>

      {showLoginHint && !isLoggedIn ? (
        <View
          accessibilityRole="alert"
          style={[styles.hint, hintPlacement === 'left' && styles.hintLeft]}
        >
          <ThemedText type="bodySm" themeColor="cardForeground">
            로그인하면 저장돼요.
          </ThemedText>
          <View style={styles.hintActions}>
            <Pressable
              onPress={() => {
                setShowLoginHint(false);
                router.push('/login' as Href);
              }}
              accessibilityRole="link"
              accessibilityLabel="로그인"
            >
              <ThemedText type="label" themeColor="primary">
                로그인
              </ThemedText>
            </Pressable>
            <Pressable
              onPress={() => setShowLoginHint(false)}
              accessibilityRole="button"
              accessibilityLabel="닫기"
            >
              <ThemedText type="label" themeColor="textSecondary">
                닫기
              </ThemedText>
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { position: 'relative' },
  button: {
    minWidth: 44,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
  },
  hint: {
    position: 'absolute',
    top: '100%',
    right: 0,
    zIndex: 50,
    width: 200,
    gap: Spacing[2],
    padding: Spacing[3],
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  // 목록 전용: 하트 왼쪽·수직중앙으로 연다(카드 안). top/right를 덮어쓰고 transform으로 세로 중앙.
  // (하트가 카드 세로중앙이라, 팝오버를 하트 중앙에 맞추면 카드 안에 들어온다.)
  hintLeft: {
    top: '50%',
    right: '100%',
    marginRight: Spacing[1],
    transform: [{ translateY: -36 }],
  },
  hintActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing[4],
  },
});
