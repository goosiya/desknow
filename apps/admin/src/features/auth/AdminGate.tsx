"use client";

// 운영 라우트 보호 게이트 (Story 8.1, AC2). 클라이언트에서 useSession으로 미로그인·비-admin을
// 로그인 화면으로 유도한다. **백엔드 403이 최종 강제**(AC2)이고 이 게이트는 보조다(아키텍처 L167).
// (Next middleware는 쿠키 존재만 알 수 있고 role은 JWT 내부라 못 읽음 → 본 스토리는 클라 게이트.)
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { useAdminSession } from "./useSession";

export function AdminGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { isLoading, isError, isAdmin, refetch } = useAdminSession();

  useEffect(() => {
    // 미로그인(null)·비-admin이 확정되면 로그인으로 보낸다(진짜 오류는 redirect하지 않음 — 재시도).
    if (!isLoading && !isError && !isAdmin) {
      router.replace("/login");
    }
  }, [isLoading, isError, isAdmin, router]);

  if (isLoading) {
    return (
      <div className="h-40 animate-pulse rounded-lg border border-border bg-muted/40" />
    );
  }

  if (isError) {
    // 네트워크/5xx — 로그아웃으로 오인하지 않고 재시도 유도(useSession 계약).
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-muted-foreground">
          세션을 확인하지 못했어요. 네트워크 연결이 끊겼을 수 있습니다.
        </p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          다시 시도
        </Button>
      </div>
    );
  }

  if (!isAdmin) return null; // 리다이렉트 진행 중 — 깜빡임 방지

  return <>{children}</>;
}
