// 제공자 가입 보류 정보(KTH 2026-06-19) — provider 가입은 "이메일/비번 입력 → 즉시 가입"이 아니라
// "이메일/비번을 들고 스터디룸 등록 화면으로 → 등록 시점에 가입+룸 생성을 함께" 처리한다. 룸 없는
// 떠도는 provider 계정이 남지 않게 하기 위함이다.
//
// 보관은 **모듈 메모리**에 한다(sessionStorage·URL 금지 — 평문 비밀번호를 저장소/주소에 남기지
// 않는다). SPA 클라이언트 네비게이션(/signup → /provider/room) 동안만 유효하고, full 새로고침이면
// 사라진다(그 경우 RoomForm 이 다시 가입하도록 안내). 룸 등록(=가입 완료) 직후 clear 한다.

export type PendingSignup = { email: string; password: string };

let pending: PendingSignup | null = null;

export function setPendingSignup(value: PendingSignup | null): void {
  pending = value;
}

export function getPendingSignup(): PendingSignup | null {
  return pending;
}

export function clearPendingSignup(): void {
  pending = null;
}
