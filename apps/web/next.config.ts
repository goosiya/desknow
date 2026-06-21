import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // @desknow/ui·@desknow/api-client 는 TS 소스를 직접 노출하는 워크스페이스 패키지이므로
  // Next 가 트랜스파일하도록 명시한다(없으면 빌드 실패). api-client는 Story 1.9 SDK.
  transpilePackages: ["@desknow/ui", "@desknow/api-client"],
  // 같은-출처 프록시(서드파티 쿠키 차단 회피): API와 웹이 서로 다른 도메인(*.up.railway.app은
  // 사이트가 분리됨)이라 API가 발급한 SameSite=None 인증 쿠키가 실제 브라우저에서 서드파티
  // 쿠키로 차단됐다. 브라우저가 웹 자기 출처의 /api/* 만 호출하고 Next 가 서버에서 API
  // (API_PROXY_TARGET)로 프록시하면, 응답 쿠키가 1st-party가 되어 차단되지 않는다.
  // API_PROXY_TARGET 미설정(로컬 dev)이면 프록시 없음 — SDK가 NEXT_PUBLIC_API_BASE_URL
  // (로컬 :8000)로 직접 호출하는 기존 동작 유지.
  async rewrites() {
    const target = process.env.API_PROXY_TARGET;
    return target
      ? [{ source: "/api/:path*", destination: `${target}/api/:path*` }]
      : [];
  },
};

export default nextConfig;
