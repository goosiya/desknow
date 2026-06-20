// Layer B 드리프트 게이트 (Story 1.9, AC3): openapi.json ↔ 커밋된 src/generated 일치 검사.
//
// openapi.json에서 SDK를 임시 디렉터리에 재생성해 커밋된 src/generated와 재귀 비교한다.
// 차이가 있으면(= openapi.json은 갱신됐는데 SDK 재생성을 누락) 비0 종료로 `turbo run test`를
// 실패시켜 계약-SDK 불일치를 차단한다.
//
// 결정성: openapi-ts CLI를 그대로 호출하므로 openapi-ts.config.ts(input·plugins)를 단일 소스로
// 재사용하고 output만 임시 경로로 override한다(설정 중복 없음). 생성기 버전은 정확 핀이라
// 환경 간 생성물 차이(거짓 드리프트)가 없다.
import { execFileSync } from "node:child_process";
import {
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
} from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const pkgRoot = fileURLToPath(new URL("..", import.meta.url));
const committedDir = join(pkgRoot, "src", "generated");
const REGEN_HINT =
  "`pnpm --filter @desknow/api-client generate` 재실행 필요(openapi.json 변경 후 SDK 재생성 누락).";

/** 디렉터리 트리의 모든 파일을 {상대경로(슬래시 정규화) → 내용} 맵으로 수집한다. */
function collectFiles(root) {
  const out = new Map();
  const walk = (dir) => {
    for (const entry of readdirSync(dir)) {
      const abs = join(dir, entry);
      if (statSync(abs).isDirectory()) {
        walk(abs);
      } else {
        // OS 무관 비교를 위해 경로 구분자를 "/"로 정규화하고 CRLF→LF로 통일한다.
        const rel = relative(root, abs).split(sep).join("/");
        out.set(rel, readFileSync(abs, "utf-8").replace(/\r\n/g, "\n"));
      }
    }
  };
  walk(root);
  return out;
}

function fail(message) {
  console.error(`\n✗ SDK 드리프트 검출 — ${message}\n`);
  process.exit(1);
}

// openapi-ts 실행 바이너리(JS)를 패키지에서 해석해 node로 직접 실행한다(크로스플랫폼).
const otsPkgJson = require.resolve("@hey-api/openapi-ts/package.json", {
  paths: [pkgRoot],
});
const otsPkg = JSON.parse(readFileSync(otsPkgJson, "utf-8"));
const binRel =
  typeof otsPkg.bin === "string" ? otsPkg.bin : otsPkg.bin["openapi-ts"];
const otsBin = join(dirname(otsPkgJson), binRel);

const tmpBase = mkdtempSync(join(tmpdir(), "desknow-sdk-drift-"));
const tmpOut = join(tmpBase, "generated");

try {
  // config 파일(openapi-ts.config.ts)의 input·plugins를 재사용하고 output만 임시 경로로 override.
  execFileSync(process.execPath, [otsBin, "--output", tmpOut, "--silent"], {
    cwd: pkgRoot,
    stdio: "inherit",
  });

  const committed = collectFiles(committedDir);
  const fresh = collectFiles(tmpOut);

  const committedKeys = [...committed.keys()].sort();
  const freshKeys = [...fresh.keys()].sort();

  const missing = freshKeys.filter((k) => !committed.has(k)); // 재생성에 있으나 커밋 안 됨
  const extra = committedKeys.filter((k) => !fresh.has(k)); // 커밋엔 있으나 재생성에 없음
  if (missing.length || extra.length) {
    fail(
      `생성 파일 목록 불일치.\n  누락(미커밋): ${missing.join(", ") || "(없음)"}\n` +
        `  잉여(구파일): ${extra.join(", ") || "(없음)"}\n${REGEN_HINT}`,
    );
  }

  const changed = freshKeys.filter((k) => committed.get(k) !== fresh.get(k));
  if (changed.length) {
    fail(`다음 파일 내용 불일치:\n  ${changed.join("\n  ")}\n${REGEN_HINT}`);
  }

  console.log("✓ SDK 드리프트 없음 — openapi.json과 src/generated 일치.");
} finally {
  rmSync(tmpBase, { recursive: true, force: true });
}
