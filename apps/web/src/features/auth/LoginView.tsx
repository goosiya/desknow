"use client";

// 로그인 화면 컨테이너 — AuthForm을 useLogin 뮤테이션·라우팅에 배선한다.
//
// 성공 시 useLogin이 ["auth","me"]를 invalidate → 세션 갱신 후 next(또는 홈)로 이동한다.
// 에러는 loginErrorCopy로 분기해 인라인 표시(막다른 화면 금지).
import { useRouter, useSearchParams } from "next/navigation";

import { AuthForm, AuthFooterLink } from "./AuthForm";
import { loginErrorCopy } from "./authCopy";
import { useLogin } from "./useAuth";

/** ?next= 안전 검증 — 오픈 리다이렉트 방지(앱 내부 경로만 허용). */
function safeNext(next: string | null): string {
  if (next && next.startsWith("/") && !next.startsWith("//")) return next;
  return "/";
}

export function LoginView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const login = useLogin();

  // 세션 만료로 SessionKeeper 가 보낸 진입(?expired=1) — 만료 안내를 띄운다(직접 로그인 진입은 미표시).
  const expired = searchParams.get("expired") === "1";

  return (
    <AuthForm
      title="로그인"
      submitLabel="로그인"
      pending={login.isPending}
      errorMessage={login.error ? loginErrorCopy(login.error.failure) : null}
      notice={
        expired ? "로그인 시간이 만료됐어요. 다시 로그인해 주세요." : null
      }
      passwordAutoComplete="current-password"
      onSubmit={(credentials) => {
        login.mutate(credentials, {
          onSuccess: () => {
            const dest = safeNext(searchParams.get("next"));
            router.replace(dest);
            router.refresh(); // 서버 컴포넌트(헤더 등) 세션 반영을 위해 라우트 갱신.
          },
        });
      }}
      footer={
        <span>
          아직 계정이 없으신가요?{" "}
          <AuthFooterLink
            href={`/signup${searchParams.get("next") ? `?next=${encodeURIComponent(searchParams.get("next")!)}` : ""}`}
          >
            회원가입
          </AuthFooterLink>
        </span>
      }
    />
  );
}
