import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';

import { NetworkNotice } from '@/components/NetworkNotice';
import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';
import { useOnlineStatus } from '@/lib/useOnlineStatus';
import type { Coords } from '@/features/list/useGeolocation';

import { buildMapHtml } from './mapHtml';
import type { PinStatus } from './pin';
import { useRoomPins } from './useRoomPins';

// 첫 진입 지도 — 웹 MapView RN 포팅 (Story 9.1 — AC3·AC5 · ADR-9.1-B). 카카오맵 캔버스만 WebView로
// 띄우고, RN이 SDK로 핀(useRoomPins)을 조회해 injectJavaScript로 주입한다. 핀 탭은 postMessage
// 브릿지로 RN이 수신해 부모(ExploreView)의 바텀시트를 연다. 5상태(로딩/에러/빈/단절/위치거부)는
// 절대 배치 오버레이로 처리한다(막다른 화면 금지).

export type SelectedPin = { room_id: string; name: string; status: PinStatus };

// 위치 거부/불가 시 기본 중심(서울 시청 — AC5 폴백).
const SEOUL_LAT = 37.5665;
const SEOUL_LNG = 126.978;
// 초기 지도 축척(카카오 level — 작을수록 확대). '내 반경' 재중심 시 이 값으로 되돌린다.
const INITIAL_MAP_LEVEL = 5;
// 카카오 콘솔에 등록된 WebView origin(JS 키 화이트리스트). 네이티브는 이 origin으로 SDK가 수용된다.
// (Expo Web=iframe 환경은 부모 origin이라 콘솔 미등록이면 거부 → AC5 graceful degrade.)
const KAKAO_WEBVIEW_ORIGIN = 'http://localhost:3000';

type MapStatus = 'loading' | 'ready' | 'error';

type MapWebViewProps = {
  // 위치 허용 시 현위치 좌표(ExploreView 단일 소유). 없으면 서울 폴백.
  coords?: Coords | null;
  // 위치 확보 대기 신호 — true면 지도를 아직 생성하지 않는다(서울 선렌더→점프 금지).
  pendingLocation?: boolean;
  // '내 반경' 재중심 — 값이 바뀔 때마다 현 coords로 중심·축척을 초기화한다.
  recenterNonce?: number;
  // 핀 탭 → 부모가 바텀시트 오픈(단일 시트 — 지도/목록 공유).
  onSelectPin: (pin: SelectedPin) => void;
  // 빈/에러의 "목록 우회" 액션(ExploreView가 목록 뷰로 전환·검색방식 지정).
  onSwitchToList?: (mode: 'region' | 'radius') => void;
};

