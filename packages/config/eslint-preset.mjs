// DeskNow 공유 ESLint flat config preset (Story 1.2).
// web·admin이 이 preset을 소비해 Next 공통 룰셋을 공유한다.
import { globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// 직접 fetch 금지 가드 (Story 1.9, AC2).
// 백엔드 호출은 오직 @desknow/api-client SDK로만 한다 — 직접 fetch는 SDK 우회·계약 이탈이라
// 금지한다. 생성 SDK(packages/api-client)는 이 preset을 소비하지 않으므로 내부 fetch는 무영향.
// no-restricted-globals(전역 `fetch`) + no-restricted-syntax(`window.fetch`·`globalThis.fetch`
// 멤버 호출)로 우회 경로까지 막는다.
// NOTE(E7): 챗봇 "룸메이트" SSE 스트리밍은 fetch 기반이라, E7에서 해당 모듈만 allowlist 예정.
const FETCH_BAN_MESSAGE =
  "백엔드 호출은 @desknow/api-client SDK로만 — 직접 fetch 금지 [architecture.md L290]. (E7 챗봇 SSE 스트리밍만 해당 모듈에서 allowlist 예정)";

export const noDirectFetch = {
  name: "desknow/no-direct-fetch",
  rules: {
    "no-restricted-globals": ["error", { name: "fetch", message: FETCH_BAN_MESSAGE }],
    "no-restricted-syntax": [
      "error",
      {
        selector:
          "MemberExpression[property.name='fetch'][object.name=/^(window|globalThis|self|global)$/]",
        message: FETCH_BAN_MESSAGE,
      },
    ],
  },
};

/** Next.js 앱 공통 flat config 배열. */
export const nextPreset = [
  ...nextVitals,
  ...nextTs,
  noDirectFetch,
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
];

export default nextPreset;
