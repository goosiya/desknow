"use client";

// 관리자 루트 (Story 8.1). 로그인 상태면 /accounts로, 아니면 /login으로 보낸다(대시보드 최소).
// 기존 토큰 쇼케이스 mock(1.6)은 운영 화면(/accounts)으로 대체됐다.
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAdminSession } from "@/features/auth/useSession";

export default function AdminHome() {
  const router = useRouter();
  const { isLoading, isError, isAdmin } = useAdminSession();

  useEffect(() => {
    if (isLoading || isError) return;
    router.replace(isAdmin ? "/accounts" : "/login");
  }, [isLoading, isError, isAdmin, router]);

  return (
    <div className="h-40 animate-pulse rounded-lg border border-border bg-muted/40" />
  );
}
