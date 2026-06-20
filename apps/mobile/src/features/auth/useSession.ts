// 세션(인증 상태) 단일 출처 — 웹 useSession RN 포팅 (Story 9.1 — AC1).
//
// 웹과 **동일**하다: `GET /auth/me`(authMe)로 로그인 여부를 판별하고 200=UserPublic·401=null로
// 정규화한다. 401만 null(미로그인=정상 분기), 네트워크/5xx 등 진짜 오류는 에러로 전파한다(소비처가
// "로그아웃 UI"가 아니라 오류/재시도). 차이는 인증 전송뿐 — 웹은 쿠키, 모바일은 Bearer 헤더이며
// 그 헤더 주입은 api-client.ts 인터셉터가 책임진다(이 훅은 무관).
//
// `_layout.tsx` 부팅 복원이 같은 캐시를 prefetch로 채우도록 queryKey/queryFn을 export한다.
import { useQuery } from "@tanstack/react-query";

import { authMe, type UserPublic } from "@/lib/api-client";

/** 세션 쿼리 키(인증 액션 성공 후 무효화·부팅 prefetch 대상). */
export const SESSION_QUERY_KEY = ["auth", "me"] as const;

/** authMe 호출 → UserPublic(로그인) | null(401=미로그인). 진짜 오류는 throw. 부팅 복원이 재사용. */
export async function fetchSession(): Promise<UserPublic | null> {
  const { data, response } = await authMe({ throwOnError: false });
  if (response?.status === 401) {
    return null; // 미로그인 — 정상 분기(에러 아님)
  }
  if (!response?.ok) {
    // 네트워크/5xx 등 진짜 오류(또는 응답 없음) → 에러 전파(소비처가 로그아웃 UI 대신 오류/재시도).
    throw new Error(`auth/me 응답 오류: ${response?.status ?? "no-response"}`);
  }
  return data ?? null;
}

/** 인증 상태 쿼리. `data`=UserPublic(로그인) | null(미로그인=401). 진짜 오류는 `isError`로 노출. */
export function useSession() {
  return useQuery<UserPublic | null>({
    queryKey: SESSION_QUERY_KEY,
    queryFn: fetchSession,
    // 세션은 자주 안 바뀌므로 5분 fresh. retry:false — 401은 throw 안 하니 재시도 무의미하고,
    // 네트워크/5xx 오류는 즉시 isError로 노출해 소비처가 "다시 시도"로 사용자 주도 재시도한다.
    staleTime: 5 * 60_000,
    retry: false,
  });
}
