// 인증 실패 → 사용자 카피 매핑(로그인·회원가입 공용 분기).
//
// 막다른 화면 금지: 모든 분기가 재시도 가능한 인라인 안내다(별도 페이지 없음). "오프라인" 금지 —
// 네트워크 단절은 프로젝트 표준 카피로 단일화한다(NetworkNotice와 동일 문구 정신).
import type { AuthFailure } from "./useAuth";

/** 비밀번호 정책 안내(가입 422 fallback) — 서버 message가 비었을 때 노출. */
export const PASSWORD_POLICY_HINT =
  "비밀번호는 8자 이상이며 대문자, 숫자, 특수문자를 각각 1개 이상 포함해야 해요.";

/**
 * 가입 자격 클라이언트 1차 검증(KTH 2026-06-19). provider 가입은 실제 서버 호출(register)이
 * 룸 등록 시점까지 미뤄지므로, 빈값·형식·정책 위반을 **넘어가기 전에** 여기서 거른다(booker는
 * register가 즉시 서버 검증). 통과 메시지(null)면 진행, 아니면 사용자 카피를 반환한다. 최종
 * 신뢰 경계는 서버(`_enforce_password_policy`)이며 이 함수는 그 규칙을 미러한 1차 가드일 뿐이다.
 */
export function validateSignupCredentials(credentials: {
  email: string;
  password: string;
}): string | null {
  const { email, password } = credentials;
  if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return "올바른 이메일 주소를 입력해 주세요.";
  }
  // 백엔드 _enforce_password_policy 미러: 8자↑ + 대문자 + 숫자 + ASCII 구두점(string.punctuation
  // = 0x21–0x2F · 0x3A–0x40 · 0x5B–0x60 · 0x7B–0x7E).
  const hasUpper = /[A-Z]/.test(password);
  const hasDigit = /[0-9]/.test(password);
  const hasSpecial = /[!-/:-@[-`{-~]/.test(password);
  if (password.length < 8 || !hasUpper || !hasDigit || !hasSpecial) {
    return PASSWORD_POLICY_HINT;
  }
  return null;
}

/** 로그인 실패 카피. 401=자격 오류 단일화(이메일/비번 구분 노출 금지). */
export function loginErrorCopy(failure: AuthFailure): string {
  switch (failure.kind) {
    case "unauthorized":
      return "이메일 또는 비밀번호가 올바르지 않아요.";
    case "network":
      return "네트워크 연결이 끊겼어요. 연결되면 다시 시도해주세요.";
    case "validation":
      // 로그인은 형식오류도 401로 단일화되지만, 예외적 422 대비 서버 message 노출.
      return failure.message || "입력값을 다시 확인해주세요.";
    default:
      return "잠시 후 다시 시도해주세요.";
  }
}

/** 회원가입 실패 카피. 409=이메일 중복 · 422=정책 위반(서버 message 우선). */
export function registerErrorCopy(failure: AuthFailure): string {
  switch (failure.kind) {
    case "conflict":
      return "이미 가입된 이메일이에요.";
    case "validation":
      return failure.message || PASSWORD_POLICY_HINT;
    case "unauthorized":
      // 가입 후 자동 로그인 연쇄가 401이면(이론상 드묾) 자격 안내로 폴백.
      return "가입은 됐지만 로그인에 실패했어요. 로그인 화면에서 다시 시도해주세요.";
    case "network":
      return "네트워크 연결이 끊겼어요. 연결되면 다시 시도해주세요.";
    default:
      return "잠시 후 다시 시도해주세요.";
  }
}
