"use client";

// 로그아웃 버튼 (Story 8.1, AC1). 셸 헤더에 둔다 — 로그인된 관리자에게만 보인다.
// authLogout → 세션 invalidate(useAdminLogout) 후 로그인 화면으로 이동한다.
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { useAdminLogout } from "./useAuthActions";
import { useAdminSession } from "./useSession";

export function LogoutButton() {
  const router = useRouter();
  const { isAdmin } = useAdminSession();
  const logout = useAdminLogout();

  if (!isAdmin) return null; // 미로그인/비-admin엔 노출하지 않음

  function handleClick() {
    logout.mutate(undefined, {
      onSettled: () => router.replace("/login"),
    });
  }

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleClick}
      disabled={logout.isPending}
    >
      {logout.isPending ? "로그아웃 중…" : "로그아웃"}
    </Button>
  );
}
