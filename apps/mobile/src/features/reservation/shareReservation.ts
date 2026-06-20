// 예약 공유 — RN 내장 Share.share() 호출 (Story 9.2 — AC7 · 범위 결정 #3). 웹 lib/kakao-share.ts
// (`window.Kakao` JS SDK)를 대체한다(RN에 window/document 무존재 → 통째 폐기).
//
// OS 공유 시트를 열어 공유 텍스트(buildReservationShareText 재사용)만 싣는다 — 룸 상세 링크(URL)는
// KTH 2026-06-20 요청으로 제거(메시지에 URL 미포함). 추가 네이티브 의존·키 불필요(RN 내장).
// **카카오톡 정확 템플릿 공유(@react-native-kakao/share)는
// EAS dev-build + 네이티브 카카오 키 필요·Expo Web/Playwright 검증 불가**라 "모바일 dev-build 푸시"
// 버킷에 명시 보류한다(§deferred).
//
// ⚠️ Expo Web: react-native-web의 Share.share는 navigator.share가 있으면 그걸 쓰고 없으면 reject한다
//    → 호출처(ShareButton)가 throw를 잡아 graceful 안내로 떨어진다(검증 시 인지).
import { Share } from "react-native";

import { buildReservationShareText } from "./share";

type ShareReservationArgs = {
  roomName: string;
  slotStarts: string[];
  // roomId: 링크 제거(2026-06-20)로 현재 미사용 — 웹 shareReservation 시그니처와 패리티 위해 유지.
  roomId: string;
};

/**
 * 확정 예약을 OS 공유 시트로 공유한다(AC7).
 *
 * 공유 텍스트 = `buildReservationShareText(roomName, slotStarts)` 만(룸 상세 링크/URL은 제거 —
 * KTH 2026-06-20). Share.share는 공유/취소 시 resolve, 실패 시 reject한다 — 실패 처리(graceful
 * 안내)는 호출처(ShareButton)가 try/catch로 담당한다(throw 전파 금지).
 */
export async function shareReservation({
  roomName,
  slotStarts,
}: ShareReservationArgs): Promise<void> {
  await Share.share({ message: buildReservationShareText(roomName, slotStarts) });
}