export function MapWebView({
  coords,
  pendingLocation = false,
  recenterNonce = 0,
  onSelectPin,
  onSwitchToList,
}: MapWebViewProps) {
  const { pins, isLoading, isError, isEmpty, refetch } = useRoomPins();
  const isOnline = useOnlineStatus();
  const jsKey = process.env.EXPO_PUBLIC_KAKAO_JS_KEY;

  const webRef = useRef<WebView>(null);
  const [mapStatus, setMapStatus] = useState<MapStatus>('loading');
  const [reloadNonce, setReloadNonce] = useState(0);

  // 초기 중심 동결(1회): 위치 확보 전(pendingLocation)에는 정하지 않고, 좌표가 오거나 위치를 안
  // 쓰기로 확정되면 그 시점의 중심(coords ?? 서울)을 한 번만 고정한다(서울 선렌더→점프 제거). 이후
  // coords가 바뀌어도 지도를 재생성하지 않고 중심 이동(아래 effect)만 한다. "렌더 중 상태 조정"
  // 패턴이라 effect 내 setState가 아니다(set-state-in-effect 회피).
  const [initialCenter, setInitialCenter] = useState<Coords | null>(null);
  if (!pendingLocation && initialCenter === null) {
    setInitialCenter({ lat: coords ? coords.lat : SEOUL_LAT, lng: coords ? coords.lng : SEOUL_LNG });
  }

  // HTML은 초기 중심+키가 정해지면 1회 생성(메모). 키가 없으면 null → 아래 keyMissing이 에러 처리.
  const mapHtml = useMemo(
    () =>
      jsKey && initialCenter
        ? buildMapHtml(jsKey, initialCenter.lat, initialCenter.lng, INITIAL_MAP_LEVEL)
        : null,
    [jsKey, initialCenter],
  );
  const keyMissing = !jsKey;

  // 핀 주입: 지도 준비 후 pins가 바뀌면 WebView에 주입한다(WebView는 캔버스만 — 직접 조회 안 함).
  useEffect(() => {
    if (mapStatus !== 'ready') return;
    const payload = JSON.stringify(pins);
    webRef.current?.injectJavaScript(
      `window.__setPins(${JSON.stringify(payload)}); true;`,
    );
  }, [pins, mapStatus]);

  // 좌표 변화(뒤늦은 도착 등) → 중심 이동.
  useEffect(() => {
    if (mapStatus !== 'ready' || !coords) return;
    webRef.current?.injectJavaScript(
      `window.__setCenter(${coords.lat}, ${coords.lng}); true;`,
    );
  }, [coords, mapStatus]);

  // '내 반경' 재중심: 중심 + 축척 초기화(사용자가 바꾼 축척 복귀).
  useEffect(() => {
    if (recenterNonce === 0 || mapStatus !== 'ready' || !coords) return;
    webRef.current?.injectJavaScript(
      `window.__recenter(${coords.lat}, ${coords.lng}, ${INITIAL_MAP_LEVEL}); true;`,
    );
  }, [recenterNonce, coords, mapStatus]);

  const handleMessage = useCallback(
    (e: WebViewMessageEvent) => {
      try {
        const msg = JSON.parse(e.nativeEvent.data) as {
          type: string;
          room_id?: string;
          name?: string;
          status?: PinStatus;
        };
        if (msg.type === 'ready') {
          setMapStatus('ready');
        } else if (msg.type === 'error') {
          setMapStatus('error');
        } else if (msg.type === 'pinTap' && msg.room_id) {
          onSelectPin({
            room_id: msg.room_id,
            name: msg.name ?? '',
            status: msg.status ?? 'full',
          });
        }
      } catch {
        // 파싱 실패 — 무시(브릿지 메시지가 아닌 잡음).
      }
    },
    [onSelectPin],
  );

  const handleRetry = useCallback(() => {
    // 재시도: WebView를 새로 마운트(reloadNonce 키)해 SDK 초기화를 재시도하고 핀을 재조회한다.
    setMapStatus('loading');
    setReloadNonce((n) => n + 1);
    refetch();
  }, [refetch]);

  // 데이터(좌표) 로드 실패·키 부재도 지도 에러와 동일 처리. 단, 네트워크 단절은 에러로 오인 표시하지
  // 않는다(단절은 NetworkNotice가 우선·마지막 핀 캐시 유지). isOnline && 게이팅으로 단절을 덮지 않는다.
  const showError = isOnline && (keyMissing || mapStatus === 'error' || isError);

  return (
    <View style={styles.container}>
      {mapHtml && jsKey ? (
        <WebView
          key={reloadNonce}
          ref={webRef}
          originWhitelist={['*']}
          source={{ html: mapHtml, baseUrl: KAKAO_WEBVIEW_ORIGIN }}
          onMessage={handleMessage}
          onError={() => setMapStatus('error')}
          onHttpError={() => setMapStatus('error')}
          javaScriptEnabled
          domStorageEnabled
          // 지도 제스처(드래그/핀치)가 RN 스크롤과 충돌하지 않게 — WebView가 터치를 소유.
          style={styles.webview}
        />
      ) : null}

      {/* 로딩: 지도/데이터 준비 전(단절·에러 아님). */}
      {(mapStatus === 'loading' || isLoading) && !showError && isOnline ? (
        <View style={styles.overlayCenter} pointerEvents="none">
          <ThemedText type="bodySm" themeColor="textSecondary">
            주변 스터디룸을 불러오는 중이에요…
          </ThemedText>
        </View>
      ) : null}

      {/* 네트워크 단절: 에러보다 우선(마지막 핀 캐시 유지·재연결 자동 재조회). */}
      {!isOnline ? <NetworkNotice style={styles.topBanner} /> : null}

      {/* 지도/데이터 실패: 안내 + 재시도 + 목록 우회(막다른 화면 금지). */}
      {showError ? (
        <View style={styles.overlayFull}>
          <ThemedText type="h3">지도를 못 불러왔어요.</ThemedText>
          <ThemedText type="bodySm" themeColor="textSecondary" style={styles.centerText}>
            잠시 후 다시 시도하거나, 목록으로 둘러볼 수 있어요.
          </ThemedText>
          <View style={styles.actionRow}>
            <Pressable onPress={handleRetry} accessibilityRole="button" style={styles.primaryButton}>
              <ThemedText type="label" themeColor="primaryForeground">
                다시 시도
              </ThemedText>
            </Pressable>
            <Pressable
              onPress={() => onSwitchToList?.('region')}
              accessibilityRole="button"
              style={styles.outlineButton}
            >
              <ThemedText type="label" themeColor="cardForeground">
                목록으로 보기
              </ThemedText>
            </Pressable>
          </View>
        </View>
      ) : null}

      {/* 위치 거부 안내는 ExploreView 의 권한 칩(permChip)이 지도 모드에서 담당한다(이중 안내 방지 —
          code-review 회수: MapWebView 의 데드 배너 제거). */}

      {/* 빈 상태: 주변 활성 룸 0개 → 다음-행동 액션(반경 확대·지역 전환). */}
      {isEmpty && !showError && mapStatus === 'ready' && isOnline ? (
        <View style={styles.bottomCard}>
          <ThemedText type="label">이 근처엔 아직 없어요.</ThemedText>
          <ThemedText type="caption" themeColor="textSecondary" style={styles.centerText}>
            동네를 넓혀볼까요? 다른 방식으로 찾아볼 수 있어요.
          </ThemedText>
          <View style={styles.actionRow}>
            <Pressable
              onPress={() => onSwitchToList?.('region')}
              accessibilityRole="button"
              style={styles.primaryButton}
            >
              <ThemedText type="label" themeColor="primaryForeground">
                지역으로 찾기
              </ThemedText>
            </Pressable>
            <Pressable
              onPress={() => onSwitchToList?.('radius')}
              accessibilityRole="button"
              style={styles.outlineButton}
            >
              <ThemedText type="label" themeColor="cardForeground">
                반경으로 넓혀보기
              </ThemedText>
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    minHeight: 320,
    overflow: 'hidden',
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.backgroundElement,
  },
  webview: { flex: 1, backgroundColor: 'transparent' },
  overlayCenter: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  overlayFull: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing[3],
    padding: Spacing[6],
    backgroundColor: Colors.light.card,
  },
  topBanner: {
    position: 'absolute',
    top: Spacing[3],
    left: Spacing[3],
    right: Spacing[3],
  },
  bottomCard: {
    position: 'absolute',
    bottom: Spacing[3],
    left: Spacing[3],
    right: Spacing[3],
    gap: Spacing[2],
    padding: Spacing[4],
    borderRadius: Radius.md,
    backgroundColor: Colors.light.card,
    alignItems: 'center',
  },
  centerText: { textAlign: 'center' },
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing[2], justifyContent: 'center' },
  primaryButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  outlineButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
});
