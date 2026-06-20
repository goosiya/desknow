// 세션(인증 상태) 단일 출처 (Story 3.7 — web 최초 프론트 인증 상태, AC4·AC5).
//
// `GET /api/v1/auth/me`(authMe)로 로그인 여부를 판별한다. 200=로그인(UserPublic), 401=미로그인.
// **401만 `null`로 정규화**한다(게이팅 분기용 — 미로그인은 실패가 아니라 정상 상태). 네트워크
// 단절·5xx 같은 **진짜 오류는 에러로 전파**해 소비처가 "로그아웃 UI"가 아니라 오류/재시도 상태를
// 보이도록 한다(code-review 결정 — 일시 장애 시 로그인 사용자가 5분간 로그아웃처럼 보이는 문제
// 해소). throwOnError:false 라 HTTP 오류는 `{ data, error, response }`로 돌아오고(`response.status`로
// 401 식별), 네트워크 reject는 queryFn 밖으로 throw 되어 그대로 쿼리 오류가 된다.
//
// 이것이 후속 스토리(상세 4.2·예약 E4)가 재사용할 프론트 인증 상태 단일 출처다. 백엔드 호출은
// 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드).
import { useQuery } from "@tanstack/react-query";

import { authMe, type UserPublic } from "@/lib/api-client";

/** 인증 상태 쿼리. `data`=UserPublic(로그인) | null(미로그인=401). 진짜 오류는 `isError`로 노출. */
export function useSession() {
  return useQuery<UserPublic | null>({
    queryKey: ["auth", "me"],
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
    // 세션은 자주 안 바뀌므로 5분 fresh. retry:false — 401은 throw 안 하니 재시도 무의미하고,
    // 네트워크/5xx 오류는 즉시 isError로 노출해 소비처가 "다시 시도" 버튼으로 사용자 주도 재시도한다.
    staleTime: 5 * 60_000,
    retry: false,
  });
}
