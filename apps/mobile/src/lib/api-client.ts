// mobile(Expo/RN) 백엔드 호출 배선 (Story 1.9 → 9.1 Bearer 인터셉터 확장).
//
// 백엔드 호출은 **오직 @desknow/api-client SDK로만** 한다(직접 fetch 금지 — eslint 가드로 강제,
// AC2). 이 모듈이 SDK 클라이언트의 baseUrl을 앱 시작 시 1회 설정하고 SDK를 re-export하므로,
// 소비처는 `@/lib/api-client`에서 SDK 함수/타입을 가져온다.
//
// 9.1 추가(ADR-9.1-A): 웹은 httpOnly 쿠키(`credentials:"include"`)지만 모바일은 secure-store
// 토큰 + `Authorization: Bearer` 헤더다. SDK `client`의 **request 인터셉터**로 매 요청 시 최신
// access 토큰을 읽어 헤더를 주입하고, **response 인터셉터**로 401을 1회 refresh 회전 후 재시도한다
// (웹 streamMessage.ts 401 재시도 패턴 미러). 백엔드는 헤더를 쿠키보다 먼저 추출하므로 무변경.
import { authRefresh, client, configureApiClient } from "@desknow/api-client";

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  saveTokenResponse,
} from "@/lib/session-store";

// baseUrl = 백엔드 **origin만**(경로 /api/v1/... 는 생성 SDK에 포함 → /api/v1 중복 금지, AC2).
// ⚠️ 실기기(Expo Go)는 localhost가 기기 자신을 가리키므로 백엔드에 닿지 못한다 →
//    EXPO_PUBLIC_API_BASE_URL을 개발 PC의 LAN IP(예: http://192.168.0.10:8000)로 설정해야 한다.
//    시뮬레이터/웹 미리보기 기본값으로 localhost를 둔다.
const explicitBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL;
// 운영/개발 분기: 운영 빌드(!__DEV__)에서 env 미설정이면 조용히 localhost(기기 자신)로 폴백해
// 전부 실패하는 대신 기동 즉시 fail-fast한다. 개발(__DEV__)은 시뮬레이터/웹 미리보기 편의로
// localhost 폴백을 유지한다(테스트/운영 구분 — 감사 회수).
if (!explicitBaseUrl && !__DEV__) {
  throw new Error(
    "EXPO_PUBLIC_API_BASE_URL이 설정되지 않았습니다(운영 빌드 필수). " +
      "백엔드 origin을 환경변수로 주입하세요(예: https://api.desknow.kr).",
  );
}
const baseUrl = explicitBaseUrl ?? "http://localhost:8000";

// credentials는 **추가하지 않는다**(웹 전용) — 모바일은 Bearer 헤더 인증이다(ADR-9.1-A).
configureApiClient({ baseUrl });

// ── Bearer 주입 + 401 refresh 재시도 인터셉터 ────────────────────────────────────────
// 인증 엔드포인트는 401 재시도 대상에서 제외한다: login/register는 자격 오류(401)를 화면 카피로
// 분기해야 하고(authCopy), refresh 자체는 재귀를 막기 위함이다.
function isAuthPath(url: string): boolean {
  return (
    url.includes("/auth/login") ||
    url.includes("/auth/register") ||
    url.includes("/auth/refresh") ||
    url.includes("/auth/logout")
  );
}

// 401 재시도용 원요청 클론 보관(원 Request는 fetch로 body가 소비되므로, 미소비 클론을 따로 둔다).
// 응답 인터셉터가 받는 request 참조는 요청 인터셉터가 반환한 그 객체와 동일하다(client.gen.ts).
const retryClones = new WeakMap<Request, Request>();

// 동시 401 다수를 단일 refresh로 합친다(토큰 회전 1회 — 무한 루프·중복 회전 방지).
let refreshInFlight: Promise<boolean> | null = null;

function refreshOnce(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const refresh_token = await getRefreshToken();
        if (!refresh_token) return false;
        // refresh는 쿠키가 없으므로 refresh 토큰을 **본문**으로 전송(ADR-9.1-A).
        const { data, response } = await authRefresh({
          body: { refresh_token },
          throwOnError: false,
        });
        if (response?.ok && data) {
          await saveTokenResponse(data);
          return true;
        }
        // refresh까지 실패(만료/회전/로그아웃) → 토큰 정리(다음 authMe가 401→세션 null로 전이).
        await clearTokens();
        return false;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

// request 인터셉터: 매 요청 시 secure-store 최신 access 토큰을 Bearer로 주입한다(토큰 변경에
// 자동 동기화 — client.gen.ts가 fns를 매 요청 실행). 재시도용 클론도 함께 보관한다.
client.interceptors.request.use(async (request) => {
  const token = await getAccessToken();
  if (token) {
    request.headers.set("Authorization", `Bearer ${token}`);
  }
  if (!isAuthPath(request.url)) {
    // body 미소비 클론을 보관 — 401 시 새 Bearer로 갈아끼워 재요청한다.
    retryClones.set(request, request.clone());
  }
  return request;
});

// response 인터셉터: 401 1회 → refresh 회전 → 새 토큰으로 원요청 재시도. 인증 엔드포인트는 제외.
// 재시도는 SDK 파이프라인을 다시 타지 않으므로(options.fetch 직접 호출) 재귀하지 않는다.
client.interceptors.response.use(async (response, request, options) => {
  const clone = retryClones.get(request);
  retryClones.delete(request);
  if (response.status !== 401 || isAuthPath(request.url) || !clone) {
    return response;
  }
  // SDK가 설정한 fetch(options.fetch)로 재요청 — 전역 fetch 금지 가드(AC2)에 저촉되지 않는다.
  // (런타임엔 항상 설정되나 타입상 optional이므로 방어: 없으면 원 401 반환.)
  const doFetch = options.fetch;
  if (!doFetch) return response;
  const refreshed = await refreshOnce();
  if (!refreshed) return response;
  const token = await getAccessToken();
  const retryReq = new Request(clone);
  if (token) {
    retryReq.headers.set("Authorization", `Bearer ${token}`);
  }
  try {
    return await doFetch(retryReq);
  } catch {
    return response; // 재시도 네트워크 실패 → 원 401 반환(소비처가 오류 처리).
  }
});

// 단일-flight 토큰 회전을 외부(SessionKeeper 슬라이딩 갱신)에 노출한다. 인터셉터의 401 재시도와
// 동일한 refreshInFlight 를 공유하므로 동시 호출도 1회 회전으로 합쳐진다(중복 회전·무한 루프 방지).
export function refreshSession(): Promise<boolean> {
  return refreshOnce();
}

// 생성 SDK 함수(authLogin·authRegister …)·타입(TokenResponse·ErrorResponse …)을 노출.
export * from "@desknow/api-client";
