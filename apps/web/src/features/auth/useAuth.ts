// 인증 액션(로그인·회원가입·로그아웃) 뮤테이션 훅.
//
// 세션 상태 단일 출처는 useSession(["auth","me"] 쿼리)이다. 이 훅들은 SDK 인증 함수를 호출한 뒤
// **반드시 ["auth","me"]를 invalidate**해 세션이 즉시 갱신되게 한다(로그인/가입 후 화면 분기·
// 헤더 반영). 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드).
//
// 웹은 httpOnly 쿠키 인증이라(api-client credentials:"include") 로그인/가입 응답 본문의 토큰은
// 무시한다 — 쿠키가 곧 세션이고, 갱신은 authMe 재조회로 확인한다.
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { authLogin, authLogout, authRegister } from "@/lib/api-client";

import { markManualLogout } from "./sessionExpiry";

/** 세션 쿼리 키(useSession과 동일) — 인증 액션 성공 후 무효화 대상. */
const SESSION_KEY = ["auth", "me"] as const;

/** 인증 실패 분류 — 화면이 카피를 분기하기 위한 판별 결과. */
export type AuthFailure =
  | { kind: "unauthorized" } // 로그인 401 — 자격 오류
  | { kind: "conflict" } // 가입 409 — 이메일 중복
  | { kind: "validation"; message: string } // 가입 422 — 정책 위반(서버 message)
  | { kind: "network" } // 네트워크 단절(fetch reject)
  | { kind: "unknown"; status?: number }; // 그 외(5xx 등)

/**
 * SDK 호출 결과({ error, response })를 AuthFailure로 정규화해 throw용 Error에 싣는다.
 *
 * throwOnError:false 라 HTTP 오류는 `{ data, error, response }`로 돌아오고(response.status로 식별),
 * 네트워크 reject만 호출부에서 throw 된다. 여기선 HTTP 오류 → AuthFailure로 변환만 한다.
 */
function classifyHttpError(
  status: number | undefined,
  errorBody: unknown,
): AuthFailure {
  if (status === 401) return { kind: "unauthorized" };
  if (status === 409) return { kind: "conflict" };
  if (status === 422) {
    // 422 본문 형상: { detail: { code, message } } — 서버 message를 노출(없으면 빈 문자열).
    const message =
      (errorBody as { detail?: { message?: string } } | undefined)?.detail
        ?.message ?? "";
    return { kind: "validation", message };
  }
  return { kind: "unknown", status };
}

/** AuthFailure를 mutation 오류로 던지기 위한 래퍼 — onError에서 cause로 꺼내 분기한다. */
export class AuthError extends Error {
  failure: AuthFailure;
  constructor(failure: AuthFailure) {
    super(failure.kind);
    this.name = "AuthError";
    this.failure = failure;
  }
}

/** 네트워크 reject(TypeError 등)인지 — SDK가 응답을 못 받은 경우. */
function toAuthError(err: unknown): AuthError {
  if (err instanceof AuthError) return err;
  // fetch 자체 실패(네트워크 단절·DNS·CORS preflight 실패) → network로 정규화.
  return new AuthError({ kind: "network" });
}

/**
 * 로그인 뮤테이션. 성공 시 세션 무효화(authMe 재조회로 로그인 반영).
 * 실패는 AuthError(failure로 카피 분기)로 throw 된다.
 */
export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation<void, AuthError, { email: string; password: string }>({
    mutationFn: async ({ email, password }) => {
      try {
        const { error, response } = await authLogin({
          body: { email, password },
        });
        if (!response?.ok) {
          throw new AuthError(classifyHttpError(response?.status, error));
        }
        // 웹은 쿠키 인증 — 응답 본문 토큰(TokenResponse)은 무시. 세션은 onSuccess의 authMe 재조회로 확인.
      } catch (err) {
        throw toAuthError(err);
      }
    },
    onSuccess: async () => {
      // 로그인 성공 → 세션 단일 출처 무효화(헤더·게이팅 화면이 즉시 로그인 상태로 갱신).
      await queryClient.invalidateQueries({ queryKey: SESSION_KEY });
    },
  });
}

/** 가입 역할 — 예약자(booker) 또는 스터디룸 제공자(provider). idea.md L6/L30 양쪽 가입. */
export type SignupRole = "booker" | "provider";

/**
 * 회원가입 뮤테이션. 역할(booker/provider)을 받아 가입한다(idea.md — 제공자도 웹 가입 대상).
 * 성공 시 자동 로그인(register→login 연쇄) 후 세션 무효화 — 호출부가 리다이렉트한다.
 */
export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation<
    void,
    AuthError,
    { email: string; password: string; role: SignupRole }
  >({
    mutationFn: async ({ email, password, role }) => {
      try {
        const { error, response } = await authRegister({
          body: { email, password, role },
        });
        if (!response?.ok) {
          throw new AuthError(classifyHttpError(response?.status, error));
        }
        // 가입 성공 → 자동 로그인 연쇄(같은 자격으로 쿠키 발급). 로그인 실패는 그대로 전파.
        const loginResult = await authLogin({ body: { email, password } });
        if (!loginResult.response?.ok) {
          throw new AuthError(
            classifyHttpError(loginResult.response?.status, loginResult.error),
          );
        }
      } catch (err) {
        throw toAuthError(err);
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: SESSION_KEY });
    },
  });
}

/**
 * 로그아웃 뮤테이션. 204 멱등 — 성공/실패 무관하게 세션 무효화로 로그아웃 상태 반영.
 * (쿠키는 서버가 제거하고, 클라는 authMe 재조회로 401=미로그인을 확인한다.)
 */
export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: async () => {
      // 이번 세션 종료는 **수동 로그아웃**임을 표시 — SessionKeeper 가 곧이은 세션 null 전이를
      // 만료로 오인해 "로그인 시간 만료" 안내·리다이렉트를 띄우지 않게 한다(만료 ≠ 자발적 로그아웃).
      markManualLogout();
      // 멱등 — 본문 없이 호출(웹은 쿠키 폴백). 실패해도 아래 onSettled가 세션을 재확인한다.
      await authLogout({ body: {} });
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: SESSION_KEY });
    },
  });
}
