"use client";

// 역할별 1급 내비 (provider 웹 표면 구축 — idea.md L66 네비). 세션 role 에 따라 진입 메뉴를 가른다:
// - 예약자/미로그인: 스터디룸 찾기 · 예약현황 · 즐겨찾기(탐색은 비로그인 가능 — 기존 IA).
// - 제공자: 내 스터디룸 · 예약자 현황 · 후기(제공자는 booker 탐색 메뉴 대신 운영 메뉴를 본다).
//
// 이게 없으면 provider 가 가입 후 화면을 벗어났을 때 룸 등록/관리로 돌아갈 입구가 사라진다
// (KTH 발견). top(md+)·bottom(sm) 두 내비를 role 분기로 렌더한다. 세션은 useSession.
//
// ★구조(KTH 2026-06-19 모바일 버그 수정): 하단 내비(`fixed bottom-0`)는 **헤더 밖**(AppShell 루트)
//   에서 렌더해야 한다. 헤더에는 `backdrop-blur`(=backdrop-filter)가 걸려 있어, 그 안의 `position:
//   fixed` 자식은 **뷰포트가 아니라 헤더를 컨테이닝 블록으로** 잡는다(transform/filter/backdrop-filter
//   의 알려진 동작). 그러면 `bottom-0` 이 56px 헤더 기준이 돼 하단바가 **화면 최상단에 붙어 헤더
//   링크를 덮고**(브랜드·로그인 등 탭 불가) 정작 바닥엔 없다. 그래서 상단바(`AppNav`)와 하단바
//   (`AppBottomNav`)를 **별도 컴포넌트**로 나눠, 하단바는 AppShell 이 헤더 밖에서 렌더한다.
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useSession } from "@/features/auth/useSession";

type NavItem = { href: string; label: string };

// 현재 경로가 nav 항목과 일치하는지(선택 강조용). "/"는 정확히, 그 외는 동일 경로 prefix 로 판정.
function useIsActive() {
  const pathname = usePathname();
  return (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

const BOOKER_NAV: NavItem[] = [
  { href: "/", label: "스터디룸 찾기" },
  { href: "/reservations", label: "예약현황" },
  { href: "/favorites", label: "즐겨찾기" },
];

const PROVIDER_NAV: NavItem[] = [
  { href: "/provider/room", label: "내 스터디룸" },
  { href: "/provider/reservations", label: "예약자 현황" },
  { href: "/provider/reviews", label: "후기" },
];

// role 분기 메뉴 — provider 만 운영 메뉴, 그 외(로딩·미로그인·booker)는 예약자 메뉴.
function useNavItems(): NavItem[] {
  const { data: session } = useSession();
  return session?.role === "provider" ? PROVIDER_NAV : BOOKER_NAV;
}

/** 상단 내비(md+) — 헤더 안에서 렌더한다. 현재 메뉴는 primary 로 강조(모바일앱 선택색 미러, 9.4 #2). */
export function AppNav() {
  const items = useNavItems();
  const isActive = useIsActive();
  return (
    <nav className="ml-4 hidden items-center gap-1 md:flex" aria-label="주요 메뉴">
      {items.map((item) => {
        const active = isActive(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`inline-flex h-11 items-center rounded-md px-3 text-sm font-medium hover:bg-muted ${
              active ? "text-primary" : "text-foreground"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * 하단 내비바(sm 전용) — **헤더 밖(AppShell 루트)** 에서 렌더해야 한다(위 ★구조 주석 참조).
 * 헤더 안에 두면 `backdrop-blur` 컨테이닝 블록 때문에 `fixed bottom-0` 이 헤더 기준이 돼 화면
 * 최상단에 붙는다(헤더 링크 가림·하단 부재). 항목 수에 맞춰 열을 분배한다.
 */
export function AppBottomNav() {
  const items = useNavItems();
  const isActive = useIsActive();
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-20 grid border-t border-border bg-background md:hidden"
      style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}
      aria-label="하단 내비게이션"
    >
      {items.map((item) => {
        const active = isActive(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            // 선택 메뉴 primary 강조(모바일앱 NativeTabs 선택색 미러, 9.4 #2).
            className={`flex min-h-12 flex-col items-center justify-center px-1 py-2 text-xs font-medium ${
              active ? "text-primary" : "text-foreground"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
