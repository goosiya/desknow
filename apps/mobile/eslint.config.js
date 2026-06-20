// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require("eslint-config-expo/flat");

// 직접 fetch 금지 가드 (Story 1.9, AC2) — web/admin preset과 동등.
// 백엔드 호출은 오직 @desknow/api-client SDK로만. 생성 SDK는 node_modules(워크스페이스 심볼릭)
// 이라 eslint 대상 밖이므로 내부 fetch는 무영향.
// NOTE(E7): 챗봇 SSE 스트리밍(react-native-sse/fetch)은 E7에서 해당 모듈만 allowlist 예정.
const FETCH_BAN_MESSAGE =
  "백엔드 호출은 @desknow/api-client SDK로만 — 직접 fetch 금지 [architecture.md L290]. (E7 챗봇 SSE 스트리밍만 해당 모듈에서 allowlist 예정)";

module.exports = defineConfig([
  expoConfig,
  {
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
  },
  {
    ignores: ["dist/*"],
  }
]);
