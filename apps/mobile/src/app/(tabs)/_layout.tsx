import AppTabs from '@/components/app-tabs';

// 탭 그룹 레이아웃 (Story 9.1). 1급 진입 3탭(찾기·예약현황·즐겨찾기)은 NativeTabs가 관리한다.
// login/signup/rooms/provider 등 탭이 아닌 화면은 루트 Stack(app/_layout.tsx)이 탭 위로 push 한다
// (NativeTabs는 비-탭 라우트를 표시할 수 없어, 인증/상세는 Stack 화면으로 분리한다).
export default function TabsLayout() {
  return <AppTabs />;
}
