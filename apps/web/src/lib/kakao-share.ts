// 카카오 JS SDK(Share) 동적 로더 + 공유 호출 (Story 5.4 — FR-19 · UJ-1 climax).
//
// **maps SDK 와는 별개 SDK 다(중요):** maps(`dapi.kakao.com/v2/maps/sdk.js`)는 `window.kakao`
// (소문자·maps 네임스페이스)만 노출해 `Kakao.Share` 가 없다. 공유는 카카오 JS SDK
// (`t1.kakaocdn.net/kakao_js_sdk/...kakao.min.js`)를 별도 주입해야 `window.Kakao`(대문자·
// `.init`/`.Share`/`.isInitialized`)가 생긴다. → kakao-map.ts 로더 패턴을 **미러**하되 별도
// 로더로 둔다(Promise 캐시·중복 주입 가드·도메인 거부 reject·재시도 + AC5 `<script>` 정리).
//
// **키 격리(NFR-6):** 공유도 maps 와 같은 도메인 화이트리스트 JS 키 하나(`NEXT_PUBLIC_KAKAO_JS_KEY`)
// 를 쓴다(한 앱=한 JS 키 — 신규 env 0). 키 미설정/도메인 거부/로드 실패는 reject 되어
// KakaoShareButton 이 AC4 graceful degrade(친근한 안내 + 재시도)로 처리한다(throw 전파 금지).
//
// SDK 는 전역 `fetch` 가 아니라 `<script>` 주입이라 eslint no-direct-fetch 가드와 무관하다(maps 동일).
import { buildReservationShareText } from "@/features/reservation/share";

// 카카오 JS SDK(공유) v2.7.6. SRI integrity 는 해당 kakao.min.js 바이트로 직접 산출한 검증값이다
// (sha384, CDN 결정적 — 버전 고정 시 불변). crossOrigin="anonymous" 와 함께 변조된 SDK 로드를 차단.
const SDK_URL = "https://t1.kakaocdn.net/kakao_js_sdk/2.7.6/kakao.min.js";
const SDK_INTEGRITY =
  "sha384-WAtVcQYcmTO/N+C1N+1m6Gp8qxh+3NlnP7X1U7qP6P5dQY/MsRBNTh+e1ahJrkEm";

let loadPromise: Promise<typeof Kakao> | null = null;

function injectScript(jsKey: string): Promise<typeof Kakao> {
  return new Promise((resolve, reject) => {
    if (typeof document === "undefined") {
      reject(new Error("카카오 공유 SDK 는 브라우저에서만 로드할 수 있습니다."));
      return;
    }
    const script = document.createElement("script");
    script.src = SDK_URL;
    script.integrity = SDK_INTEGRITY;
    script.crossOrigin = "anonymous";
    script.async = true;
    script.addEventListener("load", () => {
      // AC5(의무 회수) — load 후 `<script>` 제거. SDK 는 로드되면 전역 `window.Kakao` 에 붙으므로
      // 태그를 떼도 사용 가능하다(dead `<script>` 누적 방지). kakao-map.ts 정리와 동형.
      script.remove();
      // 핸들러 내부 throw 는 Promise executor 밖이라 reject 로 안 잡혀 Promise 가 영영 settle 안 되고
      // (코드리뷰 P1) loadPromise 가 비워지지 않아 버튼이 영구 hang(재시도·안내 불가) → AC4 무력화.
      // 본문 전체를 try/catch 로 감싸 어떤 throw 든 reject 로 전파한다(graceful degrade·재시도 보장).
      try {
        // 스크립트가 200으로 로드돼도 본문이 SDK 가 아니거나(도메인 거부·차단 응답) 광고차단/확장이
        // 서브표면 없는 스텁 `window.Kakao` 를 심으면 `.isInitialized`/`.init`/`.Share` 가 없다.
        // top-level 만 보던 가드를 **실제 호출 서브표면**까지 확장해 명시 reject 한다(maps 로더의
        // `window.kakao?.maps` 서브객체 가드 동형 — AC4 graceful degrade).
        // 스텁 가드(광고차단·차단 응답): top-level init/isInitialized 는 init 전에도 존재해야 한다.
        if (
          typeof window.Kakao?.isInitialized !== "function" ||
          typeof window.Kakao.init !== "function"
        ) {
          reject(
            new Error("카카오 공유 SDK 가 초기화되지 않았습니다 (잘못된 키 또는 차단된 응답)."),
          );
          return;
        }
        // ⚠️ init 을 먼저 한다 — `Kakao.Share` 네임스페이스는 `init()` *이후*에 생성된다(SDK 2.7.x
        // 실측: init 전 Kakao.Share=undefined). 멱등(이미 init 됐으면 재호출 안 함 — 중복 init 경고 회피).
        if (!window.Kakao.isInitialized()) {
          window.Kakao.init(jsKey);
        }
        // init 후에야 Share 서브표면이 존재한다 — 이제 검사한다(스텁/차단 응답이면 여기서 reject).
        // (init 전에 검사하면 정상 SDK 도 항상 실패 → 공유 영구 불가였던 버그를 바로잡음.)
        if (typeof window.Kakao.Share?.sendDefault !== "function") {
          reject(
            new Error("카카오 공유 SDK 가 초기화되지 않았습니다 (잘못된 키 또는 차단된 응답)."),
          );
          return;
        }
        resolve(window.Kakao);
      } catch (err: unknown) {
        // init/isInitialized 가 throw(잘못된 키 포맷·스텁) 해도 reject 로 흡수 — hang 금지(P1).
        reject(
          err instanceof Error
            ? err
            : new Error("카카오 공유 SDK 초기화에 실패했습니다."),
        );
      }
    });
    script.addEventListener("error", () => {
      script.remove(); // AC5 — 실패 태그도 정리(반복 재시도 시 dead `<script>` 누적 방지).
      reject(new Error("카카오 공유 SDK 스크립트를 불러오지 못했습니다."));
    });
    document.head.appendChild(script);
  });
}

