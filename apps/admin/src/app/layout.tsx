import type { Metadata } from "next";

import { Providers } from "@/components/Providers";
import { AdminShell } from "@/components/shell/AdminShell";
import { pretendard } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "DeskNow 관리자",
  description: "DeskNow 운영 관리자 콘솔.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning: GA opt-out 등 브라우저 확장이 하이드레이션 전 <html>에
    // data-* 속성(예: data-google-analytics-opt-out)을 주입해 발생하는 서버/클라 불일치를,
    // 재조정 없이 클라이언트 값을 신뢰하도록 허용한다. 이 엘리먼트 한 단계에만 적용되어
    // 자식(<body> 이하)의 불일치는 그대로 노출된다(web 앱 layout 과 동일 처리).
    // 주의: 향후 <html>에 동적/조건부 속성(예: 테마 클래스)을 추가하면 진짜 불일치도 숨길 수 있다.
    <html
      lang="ko"
      className={`${pretendard.variable} h-full`}
      suppressHydrationWarning
    >
      <body className="min-h-full bg-background font-sans text-foreground antialiased">
        {/* TanStack Query 컨텍스트(useSession 등)를 셸 전체에 제공 — "No QueryClient set" 방지. */}
        <Providers>
          <AdminShell>{children}</AdminShell>
        </Providers>
      </body>
    </html>
  );
}
