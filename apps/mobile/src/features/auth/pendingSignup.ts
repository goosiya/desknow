// 제공자 가입 보류 정보 (Story 9.1 — 웹 pendingSignup.ts 동일, §범위 2).
//
// provider 가입은 "이메일/비번 입력 → 즉시 가입"이 아니라 "이메일/비번을 들고 스터디룸 등록 화면
// (9.3 스텁)으로 → 등록 시점에 가입+룸 생성을 함께" 처리한다. 룸 없는 떠도는 provider 계정이 남지
// 않게 하기 위함이다(웹과 동일 원칙).
//
// 보관은 **모듈 메모리**에 한다(secure-store·AsyncStorage·URL 금지 — 평문 비밀번호를 영속
// 저장소에 남기지 않는다, 보안 동등). 가입 화면 → 룸등록 라우트 네비게이션 동안만 유효하고, 앱
// 재시작이면 사라진다. 룸 등록(=가입 완료) 직후 clear 한다(9.3 소유).
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
