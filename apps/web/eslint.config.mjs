import { defineConfig } from "eslint/config";
import { nextPreset } from "@desknow/config/eslint";

// DeskNow 공유 ESLint preset(@desknow/config) 소비 (Story 1.2).
//
// no-direct-fetch allowlist (Story 7.4): 챗봇 SSE 스트리밍은 생성 SDK(@hey-api)로 소비 불가하므로
// `features/chatbot/streamMessage.ts` **1파일만** raw fetch를 허용한다(preset NOTE가 예고한 "E7
// 챗봇 SSE만 해당 모듈 allowlist", architecture L290 예외). 파일 단위로 좁게 — feature 디렉터리
// 전체나 광역 해제가 아니다(나머지 모든 코드는 SDK 가드 유지). 후순위 config라 preset 룰을 덮는다.
const chatbotSseFetchAllowlist = {
  name: "desknow/chatbot-sse-fetch-allowlist",
  files: ["src/features/chatbot/streamMessage.ts"],
  rules: {
    "no-restricted-globals": "off",
    "no-restricted-syntax": "off",
  },
};

const eslintConfig = defineConfig([...nextPreset, chatbotSseFetchAllowlist]);

export default eslintConfig;
