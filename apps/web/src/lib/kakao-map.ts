// 카카오 지도 SDK 동적 로더 (Story 3.2 — Phase 0 스파이크 1.3 패턴을 프로덕션으로 이식).
//
// SDK 를 `<script>` 로 동적 주입하고 `kakao.maps.load(cb)` 로 명시 초기화한다
// (`autoload=false` → 자동 init 끔). 스크립트는 **1회만** 주입하고, 동시/반복 호출은 같은
// Promise 를 공유한다(중복 로드 가드). 로드 완료 시 전역 `window.kakao` 가 준비된다.
//
// **키 격리(NFR-6):** 프론트 노출 키는 도메인 화이트리스트 JS 키 하나뿐
// (`NEXT_PUBLIC_KAKAO_JS_KEY`). REST 키는 절대 프론트에서 쓰지 않는다 — 본 스토리는 저장된
// `lat`/`lng` 를 쓰므로 지오코딩(REST) 호출이 없다. 키 미설정/로드 실패는 reject 되어
// 화면이 AC5③ "지도를 못 불러왔어요" 에러 상태로 graceful degrade 한다.
//
// SDK 는 전역 `fetch` 가 아니라 `<script>` 주입이라 eslint no-direct-fetch 가드와 무관하다.

const SDK_BASE_URL = "//dapi.kakao.com/v2/maps/sdk.js";

let loadPromise: Promise<typeof kakao> | null = null;

function injectScript(jsKey: string): Promise<typeof kakao> {
  return new Promise((resolve, reject) => {
    if (typeof document === "undefined") {
      reject(new Error("카카오 지도 SDK 는 브라우저에서만 로드할 수 있습니다."));
      return;
    }
    const script = document.createElement("script");
    // autoload=false → kakao.maps.load(cb) 로 명시 초기화(동기 사용 금지 — 스파이크 실측).
    // libraries=services → 주소→좌표 Geocoder 포함(provider 가입 전 미인증 주소 검색용 — 백엔드
    // /rooms/geocode 는 provider 전용이라, 가입 폼에선 이 프론트 Geocoder 로 직접 검색한다. KTH 2026-06-19).
    script.src = `${SDK_BASE_URL}?appkey=${jsKey}&autoload=false&libraries=services`;
    script.async = true;
    script.addEventListener("load", () => {
      // 스크립트가 200으로 로드돼도 본문이 SDK 가 아니면(도메인 거부 키의 비-SDK 응답·광고차단
      // 스텁·프록시 오류 페이지) window.kakao 가 없다. 여기서 window.kakao.maps 를 그냥 호출하면
      // 핸들러 내부에서 TypeError 가 던져지는데, 이는 Promise executor 밖이라 reject 로 잡히지
      // 않아 Promise 가 영영 settle 되지 않는다 → 화면이 로딩 스켈레톤에 영구 고정된다.
      // 명시적으로 reject 해 AC5③ "지도를 못 불러왔어요" 에러 상태로 보낸다(재시도 가능).
      if (!window.kakao?.maps) {
        script.remove(); // AC5 회수 — 실패(비-SDK) 태그도 정리(dead `<script>` 누적 방지).
        reject(
          new Error("카카오 지도 SDK 가 초기화되지 않았습니다 (잘못된 키 또는 차단된 응답)."),
        );
        return;
      }
      // 스크립트 로드 ≠ maps 초기화 완료. kakao.maps.load 콜백 후에야 Map/LatLng 가 준비된다.
      // AC5 회수(Story 5.4 · deferred-work.md L60) — `<script>` 정리는 **maps.load 콜백 안**(초기화
      // 완료 후)에서 한다. maps.load 는 딸린 라이브러리를 비동기 fetch 하며 일부 SDK 빌드가 그 시점에
      // `<script>` 태그의 appkey 를 재스캔하므로, 호출 전에 태그를 떼면 maps 로드가 깨질 수 있다
      // (코드리뷰 P2 — 기존 maps 동작 회귀 방지). dead `<script>` 정리 목적은 그대로 충족.
      window.kakao.maps.load(() => {
        script.remove();
        resolve(window.kakao);
      });
    });
    script.addEventListener("error", () => {
      script.remove(); // AC5 회수 — 실패 태그도 정리(반복 재시도 시 dead `<script>` 누적 방지).
      reject(new Error("카카오 지도 SDK 스크립트를 불러오지 못했습니다."));
    });
    document.head.appendChild(script);
  });
}

/**
 * 카카오 지도 SDK 를 로드하고 초기화 완료된 전역 `kakao` 를 반환한다.
 *
 * - 키(`NEXT_PUBLIC_KAKAO_JS_KEY`) 미설정 시 reject(에러 상태로 degrade).
 * - 중복 호출/동시 호출은 같은 Promise 를 공유한다(스크립트 1회 주입). 단 한 번 실패하면
 *   다음 호출이 재시도할 수 있도록 캐시를 비운다(재시도 버튼 — AC5③).
 */
export function loadKakaoMaps(): Promise<typeof kakao> {
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
    loadPromise = null; // 실패 시 재시도 허용(AC5③ 재시도 버튼).
    throw err;
  });
  return loadPromise;
}
