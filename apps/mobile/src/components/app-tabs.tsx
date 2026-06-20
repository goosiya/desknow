import { NativeTabs } from 'expo-router/unstable-native-tabs';

import { Colors } from '@/constants/theme';
import { useSession } from '@/features/auth/useSession';

// 역할조건부 1급 네비 (Story 1.6 AC4 → 9.3 AC5·§범위 4). 웹 AppNav의 PROVIDER_NAV↔BOOKER_NAV 스왑
// 미러: provider면 운영 메뉴(예약자 현황·후기·내 스터디룸), 그 외(로딩·미로그인·booker)는 예약자
// 메뉴(찾기·예약현황·즐겨찾기). 6개 라우트를 항상 선언하고 비활성 역할 탭만 `hidden`으로 숨긴다.
// 라이트 고정 토큰 색. 아이콘은 sf(iOS)+md(Android)로 에셋 없이 구성.
export default function AppTabs() {
  const c = Colors.light;
  const { data: session } = useSession();
  const isProvider = session?.role === 'provider';

  return (
    <NativeTabs
      backgroundColor={c.background}
      indicatorColor={c.backgroundElement}
      labelStyle={{ default: { color: c.textSecondary }, selected: { color: c.primary } }}
      iconColor={{ default: c.textSecondary, selected: c.primary }}
    >
      {/* 예약자(booker) 메뉴 — provider일 때 숨김. */}
      <NativeTabs.Trigger name="index" hidden={isProvider}>
        <NativeTabs.Trigger.Label>스터디룸 찾기</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="magnifyingglass" md="search" selectedColor={c.primary} />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="reservations" hidden={isProvider}>
        <NativeTabs.Trigger.Label>예약현황</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="calendar" md="calendar_month" selectedColor={c.primary} />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="favorites" hidden={isProvider}>
        <NativeTabs.Trigger.Label>즐겨찾기</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="heart" md="favorite" selectedColor={c.primary} />
      </NativeTabs.Trigger>

      {/* 제공자(provider) 메뉴 — provider일 때만 노출. 순서는 웹 PROVIDER_NAV와 동일하게
          [내 스터디룸, 예약자 현황, 후기](AppNav.tsx:28-32). 라벨 "내 스터디룸" 유지(9.4 §범위4). */}
      <NativeTabs.Trigger name="provider/room" hidden={!isProvider}>
        <NativeTabs.Trigger.Label>내 스터디룸</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="house" md="home" selectedColor={c.primary} />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="provider/reservations" hidden={!isProvider}>
        <NativeTabs.Trigger.Label>예약자 현황</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="person.2" md="groups" selectedColor={c.primary} />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="provider/reviews" hidden={!isProvider}>
        <NativeTabs.Trigger.Label>후기</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="star" md="star" selectedColor={c.primary} />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
