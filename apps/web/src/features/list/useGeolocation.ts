"use client";

// 현위치 획득 훅 (Story 3.5 도입 → 3.6 진입 전역 신호 → 위치권한 선확인 개편).
//
// **위치 권한 선확인(KTH 2026-06-18 지도 UX 개편):** 마운트 즉시 무조건 `getCurrentPosition`을
// 호출(=권한 프롬프트를 띄움)하지 않는다. 먼저 **Permissions API**로 권한 상태를 확인해:
//   - granted  → 프롬프트 없이 즉시 측정(내 위치로 지도 이동).
//   - prompt   → 자동 측정하지 않는다(깜짝 프롬프트 금지). 기본 위치 유지 + 안내. 사용자가
//                `locate()`(안내/버튼)로 직접 요청할 때만 프롬프트가 뜬다.
//   - denied   → 측정하지 않는다(기본 위치 유지 + 안내).
//   - unsupported(geolocation 부재) → 비활성 신호.
//
// **레거시 폴백:** Permissions API가 없는 환경(구형 Safari·jsdom 테스트)에서는 상태를 미리 알 수
// 없으므로 enable 시 종전처럼 자동 측정한다(기존 동작·테스트 보존).
//
// 위치 신호 단일 출처는 그대로 ExploreView가 소유한다 — 지도 중심·반경 center·UI 분기에 공급.
import { useCallback, useEffect, useRef, useState } from "react";

// getCurrentPosition 측정 진행 상태(요청·결과).
export type GeolocationStatus =
  | "idle" // 아직 측정 안 함(권한 prompt/denied로 자동측정 보류 포함)
  | "locating" // 측정 중(권한 프롬프트 포함)
  | "granted" // 허용 — coords 보유
  | "denied" // 거부 또는 측정 실패
  | "unsupported"; // navigator.geolocation 부재

// 브라우저/기기 위치 권한 상태(Permissions API). UI 분기('내 반경' 버튼 vs 안내)에 쓴다.
export type GeolocationPermission = "granted" | "prompt" | "denied" | "unsupported";

export type Coords = { lat: number; lng: number };

// getCurrentPosition 측정 옵션 — 옵션 미지정 시 기본값(timeout:Infinity·maximumAge:0)이
// 첫 콜드 측정에서 무한정 대기(coords 영영 없음 → 내 위치로 이동 안 됨)하고, 그 동안
// locatingRef 가 true 로 고착돼 재시도(`내 반경`/refresh)마저 막아 "새로고침/재방문해야 됨"
// 증상을 만든다(Playwright 무응답 재현으로 확인). 그래서 명시한다:
//   - maximumAge 5분: 최근 측정 캐시가 있으면 즉시 반환 → 첫 진입도 바로 내 위치로 이동.
//   - timeout 10초: 무응답이어도 error 콜백을 보장 → locatingRef 복구 + 안내 노출(막힘 방지).
//   - enableHighAccuracy false: GPS 고정밀 대기 없이 네트워크 기반 빠른 측정(동네 단위면 충분).
const GEO_OPTIONS: PositionOptions = {
  enableHighAccuracy: false,
  timeout: 10000,
  maximumAge: 300000,
};

export type GeolocationState = {
  status: GeolocationStatus;
  permission: GeolocationPermission;
  /** 초기 권한 판정(Permissions API query 또는 레거시 측정 개시)이 끝났는지. 지도가 "권한 확인
   *  전이라 보류"와 "prompt/denied 확정이라 기본 위치로 그림"을 구분하는 데 쓴다. */
  permissionResolved: boolean;
  coords?: Coords;
  /** 위치 측정을 직접 요청한다(권한 prompt면 이때 브라우저 프롬프트가 뜬다). 재중심·목록 반경에 사용. */
  locate: () => void;
  /** 권한·위치를 재확인한다(탭 복귀·수동 재시도 — OS 위치 토글 등 change 이벤트 밖 변경 따라잡기). */
  refresh: () => void;
};

