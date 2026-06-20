// 예약 공유 메시지 순수 빌더 — 웹 reservation/share.ts 복사 (Story 9.2 — AC7 · 프레임워크 무관).
//
// 확정 예약을 한 단락으로 요약한 공유 텍스트를 만든다(룸 이름 + KST 날짜 + 시간 범위 + 브랜드 안내).
// **KST 날짜·시간은 기존 Asia/Seoul 포맷터 재사용**(formatDateKorean·formatSlotLabel — slots.ts).
// RN 내장 `Share.share({ message })`(ShareButton)가 이 텍스트를 OS 공유 시트에 싣는다.
//
// ⚠️ 웹 `lib/kakao-share.ts`(`window.Kakao` JS SDK)는 RN 무존재라 복사하지 않는다 — 공유 텍스트
//    빌더(이 파일)만 그대로 재사용하고, 전송은 RN `Share`가 한다(범위 결정 #3).
import { formatDateKorean, formatSlotLabel } from "./slots";

/** 슬롯 길이 = 1시간(ms). 마지막 슬롯 시작 + 1h = 예약 종료(시간 범위 끝 — reservations.ts 동형). */
const SLOT_MS = 60 * 60 * 1000;

/** 공유 텍스트 마지막 줄 브랜드 안내. */
export const SHARE_TAGLINE = "데스크나우에서 예약했어요.";

/** 룸 이름 누락(공백/빈 문자열) 폴백. */
export const ROOM_NAME_FALLBACK = "예약";

/** 슬롯 스냅샷(UTC ISO ...Z)의 KST 날짜 라벨 "6월 20일"(reservationDateLabel 동형). */
function dateLabel(firstSlotUtc: string): string {
  const kstYmd = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(firstSlotUtc));
  return formatDateKorean(kstYmd);
}

/**
 * 시간 범위 라벨 "14:00–17:00"(첫 슬롯 시작 ~ 마지막 슬롯 시작 + 1h, KST 벽시계).
 * reservationTimeRangeLabel 동형 — formatSlotLabel 재사용(클라 슬롯 재계산 아님·표시 전용).
 */
function timeRangeLabel(slotStarts: string[]): string {
  const startUtc = slotStarts[0];
  const lastStartMs = new Date(slotStarts[slotStarts.length - 1]).getTime();
  const endUtc = new Date(lastStartMs + SLOT_MS).toISOString();
  return `${formatSlotLabel(startUtc)}–${formatSlotLabel(endUtc)}`;
}

/**
 * 확정 예약 → 공유 텍스트(AC7).
 *
 * 예: `"강남 스터디라운지\n6월 20일 14:00–17:00\n데스크나우에서 예약했어요."`
 * - 룸 이름 누락(공백)이면 "예약" 폴백.
 * - slot_starts 0건(레거시 방어)이면 일시 줄을 생략하고 이름 + 안내만 낸다(막다른 화면 금지).
 * - 비연속 슬롯도 min..max+1h 범위로 요약한다(reservationTimeRangeLabel 동형 — 스냅샷 보존).
 */
export function buildReservationShareText(roomName: string, slotStarts: string[]): string {
  const name = roomName.trim() || ROOM_NAME_FALLBACK;
  const lines = [name];
  if (slotStarts.length > 0) {
    lines.push(`${dateLabel(slotStarts[0])} ${timeRangeLabel(slotStarts)}`);
  }
  lines.push(SHARE_TAGLINE);
  return lines.join("\n");
}
