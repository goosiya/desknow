"use client";

// provider 웹 표면 역할 가드 (인계 3 — booker/미로그인이 /provider/* 직접 진입 시 막는다).
//
// 그동안 provider 화면은 RBAC 를 백엔드에만 의존했다(booker/미로그인은 API 401/403 → 화면은
// "불러오지 못했어요" 에러). 이 가드가 그 앞단에서 역할을 판별해 **친절한 전환**으로 바꾼다:
// 미로그인 → 로그인 화면(?next= 로 복귀), booker/admin → 홈. 기존 ReservationList/FavoriteList
// 의 세션 매트릭스(로딩→스켈레톤·판별실패→재시도·단절→배너)를 그대로 미러한다.
//
// ★ pendingSignup(제공자 신규 가입 중 — /signup → /provider/room) 은 아직 미로그인이지만 통과
//   시킨다: 가입+룸 생성을 룸 폼에서 원자 처리하는 흐름이라(메모리 provider-signup-deferred)
//   여기서 막으면 가입 자체가 불가능해진다. RoomForm 과 동일하게 mount 1회 캡처한다.
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { Skeleton } from "@/components/ui/skeleton";
import { NetworkNotice } from "@/components/NetworkNotice";
import { useOnlineStatus } from "@/lib/useOnlineStatus";
import { getPendingSignup } from "@/features/auth/pendingSignup";
import { useSession } from "@/features/auth/useSession";

/** 리다이렉트 대기/세션 판별 중 자리 — 화면 깜빡임 방지(전역 스피너 금지, 셸 톤 스켈레톤). */
function GuardSkeleton() {
  return (
    <div
      className="mx-auto flex w-full max-w-xl flex-col gap-4 py-8"
      data-testid="provider-guard-skeleton"
    >
      <Skeleton className="h-8 w-40 rounded-md" />
      <Skeleton className="h-24 w-full rounded-lg" />
      <Skeleton className="h-24 w-full rounded-lg" />
    </div>
  );
}

export function ProviderGuard({ children }: { children: React.ReactNode }) {
  // 가입 보류(provider 신규)는 mount 1회 캡처 — 있으면 미로그인이라도 룸 폼을 통과시킨다
  // (RoomForm 과 동일 패턴: 가입+등록 원자 흐름이라 막으면 안 됨).
  const [pending] = useState(() => getPendingSignup());
  const {
    data: session,
    isLoading: sessionLoading,
    isError: sessionError,
    refetch: refetchSession,
  } = useSession();
  const isOnline = useOnlineStatus();
  const router = useRouter();
  const pathname = usePathname();

  // 리다이렉트 판정 — pending·로딩·판별실패·단절·provider 통과는 대상이 아니다(온라인+세션 확정
  // 상태에서만 보낸다). session===null = 미로그인(캐시된 401), role!=="provider" = booker/admin.
  const settled = !pending && !sessionLoading && !sessionError && isOnline;
  const isLoggedOut = settled && session === null;
  const isWrongRole = settled && !!session && session.role !== "provider";

  // 렌더 중 부작용 금지 → effect 에서 리다이렉트(막다른 화면 대신 전환). 미로그인은 ?next= 로
  // 복귀 경로를 싣고, 잘못된 역할(booker/admin)은 홈으로 보낸다.
  useEffect(() => {
    if (isLoggedOut) {
      router.replace(`/login?next=${encodeURIComponent(pathname ?? "/provider")}`);
    } else if (isWrongRole) {
      router.replace("/");
    }
  }, [isLoggedOut, isWrongRole, router, pathname]);

  // 가입 보류(provider 신규) — 미로그인이라도 룸 폼 통과.
  if (pending) return <>{children}</>;

  // 세션 판별 중 — 스켈레톤(미로그인/콘텐츠 깜빡임 방지).
  if (sessionLoading) return <GuardSkeleton />;

  // 세션 판별 실패(네트워크/5xx) — 로그아웃/리다이렉트가 아니라 오류·재시도(로그아웃 오인 금지).
  if (sessionError) {
    return (
      <div className="mx-auto flex w-full max-w-xl flex-col items-center gap-3 rounded-lg border border-border bg-card p-6 py-8 text-center">
        <p className="text-base font-medium text-card-foreground">
          로그인 상태를 확인하지 못했어요.
        </p>
        <button
          type="button"
          onClick={() => refetchSession()}
          className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
        >
          다시 시도
        </button>
      </div>
    );
  }

  // 세션 미확정(오프라인 콜드 진입) — 로그인 사용자 오인 방지로 단절 배너(FavoriteList 선례).
  if (!isOnline && session === undefined) {
    return (
      <div className="mx-auto w-full max-w-xl py-8">
        <NetworkNotice />
      </div>
    );
  }

  // 미로그인·잘못된 역할 — effect 가 리다이렉트하는 동안 잠깐 스켈레톤(깜빡임 최소화).
  if (isLoggedOut || isWrongRole) return <GuardSkeleton />;

  // provider(또는 단절 중 캐시된 provider 세션) — 통과.
  return <>{children}</>;
}
