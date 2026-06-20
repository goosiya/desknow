import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import type { RoomListItem } from '@/lib/api-client';
import { SegmentedControl } from '@/components/SegmentedControl';
import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';
import { MapWebView, type SelectedPin } from '@/features/map/MapWebView';
import { RoomSheet } from '@/features/map/RoomSheet';
import { pinStatus } from '@/features/map/pin';

import { RadiusControl } from './RadiusControl';
import { RegionCombos } from './RegionCombos';
import { RoomList } from './RoomList';
import { InfoCard } from './ListStates';
import { resolveRegionCode } from './regions';
import { useGeolocation } from './useGeolocation';

// 스터디룸 찾기 컨테이너 — 웹 ExploreView RN 포팅 (Story 9.1 — AC3·AC4·AC5). 지도(WebView 카카오맵)와
// 목록을 **지도/목록 토글**로 전환하고, 목록 안에서 **지역|반경 검색방식 서브토글**로 두 검색을 오간다.
// 선택 상태(시군구/지역 + 반경값)를 컨테이너가 보유해 토글 왕복 시 보존한다. 위치 신호(useGeolocation)도
// 컨테이너가 단일 소유해 지도 중심·반경 center·UI 분기에 공급한다. 핀/목록행 탭은 **단일 RoomSheet**를
// 연다(지도/목록 공유).

type ViewMode = 'map' | 'list';
type SearchMode = 'region' | 'radius';

const DEFAULT_RADIUS_KM = 3; // 반경 기본 3km

