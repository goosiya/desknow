// 관리자 로그인/로그아웃 액션 (Story 8.1, AC1·AC2·AC3). 백엔드 호출은 생성 SDK 경유만(1.9 가드).
//
// 로그인은 기존 `POST /auth/login`(1.8)을 재사용한다 — 관리자 전용 로그인 엔드포인트는 없다.
// 로그인 성공 후 `/auth/me`로 role을 확인해 **비-admin이면 즉시 로그아웃**(관리자 셸 비노출).
// 백엔드 403이 최종 강제(AC2)이고, 이 프론트 차단은 보조다(아키텍처 L167).
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { authLogin, authLogout, authMe } from "@/lib/api-client";
import { SESSION_KEY } from "./useSession";

/** 로그인 결과 — UI 카피 분기용. */
export type LoginOutcome = "ok" | "invalid" | "not-admin" | "network";

/**
 * 관리자 로그인 뮤테이션. 성공 시 세션 캐시를 무효화해 새로고침 없이 상태가 갱신된다(3.7 의무).
 *
 * - 401 → "invalid"(이메일/비번 오류 — enumeration 비노출 단일 카피)
 * - 네트워크/5xx → "network"
 * - 로그인 성공 & role!=admin → 즉시 로그아웃 후 "not-admin"(관리자 권한 없음)
 * - 로그인 성공 & role==admin → 세션 invalidate 후 "ok"
 */
export function useAdminLogin() {
  const queryClient = useQueryClient();
  return useMutation<LoginOutcome, never, { email: string; password: string }>({
    mutationFn: async ({ email, password }) => {
      let login;
      try {
        login = await authLogin({ body: { email, password }, throwOnError: false });
      } catch {
        return "network"; // fetch reject(서버 단절 등)
      }
      if (login.response?.status === 401) return "invalid";
      if (!login.response?.ok) return "network";

      // 로그인 성공 — 쿠키 set됨. role 확인을 위해 /me 조회.
      // ⚠️ 여기서부터 쿠키는 이미 살아있다. /me가 실패해도(쿠키 미전파 race·5xx) 세션 캐시를
      // 반드시 invalidate해야 한다 — 안 그러면 "네트워크 끊김" 안내와 달리 다음 useSession
      // refetch에서 조용히 로그인되어 안내와 모순된다(쿠키 잔존 + stale null 불일치 방지).
      let me;
      try {
        me = await authMe({ throwOnError: false });
      } catch {
        await queryClient.invalidateQueries({ queryKey: SESSION_KEY });
        return "network";
      }
      if (!me.response?.ok || !me.data) {
        await queryClient.invalidateQueries({ queryKey: SESSION_KEY });
        return "network";
      }

      if (me.data.role !== "admin") {
        // 비-admin 로그인 → 세션 정리(관리자 셸 비노출). 백엔드 403이 최종이지만 프론트도 차단.
        try {
          await authLogout({ body: {} });
        } catch {
          /* 로그아웃 실패는 무시 — 어차피 not-admin 안내 */
        }
        await queryClient.invalidateQueries({ queryKey: SESSION_KEY });
        return "not-admin";
      }

      await queryClient.invalidateQueries({ queryKey: SESSION_KEY });
      return "ok";
    },
  });
}

/** 로그아웃 뮤테이션. refresh 해시 무효화 + 쿠키 만료 후 세션 캐시를 무효화한다(멱등). */
export function useAdminLogout() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: async () => {
      await authLogout({ body: {}, throwOnError: true });
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: SESSION_KEY });
    },
  });
}
