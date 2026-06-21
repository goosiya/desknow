import { useState } from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius } from '@/constants/theme';

// 룸 상세 미니 지도(WebView 단일 핀) — 웹 detail/RoomLocationMap.tsx RN 포팅 (Story 9.2 — AC1 ·
// 범위 결정 #2). 룸 좌표(lat/lng)를 중심으로 단일 핀을 찍는 정적 미니 지도다. 9.1 MapWebView의
// 카카오 SDK 로드(autoload=false + kakao.maps.load)·origin 화이트리스트(baseUrl) 패턴을 **단일
// 핀·인터랙션 최소(줌/팬 비활성)** 변형으로 재활용한 lean 래퍼다(전체화면 MapWebView는 다중 핀이라
// 부적합 — 새 래퍼).
//
// ⚠️ Expo Web=react-native-webview 미지원(플랫폼 스텁) → Platform.OS==='web'이면 즉시 graceful
//    degrade("지도를 못 불러왔어요.")로 떨어진다(웹 RoomLocationMap도 동형 degrade — 정상). 네이티브
//    렌더는 dev build에서만. **9.1 defer 상속**: origin 하드코딩·SDK 로드 워치독 부재(§deferred).
// ⚠️ WebView는 캔버스만 — 저장 좌표를 HTML에 주입(직접 fetch 안 함). 핀 탭 핸들러 없음(정적 표시).
type RoomLocationMapProps = {
  lat: number;
  lng: number;
  /** 핀 접근성 라벨용 룸 이름(선택). */
  name?: string;
  /**
   * true면 지도 드래그/줌을 허용한다(웹 RoomLocationMap 동형). 현재 룸 상세·provider 수정 폼 둘 다
   * 인터랙티브로 켠다(KTH 2026-06-20 — 사용자가 지도 이동을 원함). 스크롤뷰 안 제스처는 WebView
   * nestedScrollEnabled 로 처리한다(지도 위 드래그=팬, 밖=페이지 스크롤). 기본 false=정적 폴백.
   */
  interactive?: boolean;
};

type MapStatus = 'loading' | 'ready' | 'error';

// 카카오 콘솔에 등록된 WebView origin(JS 키 화이트리스트) — 9.1 MapWebView 상수 동형(deferred 회수
// 후보=env화 EXPO_PUBLIC_KAKAO_WEBVIEW_ORIGIN).
const KAKAO_WEBVIEW_ORIGIN = 'http://localhost:3000';

/** 단일 핀 카카오맵 HTML(buildMapHtml 패턴 — 핀 탭 없음·ready/error 브릿지). interactive=true면 줌/팬 허용. */
function buildLocationMapHtml(
  jsKey: string,
  lat: number,
  lng: number,
  name: string,
  interactive: boolean,
): string {
  return `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
<style>
  html, body, #map { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: #F4EDDF; }
  .dot {
    box-sizing: border-box;
    width: 18px; height: 18px; border-radius: 50%;
    background: #D86E0A; border: 3px solid #fff; box-shadow: 0 2px 6px rgba(40,32,15,0.35);
  }
</style>
<!-- https 고정(스탠드얼론 빌드 Android cleartext 차단 회피 — mapHtml.ts 주석 참조). -->
<script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey=${jsKey}&autoload=false"></script>
</head>
<body>
<div id="map"></div>
<script>
  function post(msg) {
    if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(msg));
  }
  function init() {
    if (!window.kakao || !window.kakao.maps) { post({ type: 'error', message: 'sdk-unavailable' }); return; }
    try {
      kakao.maps.load(function () {
        var center = new kakao.maps.LatLng(${lat}, ${lng});
        var map = new kakao.maps.Map(document.getElementById('map'), { center: center, level: 4 });
        ${interactive ? "" : "map.setDraggable(false); map.setZoomable(false); // 정적 미니 지도(줌/팬 비활성)."}
        var el = document.createElement('div');
        el.className = 'dot';
        el.setAttribute('role', 'img');
        el.setAttribute('aria-label', ${JSON.stringify(name ? `${name} 위치` : '스터디룸 위치')});
        var overlay = new kakao.maps.CustomOverlay({ position: center, content: el, yAnchor: 0.5, zIndex: 3 });
        overlay.setMap(map);
        // ⚠️ WebView 컨테이너 크기가 늦게 확정되면 지도 투영이 stale 되어 핀이 주소 위치(중앙)에서
        //    어긋나거나 화면 밖으로 빠진다(스크롤뷰 안 WebView에서 흔함 — 핀이 "안 보이는" 원인).
        //    relayout 으로 투영을 컨테이너에 다시 맞추고 중심을 재고정한다(전체 MapView의
        //    ResizeObserver→relayout 패턴 동형). resize 이벤트 + 지연 2회로 초기 settle 을 잡는다.
        function refresh() { map.relayout(); map.setCenter(center); }
        window.addEventListener('resize', refresh);
        setTimeout(refresh, 250);
        setTimeout(refresh, 700);
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

export function RoomLocationMap({ lat, lng, name, interactive = false }: RoomLocationMapProps) {
  const jsKey = process.env.EXPO_PUBLIC_KAKAO_JS_KEY;
  const [status, setStatus] = useState<MapStatus>('loading');

  // Expo Web(WebView 미지원) 또는 키 부재 → 즉시 graceful degrade(웹 RoomLocationMap 동형).
  const cannotRender = Platform.OS === 'web' || !jsKey;

  if (cannotRender || status === 'error') {
    return (
      <View accessibilityRole="text" style={styles.degrade}>
        <ThemedText type="bodySm" themeColor="textSecondary">
          지도를 못 불러왔어요.
        </ThemedText>
      </View>
    );
  }

  const handleMessage = (e: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(e.nativeEvent.data) as { type: string };
      if (msg.type === 'ready') setStatus('ready');
      else if (msg.type === 'error') setStatus('error');
    } catch {
      // 브릿지 메시지가 아닌 잡음 — 무시.
    }
  };

  return (
    <View style={styles.container}>
      <WebView
        originWhitelist={['*']}
        source={{ html: buildLocationMapHtml(jsKey as string, lat, lng, name ?? '', interactive), baseUrl: KAKAO_WEBVIEW_ORIGIN }}
        onMessage={handleMessage}
        onError={() => setStatus('error')}
        onHttpError={() => setStatus('error')}
        javaScriptEnabled
        domStorageEnabled
        // 인터랙티브(수정 폼)면 지도가 터치 제스처를 받아 팬/줌하도록 nestedScroll 허용. 정적(상세)은
        // 스크롤뷰 세로 스와이프를 가로채지 않게 그대로 둔다.
        scrollEnabled={false}
        nestedScrollEnabled={interactive}
        style={styles.webview}
      />
      {/* 로드 중 자리(준비되면 지도 타일이 덮는다). */}
      {status === 'loading' ? (
        <View style={styles.overlay} pointerEvents="none">
          <ThemedText type="bodySm" themeColor="textSecondary">
            지도를 불러오는 중이에요…
          </ThemedText>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    height: 176,
    overflow: 'hidden',
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.backgroundElement,
  },
  webview: { flex: 1, backgroundColor: 'transparent' },
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  degrade: {
    height: 176,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.backgroundElement,
  },
});
