// provider 웹 표면 공통 레이아웃 — 모든 /provider/* 를 역할 가드로 감싼다(인계 3).
//
// 가드(역할 판별·리다이렉트)는 'use client' 경계라 ProviderGuard 가 소유하고, 페이지는 얇게
// 유지한다(reservations/page 의 "셸은 서버·상태는 feature" 패턴과 동형). booker/미로그인이
// /provider/* 로 직접 진입하면 여기서 친절히 전환된다(API 403 에러 화면 대신).
import { ProviderGuard } from "@/features/provider/ProviderGuard";

export default function ProviderLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <ProviderGuard>{children}</ProviderGuard>;
}
