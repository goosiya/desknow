"use client";

// 플로팅 챗봇 "룸메이트" FAB + 대화 패널 (Story 7.3 — AC1·AC4·AC5).
// (Story 1.6 placeholder 교체: 스타일·위치·z-30·a11y 하한선은 보존하고 onClick 만 실동작으로.)
//
// AppShell 직속에 영속 마운트되므로(App Router layout 은 네비게이션 간 리마운트 안 됨) 패널 오픈
// 상태·대화 맥락이 화면 이동을 가로질러 보존된다(AC4). vaul Drawer.Trigger 로 FAB 를 감싸 Esc/
// 오버레이 닫기 시 포커스가 FAB 로 복귀한다(Radix 상속, AC2). 로그아웃 시 useChatbot 이 패널을
// 닫는다(onSessionEnd, AC5). 웹 전용 — 모바일은 인증/화면 전제 부재로 dev-build 버킷(Task 12).
import { useState } from "react";
import { MessageCircle } from "lucide-react";
import { Drawer } from "vaul";

import { ChatbotPanel } from "@/features/chatbot/ChatbotPanel";
import { useDeviceId } from "@/features/chatbot/deviceId";
import { useChatbot } from "@/features/chatbot/useChatbot";

export function ChatbotFabSlot() {
  const [open, setOpen] = useState(false);
  const deviceId = useDeviceId();
  // 로그아웃 전이 시 패널을 닫는다(AC5 — useChatbot 이 캐시 제거 + 서버 thread 폐기 동반).
  const chatbot = useChatbot({ deviceId, onSessionEnd: () => setOpen(false) });

  return (
    <Drawer.Root open={open} onOpenChange={setOpen}>
      <Drawer.Trigger asChild>
        <button
          type="button"
          aria-label="룸메이트 챗봇 열기"
          // FAB은 뷰포트 우측 끝이 아니라 중앙 콘텐츠 컬럼(max-w-6xl=72rem) 우측 안쪽에 정렬한다 —
          // 와이드 모니터에서 콘텐츠와 동떨어져 "화면 밖"처럼 보이던 문제 수정. 좁은 화면(≤72rem)은
          // max()가 1.5rem로 떨어져 기존과 동일. (계산: 콘텐츠 우측 여백 50vw-36rem + 인셋 1.5rem)
          className="fixed bottom-20 right-4 z-30 flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-fab transition-transform hover:scale-105 md:bottom-6 md:right-[max(1.5rem,calc(50vw_-_36rem_+_1.5rem))]"
        >
          <MessageCircle className="size-6" aria-hidden />
        </button>
      </Drawer.Trigger>
      <ChatbotPanel chatbot={chatbot} open={open} />
    </Drawer.Root>
  );
}
