"use client";

// 클라이언트 경계 Provider (Story 8.1 — admin). App Router(RSC)에서 QueryClientProvider는
// 클라이언트 컴포넌트여야 하므로(컨텍스트·상태 보유), layout.tsx(서버)는 이 컴포넌트로만
// children을 감싼다 — 'use client' 경계를 Provider에 국한해 셸은 서버로 유지한다(web 미러).
import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { createQueryClient } from "@/lib/query-client";

export function Providers({ children }: { children: React.ReactNode }) {
  // QueryClient는 컴포넌트 생명주기당 1회만 생성한다(렌더마다 재생성 시 캐시 유실).
  const [queryClient] = useState(createQueryClient);
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
