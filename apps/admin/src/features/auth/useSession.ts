// 세션(인증 상태) 단일 출처 (Story 8.1 — admin 프론트 인증 상태). web 미러.
//
// `GET /api/v1/auth/me`(authMe)로 로그인 여부를 판별한다. 200=로그인(UserPublic), 401=미로그인.
// **401만 `null`로 정규화**한다(게이팅 분기용 — 미로그인은 실패가 아니라 정상 상태). 네트워크
// 단절·5xx 같은 **진짜 오류는 에러로 전파**해 소비처가 "로그아웃 UI"가 아니라 오류/재시도 상태를
// 보이도록 한다(web useSession와 동형). 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드).
//
// ⚠️ 관리자 권한 판정(role === "admin")은 useAdminSession(아래)이 파생한다 — 셸 게이트가 소비.
import { useQuery } from "@tanstack/react-query";

import { authMe, type UserPublic } from "@/lib/api-client";

/** 세션 캐시 키 — 로그인/로그아웃 핸들러가 invalidate 대상으로 공유한다. */
export const SESSION_KEY = ["auth", "me"] as const;

/** 인증 상태 쿼리. `data`=UserPublic(로그인) | null(미로그인=401). 진짜 오류는 `isError`로 노출. */
export function useSession() {
  return useQuery<UserPublic | null>({
    queryKey: SESSION_KEY,
    queryFn: async () => {
      const { data, response } = await authMe({ throwOnError: false });
      if (response?.status === 401) {
        return null; // 미로그인 — 정상 분기(에러 아님)
      }
      if (!response?.ok) {
        // 네트워크/5xx 등 진짜 오류(또는 응답 없음) → 에러 전파(소비처가 로그아웃 UI 대신 오류/재시도).
        throw new Error(`auth/me 응답 오류: ${response?.status ?? "no-response"}`);
      }
      return data ?? null;
    },
    staleTime: 5 * 60_000,
    retry: false,
  });
}

/** 관리자 게이트용 파생 — 로딩/세션/관리자 여부를 한데 노출한다(셸·페이지가 소비). */
export function useAdminSession() {
  const query = useSession();
  const session = query.data ?? null;
  return {
    ...query,
    session,
    isAdmin: session?.role === "admin",
  };
}
