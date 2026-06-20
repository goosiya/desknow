"use client";

// 회원가입 화면 컨테이너 — AuthForm을 useRegister(가입→자동 로그인 연쇄) 뮤테이션·라우팅에 배선.
//
// idea.md L6/L30: 예약자·스터디룸 제공자 **둘 다 웹 가입 대상**이다. 역할 토글로 선택해 가입하고,
// 성공(자동 로그인 완료) 시 — booker는 next(또는 홈), provider는 룸 등록 화면으로 보낸다.
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthForm, AuthFooterLink } from "./AuthForm";
import {
  PASSWORD_POLICY_HINT,
  registerErrorCopy,
  validateSignupCredentials,
} from "./authCopy";
import { setPendingSignup } from "./pendingSignup";
import { useRegister, type SignupRole } from "./useAuth";

/** ?next= 안전 검증 — 오픈 리다이렉트 방지(앱 내부 경로만 허용). */
function safeNext(next: string | null): string {
  if (next && next.startsWith("/") && !next.startsWith("//")) return next;
  return "/";
}

/** 역할 선택 세그먼트 한 버튼(상단 토글 — 만다린 토큰). */
function RoleButton({
  active,
  label,
  desc,
  onClick,
}: {
  active: boolean;
  label: string;
  desc: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`flex flex-1 flex-col items-center gap-0.5 rounded-md border px-3 py-2.5 text-center transition-colors ${
        active
          ? "border-primary bg-primary/10 text-foreground"
          : "border-border bg-background text-muted-foreground hover:bg-muted"
      }`}
    >
      <span className="text-sm font-semibold">{label}</span>
      <span className="text-xs leading-[1.5]">{desc}</span>
    </button>
  );
}

export function SignupView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const register = useRegister();
  const [role, setRole] = useState<SignupRole>("booker");
  // provider 클라 1차 검증 실패 카피(가입을 미루기 전에 거른 이메일/비번 오류).
  const [localError, setLocalError] = useState<string | null>(null);
  const isProvider = role === "provider";

  // 역할 전환 시 직전 시도의 에러를 정리한다(예: 예약자 가입 실패 후 제공자로 바꾸면 stale 한
  // register 에러 카피가 남는 것 방지 — code-review 회수, 모바일 9.1 P2 패리티).
  function selectRole(next: SignupRole) {
    setRole(next);
    setLocalError(null);
    register.reset();
  }

  return (
    <AuthForm
      title="회원가입"
      // provider 는 이 단계에서 가입하지 않는다 — 버튼이 곧 "스터디룸 등록 화면으로" 이동을 뜻한다.
      submitLabel={isProvider ? "스터디룸 정보 등록" : "가입하고 시작하기"}
      pending={register.isPending}
      errorMessage={
        localError ??
        (register.error ? registerErrorCopy(register.error.failure) : null)
      }
      passwordAutoComplete="new-password"
      passwordHint={PASSWORD_POLICY_HINT}
      topSlot={
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-foreground">가입 유형</span>
          <div role="group" aria-label="가입 유형 선택" className="flex gap-2">
            <RoleButton
              active={role === "booker"}
              label="예약자"
              desc="스터디룸을 찾고 예약"
              onClick={() => selectRole("booker")}
            />
            <RoleButton
              active={role === "provider"}
              label="제공자"
              desc="내 스터디룸을 등록"
              onClick={() => selectRole("provider")}
            />
          </div>
          {/* provider 안내(온보딩 톤 빨강) — 룸 등록 전에는 가입이 완료되지 않음을 명확히. */}
          {isProvider ? (
            <p className="text-xs font-semibold leading-[1.6] text-destructive">
              스터디룸 정보를 등록해야 가입이 완료돼요. 등록 전에 나가면 가입되지 않아요.
            </p>
          ) : null}
        </div>
      }
      onSubmit={(credentials) => {
        setLocalError(null);
        if (isProvider) {
          // 가입은 룸 등록 시점으로 미루되, 빈값·형식·정책은 넘어가기 전에 1차 검증한다(아무것도
          // 입력 안 해도 넘어가던 문제 차단). 최종 검증은 등록 시 서버가 한다.
          const invalid = validateSignupCredentials(credentials);
          if (invalid) {
            setLocalError(invalid);
            return;
          }
          // 가입을 미룬다 — 이메일/비번을 들고 룸 등록 화면으로. 실제 가입은 거기서 등록과 함께.
          setPendingSignup(credentials);
          router.push("/provider/room");
          return;
        }
        register.mutate(
          { ...credentials, role },
          {
            onSuccess: () => {
              // booker는 가입 성공(자동 로그인) 후 next(또는 홈)로.
              router.replace(safeNext(searchParams.get("next")));
              router.refresh();
            },
          },
        );
      }}
      footer={
        <span>
          이미 계정이 있으신가요?{" "}
          <AuthFooterLink
            href={`/login${searchParams.get("next") ? `?next=${encodeURIComponent(searchParams.get("next")!)}` : ""}`}
          >
            로그인
          </AuthFooterLink>
        </span>
      }
    />
  );
}
