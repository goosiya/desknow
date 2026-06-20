import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { colors } from './tokens';

// 토큰 정본(tokens.ts) ↔ web/admin 소비본(tailwind-preset.css) 드리프트 차단 (AC1).
// CSS 파일 텍스트를 읽어 모든 색 hex 가 shadcn 규약 변수로 존재하는지 단언한다.
// (RN 은 tokens.ts 를 직접 import 하므로 구성상 동일 — 별도 단언 불필요.)

const cssPath = fileURLToPath(new URL('../../config/tailwind-preset.css', import.meta.url));
const css = readFileSync(cssPath, 'utf8');

// 다크 부재 단언은 **실제 CSS 규칙**만 대상으로 한다.
// (설명용 주석에 `.dark { … }` 같은 안내 문구가 있어도 토큰 값이 아니므로 무시.)
const cssWithoutComments = css.replace(/\/\*[\s\S]*?\*\//g, '');

/** camelCase 토큰 키 → CSS 커스텀 프로퍼티 kebab 이름. */
function toCssVar(key: string): string {
  return '--' + key.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase());
}

describe('디자인 토큰 parity (tokens.ts ↔ tailwind-preset.css)', () => {
  it('모든 색 토큰 hex 값이 preset 의 :root 변수로 존재한다', () => {
    for (const [key, hex] of Object.entries(colors)) {
      const decl = `${toCssVar(key)}: ${hex};`;
      expect(css, `누락된 색 토큰 선언: ${decl}`).toContain(decl);
    }
  });

  it('preset 에 다크 토큰이 존재하지 않는다 (AC2 — 라이트 전용)', () => {
    expect(cssWithoutComments).not.toMatch(/prefers-color-scheme:\s*dark/);
    expect(cssWithoutComments).not.toMatch(/\.dark\b/);
  });

  it('radius·font-sans 시맨틱 토큰이 존재한다', () => {
    expect(css).toContain('--radius: 0.5rem;');
    expect(css).toContain('--font-sans:');
  });
});
