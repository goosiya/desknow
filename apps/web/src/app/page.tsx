import { Suspense } from "react";

import { OnboardingOverlay } from "@/components/OnboardingOverlay";
import { ExploreView } from "@/features/list/ExploreView";

// 스터디룸 찾기 — 첫 진입 탐색 화면 (Story 3.2 지도 → 3.4 지도/목록 토글). `/` 가 진입점이다.
// 3.4: MapView 단독을 ExploreView(지도/목록 토글 + 지역 콤보 목록)로 교체했다(헤더 유지).
// 3.9: 첫 방문 온보딩 오버레이를 ExploreView 형제로 얹는다(Radix Portal 로 body 에 떠 탐색 트리와
//      독립 — ExploreView 내부 무변경). 서버 컴포넌트가 클라 자식을 렌더하는 것은 정상.
// ExploreView/OnboardingOverlay 는 클라이언트 컴포넌트('use client'); 이 페이지는 서버 컴포넌트로 셸만 제공한다.
export default function Home() {
  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">
          내 주변 스터디룸
        </h1>
        <p className="text-sm leading-[1.6] text-muted-foreground">
          지금 비어 있는 곳을 지도나 목록에서 한눈에 확인하고 바로 예약하세요.
        </p>
      </section>
      {/* ExploreView 는 useSearchParams(딥링크 ?view=list&sigungu=) 를 읽으므로 Suspense 경계가
          필요하다(App Router CSR bailout 가드 — LoginView 선례). */}
      <Suspense fallback={null}>
        <ExploreView />
      </Suspense>
      <OnboardingOverlay />
    </div>
  );
}
