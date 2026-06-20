// 디바이스 식별자 — 웹 deviceId.ts RN 포팅 (Story 9.3 — AC6).
//
// thread_id = `${user_id}:${device_id}`(서버 도출)의 device 부분을 클라가 책임진다. 웹은
// localStorage였지만 모바일은 **AsyncStorage**(온보딩과 동형·키 `desknow.deviceId`)에 1회
// 생성·영속하며 **로그아웃에도 회전하지 않는다**(디바이스 식별자 — 세션이 아니라 기기 단위).
//
// ⚠️ RN(Hermes)엔 `crypto.randomUUID`가 없으므로 **Math.random v4 폴백**(웹의 비-secure-context
//    폴백 복사). device_id는 보안 토큰이 아니라 불투명 식별자라 충분하다. 와이어는 snake_case
//    `device_id`(camelCase 변환 금지).
import { useEffect, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";

/** AsyncStorage 키 — 디바이스 식별자 단일 출처. */
const DEVICE_ID_KEY = "desknow.deviceId";

/** 클라 1회 확정한 device_id 캐시 — 동기 초기값(같은 참조)·생성 write 1회화. */
let cachedDeviceId: string | null = null;

/** RFC4122 v4 UUID — Math.random 폴백(crypto 부재 RN). device_id는 비민감이라 충분(웹 폴백 복사). */
function generateUuid(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * AsyncStorage에서 device_id를 읽고, 없으면 생성·저장해 반환한다. 캐시 적중 시 write 없이
 * 동일 참조 반환. 저장 실패(프라이빗 모드 등)는 graceful(메모리 캐시로 세션 내 일관 — 다음 진입 재생성).
 */
export async function getOrCreateDeviceId(): Promise<string> {
  if (cachedDeviceId !== null) return cachedDeviceId;
  let id: string | null = null;
  try {
    id = await AsyncStorage.getItem(DEVICE_ID_KEY);
  } catch {
    id = null;
  }
  if (!id) {
    id = generateUuid();
    try {
      await AsyncStorage.setItem(DEVICE_ID_KEY, id);
    } catch {
      // 저장 실패 — 메모리 캐시로 세션 내 일관 유지(다음 앱 진입 시 재생성 감수).
    }
  }
  cachedDeviceId = id;
  return id;
}

/**
 * device_id를 제공하는 클라 훅. AsyncStorage가 비동기라 `useSyncExternalStore`(웹) 대신
 * `useState`+effect로 단순화한다. 해소 전엔 빈 문자열(`""`)을 반환하고, 소비처(useChatbot)는
 * `""` 동안 쿼리/스트림을 비활성화한다(빈 device_id로 서버 422 회피).
 */
export function useDeviceId(): string {
  // 초기값이 캐시 적중 시 곧 값이다(동기 setState 불요). 캐시 미스일 때만 effect에서 비동기 해소.
  const [deviceId, setDeviceId] = useState<string>(cachedDeviceId ?? "");
  useEffect(() => {
    if (cachedDeviceId !== null) return; // 이미 확정 — 초기 state로 충분
    let active = true;
    void getOrCreateDeviceId().then((id) => {
      if (active) setDeviceId(id);
    });
    return () => {
      active = false;
    };
  }, []);
  return deviceId;
}
