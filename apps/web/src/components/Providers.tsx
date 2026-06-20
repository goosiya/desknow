"use client";

// 클라이언트 경계 Provider (Story 3.2). App Router(RSC)에서 QueryClientProvider 는
// 클라이언트 컴포넌트여야 하므로(컨텍스트·상태 보유), layout.tsx(서버)는 이 컴포넌트로만
// children 을 감싼다 — 'use client' 경계를 Provider 에 국한해 페이지 셸은 서버로 유지한다.
import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { createQueryClient } from "@/lib/query-client";
import { SessionKeeper } from "@/features/auth/SessionKeeper";

export function Providers({ children }: { children: React.ReactNode }) {
  // QueryClient 는 컴포넌트 생명주기당 1회만 생성한다(렌더마다 재생성 시 캐시 유실).
  const [queryClient] = useState(createQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      {/* 세션 슬라이딩 연장 + 만료 안내/리다이렉트 — QueryClient 안에서 useSession 을 구독한다. */}
      <SessionKeeper />
      {children}
    </QueryClientProvider>
  );
}
