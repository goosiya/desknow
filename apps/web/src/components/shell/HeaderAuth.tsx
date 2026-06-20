"use client";

// 헤더 인증 슬롯 — useSession으로 로그인/미로그인 분기(AppShell 헤더 우측).
//
// 로그인: 사용자 이메일(또는 익명 라벨) + 로그아웃 버튼(클릭 시 authLogout→세션 invalidate).
// 미로그인: "로그인" → /login. 세션 판별 중/실패는 "로그인"으로 안전 폴백(로그아웃 오인 방지 —
// undefined는 미확정이지 미로그인이 아니므로 사용자 정보를 노출하지 않는다).
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useSession } from "@/features/auth/useSession";
import { useLogout } from "@/features/auth/useAuth";

/** 로그인 링크(미로그인·세션 미확정 공용 폴백). */
function LoginLink() {
  return (
    <Link
      href="/login"
      className="ml-auto inline-flex h-11 items-center rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-muted"
    >
      로그인
    </Link>
  );
}

export function HeaderAuth() {
  const router = useRouter();
  const { data: user, isLoading, isError } = useSession();
  const logout = useLogout();

  // 세션 판별 중/실패 — "로그인"으로 안전 폴백(사용자 정보 미노출, 로그아웃 오인 방지).
  if (isLoading || isError || !user) {
    return <LoginLink />;
  }

  function handleLogout() {
    logout.mutate(undefined, {
      onSettled: () => {
        // 세션 무효화 후 서버 컴포넌트(헤더 등) 갱신 — 미로그인 상태 반영.
        router.refresh();
      },
    });
  }

  return (
    <div className="ml-auto flex items-center gap-1">
      {/* 사용자 식별 — 이메일 노출(provider/타인-facing 표면이 아니므로 본인 이메일 표시 OK). */}
      <span
        className="hidden max-w-[12rem] truncate text-sm text-muted-foreground sm:inline"
        title={user.email}
      >
        {user.email}
      </span>
      <button
        type="button"
        onClick={handleLogout}
        disabled={logout.isPending}
        className="inline-flex h-11 items-center rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-muted disabled:opacity-50"
      >
        {logout.isPending ? "로그아웃 중…" : "로그아웃"}
      </button>
    </div>
  );
}