/**
 * 카카오 JS SDK(공유)를 로드·초기화하고 전역 `Kakao` 를 반환한다.
 *
 * - 키(`NEXT_PUBLIC_KAKAO_JS_KEY`) 미설정 시 reject(graceful degrade — AC4).
 * - 중복/동시 호출은 같은 Promise 를 공유한다(스크립트 1회 주입). 한 번 실패하면 다음 호출이
 *   재시도할 수 있도록 캐시를 비운다(KakaoShareButton 재시도 — AC4). kakao-map.ts 동형.
 */
export function loadKakaoShare(): Promise<typeof Kakao> {
  if (loadPromise) {
    return loadPromise;
  }
  const jsKey = process.env.NEXT_PUBLIC_KAKAO_JS_KEY;
  if (!jsKey) {
    // 캐시하지 않는다(키 주입 후 재시도 가능). 즉시 reject.
    return Promise.reject(
      new Error("NEXT_PUBLIC_KAKAO_JS_KEY 가 설정되지 않았습니다."),
    );
  }
  loadPromise = injectScript(jsKey).catch((err: unknown) => {
    loadPromise = null; // 실패 시 재시도 허용(AC4 재시도).
    throw err;
  });
  return loadPromise;
}

/**
 * 확정 예약을 카카오톡으로 공유한다(AC1·AC2) — 한 번의 호출 = 공유 시트 1회(추가 단계 없음).
 *
 * SDK 를 lazy 로드(클릭 이벤트 시점 — mount-effect 아님)한 뒤 text 템플릿으로 룸·일시 + 룸 상세
 * 딥링크를 공유한다. 링크 = `{origin}/rooms/{roomId}`(등록 도메인·예약현황 행 Link 와 동일 경로 —
 * 수신자가 같은 룸을 바로 본다). 로드/초기화 실패는 reject 로 전파해 호출처가 graceful degrade 한다.
 */
export async function shareReservation({
  roomName,
  slotStarts,
  roomId,
}: {
  roomName: string;
  slotStarts: string[];
  roomId: string;
}): Promise<void> {
  const kakao = await loadKakaoShare();
  const url = `${window.location.origin}/rooms/${roomId}`;
  kakao.Share.sendDefault({
    objectType: "text",
    text: buildReservationShareText(roomName, slotStarts),
    link: { webUrl: url, mobileWebUrl: url },
  });
}
