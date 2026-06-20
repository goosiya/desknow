"use client";

// 첫 방문 온보딩 판별 + 영속 (Story 3.9 — AC2·AC3). 기기 로컬 1회 노출 플래그.
//
// 서버는 "본 적 있음"을 추적하지 않는다(로그인 무관·쿠키 미사용·서버 미전송 — 본 스토리 본질).
// localStorage 1개 불리언 플래그만 본다. 세션(useSession)·네트워크 단절(useOnlineStatus)·위치
// 권한(useGeolocation)과 무관한 별도 축이다 — 엮지 말 것.
//
// ⚠️ SSR/하이드레이션 깜빡임 = 최대 함정. `localStorage` 는 서버에 없으므로 **초기 상태를 "미표시"
//    (false)로 두고 useEffect 에서만 켠다.** 동기로 읽으면 하이드레이션 미스매치, SSR 에서 "표시"로
//    가정하면 본 적 있는 재방문자에게 한 틱 깜빡인다 → 둘 다 금지. mounted-gate 가 정답
//    (useOnlineStatus.ts 의 getServerSnapshot=true 와 같은 SSR 안전 사상).
import { useEffect, useState } from "react";

// 스토리지 키 — 네임스페이스로 충돌·오탐 방지.
const ONBOARDING_SEEN_KEY = "desknow:onboarding:seen";

type UseOnboarding = {
  /** 온보딩 오버레이를 띄울지 여부. 서버·최초 클라 렌더에선 항상 false(깜빡임 방지). */
  shouldShow: boolean;
  /** "다시 보지 않기" — 플래그 영속(재방문 무노출) + 즉시 미표시. */
  dismiss: () => void;
  /** "시작하기"·우상단 X·Esc·바깥 클릭 — 영속 없이 이번만 닫는다(다음 방문 시 재노출). */
  close: () => void;
};

export function useOnboarding(): UseOnboarding {
  // 초기 false = 서버/최초 클라 렌더는 미표시. effect 에서만 켠다.
  const [shouldShow, setShouldShow] = useState(false);

  useEffect(() => {
    let cancelled = false; // 언마운트 가드.
    // 시크릿 모드/스토리지 차단 시 getItem 이 throw 가능 → graceful(미표시).
    let unseen = false;
    try {
      unseen = window.localStorage.getItem(ONBOARDING_SEEN_KEY) === null;
    } catch {
      // 스토리지 접근 불가 → 막다른 화면·콘솔 에러 금지. 그냥 표시하지 않는다.
    }
    // effect 동기 setState 금지(react-hooks/set-state-in-effect, 3.5/3.6 학습) — 마이크로태스크로
    // 이월한다. useGeolocation 선례와 동일. 첫 페인트엔 지도만, 다음 틱에 오버레이.
    if (unseen) {
      queueMicrotask(() => {
        if (!cancelled) setShouldShow(true);
      });
    }
    return () => {
      cancelled = true;
    };
  }, []);

  function dismiss() {
    try {
      window.localStorage.setItem(ONBOARDING_SEEN_KEY, "1");
    } catch {
      // 영속 실패해도 현 세션은 닫는다(아래 setShouldShow). 다음 방문 재노출은 감수.
    }
    setShouldShow(false);
  }

  function close() {
    // 영속하지 않고 이번 세션만 닫는다 — "다시 보지 않기"를 누르기 전까지 다음 방문에 재노출.
    setShouldShow(false);
  }

  return { shouldShow, dismiss, close };
}
