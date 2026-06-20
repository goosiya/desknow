import {
  Tabs,
  TabList,
  TabTrigger,
  TabSlot,
  TabTriggerSlotProps,
  TabListProps,
} from 'expo-router/ui';
import type { Href } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from './themed-text';

import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';
import { useSession } from '@/features/auth/useSession';

const c = Colors.light;

// 웹(react-native-web) 변형 — 역할조건부 1급 네비 (Story 1.6 AC4 → 9.3 AC5·§범위 4). 웹 AppNav의
// PROVIDER_NAV↔BOOKER_NAV 스왑 미러: provider면 운영 메뉴(예약자 현황·후기·내 스터디룸), 그 외(로딩·
// 미로그인·booker)는 예약자 메뉴(찾기·예약현황·즐겨찾기). **6개 라우트를 항상 등록**(TabTrigger가 곧
// 라우트 정의 — TabSlot이 어떤 역할에서도 렌더 가능·pendingSignup이 /provider/room으로 가도 navigable)
// 하고, 비활성 역할 버튼만 display:none으로 숨긴다(라우트 등록은 유지·바만 스왑).
export default function AppTabs() {
  const { data: session } = useSession();
  const isProvider = session?.role === 'provider';
  return (
    <Tabs>
      <TabSlot style={{ height: '100%' }} />
      <TabList asChild>
        <CustomTabList>
          <TabTrigger name="index" href="/" asChild>
            <TabButton hidden={isProvider}>스터디룸 찾기</TabButton>
          </TabTrigger>
          <TabTrigger name="reservations" href="/reservations" asChild>
            <TabButton hidden={isProvider}>예약현황</TabButton>
          </TabTrigger>
          <TabTrigger name="favorites" href="/favorites" asChild>
            <TabButton hidden={isProvider}>즐겨찾기</TabButton>
          </TabTrigger>
          {/* provider 순서 = 웹 PROVIDER_NAV와 동일 [내 스터디룸, 예약자 현황, 후기](9.4 SYS-4). */}
          <TabTrigger name="provider/room" href={"/provider/room" as Href} asChild>
            <TabButton hidden={!isProvider}>내 스터디룸</TabButton>
          </TabTrigger>
          <TabTrigger name="provider/reservations" href={"/provider/reservations" as Href} asChild>
            <TabButton hidden={!isProvider}>예약자 현황</TabButton>
          </TabTrigger>
          <TabTrigger name="provider/reviews" href={"/provider/reviews" as Href} asChild>
            <TabButton hidden={!isProvider}>후기</TabButton>
          </TabTrigger>
        </CustomTabList>
      </TabList>
    </Tabs>
  );
}

function TabButton({
  children,
  isFocused,
  hidden,
  ...props
}: TabTriggerSlotProps & { hidden?: boolean }) {
  return (
    <Pressable
      {...props}
      style={({ pressed }) => [styles.tabButton, hidden && styles.hidden, pressed && styles.pressed]}
    >
      {!hidden ? (
        <ThemedText type="label" themeColor={isFocused ? 'primary' : 'textSecondary'}>
          {children}
        </ThemedText>
      ) : null}
    </Pressable>
  );
}

function CustomTabList(props: TabListProps) {
  return (
    <View style={styles.barContainer}>
      <View style={styles.bar}>{props.children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  barContainer: {
    position: 'absolute',
    bottom: 0,
    width: '100%',
    alignItems: 'center',
    backgroundColor: c.background,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.border,
  },
  bar: {
    flexDirection: 'row',
    width: '100%',
    maxWidth: MaxContentWidth,
    justifyContent: 'space-around',
    paddingVertical: Spacing[2],
  },
  tabButton: {
    minHeight: 44,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing[2],
  },
  // 비활성 역할 버튼 — 라우트 등록은 유지하되 바에서 숨긴다(레이아웃 제외).
  hidden: { display: 'none' },
  pressed: {
    opacity: 0.7,
  },
});
