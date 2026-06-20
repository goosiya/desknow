import { defineConfig } from "eslint/config";
import { nextPreset } from "@desknow/config/eslint";

// DeskNow 공유 ESLint preset(@desknow/config) 소비 (Story 1.2).
const eslintConfig = defineConfig([...nextPreset]);

export default eslintConfig;
