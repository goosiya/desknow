// 인증 액션(로그인·회원가입·로그아웃) 뮤테이션 훅 — 웹 useAuth.ts RN 포팅 (Story 9.1 — AC1·AC2).
//
// 세션 상태 단일 출처는 useSession(["auth","me"] 쿼리)이다. 이 훅들은 SDK 인증 함수를 호출한 뒤
// **반드시 ["auth","me"]를 invalidate**해 세션이 즉시 갱신되게 한다(로그인/가입 후 화면 분기).
//
// ⚠️ 웹과의 유일한 차이(ADR-9.1-A): 웹은 httpOnly 쿠키라 응답 본문 토큰을 **무시**하지만, 모바일은
//    로그인/refresh 응답 본문 `TokenResponse`를 **secure-store에 저장**한다(saveTokenResponse). 이후
//    모든 SDK 호출에 api-client.ts 인터셉터가 Bearer 헤더를 주입한다. 로그아웃은 쿠키가 없으므로
//    refresh 토큰을 **본문**으로 보내고 secure-store를 비운다. 분류 로직(AuthFailure·classifyHttpError)
//    은 웹 그대로 복사(RN 의존성 없음).
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { authLogin, authLogout, authRegister } from "@/lib/api-client";
import {
  clearTokens,
  getRefreshToken,
  saveTokenResponse,
} from "@/lib/session-store";

import { markManualLogout } from "./sessionExpiry";
import { SESSION_QUERY_KEY } from "./useSession";

/** 인증 실패 분류 — 화면이 카피를 분기하기 위한 판별 결과(웹과 동일). */
export type AuthFailure =
  | { kind: "unauthorized" } // 로그인 401 — 자격 오류
  | { kind: "conflict" } // 가입 409 — 이메일 중복
  | { kind: "validation"; message: string } // 가입 422 — 정책 위반(서버 message)
  | { kind: "network" } // 네트워크 단절(fetch reject)
  | { kind: "unknown"; status?: number }; // 그 외(5xx 등)

/**
 * SDK 호출 결과({ error, response })를 AuthFailure로 정규화한다.
 * throwOnError:false 라 HTTP 오류는 `{ data, error, response }`로 돌아오고(response.status로 식별),
 * 네트워크 reject만 호출부에서 throw 된다.
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

/** AuthFailure를 mutation 오류로 던지기 위한 래퍼 — error.failure로 꺼내 카피 분기한다. */
export class AuthError extends Error {
  failure: AuthFailure;
  constructor(failure: AuthFailure) {
    super(failure.kind);
    this.name = "AuthError";
    this.failure = failure;
  }
}

/** 네트워크 reject(TypeError 등)인지 — SDK가 응답을 못 받은 경우 network로 정규화. */
function toAuthError(err: unknown): AuthError {
  if (err instanceof AuthError) return err;
  return new AuthError({ kind: "network" });
}

/**
 * 로그인 뮤테이션. 성공 시 응답 본문 토큰을 secure-store에 저장(웹과 갈리는 지점) 후 세션 무효화.
 * 실패는 AuthError(failure로 카피 분기)로 throw 된다.
 */
export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation<void, AuthError, { email: string; password: string }>({
    mutationFn: async ({ email, password }) => {
      try {
        const { data, error, response } = await authLogin({
          body: { email, password },
          throwOnError: false,
        });
        if (!response?.ok || !data) {
          throw new AuthError(classifyHttpError(response?.status, error));
        }
        // 모바일은 Bearer 인증 — 응답 본문 TokenResponse를 secure-store에 저장한다(웹은 쿠키라 무시).
        await saveTokenResponse(data);
      } catch (err) {
        throw toAuthError(err);
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
    },
  });
}

/** 가입 역할 — 예약자(booker) 또는 스터디룸 제공자(provider). */
export type SignupRole = "booker" | "provider";

/**
 * 회원가입 뮤테이션(booker 완결 경로). register는 토큰을 주지 않으므로(UserPublic 201) 웹과 동일하게
 * **register→자동 로그인 연쇄**를 유지하고, 그 로그인 응답 토큰을 secure-store에 저장한다.
 * (provider는 register를 룸 등록까지 지연하므로 이 훅을 호출하지 않는다 — SignupView 참조, §범위 2.)
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
        const register = await authRegister({
          body: { email, password, role },
          throwOnError: false,
        });
        if (!register.response?.ok) {
          throw new AuthError(
            classifyHttpError(register.response?.status, register.error),
          );
        }
        // 가입 성공 → 자동 로그인 연쇄(같은 자격으로 토큰 발급). 로그인 실패는 그대로 전파.
        const login = await authLogin({
          body: { email, password },
          throwOnError: false,
        });
        if (!login.response?.ok || !login.data) {
          throw new AuthError(
            classifyHttpError(login.response?.status, login.error),
          );
        }
        await saveTokenResponse(login.data);
      } catch (err) {
        throw toAuthError(err);
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
    },
  });
}

/**
 * 로그아웃 뮤테이션. 쿠키가 없으므로 refresh 토큰을 **본문**으로 보내고 secure-store를 비운다.
 * 204 멱등 — 성공/실패 무관하게 세션 무효화로 로그아웃 상태를 반영한다.
 */
export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: async () => {
      // 수동 로그아웃 표시 — SessionKeeper 가 뒤따르는 로그인→null 전이를 "만료"로 오인해
      // /login?expired=1 안내를 띄우지 않게 한다(만료 아님 — sessionExpiry 1-bit 신호).
      markManualLogout();
      // 서버에 refresh 토큰 폐기를 요청(본문 전송). 실패해도 아래 onSettled가 세션을 재확인한다.
      const refresh_token = await getRefreshToken();
      try {
        await authLogout({
          body: refresh_token ? { refresh_token } : {},
          throwOnError: false,
        });
      } finally {
        // 로컬 토큰은 무조건 비운다(서버 호출 실패와 무관 — 기기에서 로그아웃 보장).
        await clearTokens();
      }
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY });
    },
  });
}
