"use client";

// 네트워크 단절 감지 단일 출처 (Story 3.8 — AC1·AC2).
//
// `navigator.onLine` + window `online`/`offline` 이벤트를 `useSyncExternalStore` 로 구독한다.
// 수동 `useEffect`+`useState` 대비 tearing-safe 하고 SSR 안전하다(getServerSnapshot). 신규
// 의존성 0(React 내장 — 확정②). 반환값 `isOnline` 의 식별자는 navigator API 표준어를 따르되,
// **사용자 의미는 "네트워크 연결" 상태**다(로그인/세션·위치 권한과 무관한 별도 축 — 확정①).
//
// ⚠️ `navigator.onLine` 한계: 브라우저가 "연결됨"이라 보고해도 실제 도달 불가일 수 있다(캡티브
//    포털 등). 단 본 스토리 목적(완전 단절 시 막다른 화면 방지)에는 충분하다 — 정밀 헬스체크는
//    과설계·범위 밖이다.
import { useSyncExternalStore } from "react";

// online/offline 이벤트에 콜백을 등록/해제한다. 이 함수는 클라이언트에서만 호출된다
// (useSyncExternalStore 계약 — 서버에서는 getServerSnapshot 만 사용).
function subscribe(callback: () => void): () => void {
  window.addEventListener("online", callback);
  window.addEventListener("offline", callback);
  return () => {
    window.removeEventListener("online", callback);
    window.removeEventListener("offline", callback);
  };
}

// 클라이언트 스냅샷 — 현재 네트워크 연결 여부.
function getSnapshot(): boolean {
  return navigator.onLine;
}

// 서버/최초 하이드레이션 스냅샷 — 항상 "연결됨"으로 가정한다(SSR 에는 navigator 가 없고,
// 하이드레이션 직후 단절 배너가 깜빡이는 것을 막는다).
function getServerSnapshot(): boolean {
  return true;
}

/** 현재 네트워크 연결 여부. `false` 면 네트워크 단절(확정① — "오프라인" 금지, 의미는 네트워크). */
export function useOnlineStatus(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
