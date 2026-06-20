// 디바이스 식별자 — 클라 생성 안정 UUID (Story 7.3, AC3·AC4).
//
// thread_id = `${user_id}:${device_id}`(서버 도출)의 device 부분을 클라가 책임진다. localStorage
// 에 1회 생성·영속하며 **로그아웃에도 회전하지 않는다**(디바이스 식별자 — 세션이 아니라 기기 단위).
// 인증 스키마(refresh_tokens·JWT)를 건드리지 않고 "사용자×디바이스" 세션을 충족하는 핵심 장치다.
import { useSyncExternalStore } from "react";

/** localStorage 키 — 디바이스 식별자 단일 출처. */
const DEVICE_ID_KEY = "desknow.deviceId";

/** 클라 1회 생성한 device_id 캐시 — getSnapshot 안정성(동일 참조 반환) + 생성 write 1회화. */
let cachedDeviceId: string | null = null;

/**
 * RFC4122 v4 UUID 를 생성한다. `crypto.randomUUID` 가 있으면 사용하고, 없으면 폴백한다.
 *
 * `crypto.randomUUID` 는 **secure context(HTTPS/localhost)에서만** 정의된다 — HTTP(사내망·IP
 * 접속)·일부 구형 웹뷰에서는 미정의라 직접 호출 시 TypeError 로 렌더가 깨진다. device_id 는 보안
 * 토큰이 아니라 불투명 식별자이므로 비-보안 컨텍스트에서는 `Math.random` 폴백으로 충분하다.
 */
function generateUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * localStorage 에서 device_id 를 읽고, 없으면 생성·저장해 반환한다.
 *
 * **SSR 안전:** `window` 가 없으면 빈 문자열을 반환한다(서버 렌더에서 localStorage 미접근).
 * **getSnapshot 안정성:** 클라에서 1회 확정한 값을 모듈 캐시(`cachedDeviceId`)에 보관해 이후 호출은
 * localStorage 접근·write 없이 동일 참조를 반환한다(`useSyncExternalStore` 순수성 — 생성 write 1회).
 */
export function getOrCreateDeviceId(): string {
  if (typeof window === "undefined") {
    return ""; // SSR — 클라 마운트 후 실값으로 대체
  }
  if (cachedDeviceId !== null) {
    return cachedDeviceId; // 캐시 적중: write 없이 안정 참조 반환
  }
  let id = window.localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id = generateUuid();
    window.localStorage.setItem(DEVICE_ID_KEY, id);
  }
  cachedDeviceId = id;
  return id;
}

// device_id 는 한 번 정해지면 변하지 않으므로 외부 스토어 구독은 no-op(변경 알림 불요).
function subscribe(): () => void {
  return () => {};
}

/**
 * device_id 를 제공하는 클라 훅. `useSyncExternalStore` 로 **하이드레이션 안전**하게 읽는다:
 * 서버 스냅샷은 `""`(SSR — localStorage 미접근), 클라 스냅샷은 실 device_id. 첫 클라 렌더는
 * 서버와 동일한 `""` 로 맞춘 뒤 즉시 실값으로 재조정돼 미스매치 경고가 없다. 소비처(useChatbot)는
 * `""` 동안 쿼리/뮤테이션을 비활성화한다(device_id 형식 8자 미만 = 서버 422 회피).
 */
export function useDeviceId(): string {
  return useSyncExternalStore(
    subscribe,
    getOrCreateDeviceId, // 클라 스냅샷(같은 문자열 반환 → Object.is 안정, 루프 없음)
    () => "", // 서버 스냅샷
  );
}
