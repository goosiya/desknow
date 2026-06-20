import localFont from "next/font/local";

// Pretendard 가변 woff2 자체호스팅(무FOUT). pnpm 모노레포에서
// apps/web/node_modules/pretendard(심볼릭) 경로로 참조한다.
// 경로가 깨지면 woff2 를 apps/web/src/app/fonts/ 로 복사해 참조(대안).
export const pretendard = localFont({
  src: "../../node_modules/pretendard/dist/web/variable/woff2/PretendardVariable.woff2",
  display: "swap",
  weight: "45 920",
  variable: "--font-pretendard",
});
