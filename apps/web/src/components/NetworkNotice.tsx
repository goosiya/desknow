// 네트워크 단절 표시 (Story 3.8 — AC1·AC2·AC3). 공유 단절 배너.
//
// cross-feature 표시라 features 밖 components 직하에 둔다(지도·목록·즐겨찾기 공용). 토스트
// 라이브러리(sonner 등) 미도입 — 매트릭스의 "토스트"는 자동 소멸 위젯이 아니라 **단절 동안
// 떠 있다가 연결되면 사라지는 인라인 배너**로 충족한다(확정② — 상태가 곧 표시). 카피·a11y·
// 토큰만 책임지고, 배치는 className prop 으로 오버라이드한다(지도=상단 떠 있는 배너, 목록/
// 즐겨찾기=목록 상단 인라인).
//
// `role="status"` + `aria-live="polite"` 로 스크린리더에 단절을 공지한다(NFR-5). 카피는 확정
// 문구 고정(확정① — "오프라인" 금지, 로그인/네트워크 모호성 회피). 토큰만 사용(하드코딩 색/
// 픽셀 0) — MapView 위치 거부 배너의 secondary 토큰을 미러한다.
import { cn } from "@/lib/utils";

type NetworkNoticeProps = {
  /** 배치 오버라이드(지도=절대 배치 상단, 목록=인라인 상단 등). 토큰·a11y 는 컴포넌트가 고정. */
  className?: string;
};

export function NetworkNotice({ className }: NetworkNoticeProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "rounded-md border border-border bg-secondary px-4 py-2 text-sm leading-[1.6] text-secondary-foreground",
        className,
      )}
    >
      네트워크 연결이 끊겼어요. 연결되면 다시 보여드릴게요.
    </div>
  );
}
