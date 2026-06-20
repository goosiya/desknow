import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // @desknow/ui·@desknow/api-client 는 TS 소스를 직접 노출하는 워크스페이스 패키지이므로
  // Next 가 트랜스파일하도록 명시한다(없으면 빌드 실패). api-client는 Story 1.9 SDK.
  transpilePackages: ["@desknow/ui", "@desknow/api-client"],
};

export default nextConfig;
