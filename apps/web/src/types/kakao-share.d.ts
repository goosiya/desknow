// 카카오 JS SDK(Share) 최소 ambient 타입 (Story 5.4).
//
// maps SDK(`window.kakao` 소문자·`kakao-maps.d.ts`)와는 **별개 SDK**다. 공유 SDK
// (`t1.kakaocdn.net/kakao_js_sdk/...`)는 `<script>` 주입 후 전역 `window.Kakao`(대문자)로
// 노출되며 `.init`/`.isInitialized`/`.Share` 를 제공한다. 공식 타입 패키지가 없으므로
// **본 스토리가 실제로 쓰는 표면만** 선언한다(over-declare 금지 — maps 타입 패턴).

declare global {
  interface Window {
    Kakao?: typeof Kakao;
  }

  namespace Kakao {
    /** JS 앱 키로 SDK 를 1회 초기화한다(중복 init 시 경고 — isInitialized 가드 필요). */
    function init(jsKey: string): void;

    /** 이미 init 됐는지 — 멱등 초기화 가드. */
    function isInitialized(): boolean;

    namespace Share {
      interface LinkObject {
        webUrl?: string;
        mobileWebUrl?: string;
      }

      /** text 템플릿 — 텍스트(≤200자) + 링크만(이미지 불요). */
      interface TextTemplate {
        objectType: "text";
        text: string;
        link: LinkObject;
      }

      /** 기본 템플릿으로 공유 시트를 1회 연다(추가 단계 없음 — AC1 "한 번에"). */
      function sendDefault(settings: TextTemplate): void;
    }
  }
}

export {};
