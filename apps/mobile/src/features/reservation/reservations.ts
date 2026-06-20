// 예약현황 분류·표시 순수 로직 — 웹 reservation/reservations.ts 복사 (Story 9.2 — 프레임워크 무관).
//
// 다가오는/지난 분류와 6h 취소 가능 판정을 `now` 기준으로 **순수 계산**한다(슬롯 스냅샷
// `slot_starts` ISO ...Z 만으로). 소비처(ReservationRow/List)는 이 결과를 **render-time** 으로
// 쓴다 — effect 에서 setState 로 파생하지 않는다(set-state-in-effect 함정 회피).
//
// ⚠️ 시간은 전부 서버가 준 `slot_starts`(UTC ISO ...Z) 스냅샷에서만 읽는다(클라 슬롯 재계산
//    아님 — architecture.md L367). 표시 포맷은 slots.ts 헬퍼(formatSlotLabel·formatDateKorean)를
//    재사용한다(중복 금지).
import type { ReservationListItem } from "@/lib/api-client";

import { formatDateKorean, formatSlotLabel } from "./slots";

/** 취소 가능 리드타임 = 6시간(밀리초). 예약 시작까지 이 이상 남아야 취소 가능(FR-16). */
export const CANCEL_LEAD_MS = 6 * 60 * 60 * 1000;

/** 슬롯 길이 = 1시간(밀리초). 마지막 슬롯 시작 + 1h = 예약 종료 시각(표시·다가오는 판정용). */
const SLOT_MS = 60 * 60 * 1000;

/** 스냅샷의 가장 이른 슬롯 시작(ms). 슬롯 0건(레거시 취소 행)이면 null. */
function earliestMs(item: ReservationListItem): number | null {
  if (item.slot_starts.length === 0) return null;
  // slot_starts 는 서버가 오름차순 ...Z 로 보장 → [0] 이 곧 earliest(사전식=시간순).
  return new Date(item.slot_starts[0]).getTime();
}

/** 스냅샷의 예약 종료 시각(ms) = 마지막 슬롯 시작 + 1h. 슬롯 0건이면 null. */
function endMs(item: ReservationListItem): number | null {
  if (item.slot_starts.length === 0) return null;
  const lastStart = new Date(item.slot_starts[item.slot_starts.length - 1]).getTime();
  return lastStart + SLOT_MS;
}

/**
 * 다가오는 예약인가 — `confirmed` 이고 예약 종료(마지막 슬롯 +1h)가 아직 안 지났는가(AC4).
 *
 * 취소/거절(종료 상태)은 항상 "지난" 섹션이다(미upcoming). 슬롯 0건(레거시)도 미upcoming
 * (종료 시각 계산 불가 → 지난으로 분류). 순수 함수 — `now` 는 호출처가 render-time 으로 주입.
 */
export function isUpcoming(item: ReservationListItem, now: Date): boolean {
  if (item.status !== "confirmed") return false;
  const end = endMs(item);
  if (end === null) return false;
  return end > now.getTime();
}

/**
 * 취소 가능한가 — `confirmed` 이고 가장 이른 슬롯 시작까지 6시간 이상 남았는가(AC4).
 *
 * `earliest - now >= 6h`(순수 duration — 두 UTC 인스턴트 차, ROOM_TZ 불요). 취소/거절/이용
 * 완료(종료·과거)는 미cancellable. 서버가 6h 경계를 timedelta 로 최종 강제하므로(클럭 스큐
 * graceful) 이 FE 계산은 버튼 활성/비활성 표시용이다(AC4).
 */
export function isCancellable(item: ReservationListItem, now: Date): boolean {
  if (item.status !== "confirmed") return false;
  const earliest = earliestMs(item);
  if (earliest === null) return false;
  return earliest - now.getTime() >= CANCEL_LEAD_MS;
}

/** 예약 날짜 라벨 "6월 20일"(가장 이른 슬롯의 KST 날짜). 슬롯 0건(레거시)이면 null(시간 미표시). */
export function reservationDateLabel(item: ReservationListItem): string | null {
  if (item.slot_starts.length === 0) return null;
  // 서버 UTC 인스턴트 → KST "YYYY-MM-DD"(slots.kstToday 와 동일 en-CA Asia/Seoul 패턴) → 한국어.
  const kstYmd = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(item.slot_starts[0]));
  return formatDateKorean(kstYmd);
}

/**
 * 예약 시간 범위 라벨 "14:00–17:00"(첫 슬롯 시작 ~ 마지막 슬롯 시작 +1h, KST 벽시계, AC4).
 *
 * `selectionLabels.rangeLabel` 과 동형(formatSlotLabel + 끝슬롯 +1h). 슬롯 0건(레거시)이면 null.
 * 비연속 슬롯도 min..max+1h 범위로 요약한다(자정 넘김 표기 한계는 5.4 defer와 동형·그대로 복사).
 */
export function reservationTimeRangeLabel(item: ReservationListItem): string | null {
  if (item.slot_starts.length === 0) return null;
  const startUtc = item.slot_starts[0];
  const end = endMs(item);
  if (end === null) return null;
  return `${formatSlotLabel(startUtc)}–${formatSlotLabel(new Date(end).toISOString())}`;
}
