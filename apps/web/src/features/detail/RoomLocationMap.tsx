"use client";

// 상세 위치 미니 지도 (Story 4.2 — AC3). 룸 좌표(lat/lng)를 중심으로 단일 핀을 찍는 정적 지도다.
//
// 3.2 `loadKakaoMaps` 동적 로더를 **재사용**한다(REST 키 없이 저장 좌표만 사용 — 지오코딩 호출
// 0, NFR-6). 탐색 지도(MapView)와 달리 드래그·핀 클릭·재조회가 필요 없어 정적 표시만 한다.
// 카카오 Map 은 destroy() 가 없어 언마운트/재시도 시 컨테이너 innerHTML 비우기 + overlay
// setMap(null) 로 정리한다(MapView L85-94 선례).
//
// ⚠️ graceful degrade(AC3): SDK 로드 실패 시 **이 지도 영역만** "지도를 못 불러왔어요" 자리로
//    대체되고 상세 화면 전체는 막히지 않는다(나머지 정보·예약 전개는 정상). jsdom 은 실 타일을
//    렌더하지 못하므로 테스트는 loadKakaoMaps·SDK 함수를 모킹해 호출·중심 좌표·실패 자리만 단언한다.
import { useEffect, useRef, useState } from "react";

import { loadKakaoMaps } from "@/lib/kakao-map";

type RoomLocationMapProps = {
  lat: number;
  lng: number;
  /** 핀 접근성 라벨용 룸 이름(선택). */
  name?: string;
};

type MapStatus = "loading" | "ready" | "error";

/** 단일 핀 CustomOverlay 의 content 엘리먼트(정적 표시 — 색+점). aria 라벨로 위치를 알린다. */
function createPinContent(name?: string): HTMLElement {
  const el = document.createElement("div");
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", name ? `${name} 위치` : "스터디룸 위치");
  el.className = "size-4 rounded-full border-2 border-card bg-primary";
  return el;
}

export function RoomLocationMap({ lat, lng, name }: RoomLocationMapProps) {
  const [status, setStatus] = useState<MapStatus>("loading");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const overlayRef = useRef<kakao.maps.CustomOverlay | null>(null);

  useEffect(() => {
    let cancelled = false;
    // 컨테이너 DOM 을 effect 시작 시점에 캡처한다(cleanup 시 ref.current 가 바뀔 수 있어 — MapView 선례).
    const container = containerRef.current;
    loadKakaoMaps()
      .then((kakao) => {
        if (cancelled || !container) return;
        const center = new kakao.maps.LatLng(lat, lng);
        const map = new kakao.maps.Map(container, { center, level: 4 });
        // 단일 핀(드래그/탐색 불필요 — 정적 표시). CustomOverlay 로 접근성 라벨을 직접 통제한다.
        overlayRef.current = new kakao.maps.CustomOverlay({
          position: center,
          content: createPinContent(name),
          map,
          yAnchor: 1,
        });
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
      // 카카오 Map 은 destroy() 가 없어 컨테이너를 비워 고스트 레이어 누적을 막는다(MapView 선례).
      if (overlayRef.current) {
        overlayRef.current.setMap(null);
        overlayRef.current = null;
      }
      if (container) container.innerHTML = "";
    };
    // lat/lng/name 변경 시 재초기화(상세는 단일 룸이라 사실상 1회).
  }, [lat, lng, name]);

  // 지도 로드 실패 → 이 영역만 graceful degrade(전체 화면 막지 않음, AC3).
  if (status === "error") {
    return (
      <div
        role="status"
        className="flex h-44 w-full items-center justify-center rounded-lg border border-border bg-muted px-4 text-center text-sm text-muted-foreground"
      >
        지도를 못 불러왔어요.
      </div>
    );
  }

  return (
    <div className="relative">
      {/* 지도 타일 컨테이너(카카오가 이 div 에 렌더 — MapView 컨테이너 토큰 미러). */}
      <div
        ref={containerRef}
        data-testid="location-map-container"
        className="h-44 w-full overflow-hidden rounded-lg border border-border bg-muted"
      />
      {/* 로드 중 자리 스켈레톤(준비되면 지도 타일이 덮는다). */}
      {status === "loading" && (
        <div
          data-testid="location-map-skeleton"
          className="absolute inset-0 flex items-center justify-center rounded-lg bg-muted/80"
        >
          <p className="animate-pulse text-sm text-muted-foreground">
            지도를 불러오는 중이에요…
          </p>
        </div>
      )}
    </div>
  );
}
