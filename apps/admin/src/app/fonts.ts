import localFont from "next/font/local";

// Pretendard 가변 woff2 자체호스팅(무FOUT). pnpm 모노레포에서
// apps/admin/node_modules/pretendard(심볼릭) 경로로 참조한다.
export const pretendard = localFont({
  src: "../../node_modules/pretendard/dist/web/variable/woff2/PretendardVariable.woff2",
  display: "swap",
  weight: "45 920",
  variable: "--font-pretendard",
});
