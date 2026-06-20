"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import { LogoutButton } from "@/features/auth/LogoutButton";
import { useAdminSession } from "@/features/auth/useSession";
import { InAppBannerSlot } from "./InAppBannerSlot";

// 관리자 웹 셸 (Story 1.6 골격 → 8.1 운영 라우트 배선).
// AC4(관리자형): 좌측 사이드바 내비 + 데이터테이블·폼 중심 콘텐츠 영역. 전역 인앱 배너 슬롯은
// 두되 챗봇 FAB는 없음(챗봇은 사용자 표면 — EXPERIENCE). 8.1에서 nav를 실 운영 라우트로 잇고
// active 표시 + 로그아웃을 더한다(usePathname·LogoutButton 때문에 클라이언트 컴포넌트).

const ADMIN_NAV = [
  { href: "/accounts", label: "계정 관리" },
  { href: "/reservations", label: "예약 임의취소" },
  { href: "/ingest", label: "챗봇 인제스트" },
] as const;

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // 운영 nav는 관리자에게만 노출한다 — 비로그인/비-admin(로그인 화면 등)엔 사이드바를 숨긴다.
  // 백엔드 403이 최종 강제(AC2)이고 이 노출 제어는 보조다(아키텍처 L167). 게이트는 페이지별
  // AdminGate가 별도로 강제하므로, 여기선 운영 chrome(nav)의 표면만 가린다.
  const { isAdmin } = useAdminSession();

  return (
    // min-h-[100dvh](=동적 뷰포트 높이): 루트 행 컨테이너를 최소 뷰포트 높이로 잡아, 좌측 사이드바
    // (flex stretch)가 **콘텐츠가 짧아도 뷰포트 바닥까지** 채워지게 한다(KTH 2026-06-19 — 짧은
    // 콘텐츠에서 사이드바 배경이 콘텐츠 높이에 맞춰 잘리던 문제). min-h-full(=100%)은 body 의 확정
    // 높이가 없어 콘텐츠 높이로 떨어졌고, min-h-screen 은 이 Tailwind v4 설정에서 CSS 가 생성되지
    // 않아(arbitrary 값으로 대체) 동작하지 않았다. 콘텐츠가 길면 컨테이너가 그만큼 커지고 사이드바도
    // 함께 늘어난다.
    <div className="flex min-h-[100dvh]">
      {/* 좌측 사이드바 내비 — 관리자에게만 (로그아웃 상태엔 운영 nav 비노출) */}
      {isAdmin && (
        <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-card md:flex">
          <div className="flex h-14 items-center border-b border-border px-4">
            <Link href="/" className="flex h-11 items-center gap-2 text-lg font-bold text-primary">
              <Image src="/desknow_logo.png" alt="" width={30} height={28} priority unoptimized />
              DeskNow <span className="ml-1 text-sm text-muted-foreground">관리자</span>
            </Link>
          </div>
          <nav className="flex flex-col gap-1 p-2" aria-label="관리자 메뉴">
            {ADMIN_NAV.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "inline-flex min-h-11 items-center rounded-md px-3 text-sm font-medium text-foreground hover:bg-muted",
                    active && "bg-muted text-primary"
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </aside>
      )}

      {/* 우측 콘텐츠 — 데이터테이블·폼 중심 */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 상단 바: 모바일 로고(사이드바는 md+) + 로그아웃(로그인 시에만 노출). */}
        <header className="flex h-14 items-center justify-between border-b border-border px-4">
          <Link
            href="/"
            className="flex h-11 items-center gap-2 text-lg font-bold text-primary md:hidden"
          >
            <Image src="/desknow_logo.png" alt="" width={30} height={28} priority unoptimized />
            DeskNow <span className="ml-1 text-sm text-muted-foreground">관리자</span>
          </Link>
          <div className="ml-auto">
            <LogoutButton />
          </div>
        </header>

        {/* 인앱 배너 슬롯 (E5 자리 — 임의취소 통지 등) */}
        <InAppBannerSlot />

        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
