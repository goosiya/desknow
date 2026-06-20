import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClientProvider } from '@tanstack/react-query';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import { AppHeader } from '@/components/AppHeader';
import { ChatbotFabSlot } from '@/components/ChatbotFabSlot';
import { InAppBannerSlot } from '@/components/InAppBannerSlot';
import { SessionKeeper } from '@/features/auth/SessionKeeper';
import { SESSION_QUERY_KEY, fetchSession } from '@/features/auth/useSession';
import { createQueryClient } from '@/lib/query-client';
import { getAccessToken } from '@/lib/session-store';

// DeskNow 는 라이트 전용(AC2) — DarkTheme 분기 없이 라이트로 고정한다.
// 9.1: 프로바이더 스택(제스처 루트·SafeArea·QueryClient)을 두르고, 루트 네비게이터를 Stack 으로
// 둔다. 1급 진입 3탭은 `(tabs)` 그룹(NativeTabs)이고, 인증/상세 화면(login·signup·rooms/[id]·
// provider/room)은 그 위로 push 되는 Stack 화면이다(NativeTabs는 비-탭 라우트를 표시할 수 없음).
// 부팅 시 secure-store 토큰이 있으면 세션을 복원한다(웹은 쿠키 자동 복원이지만 모바일은 명시
// 부트스트랩). 전역 오버레이 슬롯(인앱 배너·챗봇 FAB)은 기존 Z-순서를 보존한다(현 9.1은 no-op).
export default function RootLayout() {
  // QueryClient 는 앱 생애주기 1개(리렌더에도 동일 인스턴스 — 캐시 보존).
  const [queryClient] = useState(createQueryClient);

  // 부팅 세션 복원: 토큰이 있으면 authMe(인터셉터가 Bearer 주입)로 ["auth","me"]를 prefetch 한다.
  // 토큰이 없으면 아무 것도 안 한다(useSession 이 마운트 시 authMe→401→null 로 미로그인 확정).
  useEffect(() => {
    let active = true;
    (async () => {
      const token = await getAccessToken();
      if (!active || !token) return;
      void queryClient.prefetchQuery({
        queryKey: SESSION_QUERY_KEY,
        queryFn: fetchSession,
      });
    })();
    return () => {
      active = false;
    };
  }, [queryClient]);

  // E2E 세션주입 하니스(AC7) — 개발 + 게이트 ON 일 때만. 프로덕션(!__DEV__)에선 이 분기가 빌드타임
  // 상수 dead-code 제거로 사라져 e2e-session 모듈이 번들에 포함되지 않는다(주입 심볼 부재 보장).
  useEffect(() => {
    if (__DEV__ && process.env.EXPO_PUBLIC_E2E_ENABLED === '1') {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { installE2ESessionHarness } = require('@/lib/e2e-session');
      installE2ESessionHarness(queryClient);
    }
  }, [queryClient]);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider value={DefaultTheme}>
            {/* 세션 슬라이딩 연장 + 만료 안내/리다이렉트 — QueryClient 안에서 useSession 구독·null 렌더. */}
            <SessionKeeper />
            {/* 글로벌 셸(9.4 AC1·SYS-1): 영속 헤더를 Stack 위에 흐름 배치(웹 AppShell 미러 — 전 화면
                상단 헤더). 헤더가 top 안전영역을 소비하므로 각 화면은 edges에서 'top'을 뺀다. */}
            <View style={styles.shell}>
              <AppHeader />
              <View style={styles.body}>
                <Stack screenOptions={{ headerShown: false }} />
              </View>
            </View>
            {/* 절대 오버레이 — 헤더/콘텐츠 위로 그려지도록 셸 뒤에 둔다(스플래시는 부팅 시 헤더까지 덮음). */}
            <AnimatedSplashOverlay />
            <InAppBannerSlot />
            <ChatbotFabSlot />
          </ThemeProvider>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  shell: { flex: 1 },
  body: { flex: 1 },
});
