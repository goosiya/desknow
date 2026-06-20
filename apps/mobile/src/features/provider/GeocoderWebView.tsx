import { useEffect, useRef, useState } from "react";
import { StyleSheet } from "react-native";
import { WebView, type WebViewMessageEvent } from "react-native-webview";

import type { GeocodeResult } from "@/lib/api-client";

// 가입 전(pendingSignup) 주소 검색용 카카오 Geocoder WebView — 웹 geocodeViaKakaoJs RN 대체
// (Story 9.3 — AC4·§범위 2). 가입 전 provider는 백엔드 /rooms/geocode(provider 전용)를 못 쓰므로,
// 9.1 WebView 카카오맵 패턴을 재사용해 `services` 라이브러리를 로드한 **보이지 않는** WebView에서
// `kakao.maps.services.Geocoder().addressSearch`를 돌리고 결과를 백엔드 GeocodeResult 형상으로
// 통일해 postMessage로 RN에 회신한다. WebView는 캔버스/지도가 아니라 지오코딩 브릿지만 담당한다.
//
// ⚠️ Expo Web=react-native-webview 미지원(맵 degrade와 동형) → 가입 전 지오코딩은 Playwright
//    검증 불가(AC9 인지 한계). 네이티브 dev-build에서만 실동작. origin 화이트리스트(baseUrl)는
//    9.1 MapWebView 상수 동형(deferred 회수 후보=env화 EXPO_PUBLIC_KAKAO_WEBVIEW_ORIGIN).

// 카카오 콘솔 등록 WebView origin(JS 키 화이트리스트) — 9.1 MapWebView/RoomLocationMap 동형.
const KAKAO_WEBVIEW_ORIGIN = "http://localhost:3000";

type GeocoderWebViewProps = {
  // 검색어. nonce가 바뀔 때마다 이 query로 addressSearch를 실행한다.
  query: string;
  // 검색 트리거 — RoomForm이 "검색" 누를 때 증가시킨다(0=미실행).
  nonce: number;
  // 검색 결과(GeocodeResult 형상으로 통일됨) — RoomForm이 usable 필터·선택 처리.
  onResults: (results: GeocodeResult[]) => void;
  // SDK 로드/검색 실패 — RoomForm이 graceful 안내("주소 검색에 실패했어요…").
  onError: () => void;
};

/** services 라이브러리 로드 카카오 SDK HTML — window.__search(query)로 addressSearch 실행·결과 회신. */
function buildGeocoderHtml(jsKey: string): string {
  return `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<script src="//dapi.kakao.com/v2/maps/sdk.js?appkey=${jsKey}&autoload=false&libraries=services"></script>
</head>
<body>
<script>
  function post(msg) {
    if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(msg));
  }
  function init() {
    if (!window.kakao || !window.kakao.maps) { post({ type: 'error', message: 'sdk-unavailable' }); return; }
    try {
      kakao.maps.load(function () {
        var geocoder = new kakao.maps.services.Geocoder();
        window.__search = function (query) {
          try {
            geocoder.addressSearch(query, function (data, status) {
              if (status === 'ZERO_RESULT') { post({ type: 'results', results: [] }); return; }
              if (status !== 'OK' || !Array.isArray(data)) { post({ type: 'error', message: 'search-failed' }); return; }
              var out = data.map(function (d) {
                var bcode = (d.address && d.address.b_code) || (d.road_address && d.road_address.b_code) || '';
                return { address: d.address_name, lat: Number(d.y), lng: Number(d.x), admin_dong_code: bcode };
              });
              post({ type: 'results', results: out });
            });
          } catch (e) {
            post({ type: 'error', message: 'search-threw' });
          }
        };
        post({ type: 'ready' });
      });
    } catch (e) {
      post({ type: 'error', message: 'init-failed' });
    }
  }
  init();
</script>
</body>
</html>`;
}

export function GeocoderWebView({ query, nonce, onResults, onError }: GeocoderWebViewProps) {
  const jsKey = process.env.EXPO_PUBLIC_KAKAO_JS_KEY;
  const webRef = useRef<WebView>(null);
  const [ready, setReady] = useState(false);
  // ready 전에 들어온 검색을 보류했다가 ready 직후 1회 실행한다(SDK 로드 레이스).
  const pendingNonce = useRef(0);

  // 키 부재 → 즉시 graceful 실패(웹 키 부재 degrade 동형).
  useEffect(() => {
    if (!jsKey) onError();
  }, [jsKey, onError]);

  // nonce 변화 → 검색 실행(ready면 즉시, 아니면 보류 후 ready에서 flush).
  useEffect(() => {
    if (nonce === 0) return;
    if (ready) {
      webRef.current?.injectJavaScript(
        `window.__search(${JSON.stringify(query)}); true;`,
      );
    } else {
      pendingNonce.current = nonce;
    }
  }, [nonce, ready, query]);

  const handleMessage = (e: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(e.nativeEvent.data) as {
        type: string;
        results?: GeocodeResult[];
      };
      if (msg.type === "ready") {
        setReady(true);
        // ready 전 보류된 검색이 있으면 1회 실행.
        if (pendingNonce.current !== 0) {
          webRef.current?.injectJavaScript(
            `window.__search(${JSON.stringify(query)}); true;`,
          );
          pendingNonce.current = 0;
        }
      } else if (msg.type === "results") {
        onResults(msg.results ?? []);
      } else if (msg.type === "error") {
        onError();
      }
    } catch {
      // 브릿지 메시지가 아닌 잡음 — 무시.
    }
  };

  if (!jsKey) return null;

  return (
    <WebView
      ref={webRef}
      originWhitelist={["*"]}
      source={{ html: buildGeocoderHtml(jsKey), baseUrl: KAKAO_WEBVIEW_ORIGIN }}
      onMessage={handleMessage}
      onError={onError}
      onHttpError={onError}
      javaScriptEnabled
      domStorageEnabled
      // 보이지 않는 브릿지 — 화면에 지도/캔버스를 그리지 않는다(지오코딩 전용).
      style={styles.hidden}
      pointerEvents="none"
    />
  );
}

const styles = StyleSheet.create({
  hidden: { position: "absolute", width: 0, height: 0, opacity: 0 },
});