export function ExploreView() {
  const [viewMode, setViewMode] = useState<ViewMode>('map');
  const [searchMode, setSearchMode] = useState<SearchMode>('region');
  // 지역 선택 — 컨테이너가 보유(토글/검색방식 왕복 시 보존). RegionCombos는 controlled.
  const [sigunguCode, setSigunguCode] = useState<string | undefined>(undefined);
  const [dongCode, setDongCode] = useState<string | undefined>(undefined);
  // 반경값 — 컨테이너가 보유(검색방식 전환 후에도 보존). 기본 3km.
  const [radiusKm, setRadiusKm] = useState<number>(DEFAULT_RADIUS_KM);
  // 핀/목록행 탭으로 열리는 시트 대상(지도/목록 공유 — 단일 시트).
  const [selected, setSelected] = useState<SelectedPin | null>(null);
  // '내 반경' 재중심 신호 — 클릭마다 증가시켜 지도가 현 위치로 중심·축척을 다시 맞추게 한다.
  const [recenterNonce, setRecenterNonce] = useState(0);

  const regionCode = resolveRegionCode(sigunguCode, dongCode);

  // 위치는 ExploreView 단일 소유 — 지도 중심·반경 center·UI 분기에 공급(요청 1회). 권한 선확인:
  // granted면 자동 측정해 내 위치로, prompt/denied면 자동 측정하지 않고 기본 위치 유지.
  const geo = useGeolocation(true);
  const {
    status: geoStatus,
    permission: geoPermission,
    permissionResolved: geoPermissionResolved,
    coords: geoCoords,
    locate: geoLocate,
    refresh: geoRefresh,
  } = geo;
  const locationDenied = geoStatus === 'denied' || geoStatus === 'unsupported';
  const hasLocationPermission = geoPermission === 'granted';

  // 지도 생성 보류 신호: 권한이 있으면 좌표를 확보할 때까지 지도 생성을 미뤄 처음부터 내 위치로
  // 그린다(서울 선렌더→점프 금지). 권한 판정 전이거나, 측정/권한 프롬프트 진행 중(locating —
  // 진입 시 자동 프롬프트 포함)일 때 보류한다. 허용=내 위치로, 거부=서울로 그때 1회 렌더(점프 없음).
  const mapPendingLocation =
    !geoCoords &&
    (!geoPermissionResolved ||
      geoStatus === 'locating' ||
      (geoPermission === 'granted' && geoStatus === 'idle'));

  // 목록 반경 모드 진입 시 권한이 prompt면 그때 측정을 요청한다(진입만으로 프롬프트를 띄우지 않되,
  // 사용자가 반경 검색을 고르면 측정 — 막힘 방지). 동기 setState 회피로 마이크로태스크 이월.
  useEffect(() => {
    if (searchMode === 'radius' && geoPermission === 'prompt' && geoStatus === 'idle') {
      queueMicrotask(() => geoLocate());
    }
  }, [searchMode, geoPermission, geoStatus, geoLocate]);

  function handleSwitchToList(mode: SearchMode): void {
    setViewMode('list');
    setSearchMode(mode);
  }

  function handleRecenter(): void {
    // 이미 확보한 coords로 즉시 재중심한다. ⚠️ geoLocate()를 부르지 않는다 — 부르면 status='locating'으로
    // coords가 null이 돼 MapWebView 재중심 effect가 막히고, getCurrentPositionAsync 2번째 호출이 새 GPS fix를
    // 기다리며 멈춰 "수동 팬 후 재중심이 안 되던" 원인이었다(실기기 2026-06-20). 위치 갱신은 반경 검색 진입 때.
    setRecenterNonce((n) => n + 1);
  }

  // 목록 행 → 시트 대상으로 정규화(룸의 신선 remaining_slots를 fallback 상태로).
  function handleSelectRoom(room: RoomListItem): void {
    setSelected({
      room_id: room.room_id,
      name: room.name,
      status: pinStatus(room.remaining_slots),
    });
  }

  return (
    <View style={styles.container}>
      {/* 최상위 줄: 지도/목록 토글(왼쪽) + 지도 화면 + 위치 권한 있을 때 '내 반경'(오른쪽). */}
      <View style={styles.topRow}>
        <SegmentedControl
          accessibilityLabel="지도·목록 보기 전환"
          value={viewMode}
          onChange={(v) => setViewMode(v as ViewMode)}
          options={[
            { value: 'map', label: '지도' },
            { value: 'list', label: '목록' },
          ]}
        />
        {viewMode === 'map' && hasLocationPermission ? (
          <Pressable onPress={handleRecenter} accessibilityRole="button" style={styles.recenter}>
            <ThemedText type="label" themeColor="cardForeground">
              📍 내 반경
            </ThemedText>
          </Pressable>
        ) : null}
      </View>

      {viewMode === 'map' ? (
        // 지도 영역 — MapWebView가 채우고, 위치 권한 안내 칩을 그 위 absolute 오버레이로 얹는다
        // (9.4 #10·웹 ExploreView 동형: 지도 안 top 오버레이, 권한 granted면 숨김 = "보였다 안보였다").
        <View style={styles.mapArea}>
          <MapWebView
            coords={geoStatus === 'granted' ? geoCoords : null}
            pendingLocation={mapPendingLocation}
            recenterNonce={recenterNonce}
            onSelectPin={setSelected}
            onSwitchToList={handleSwitchToList}
          />
          {/* 권한 확인 완료 후에만 렌더(깜빡임 방지) — prompt면 허용 유도, denied면 재시도. box-none로
              칩 밖 지도 영역은 그대로 드래그 가능, 칩만 터치(웹 pointer-events-none 래퍼 동형). */}
          {geoPermissionResolved && !hasLocationPermission ? (
            <View style={styles.permOverlay} pointerEvents="box-none">
              {geoPermission === 'prompt' ? (
                <Pressable onPress={geoLocate} accessibilityRole="button" style={styles.permChip}>
                  <ThemedText type="bodySm" themeColor="secondaryForeground">
                    📍 위치 권한을 허용하면 내 위치로 지도를 옮겨드려요.
                  </ThemedText>
                </Pressable>
              ) : (
                <Pressable onPress={geoRefresh} accessibilityRole="button" style={styles.permChip}>
                  {/* 모바일 앱 전용 카피(웹 ExploreView는 자체 문구 유지 — KTH 지시로 모바일만 수정, 2026-06-20). */}
                  <ThemedText type="bodySm" themeColor="secondaryForeground">
                    📍 위치 권한이 꺼져 있어요. 앱이나 휴대폰의 위치 권한을 허용해 주세요.
                  </ThemedText>
                </Pressable>
              )}
            </View>
          ) : null}
        </View>
      ) : (
        <View style={styles.listArea}>
          {/* 검색방식 토글(지역|내 반경) + 인라인 컨트롤(지역 콤보 / 반경 프리셋). */}
          <View style={styles.controlsRow}>
            <SegmentedControl
              accessibilityLabel="검색 방식 전환"
              value={searchMode}
              onChange={(v) => setSearchMode(v as SearchMode)}
              options={[
                { value: 'region', label: '지역' },
                { value: 'radius', label: '내 반경' },
              ]}
            />
            {searchMode === 'region' ? (
              <RegionCombos
                sigunguCode={sigunguCode}
                dongCode={dongCode}
                onSigunguChange={setSigunguCode}
                onDongChange={setDongCode}
              />
            ) : geoStatus === 'granted' && geoCoords ? (
              <RadiusControl radiusKm={radiusKm} onChange={setRadiusKm} />
            ) : null}
          </View>

          {/* 안내·목록 */}
          {searchMode === 'region' ? (
            <View style={styles.listFill}>
              {locationDenied ? (
                <View style={styles.notice} accessibilityRole="alert">
                  <ThemedText type="bodySm" themeColor="secondaryForeground">
                    현재 위치를 못 받았어요. 동네를 골라서 찾아볼게요.
                  </ThemedText>
                </View>
              ) : null}
              <RoomList search={{ kind: 'region', regionCode }} onSelectRoom={handleSelectRoom} />
            </View>
          ) : geoStatus === 'granted' && geoCoords ? (
            <RoomList
              search={{ kind: 'radius', center: geoCoords, radiusKm }}
              onSelectRoom={handleSelectRoom}
            />
          ) : geoStatus === 'denied' || geoStatus === 'unsupported' ? (
            <InfoCard
              text="현재 위치를 못 받았어요. 동네를 골라서 찾아볼게요."
              action={{ label: '지역으로 찾기', onPress: () => setSearchMode('region') }}
            />
          ) : (
            <InfoCard text="현위치를 확인하고 있어요…" />
          )}
        </View>
      )}

      {/* 핀/목록행 탭 → 단일 바텀시트(지도/목록 공유). */}
      <RoomSheet
        roomId={selected?.room_id ?? ''}
        name={selected?.name ?? ''}
        fallbackStatus={selected?.status}
        open={!!selected}
        onOpenChange={(o) => {
          if (!o) setSelected(null);
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: Spacing[4], gap: Spacing[3] },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing[2],
  },
  recenter: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing[3],
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  mapArea: { flex: 1 },
  // 지도 안 top 오버레이 — 칩을 가운데 정렬해 지도 위에 띄운다(웹 absolute inset-x-0 top-0 동형).
  permOverlay: {
    position: 'absolute',
    top: Spacing[3],
    left: Spacing[3],
    right: Spacing[3],
    alignItems: 'center',
    zIndex: 10,
  },
  permChip: {
    borderRadius: Radius.md,
    backgroundColor: Colors.light.secondary,
    paddingHorizontal: Spacing[4],
    paddingVertical: Spacing[2],
  },
  listArea: { flex: 1, gap: Spacing[3] },
  controlsRow: { gap: Spacing[2] },
  listFill: { flex: 1, gap: Spacing[2] },
  notice: {
    borderRadius: Radius.md,
    backgroundColor: Colors.light.secondary,
    paddingHorizontal: Spacing[4],
    paddingVertical: Spacing[2],
  },
});
