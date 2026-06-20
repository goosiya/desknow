"use client";

// 인증 폼(로그인·회원가입 공용 셸). 이메일/비밀번호 입력 + 제출 + 로딩/에러 표시 + 상호 이동 링크.
//
// 막다른 화면 금지: 에러는 인라인으로 띄우고 재제출 가능(폼 유지). 카피는 친근한 해요체.
// 토큰·기존 button 프리미티브 재사용(하드코딩 색/픽셀 없음). 반응형(모바일=풀폭, PC=중앙 카드).
import { useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type AuthFormProps = {
  /** 화면 제목(예: "로그인"·"회원가입"). */
  title: string;
  /** 제출 버튼 라벨. */
  submitLabel: string;
  /** 제출 핸들러 — 자격을 받아 비동기 처리(성공 시 호출부가 리다이렉트). */
  onSubmit: (credentials: { email: string; password: string }) => void;
  /** 제출 진행 중(버튼 비활성·로딩 라벨). */
  pending: boolean;
  /** 인라인 에러 카피(없으면 미표시). */
  errorMessage?: string | null;
  /** 정보성 안내 배너(예: 세션 만료) — 에러와 구분된 중립 톤, 폼 위에 표시(없으면 미표시). */
  notice?: string | null;
  /** 비밀번호 필드 보조 안내(가입=정책 안내 등). */
  passwordHint?: string;
  /** 이메일 입력 위에 들어갈 추가 영역(가입=역할 선택 등). 없으면 미표시. */
  topSlot?: ReactNode;
  /** 하단 상호 이동 링크 영역. */
  footer: ReactNode;
  /** 이메일 input의 autoComplete(login=email / signup=email). */
  emailAutoComplete?: string;
  /** 비밀번호 input의 autoComplete(login=current-password / signup=new-password). */
  passwordAutoComplete?: string;
};

/** 라벨 + input 묶음(토큰 기반 스타일 — 디자인 일관성). */
function Field({
  id,
  label,
  type,
  value,
  onChange,
  autoComplete,
  hint,
}: {
  id: string;
  label: string;
  type: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        required
        className={cn(
          "h-11 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground",
          "outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
        )}
      />
      {hint ? (
        <p className="text-xs leading-[1.6] text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

export function AuthForm({
  title,
  submitLabel,
  onSubmit,
  pending,
  errorMessage,
  notice,
  passwordHint,
  topSlot,
  footer,
  emailAutoComplete = "email",
  passwordAutoComplete = "current-password",
}: AuthFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending) return;
    onSubmit({ email: email.trim(), password });
  }

  return (
    <div className="mx-auto flex w-full max-w-sm flex-col gap-6 py-8">
      <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">
        {title}
      </h1>

      {/* 정보성 안내(예: 세션 만료) — 중립 톤(에러 destructive 와 구분). status 로 스크린리더 공지. */}
      {notice ? (
        <p
          role="status"
          className="rounded-md border border-border bg-muted px-3 py-2 text-sm leading-[1.6] text-muted-foreground"
        >
          {notice}
        </p>
      ) : null}

      <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
        {topSlot}
        <Field
          id="email"
          label="이메일"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete={emailAutoComplete}
        />
        <Field
          id="password"
          label="비밀번호"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete={passwordAutoComplete}
          hint={passwordHint}
        />

        {/* 인라인 에러 — role=alert로 스크린리더 공지(막다른 화면 금지: 폼 유지·재제출 가능). */}
        {errorMessage ? (
          <p
            role="alert"
            className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm leading-[1.6] text-destructive"
          >
            {errorMessage}
          </p>
        ) : null}

        <Button type="submit" size="lg" disabled={pending} className="w-full">
          {pending ? "처리 중…" : submitLabel}
        </Button>
      </form>

      <div className="text-center text-sm text-muted-foreground">{footer}</div>
    </div>
  );
}

/** 푸터 상호 이동 링크(스타일 공용). */
export function AuthFooterLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className="font-medium text-primary underline-offset-4 hover:underline">
      {children}
    </Link>
  );
}
