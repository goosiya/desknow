// 세션 만료 vs 수동 로그아웃 구분 플래그 — 웹 sessionExpiry.ts 복사 (Story 9.1 code-review 회수).
//
// SessionKeeper 가 "로그인→미로그인 전이"를 만료로 보고 /login?expired=1 로 보낸다. 그런데 사용자가
// **직접 로그아웃**한 경우는 만료가 아니므로 그 안내·리다이렉트를 띄우면 안 된다. useLogout 이
// 로그아웃 직전 이 플래그를 세워 두고, SessionKeeper 가 전이 시 consume 해 만료 처리를 건너뛴다.
// (모듈 스코프 1-bit 신호 — QueryClient 캐시·라우터와 무관한 순간 신호라 별도 상태관리 불필요.)
let manualLogout = false;

/** 수동 로그아웃 시작을 표시한다(useLogout mutationFn 진입 시). */
export function markManualLogout(): void {
  manualLogout = true;
}

/** 플래그를 읽고 즉시 해제한다(true면 이번 전이는 수동 로그아웃 — 만료 처리 skip). */
export function consumeManualLogout(): boolean {
  const was = manualLogout;
  manualLogout = false;
  return was;
}
