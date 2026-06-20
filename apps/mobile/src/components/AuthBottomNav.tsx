import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, type Href } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { Colors, Spacing } from '@/constants/theme';
import { useSession } from '@/features/auth/useSession';

// 인증화면(로그인·가입) 하단 탭 바 (Story 9.4 — AC1②·SYS-2 / code-review 2026-06-20 역할 인지 정정).
// 웹은 루트 AppShell이 인증화면도 감싸 AppBottomNav(useNavItems role 분기)를 노출한다(웹=정본). 모바일
// login/signup은 (tabs) 밖 Stack 화면이라 NativeTabs 하단바가 없으므로, 웹 AppBottomNav를 미러한 faux
// 하단탭을 여기서 렌더한다(탭 화면은 NativeTabs가 담당 — 이 컴포넌트는 인증화면 전용).
//
// 역할 분기(웹 AppNav.tsx useNavItems 동형): provider 세션이면 운영 메뉴(내 스터디룸·예약자 현황·후기),
// 그 외(로딩·미로그인·booker)는 예약자 메뉴(찾기·예약현황·즐겨찾기). 인증화면은 보통 로그아웃 상태라
// booker가 기본이나, 로그인된 provider가 인증화면에 재진입해도 웹과 동일하게 운영 메뉴를 본다.
const c = Colors.light;

type NavItem = { href: Href; label: string };

// 웹 AppNav.tsx BOOKER_NAV/PROVIDER_NAV 미러. 라우트는 (tabs) 탭으로 매핑된다.
const BOOKER_NAV: NavItem[] = [
  { href: '/', label: '스터디룸 찾기' },
  { href: '/reservations', label: '예약현황' },
  { href: '/favorites', label: '즐겨찾기' },
];

const PROVIDER_NAV: NavItem[] = [
  { href: '/provider/room', label: '내 스터디룸' },
  { href: '/provider/reservations', label: '예약자 현황' },
  { href: '/provider/reviews', label: '후기' },
];

export function AuthBottomNav() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  // 웹 useNavItems 동형 — provider만 운영 메뉴, 그 외(로딩·미로그인·booker)는 예약자 메뉴.
  const { data: session } = useSession();
  const items = session?.role === 'provider' ? PROVIDER_NAV : BOOKER_NAV;

  return (
    <View
      accessibilityRole="tablist"
      style={[styles.nav, { paddingBottom: insets.bottom }]}
    >
      {items.map((item) => (
        <Pressable
          key={item.label}
          accessibilityRole="link"
          accessibilityLabel={item.label}
          onPress={() => router.push(item.href)}
          style={styles.item}
        >
          <ThemedText type="caption" themeColor="text">
            {item.label}
          </ThemedText>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  nav: {
    flexDirection: 'row',
    borderTopWidth: 1,
    borderTopColor: c.border,
    backgroundColor: c.background,
  },
  item: {
    flex: 1,
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing[1],
    paddingVertical: Spacing[2],
  },
});
