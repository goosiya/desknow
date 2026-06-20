// 현위치 획득 훅 — 웹 useGeolocation.ts RN 포팅 (Story 9.1 — AC5).
//
// **위치 권한 — 지도 진입 시 자동 요청(KTH 2026-06-20):** 마운트 시 권한을 확인하고, **미결정이면
// 그 자리에서 시스템 프롬프트를 자동으로 띄워** 첫 허용을 앱 안에서 받는다(설정에 갈 마찰 제거).
// (이전엔 "깜짝 프롬프트 금지"로 사용자가 직접 요청할 때만 띄웠으나, KTH 요청으로 진입 시 1회 자동
// 요청으로 변경.) 한 번 거부한 기기는 OS가 재프롬프트를 막으므로 그때만 설정 유도(안내 칩)가 불가피.
//   - granted     → 프롬프트 없이 즉시 측정(내 위치로 지도 이동).
//   - undetermined→ 진입 시 `requestForegroundPermissionsAsync` 자동 프롬프트(허용=측정·이동, 거부=서울+안내).
//   - denied      → 자동 요청 안 함(OS 재프롬프트 차단 — 안내 칩으로 설정 유도). 서울 기본 유지.
//   - unsupported → 측정 부재 신호(Expo Web에서 geolocation 부재 등).
// 지도 초기 렌더는 프롬프트 결과 전까지 보류한다(ExploreView mapPendingLocation) — "서울→내위치 점프"
// 방지([[map-create-after-location-not-render-then-move]]). 프롬프트 중엔 status='locating'.
//
// 위치 신호 단일 출처는 ExploreView가 소유한다 — 지도 중심·반경 center·UI 분기에 공급(웹과 동일).
import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";
import * as Location from "expo-location";

// 측정 진행 상태(요청·결과) — 웹과 동일 유니온.
export type GeolocationStatus =
  | "idle" // 아직 측정 안 함(권한 undetermined/denied로 자동측정 보류 포함)
  | "locating" // 측정 중(권한 프롬프트 포함)
  | "granted" // 허용 — coords 보유
  | "denied" // 거부 또는 측정 실패
  | "unsupported"; // 위치 기능 부재

// 권한 상태(UI 분기: '내 반경' 버튼 vs 안내). 웹의 navigator.permissions 상태와 동형.
export type GeolocationPermission = "granted" | "prompt" | "denied" | "unsupported";

export type Coords = { lat: number; lng: number };

export type GeolocationState = {
  status: GeolocationStatus;
  permission: GeolocationPermission;
  /** 초기 권한 판정이 끝났는지. 지도가 "권한 확인 전 보류"와 "prompt/denied 확정이라 서울로 그림"을
   *  구분하는 데 쓴다(권한 안내 칩 깜빡임 방지 — 판정 후에만 렌더). */
  permissionResolved: boolean;
  coords?: Coords;
  /** 위치 측정을 직접 요청한다(권한 undetermined면 이때 프롬프트가 뜬다). 재중심·목록 반경에 사용. */
  locate: () => void;
  /** 권한·위치를 재확인한다(앱 포그라운드 복귀·수동 재시도 — 설정 변경 따라잡기). */
  refresh: () => void;
};

/** expo PermissionStatus → 우리 permission 유니온 매핑. */
function mapPermission(status: Location.PermissionStatus): GeolocationPermission {
  if (status === Location.PermissionStatus.GRANTED) return "granted";
  if (status === Location.PermissionStatus.DENIED) return "denied";
  return "prompt"; // UNDETERMINED
}

export function useGeolocation(enabled = true): GeolocationState {
  const [status, setStatus] = useState<GeolocationStatus>("idle");
  const [permission, setPermission] = useState<GeolocationPermission>("prompt");
  const [permissionResolved, setPermissionResolved] = useState(false);
  const [coords, setCoords] = useState<Coords | undefined>(undefined);
  // 측정 중복 호출 가드(연타·effect+버튼 동시).
  const locatingRef = useRef(false);
  // 포그라운드 복귀 재확인이 최신 status를 읽도록 ref 미러(리스너 클로저 stale 회피).
  const statusRef = useRef<GeolocationStatus>("idle");
  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  // 측정 — 권한 undetermined면 이때 요청(프롬프트). granted면 즉시 측정. denied면 안내 상태로.
  const locate = useCallback(async () => {
    if (locatingRef.current) return;
    locatingRef.current = true;
    setStatus("locating");
    try {
      let perm = await Location.getForegroundPermissionsAsync();
      if (perm.status === Location.PermissionStatus.UNDETERMINED && perm.canAskAgain) {
        perm = await Location.requestForegroundPermissionsAsync();
      }
      if (perm.status !== Location.PermissionStatus.GRANTED) {
        // 거부·미요청 — 측정하지 않고 안내(서울 기본 유지). denied만 명시 거부, 그 외는 idle 복귀.
        setPermission(mapPermission(perm.status));
        setStatus(perm.status === Location.PermissionStatus.DENIED ? "denied" : "idle");
        return;
      }
      setPermission("granted");
      // 빠른 측정(동네 단위면 Balanced 충분 — 고정밀 GPS 대기 회피).
      const pos = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
      setStatus("granted");
    } catch {
      // 측정 실패·타임아웃·미지원 모두 denied로 합친다(결과 대신 안내 + 지역 유도).
      setStatus("denied");
      setPermission("denied");
    } finally {
      locatingRef.current = false;
    }
  }, []);

  // 마운트 시 권한 확인 + 진입 자동 요청 — granted는 즉시 측정, undetermined(canAskAgain)는 그 자리에서
  // 프롬프트(locate가 request→측정 수행). denied/restricted는 자동 요청 안 함(OS 재프롬프트 차단).
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    (async () => {
      try {
        const perm = await Location.getForegroundPermissionsAsync();
        if (cancelled) return;
        setPermission(mapPermission(perm.status));
        setPermissionResolved(true); // 권한 판정 완료 — 지도가 보류/생성을 결정할 수 있다.
        // granted: 즉시 측정 / undetermined(재요청 가능): locate가 시스템 프롬프트를 띄운 뒤 측정.
        if (
          perm.status === Location.PermissionStatus.GRANTED ||
          (perm.status === Location.PermissionStatus.UNDETERMINED && perm.canAskAgain)
        ) {
          void locate();
        }
      } catch {
        if (cancelled) return;
        // 위치 기능 부재(Expo Web geolocation 부재 등) — 비활성 신호(막힘 없이 지역 유도).
        setStatus("unsupported");
        setPermission("unsupported");
        setPermissionResolved(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled, locate]);

  // 권한·위치 재확인 — 앱 설정에서 허용을 켜고 돌아온 사용자에게 즉시 반영(granted인데 좌표 없으면
  // 조용히 재측정). undetermined면 깜짝 프롬프트 방지로 재측정하지 않는다.
  const refresh = useCallback(async () => {
    try {
      const perm = await Location.getForegroundPermissionsAsync();
      setPermission(mapPermission(perm.status));
      const noFix = statusRef.current !== "granted" && statusRef.current !== "locating";
      if (perm.status === Location.PermissionStatus.GRANTED && noFix) {
        void locate();
      }
    } catch {
      // 재확인 실패는 무시(기존 상태 유지).
    }
  }, [locate]);

  // 앱 포그라운드 복귀 시 재확인(OS 위치 설정 변경 따라잡기 — 웹 focus/visibility 등가).
  useEffect(() => {
    if (!enabled) return;
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") void refresh();
    });
    return () => sub.remove();
  }, [enabled, refresh]);

  return { status, permission, permissionResolved, coords, locate, refresh };
}
