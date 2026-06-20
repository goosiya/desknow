import { Image, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, type Href } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { Colors, Spacing } from '@/constants/theme';
import { useLogout } from '@/features/auth/useAuth';
import { useSession } from '@/features/auth/useSession';

// 글로벌 앱 헤더 (Story 9.4 — AC1·SYS-1). 웹 AppShell 헤더(apps/web/.../shell/AppShell.tsx:18-31 +
// HeaderAuth.tsx) 미러: 좌 "DeskNow" 브랜드 + 우 인증 컨트롤. 웹은 루트 layout이 모든 페이지를
// AppShell로 감싸 인증화면 포함 전 화면에 헤더가 뜨므로(웹=정본), 모바일도 루트 _layout에서
// Stack 위에 영속 마운트해 전 화면 상단에 노출한다. top 안전영역은 이 헤더가 소비하므로 각 화면은
// SafeAreaView edges에서 'top'을 뺀다(이중 패딩 방지). 상단 내비(웹 md+ AppNav)는 모바일 sm
// 뷰포트에선 웹도 숨기므로(hidden md:flex) 모바일 헤더에도 두지 않는다.
const c = Colors.light;

/** 헤더 콘텐츠 높이(top 인셋 제외) — 배너 슬롯이 헤더 아래로 내려오도록 오프셋에 재사용. */
export const HEADER_CONTENT_HEIGHT = 56;

function HeaderAuth() {
  const router = useRouter();
  const { data: user, isLoading, isError } = useSession();
  const logout = useLogout();

  // 세션 판별 중/실패/미로그인 — "로그인"으로 안전 폴백(사용자 정보 미노출, 로그아웃 오인 방지).
  if (isLoading || isError || !user) {
    return (
      <Pressable
        accessibilityRole="link"
        accessibilityLabel="로그인"
        hitSlop={8}
        onPress={() => router.push('/login')}
        style={styles.authAction}
      >
        <ThemedText type="label" themeColor="textSecondary">
          로그인
        </ThemedText>
      </Pressable>
    );
  }

  return (
    <View style={styles.authRow}>
      {/* 본인 이메일 — provider/타인-facing 표면이 아니므로 노출 OK(웹 HeaderAuth 동형). */}
      <ThemedText
        type="bodySm"
        themeColor="textSecondary"
        numberOfLines={1}
        style={styles.email}
      >
        {user.email}
      </ThemedText>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="로그아웃"
        disabled={logout.isPending}
        hitSlop={8}
        onPress={() => logout.mutate()}
        style={[styles.authAction, logout.isPending && styles.disabled]}
      >
        <ThemedText type="label" themeColor="textSecondary">
          {logout.isPending ? '로그아웃 중…' : '로그아웃'}
        </ThemedText>
      </Pressable>
    </View>
  );
}

export function AppHeader() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { data: session } = useSession();
  // DeskNow 탭 = 역할별 홈. ⚠️ provider는 booker 홈('/'=index 탭)이 탭셋에서 hidden 이라
  // router.push('/')가 무반응이다(숨은 탭으로 못 감). provider는 자기 첫 탭(/provider/room=내 스터디룸),
  // 그 외(booker/미로그인)는 '/'(찾기)로 보낸다. navigate=탭 전환(스택 중복 없이). (웹은 항상 '/'지만
  // 모바일 NativeTabs 역할분기 구조상 갈라진다 — KTH 2026-06-20.)
  const homeHref: Href = session?.role === 'provider' ? '/provider/room' : '/';

  return (
    <View style={[styles.header, { paddingTop: insets.top }]}>
      <View style={styles.bar}>
        <Pressable
          accessibilityRole="link"
          accessibilityLabel="DeskNow 홈"
          hitSlop={8}
          onPress={() => router.navigate(homeHref)}
          style={styles.brandHit}
        >
          <View style={styles.brandRow}>
            {/* 브랜드 로고 — 인접 "DeskNow" 텍스트가 접근성 이름 제공(Pressable label=홈). */}
            <Image
              source={require('../../assets/images/desknow_logo.png')}
              style={styles.logo}
              accessibilityIgnoresInvertColors
            />
            <ThemedText type="h3" themeColor="primary" style={styles.brand}>
              DeskNow
            </ThemedText>
          </View>
        </Pressable>
        <HeaderAuth />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    borderBottomWidth: 1,
    borderBottomColor: c.border,
    backgroundColor: c.background,
    zIndex: 30,
  },
  bar: {
    height: HEADER_CONTENT_HEIGHT,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing[4],
    gap: Spacing[2],
  },
  brandHit: { height: 44, justifyContent: 'center' },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing[2] },
  logo: { width: 28, height: 28, resizeMode: 'contain' },
  brand: { fontWeight: '700' },
  authRow: {
    marginLeft: 'auto',
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing[2],
    flexShrink: 1,
  },
  email: { maxWidth: 160, flexShrink: 1 },
  authAction: {
    marginLeft: 'auto',
    height: 44,
    justifyContent: 'center',
    paddingHorizontal: Spacing[2],
  },
  disabled: { opacity: 0.5 },
});
