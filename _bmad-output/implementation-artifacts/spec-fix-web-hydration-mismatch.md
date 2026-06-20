---
title: '웹 초기 화면 하이드레이션 불일치 경고 제거'
type: 'bugfix'
created: '2026-06-18'
status: 'done'
route: 'one-shot'
---

# 웹 초기 화면 하이드레이션 불일치 경고 제거

## Intent

**Problem:** 웹 초기 화면에서 Next.js가 "server rendered HTML didn't match the client" 하이드레이션 불일치 콘솔 에러를 띄웠다. 불일치 속성은 루트 `<html>`의 `data-google-analytics-opt-out=""`로, 앱 소스에는 전혀 없고(`.next` 캐시·로그에만 등장) Google "Google Analytics Opt-out" 브라우저 확장이 하이드레이션 전에 주입한 것이다 — 코드 버그가 아니라 외부 확장이 루트 엘리먼트 속성을 변형해 발생.

**Approach:** React가 이런 최상위 `html`/`body` 속성 주입에 제공하는 escape hatch인 `suppressHydrationWarning`을 `apps/web/src/app/layout.tsx`의 `<html>`에 추가. 이 prop은 해당 엘리먼트 한 단계에만 적용되어 자식의 진짜 불일치는 그대로 노출하므로 동작 변화 없이 경고만 제거한다. `<body>` 주입(문법교정기 등) 대응은 실제 보고 시점에 추가(선제 마스킹 비권장).

## Suggested Review Order

1. [`apps/web/src/app/layout.tsx`](../../apps/web/src/app/layout.tsx) — `<html>`에 `suppressHydrationWarning` 추가 + 적용 범위·유지보수 경고 주석. 변경의 전부.
