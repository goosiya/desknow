// 네트워크 단절 감지 단일 출처 — 웹 useOnlineStatus.ts RN 포팅 (Story 9.1 — 5상태 매트릭스).
//
// 웹은 `navigator.onLine` + online/offline 이벤트지만, RN은 **NetInfo**로 연결 상태를 구독한다.
// 반환값 `isOnline`이 false면 네트워크 단절 — UI는 NetworkNotice("네트워크 연결이 끊겼어요…")로
// 처리한다([[terminology-network-disconnect-not-offline]] — "오프라인" 단어 금지). 로그인/위치와
// 무관한 별도 축이다.
//
// ⚠️ 초기값은 낙관적(true) — 콜드 진입 시 NetInfo 첫 콜백 전 단절 배너가 깜빡이는 것을 막는다
//    (웹 getServerSnapshot=true와 동형). isConnected가 명시적 false일 때만 단절로 본다(null=불명은
//    연결로 간주).
import { useEffect, useState } from "react";
import NetInfo from "@react-native-community/netinfo";

/** 현재 네트워크 연결 여부. `false`면 네트워크 단절("오프라인" 금지 — 의미는 네트워크 연결). */
export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(true);

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      setIsOnline(state.isConnected !== false);
    });
    return unsubscribe;
  }, []);

  return isOnline;
}
