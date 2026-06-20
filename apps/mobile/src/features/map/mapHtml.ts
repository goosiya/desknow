// WebView 카카오맵 HTML 빌더 (Story 9.1 — AC3 · ADR-9.1-B). WebView는 **지도 렌더 캔버스만**
// 담당한다 — 데이터(핀)는 RN이 SDK로 조회해 injectJavaScript로 주입하고(WebView는 직접 fetch 안
// 함 — 단일 SDK 데이터 경로·eslint 가드 정신 유지), 핀 탭은 postMessage 브릿지로 RN에 올린다.
//
// 웹 kakao-map.ts 패턴 재현: `<script src=...sdk.js?appkey=KEY&autoload=false>` + `kakao.maps.load(cb)`
// 명시 초기화. 키=JS 키만(REST 키 금지). 저장된 lat/lng를 쓰므로 지오코딩 불요(provider 지오코딩=9.3).
//
// ⚠️ origin 화이트리스트(가장 큰 함정): 카카오 JS SDK는 요청 origin을 콘솔 등록 도메인과 대조한다.
//    WebView `source={{ html, baseUrl }}`의 baseUrl을 카카오 콘솔 등록 origin으로 설정해야 거부되지
//    않는다(MapWebView가 KAKAO_WEBVIEW_ORIGIN으로 지정). 실패는 'error' 메시지 → AC5 "지도를 못
//    불러왔어요" graceful degrade로 떨어진다.

/** 카카오 마커 색·아이콘(웹 pinVisual 미러 — 토큰 hex 인라인). 색 단독 금지(아이콘 동반). */
const PIN_AVAILABLE_HEX = '#157F45';
const PIN_FULL_HEX = '#7E7466';

/**
 * 카카오맵 캔버스 HTML을 만든다. 초기 중심(lat/lng/level)은 생성 시 1회 주입한다(서울 폴백 또는
 * 내 위치). 이후 핀 주입·재중심은 RN이 injectJavaScript로 window.__setPins/__setCenter/__recenter를
 * 호출한다.
 */
export function buildMapHtml(
  jsKey: string,
  initLat: number,
  initLng: number,
  level: number,
): string {
  return `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
<style>
  html, body, #map { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: #F4EDDF; }
  .pin {
    display: flex; align-items: center; justify-content: center;
    width: 30px; height: 30px; border-radius: 50% 50% 50% 0;
    transform: rotate(-45deg); border: 2px solid #fff;
    box-shadow: 0 2px 6px rgba(40,32,15,0.3);
  }
  .pin > span { transform: rotate(45deg); color: #fff; font-size: 14px; font-weight: 700; line-height: 1; }
</style>
<script src="//dapi.kakao.com/v2/maps/sdk.js?appkey=${jsKey}&autoload=false"></script>
</head>
<body>
<div id="map"></div>
<script>
  function post(msg) {
    if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(msg));
  }
  var map = null;
  var overlays = [];
  function visual(status) {
    return status === 'available'
      ? { hex: '${PIN_AVAILABLE_HEX}', icon: '\\u2713' }
      : { hex: '${PIN_FULL_HEX}', icon: '\\u2715' };
  }
  function renderPins(pins) {
    if (!map) return;
    for (var i = 0; i < overlays.length; i++) overlays[i].setMap(null);
    overlays = [];
    for (var j = 0; j < pins.length; j++) {
      (function (pin) {
        var v = visual(pin.status);
        var el = document.createElement('div');
        el.className = 'pin';
        el.style.background = v.hex;
        el.setAttribute('role', 'button');
        el.setAttribute('aria-label', pin.name + ' 스터디룸, ' + (pin.status === 'available' ? '예약 가능' : '오늘 마감'));
        var span = document.createElement('span');
        span.setAttribute('aria-hidden', 'true');
        span.textContent = v.icon;
        el.appendChild(span);
        el.addEventListener('click', function () {
          post({ type: 'pinTap', room_id: pin.room_id, name: pin.name, status: pin.status });
        });
        var overlay = new kakao.maps.CustomOverlay({
          position: new kakao.maps.LatLng(pin.lat, pin.lng),
          content: el,
          yAnchor: 1,
        });
        overlay.setMap(map);
        overlays.push(overlay);
      })(pins[j]);
    }
  }
  window.__setPins = function (json) { try { renderPins(JSON.parse(json)); } catch (e) {} };
  window.__setCenter = function (lat, lng) { if (map) map.setCenter(new kakao.maps.LatLng(lat, lng)); };
  window.__recenter = function (lat, lng, lvl) {
    if (map) { map.setCenter(new kakao.maps.LatLng(lat, lng)); map.setLevel(lvl); }
  };
  window.__relayout = function () {
    if (map) { var c = map.getCenter(); map.relayout(); map.setCenter(c); }
  };
  function init() {
    if (!window.kakao || !window.kakao.maps) { post({ type: 'error', message: 'sdk-unavailable' }); return; }
    try {
      kakao.maps.load(function () {
        map = new kakao.maps.Map(document.getElementById('map'), {
          center: new kakao.maps.LatLng(${initLat}, ${initLng}),
          level: ${level},
        });
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
