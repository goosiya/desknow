"use client";

// 첫 진입 지도 화면 (Story 3.2 — AC1·AC2·AC3·AC5; 3.6 위치 통합 — AC4·AC5). 카카오맵 +
// 주변 핀 + 가용성 색/아이콘 + 핀 탭 → 최소 바텀시트 + 막다른 화면 금지(로딩/빈/에러/권한거부).
//
// 3.6: 위치 신호는 더 이상 자체 소유하지 않는다 — ExploreView 가 useGeolocation 단일 소유로
// 좌표/거부를 `coords`/`locationDenied` prop 으로 주입한다(인라인 getCurrentPosition 제거,
// 위치 요청 2곳→1곳 통합). coords 가 오면 현위치 중심으로 이동(AC1), locationDenied 면 서울
// 폴백 중심 유지 + 배너(AC5④). MapView 는 navigator.geolocation 을 직접 호출하지 않는다.
//
// 카카오 SDK 는 외부 `<script>` 라 e2e(NFR-2 ≤2초)는 수동/후속 측정이다. 테스트는 loadKakaoMaps
// 와 SDK 함수를 모킹하고 coords/locationDenied prop 으로 상태 분기·마커 생성·핀→시트를 검증한다.
import { useCallback, useEffect, useRef, useState } from "react";

import { loadKakaoMaps } from "@/lib/kakao-map";
import { useOnlineStatus } from "@/lib/useOnlineStatus";
import { NetworkNotice } from "@/components/NetworkNotice";
import type { Coords } from "@/features/list/useGeolocation";
import { createPinElement } from "./pinElement";
import type { RoomPin } from "./pin";
import { RoomSheet } from "./RoomSheet";
import { useRoomPins } from "./useRoomPins";

// 빈/에러 상태의 "목록 우회" 액션이 ExploreView 로 전환할 검색방식(3.4 지역 / 3.5 반경).
// ExploreView 의 SearchMode 와 같은 유니온 — 구조적 호환(타입 중복 최소·순환 import 회피).
export type SwitchToListMode = "region" | "radius";

// 위치 거부/불가 시 기본 중심(서울 시청 — AC5④ 폴백).
const SEOUL_LAT = 37.5665;
const SEOUL_LNG = 126.978;

// 초기 지도 축척(카카오 level — 작을수록 확대). 생성 시 중심과 함께 쓰고, '내 반경' 재중심 시
// 사용자가 바꾼 축척을 이 값으로 되돌린다(내 위치를 초기 표현으로 복귀 — KTH 2026-06-19).
const INITIAL_MAP_LEVEL = 5;

type MapStatus = "loading" | "ready" | "error";

type MapViewProps = {
  // 위치 허용 시 현위치 좌표(ExploreView 단일 소유 — useGeolocation 에서 주입). 없으면 서울 폴백.
  coords?: Coords | null;
  // 위치 확보 대기 신호(KTH 2026-06-19) — true 면 지도를 아직 생성하지 않는다. 권한이 있는데
  // 좌표 측정이 끝나기 전이라는 뜻으로, 서울로 먼저 그렸다가 점프하는 대신 좌표가 올 때까지
  // 기다렸다 처음부터 내 위치로 그리기 위함이다(스켈레톤 유지). false 면 coords(있으면)·서울로 생성.
  pendingLocation?: boolean;
  // 위치 거부/미지원 신호 — true 면 서울 폴백 중심 유지 + 배너(AC5④).
  locationDenied?: boolean;
  // '내 반경' 재중심 신호 — 값이 바뀔 때마다 현 coords 로 지도 중심을 다시 옮긴다(좌표가 동일해도
  // effect 가 재실행되도록 nonce 로 전달). 0(기본)이면 재중심하지 않는다.
  recenterNonce?: number;
  // 빈/에러 상태의 "목록 우회" 액션(3.8 AC1) — ExploreView 가 목록 뷰로 전환·검색방식 지정.
  onSwitchToList?: (mode: SwitchToListMode) => void;
};