export function useGeolocation(enabled = true): GeolocationState {
  const [status, setStatus] = useState<GeolocationStatus>("idle");
  const [permission, setPermission] = useState<GeolocationPermission>("prompt");
  const [permissionResolved, setPermissionResolved] = useState(false);
  const [coords, setCoords] = useState<Coords | undefined>(undefined);
  // locate 중복 호출 가드(연타·effect+버튼 동시) — 측정 중이면 재요청하지 않는다.
  const locatingRef = useRef(false);
  // 포커스/가시성 복귀 시 재확인 핸들러가 최신 값을 읽도록 ref 로 미러한다(리스너 클로저 stale 회피).
  const statusRef = useRef<GeolocationStatus>("idle");
  const permStatusRef = useRef<PermissionStatus | undefined>(undefined);
  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  const locate = useCallback(() => {
    const geolocation =
      typeof navigator !== "undefined" ? navigator.geolocation : undefined;
    if (!geolocation) {
      setStatus("unsupported");
      setPermission("unsupported");
      return;
    }
    if (locatingRef.current) return;
    locatingRef.current = true;
    setStatus("locating");
    geolocation.getCurrentPosition(
      (pos) => {
        locatingRef.current = false;
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setStatus("granted");
        setPermission("granted");
      },
      () => {
        // 거부·측정 실패·타임아웃 모두 denied로 합친다(결과 대신 안내 + 지역 유도).
        locatingRef.current = false;
        setStatus("denied");
        setPermission("denied");
      },
      GEO_OPTIONS,
    );
  }, []);

  // 탭 복귀(focus/visibility) 시 권한·위치를 재확인한다 — OS 위치 서비스 토글은 브라우저 권한
  // 상태를 바꾸지 않아 Permissions `change` 가 안 오므로, 설정을 바꾸고 돌아온 사용자에게 즉시
  // 반영되도록 한다. 브라우저 권한이 granted(또는 Permissions API 부재)인데 아직 좌표가 없으면
  // 조용히 재측정(프롬프트 없음). prompt 면 깜짝 프롬프트 방지로 재측정하지 않는다.
  const refresh = useCallback(() => {
    const ps = permStatusRef.current;
    if (ps) setPermission(ps.state as GeolocationPermission);
    const live = ps?.state; // 브라우저 권한(미지원이면 undefined → 레거시 재시도 허용)
    const noFix = statusRef.current !== "granted" && statusRef.current !== "locating";
    if ((live === "granted" || live === undefined) && noFix) locate();
  }, [locate]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const nav = typeof navigator !== "undefined" ? navigator : undefined;
    const geolocation = nav?.geolocation;

    if (!geolocation) {
      // 미지원 — 비활성 신호(막힘 없이 지역 유도). 동기 setState 금지(마이크로태스크 이월).
      queueMicrotask(() => {
        if (cancelled) return;
        setStatus("unsupported");
        setPermission("unsupported");
        setPermissionResolved(true);
      });
      return () => {
        cancelled = true;
      };
    }

    const permissions = nav?.permissions;
    let permStatus: PermissionStatus | undefined;
    const onChange = () => {
      if (!cancelled && permStatus) {
        setPermission(permStatus.state as GeolocationPermission);
        // 사용자가 브라우저 설정에서 허용으로 바꾸면 즉시 측정해 내 위치로 이동.
        if (permStatus.state === "granted") locate();
      }
    };

    if (permissions?.query) {
      // 권한 선확인 — granted만 자동 측정, prompt/denied는 자동 프롬프트를 띄우지 않는다.
      permissions
        .query({ name: "geolocation" as PermissionName })
        .then((ps) => {
          if (cancelled) return;
          permStatus = ps;
          permStatusRef.current = ps; // 포커스 재확인이 최신 브라우저 권한을 읽도록 공유.
          setPermission(ps.state as GeolocationPermission);
          setPermissionResolved(true); // 권한 판정 완료 — 지도가 보류/생성을 결정할 수 있다.
          ps.addEventListener?.("change", onChange);
          if (ps.state === "granted") locate();
        })
        .catch(() => {
          // Permissions API 조회 실패 → 레거시 자동 측정으로 폴백.
          if (!cancelled) {
            setPermissionResolved(true);
            locate();
          }
        });
    } else {
      // Permissions API 미지원(구형 Safari·jsdom) → 레거시 자동 측정(기존 동작·테스트 보존).
      queueMicrotask(() => {
        if (cancelled) return;
        setPermissionResolved(true);
        locate();
      });
    }

    return () => {
      cancelled = true;
      permStatus?.removeEventListener?.("change", onChange);
    };
  }, [enabled, locate]);

  // 탭 복귀 시 재확인(OS 위치 토글 등 — Permissions change 가 안 오는 변경을 따라잡는다).
  useEffect(() => {
    if (!enabled) return;
    const onFocus = () => refresh();
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled, refresh]);

  return { status, permission, permissionResolved, coords, locate, refresh };
}
