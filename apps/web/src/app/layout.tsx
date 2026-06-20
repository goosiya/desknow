import type { Metadata } from "next";

import { Providers } from "@/components/Providers";
import { AppShell } from "@/components/shell/AppShell";
import { pretendard } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "DeskNow",
  description: "내 주변 스터디룸을 찾고 바로 예약하세요.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning: GA opt-out 등 브라우저 확장이 하이드레이션 전 <html>에
    // data-* 속성을 주입해 발생하는 불일치를, 재조정 없이 클라이언트 값을 신뢰하도록 허용한다.
    // 이 엘리먼트 한 단계에만 적용되어 자식(<body> 이하)의 불일치는 그대로 노출된다.
    // 주의: 향후 <html>에 동적/조건부 속성(예: 테마 클래스)을 추가하면 진짜 불일치도 숨길 수 있다.
    <html lang="ko" className={`${pretendard.variable} h-full`} suppressHydrationWarning>
      <body className="min-h-full bg-background font-sans text-foreground antialiased">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