export function MapView({
  coords,
  pendingLocation = false,
  locationDenied = false,
  recenterNonce = 0,
  onSwitchToList,
}: MapViewProps) {
  const { pins, isLoading, isError, isEmpty, refetch } = useRoomPins();
  // 네트워크 단절 감지(3.8 AC1) — 단절을 일반 에러로 오인 표시하지 않도록 최우선 게이팅한다.
  const isOnline = useOnlineStatus();

  const [mapStatus, setMapStatus] = useState<MapStatus>("loading");
  const [selectedRoom, setSelectedRoom] = useState<RoomPin | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<kakao.maps.Map | null>(null);
  const overlaysRef = useRef<kakao.maps.CustomOverlay[]>([]);

  // ── 모바일 지도 높이 맞춤(KTH 2026-06-20): 세로가 짧은 폰에서 60vh/min-h-80 이 헤더·제목·토글·
  //    하단 네비를 빼고 남는 공간보다 커서, 지도 바닥이 fixed 하단 내비 **밑으로 묻혔다**. 모바일(sm)
  //    에서만 지도 높이를 "컨테이너 상단 ~ 하단 네비 상단"으로 측정해 맞춰(바닥=네비 상단) 묻힘을
  //    없앤다. PC(md+)는 측정하지 않고(null) CSS `md:h-[60vh]` 를 그대로 둔다(요구사항 — PC 무영향).
  //    주소창 접힘·회전으로 뷰포트가 바뀌면 resize 로 재계산한다. 하한 240px(과도 축소 방지). ──
  const [fitHeight, setFitHeight] = useState<number | null>(null);
  useEffect(() => {
    const MD_BREAKPOINT = 768; // tailwind md — 이상이면 PC 취급(측정 안 함)
    const compute = () => {
      const container = containerRef.current;
      if (!container) return;
      if (window.innerWidth >= MD_BREAKPOINT) {
        setFitHeight(null); // PC = CSS 60vh 유지
        return;
      }
      const nav = document.querySelector('nav[aria-label="하단 내비게이션"]');
      const navTop = nav
        ? nav.getBoundingClientRect().top
        : window.innerHeight;
      const containerTop = container.getBoundingClientRect().top;
      // 둘 다 뷰포트 기준 — 지도 바닥이 네비 상단에 닿는 높이. 패딩 제거로 스크롤이 없어 안정적.
      setFitHeight(Math.max(240, Math.round(navTop - containerTop)));
    };
    compute();
    window.addEventListener("resize", compute);
    window.addEventListener("orientationchange", compute);
    return () => {
      window.removeEventListener("resize", compute);
      window.removeEventListener("orientationchange", compute);
    };
  }, []);
  // 직전 렌더가 단절 상태였는지 — 재연결(단절→연결) 전이에서만 지도 SDK 자동 재시도하기 위한 가드.
  const wasOfflineRef = useRef(false);

  // ── SDK 병렬 prefetch(KTH 2026-06-19): 위치 측정과 무관하게 mount 즉시 카카오 SDK 로드를 시작한다.
  //    지도 생성을 위치 확보까지 보류하므로, prefetch 가 없으면 SDK 로드가 측정 뒤로 밀려 "측정 시간 +
  //    SDK 로드"가 순차로 합산된다(느림). loadKakaoMaps 는 Promise 를 캐시하므로 아래 생성 effect 의
  //    재호출은 이미 진행/완료된 같은 Promise 를 받아 즉시 지도를 만든다. 실패는 생성 effect 가 표면화한다. ──
  useEffect(() => {
    loadKakaoMaps().catch(() => {});
  }, []);

  // ── 지도 생성(KTH 2026-06-19 재설계): 위치 확보 전(pendingLocation)에는 생성하지 않고 스켈레톤을
  //    유지하다가, 좌표가 오거나(권한 허용) 위치를 안 쓰기로 확정되면(prompt/denied/미지원) **그 시점에
  //    올바른 초기 중심(coords ?? 서울)으로 단 한 번 생성**한다. 서울로 먼저 그렸다 coords 로 점프하던
  //    구조를 제거해 "처음부터 내 위치"를 보장한다. 이미 생성됐으면(좌표가 늦게 와도) 재생성하지 않고
  //    아래 좌표 반응 effect 가 이동을 맡는다('내 반경' 재측정 등). reloadNonce 로 재시도. ──
  useEffect(() => {
    if (pendingLocation || mapRef.current) return; // 위치 대기 중이거나 이미 생성됨 → 보류
    let cancelled = false;
    // 컨테이너 DOM 노드를 effect 시작 시점에 캡처한다(cleanup 시 ref 변동 대비, exhaustive-deps).
    const container = containerRef.current;
    // 초기 중심: 좌표가 있으면 내 위치, 없으면 서울 폴백(권한 없음/거부 확정).
    const initLat = coords ? coords.lat : SEOUL_LAT;
    const initLng = coords ? coords.lng : SEOUL_LNG;
    loadKakaoMaps()
      .then((kakao) => {
        if (cancelled || !container || mapRef.current) return;
        const map = new kakao.maps.Map(container, {
          center: new kakao.maps.LatLng(initLat, initLng),
          level: INITIAL_MAP_LEVEL,
        });
        mapRef.current = map;
        setMapStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setMapStatus("error");
      });
    // 이 effect 는 좌표/대기 변화로 재실행될 수 있으나(생성은 1회·위 가드), 생성된 지도를 여기서
    // 정리하면 안 된다(재실행마다 파괴됨) → cancelled 만 처리하고, 지도/오버레이 정리는 재시도
    // (handleRetry)와 언마운트 정리 effect 가 책임진다.
    return () => {
      cancelled = true;
    };
  }, [reloadNonce, pendingLocation, coords]);

  // ── 현위치 중심 이동: 지도 생성 후 coords 가 바뀌면(예: '내 반경' 재측정·뒤늦은 좌표 도착) 그
  //    좌표로 중심을 옮긴다. 최초 생성은 이미 올바른 중심으로 그려지므로 보통 추가 이동은 없다.
  //    setCenter 는 카카오 API 호출이라 setState 가 아니다(cascading render 없음). ──
  useEffect(() => {
    const map = mapRef.current;
    if (mapStatus !== "ready" || !map || !coords) return;
    const kakao = typeof window !== "undefined" ? window.kakao : undefined;
    if (!kakao) return;
    map.setCenter(new kakao.maps.LatLng(coords.lat, coords.lng));
  }, [coords, mapStatus]);

  // ── 컨테이너 크기 변화 시 relayout(KTH 2026-06-19 모바일 인터랙션): 카카오 지도는 **생성 후
  //    컨테이너 크기가 바뀌면** 내부 타일/좌표 캐시가 stale 되어, 일부가 회색으로 남거나 드래그/탭
  //    좌표가 어긋나 "지도가 움직이지 않는" 것처럼 보인다. 모바일에서 흔히 발생한다 — 스크롤 시
  //    주소창이 접히며 뷰포트 높이(60vh)가 변하고, 화면 회전·동적 레이아웃(상단 배너 등장/소멸)도
  //    컨테이너를 리사이즈한다. ResizeObserver 로 실제 크기 변화만 감지해 ``relayout()`` 으로
  //    내부 상태를 컨테이너에 다시 맞춘다(relayout 후 중심 보존). **PC 는 컨테이너 크기가 거의 안
  //    변해 관찰자가 초기 1회 외엔 발화하지 않아 사실상 no-op**(데스크탑 동작 무영향). ──
  useEffect(() => {
    if (mapStatus !== "ready") return;
    const map = mapRef.current;
    const container = containerRef.current;
    if (!map || !container || typeof ResizeObserver === "undefined") return;
    // 관찰 시작 시점 크기를 기준으로 잡아, observe() 직후 동일 크기로 오는 최초 콜백은 건너뛴다
    // (생성 직후 불필요한 relayout 방지). 이후 실제 크기 변화에만 relayout 한다.
    let prevW = container.clientWidth;
    let prevH = container.clientHeight;
    const observer = new ResizeObserver(() => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w === prevW && h === prevH) return; // 변화 없음 → no-op(PC 안정 상태 포함)
      prevW = w;
      prevH = h;
      // relayout 은 중심을 보존하지만 일부 빌드에서 미세 이동이 있어 명시적으로 복원한다.
      const center = map.getCenter();
      map.relayout();
      map.setCenter(center);
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [mapStatus]);

  // ── 언마운트 정리: 카카오는 destroy() 가 없어 오버레이를 지도에서 분리하고 ref 를 비운다(누수 방지). ──
  useEffect(() => {
    return () => {
      for (const overlay of overlaysRef.current) overlay.setMap(null);
      overlaysRef.current = [];
      mapRef.current = null;
    };
  }, []);

  // ── '내 반경' 재중심: recenterNonce 가 바뀌면(사용자 클릭) 현 coords 로 중심을 다시 옮기고
  //    **축척도 초기값(INITIAL_MAP_LEVEL)으로 되돌린다**(KTH 2026-06-19). 사용자가 다른 지역으로
  //    이동하며 확대/축소를 바꿔놨더라도, '내 반경'은 "내 위치를 초기 표현으로 보여주기"이므로
  //    중심뿐 아니라 축척까지 초기 상태로 복귀시킨다. 좌표가 직전과 같아도(위 coords effect 가
  //    재실행 안 됨) 사용자가 지도를 옮긴 뒤 눌렀을 수 있으므로 별도 nonce effect 로 강제한다.
  //    nonce 0(초기)·좌표 없음이면 아무 것도 하지 않는다. setCenter→setLevel 순서로, 내 위치를
  //    중심에 놓은 뒤 그 중심 기준으로 초기 축척으로 줌한다. ──
  useEffect(() => {
    if (recenterNonce === 0) return;
    const map = mapRef.current;
    if (mapStatus !== "ready" || !map || !coords) return;
    const kakao = typeof window !== "undefined" ? window.kakao : undefined;
    if (!kakao) return;
    map.setCenter(new kakao.maps.LatLng(coords.lat, coords.lng));
    map.setLevel(INITIAL_MAP_LEVEL); // 사용자가 바꾼 축척을 초기값으로 복귀(중심 유지 줌)
  }, [recenterNonce, coords, mapStatus]);

  // ── 핀 렌더: 지도 준비 후 pins 변화 시 CustomOverlay 를 다시 그린다(색+아이콘+aria). ──
  useEffect(() => {
    const map = mapRef.current;
    if (mapStatus !== "ready" || !map) return;
    const kakao = typeof window !== "undefined" ? window.kakao : undefined;
    if (!kakao) return;
    // 기존 오버레이 제거 후 재생성(가용성 갱신 시 색이 바뀜).
    for (const overlay of overlaysRef.current) overlay.setMap(null);
    overlaysRef.current = [];
    for (const pin of pins) {
      const overlay = new kakao.maps.CustomOverlay({
        position: new kakao.maps.LatLng(pin.lat, pin.lng),
        content: createPinElement(pin, setSelectedRoom),
        map,
        yAnchor: 1,
      });
      overlaysRef.current.push(overlay);
    }
    // cleanup: pins/mapStatus 변경 또는 언마운트 시 이번 run 의 오버레이를 지도에서 분리한다
    // (재실행 시작부의 정리와 더불어 언마운트 누수도 막는다).
    return () => {
      for (const overlay of overlaysRef.current) overlay.setMap(null);
      overlaysRef.current = [];
    };
  }, [pins, mapStatus]);

  const handleRetry = useCallback(() => {
    // 재시도: 생성 effect 가 더는 정리하지 않으므로 여기서 직접 이전 지도/오버레이를 치운다. 카카오는
    // destroy() 가 없어 컨테이너 DOM 을 비워 고스트 레이어 누적을 막고, mapRef 를 비워 effect 가 새
    // 지도를 만들게 한다(reloadNonce 증가로 재실행 트리거).
    for (const overlay of overlaysRef.current) overlay.setMap(null);
    overlaysRef.current = [];
    mapRef.current = null;
    if (containerRef.current) containerRef.current.innerHTML = "";
    setMapStatus("loading");
    setReloadNonce((n) => n + 1);
    refetch();
  }, [refetch]);

  // ── 재연결 자동 복구(3.8 code-review 2026-06-16): 최초 진입부터 단절이면 loadKakaoMaps 가
  //    실패해 mapStatus="error" 가 되지만 단절 동안엔 배너만 보인다. 연결되면 핀은
  //    refetchOnReconnect 로 자동 재조회되나 **지도 SDK 로드 effect 는 [reloadNonce] 의존이라
  //    재실행되지 않는다** → 사용자가 직접 "다시 시도"를 눌러야 했다. 단절→연결 전이에서
  //    지도가 error 면 1회 자동 재시도해 "연결되면 다시 보여드릴게요"를 충족한다.
  //    wasOfflineRef 가드로 **온라인 중 발생한 일반 에러는 자동 재시도하지 않는다**(무한 루프 방지·
  //    사용자 주도 재시도 유지). ──
  useEffect(() => {
    if (!isOnline) {
      wasOfflineRef.current = true;
      return;
    }
    if (wasOfflineRef.current) {
      wasOfflineRef.current = false;
      // set-state-in-effect 함정(3.5 학습·ExploreView 선례) 회피: 동기 cascading setState 대신
      // 마이크로태스크로 이월한다. mapStatus 는 재연결 시점 값으로 캡처된다.
      if (mapStatus === "error") queueMicrotask(handleRetry);
    }
  }, [isOnline, mapStatus, handleRetry]);

  // 데이터(좌표) 로드 실패도 지도 에러와 동일하게 "막힘 방지" 처리한다. 단, **네트워크 단절은
  // 에러로 오인 표시하지 않는다**(3.8 AC1) — 단절은 NetworkNotice 가 우선 처리하고 마지막 핀
  // 캐시를 유지한다. `isOnline &&` 게이팅으로 단절을 "지도를 못 불러왔어요"로 덮지 않는다.
  const showError = isOnline && (mapStatus === "error" || isError);

  return (
    <section className="relative" aria-label="스터디룸 찾기 지도">
      {/* 지도 타일 컨테이너(카카오가 이 div 에 렌더). 핀은 CustomOverlay 로 이 위에 얹힌다. */}
      <div
        ref={containerRef}
        data-testid="map-container"
        // 모바일은 fitHeight(네비 상단까지 측정값)로 덮어쓰고, PC(md+)는 CSS h-[60vh] 유지.
        // 측정 전(SSR/첫 페인트)·모바일 기본은 h-[60dvh](주소창 반영). md:min-h-80 은 PC 하한.
        style={fitHeight !== null ? { height: fitHeight } : undefined}
        className="h-[60dvh] w-full overflow-hidden rounded-lg border border-border bg-muted md:h-[60vh] md:min-h-80"
      />

      {/* AC5① 로딩: 지도/데이터 준비 전 스켈레톤 + 핀 placeholder(전역 스피너 금지). 단절 시에는
          표시하지 않는다(refetch 가 멈춰 무한 스켈레톤이 되므로 — NetworkNotice 만 띄운다, 3.8). */}
      {(mapStatus === "loading" || isLoading) && !showError && isOnline && (
        <div
          data-testid="map-skeleton"
          className="absolute inset-0 flex items-center justify-center rounded-lg bg-muted/80"
        >
          <p className="animate-pulse text-sm text-muted-foreground">
            주변 스터디룸을 불러오는 중이에요…
          </p>
        </div>
      )}

      {/* 3.8 AC1 네트워크 단절: 에러보다 우선. 마지막 핀 캐시(TanStack 메모리 잔존)는 그대로 두고
          상단 배너만 얹는다. 재연결 시 refetchOnReconnect(query-client 기본 true) 가 자동 재조회 →
          "연결되면 다시 보여드릴게요" 충족. 최초 진입부터 단절이면 캐시·지도 없이 배너만 표시(막힘 아님). */}
      {!isOnline && <NetworkNotice className="absolute inset-x-0 top-0 z-10 m-3" />}

      {/* AC5③ 지도/데이터 실패: 안내 + 재시도 + 목록 우회(3.8 AC1 — 막다른 화면 금지). */}
      {showError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 rounded-lg bg-card/95 p-6 text-center">
          <p className="text-base font-medium text-card-foreground">
            지도를 못 불러왔어요.
          </p>
          <p className="text-sm text-muted-foreground">
            잠시 후 다시 시도하거나, 목록으로 둘러볼 수 있어요.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <button
              type="button"
              onClick={handleRetry}
              className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
            >
              다시 시도
            </button>
            <button
              type="button"
              onClick={() => onSwitchToList?.("region")}
              className="tap-target inline-flex items-center justify-center rounded-md border border-border bg-card px-4 text-sm font-medium text-card-foreground"
            >
              목록으로 보기
            </button>
          </div>
        </div>
      )}

      {/* AC5④ 위치 거부: 안내 배너 + 기본 중심(서울) 폴백으로 핀은 그대로 표시(막힘 없음). 단절
          시에는 NetworkNotice 가 상단을 차지하므로 위치 배너는 생략한다(연결되면 다시 노출, 3.8). */}
      {locationDenied && !showError && isOnline && (
        <div
          role="status"
          className="absolute inset-x-0 top-0 m-3 rounded-md bg-secondary px-4 py-2 text-sm text-secondary-foreground"
        >
          현재 위치를 못 받았어요. 동네를 골라서 찾아볼게요.
        </div>
      )}

      {/* AC5② 빈 상태: 주변 활성 룸 0개 → 다음-행동 액션 버튼(3.8 AC1 — 반경 확대·지역 전환).
          단절 시에는 표시하지 않는다(빈 결과가 아니라 단절일 수 있으므로 — NetworkNotice 우선). */}
      {isEmpty && !showError && mapStatus === "ready" && isOnline && (
        <div className="absolute inset-x-0 bottom-0 m-3 flex flex-col gap-2 rounded-md bg-card/95 px-4 py-3 text-center shadow-sheet">
          <p className="text-sm font-medium text-card-foreground">
            이 근처엔 아직 없어요.
          </p>
          <p className="text-xs text-muted-foreground">
            동네를 넓혀볼까요? 다른 방식으로 찾아볼 수 있어요.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <button
              type="button"
              onClick={() => onSwitchToList?.("region")}
              className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
            >
              지역으로 찾기
            </button>
            <button
              type="button"
              onClick={() => onSwitchToList?.("radius")}
              className="tap-target inline-flex items-center justify-center rounded-md border border-border bg-card px-4 text-sm font-medium text-card-foreground"
            >
              반경으로 넓혀보기
            </button>
          </div>
        </div>
      )}

      {/* 핀 탭 → 바텀시트(vaul). 신선 단일 조회 콘텐츠는 RoomSheet 가 책임진다(3.3). 항상
          마운트하고 open 으로 제어한다 — vaul 이 Esc/드래그-다운/오버레이 클릭을 onOpenChange(false)
          로 알리면 selectedRoom 을 해제해 닫는다. name/status 는 핀에서 즉시 헤더·배지 초기 표시. */}
      <RoomSheet
        roomId={selectedRoom?.room_id ?? ""}
        name={selectedRoom?.name ?? ""}
        fallbackStatus={selectedRoom?.status}
        open={!!selectedRoom}
        onOpenChange={(o) => {
          if (!o) setSelectedRoom(null);
        }}
      />
    </section>
  );
}
