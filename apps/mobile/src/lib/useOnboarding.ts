import { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

// 첫 방문 온보딩 판별 + 영속 (Story 3.9 → 9.4 — AC2·AC3). 기기 로컬 1회 노출 플래그(모바일).
//
// 웹 useOnboarding 과 동일한 동작 패턴(플래그 읽기 → 미노출이면 표시 → 닫음)이나, 저장소가 다르다:
// AsyncStorage 는 **비동기**(웹 localStorage 동기와 핵심 차이)다. 읽기 완료 전엔 미표시 → 깜빡임
// 없음. 서버 추적 0(로그인·네트워크·위치와 무관한 별도 축).
//
// ⚠️ 닫기 정책(9.4 — 웹=정본이 과거 확정③ supersede): **"다시 보지 않기"만 영속(dismiss)**,
//    "시작하기"·X·바깥 탭·Android 백은 **비영속 close**(다음 방문 재노출). 과거 모바일은 어떤 닫힘이든
//    dismiss 로 수렴(확정③)했으나, 웹 정책(close/dismiss 분리)으로 교체한다.
//
// ⚠️ 비동기 setState 누수 = 함정. 언마운트 가드(active 플래그)로 읽기 완료가 언마운트 이후 도착해도
//    setState 하지 않는다.
const ONBOARDING_SEEN_KEY = 'desknow:onboarding:seen';

type UseOnboarding = {
  /** 온보딩 오버레이를 띄울지 여부. 읽기 완료 전엔 false(깜빡임 방지). */
  shouldShow: boolean;
  /** "다시 보지 않기" — 플래그 영속(재방문 무노출) + 즉시 미표시. */
  dismiss: () => void;
  /** "시작하기"·X·바깥 탭·Android 백 — 영속 없이 이번만 닫는다(다음 방문 재노출). */
  close: () => void;
};

export function useOnboarding(): UseOnboarding {
  const [shouldShow, setShouldShow] = useState(false);

  useEffect(() => {
    let active = true; // 언마운트 가드 — 비동기 읽기 누수 방지.
    (async () => {
      try {
        const seen = await AsyncStorage.getItem(ONBOARDING_SEEN_KEY);
        if (active && seen === null) {
          setShouldShow(true);
        }
      } catch {
        // 스토리지 실패 → graceful(미표시). 막다른 화면·크래시 금지.
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  function dismiss() {
    // fire-and-forget — 영속을 기다리지 않고 즉시 닫는다(실패는 catch 로 삼킴, 다음 방문 재노출 감수).
    AsyncStorage.setItem(ONBOARDING_SEEN_KEY, '1').catch(() => {});
    setShouldShow(false);
  }

  function close() {
    // 영속하지 않고 이번 세션만 닫는다 — "다시 보지 않기"를 누르기 전까지 다음 방문에 재노출.
    setShouldShow(false);
  }

  return { shouldShow, dismiss, close };
}
