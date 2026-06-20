"use client";

// 관리자 로그인 화면 (Story 8.1, AC1·AC2·AC3). 시드 관리자만 로그인 가능(가입 UI 없음 — AC3).
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAdminLogin, type LoginOutcome } from "@/features/auth/useAuthActions";
import { useAdminSession } from "@/features/auth/useSession";

// 결과 코드 → 사용자 카피. 401은 enumeration 비노출 단일 카피(1.8 정신), 네트워크는 단절 카피
// (메모 terminology-network-disconnect-not-offline — "오프라인" 금지).
const MESSAGES: Record<Exclude<LoginOutcome, "ok">, string> = {
  invalid: "이메일 또는 비밀번호가 올바르지 않습니다.",
  "not-admin": "관리자 권한이 없습니다.",
  network: "네트워크 연결이 끊겼어요. 잠시 후 다시 시도해 주세요.",
};

export default function LoginPage() {
  const router = useRouter();
  const { isAdmin } = useAdminSession();
  const login = useAdminLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  // 이미 관리자로 로그인된 상태로 /login에 오면 운영 화면으로 보낸다.
  useEffect(() => {
    if (isAdmin) router.replace("/accounts");
  }, [isAdmin, router]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    login.mutate(
      { email, password },
      {
        onSuccess: (outcome) => {
          if (outcome === "ok") {
            router.replace("/accounts");
            return;
          }
          setMessage(MESSAGES[outcome]);
        },
      }
    );
  }

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">관리자 로그인</CardTitle>
          <CardDescription>시드 관리자 계정으로 로그인하세요.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">이메일</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">비밀번호</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {message ? (
              <p role="alert" className="text-sm text-destructive">
                {message}
              </p>
            ) : null}
            <Button type="submit" disabled={login.isPending}>
              {login.isPending ? "로그인 중…" : "로그인"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
