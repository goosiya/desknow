import Image from "next/image";
import Link from "next/link";

import { AppBottomNav, AppNav } from "./AppNav";
import { ChatbotFabSlot } from "./ChatbotFabSlot";
import { HeaderAuth } from "./HeaderAuth";
import { InAppBannerSlot } from "./InAppBannerSlot";

// 사용자 웹 반응형 셸 (Story 1.6 — 골격만, 기능 화면 아님).
// AC4: lg/md 는 헤더 상단 내비, sm 은 하단 내비바로 전환(단일 컬럼).
//      전역 레이어(인앱 배너 슬롯 · 챗봇 FAB)를 Z-순서로 배치한다.
//      (배너 < 콘텐츠 < FAB). 실제 화면/2열 레이아웃은 각 페이지(E3~)가 채운다.
// 내비는 역할별 분기(예약자/제공자)라 client 컴포넌트 AppNav 가 소유한다(provider 웹 표면 구축).

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-full flex-col">
      {/* 헤더 — 브랜드 + 1급 내비(md+) + 로그인 자리 */}
      <header className="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-2 px-4">
          <Link
            href="/"
            className="flex h-11 items-center gap-2 text-lg font-bold text-primary"
          >
            {/* 브랜드 로고 — 텍스트가 접근성 이름을 제공하므로 이미지는 장식(alt="").
                unoptimized: next/image 손실 WebP 최적화(q=75)가 투명 로고 경계에 색 번짐을 만들어,
                원본 PNG를 그대로 내보내 투명도를 보존한다(KTH 2026-06-20). */}
            <Image
              src="/desknow_logo.png"
              alt=""
              width={30}
              height={28}
              priority
              unoptimized
            />
            DeskNow
          </Link>
          {/* 역할별 상단 내비(md+) — 하단바는 헤더 밖 AppBottomNav 가 별도 렌더. */}
          <AppNav />
          {/* 인증 슬롯(미로그인="로그인"→/login · 로그인=이메일+로그아웃). useSession 분기는 client. */}
          <HeaderAuth />
        </div>
      </header>

      {/* 인앱 배너 슬롯 (E5 자리) */}
      <InAppBannerSlot />

      {/* 콘텐츠 영역 — sm 은 하단 내비 높이만큼 하단 여백 확보 */}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 pb-24 md:pb-8">
        {children}
      </main>

      {/* 하단 내비바(sm 전용) — ★헤더 밖에서 렌더(헤더의 backdrop-blur 가 fixed 자식의 컨테이닝
          블록이 되어 bottom-0 이 화면 최상단에 붙던 버그 수정, AppNav 주석 참조). md+ 는 md:hidden. */}
      <AppBottomNav />

      {/* 전역 챗봇 FAB (E7 자리) */}
      <ChatbotFabSlot />
    </div>
  );
}
