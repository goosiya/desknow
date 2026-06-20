// 예약 흐름 날짜·시간 순수 로직 — 웹 reservation/slots.ts 복사 (Story 9.2 — 프레임워크 무관 · 단일 출처).
//
// 카카오/DOM/React 에 의존하지 않는 순수 함수만 둔다(웹과 100% 동일). 달력 그리드 계산·선택 가능
// 날짜 판정·날짜/시간 표시 포맷·연속 슬롯 선택 헬퍼를 담당한다. `Intl` 기반이라 RN 무수정 호환.
//
// ⚠️ 금지 안티패턴(architecture.md L298·L367): **클라가 슬롯을 재계산하지 않는다.** 슬롯 리스트·
//    상태는 전부 서버(`/slots`)가 준다. 여기서는 표시 포맷(UTC→KST 벽시계 "14:00")·달력 그리드
//    날짜 산술·선택 가능 날짜 범위 판정·**렌더된 `slots` 배열의 인덱스 산술**만 한다. 가용성 판정은
//    서버가 준 `slot.status` 를 **읽기만** 한다.
import type { RoomSlot } from "@/lib/api-client";

// 예약 가능 기간 상한(범위 결정 #2) — 오늘 포함 ~ 오늘+29일(=30일 창). 백엔드 상한과 정합.
export const RESERVATION_HORIZON_DAYS = 30;

/** "YYYY-MM-DD" → [year, month(1-12), day]. 순수 파싱(타임존 무관 — 달력은 벽 날짜만 다룬다). */
function parseYmd(date: string): [number, number, number] {
  const [y, m, d] = date.split("-").map(Number);
  return [y, m, d];
}

/** [year, month(1-12), day] → "YYYY-MM-DD"(2자리 패딩). */
function toYmd(year: number, month: number, day: number): string {
  const mm = String(month).padStart(2, "0");
  const dd = String(day).padStart(2, "0");
  return `${year}-${mm}-${dd}`;
}

/**
 * ROOM_TZ(Asia/Seoul) "오늘"을 "YYYY-MM-DD" 로 반환한다(달력 초기 선택·선택 가능 하한).
 *
 * 프로세스/클라 로컬 타임존이 아니라 Asia/Seoul 벽시계 날짜로 판정한다(NFR-1 — roomSummary.ts
 * 의 Intl Asia/Seoul 패턴 재사용, 신규 의존성 0). now 는 테스트 결정성을 위해 주입받는다.
 */
export function kstToday(now: Date = new Date()): string {
  // en-CA 로케일은 "YYYY-MM-DD" 형식을 낸다(ISO 정렬 가능 문자열).
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

/** "YYYY-MM-DD" 에 n일을 더한 날짜(순수 달력 산술 — UTC 기준으로 DST/로컬 함정 회피). */
export function addDays(date: string, n: number): string {
  const [y, m, d] = parseYmd(date);
  const shifted = new Date(Date.UTC(y, m - 1, d + n));
  return toYmd(
    shifted.getUTCFullYear(),
    shifted.getUTCMonth() + 1,
    shifted.getUTCDate(),
  );
}

/**
 * 7열(일~토) 월 그리드용 날짜 배열. 앞쪽 빈칸은 `null`, 날짜 칸은 "YYYY-MM-DD".
 *
 * 일요일 시작(목업 `.dow` 일·월·화…). 첫 주의 1일 앞 빈칸 수 = 1일의 요일(일=0…토=6).
 * 타임존 무관(UTC 기준 요일 계산 — 달력은 벽 날짜만 다룬다). month 는 1-12.
 */
export function monthGrid(year: number, month: number): (string | null)[] {
  const firstWeekday = new Date(Date.UTC(year, month - 1, 1)).getUTCDay(); // 일=0…토=6
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate(); // month의 말일
  const cells: (string | null)[] = [];
  for (let i = 0; i < firstWeekday; i += 1) cells.push(null); // 앞쪽 빈칸(요일 정렬)
  for (let day = 1; day <= daysInMonth; day += 1) cells.push(toYmd(year, month, day));
  return cells;
}

/** "YYYY-MM-DD" → 그 달의 [year, month(1-12)] (달력 헤더·월 이동용). */
export function yearMonthOf(date: string): [number, number] {
  const [y, m] = parseYmd(date);
  return [y, m];
}

/** [year, month(1-12)] → 그 달 1일 "YYYY-MM-01"(달력 보기 앵커 — 월 이동 결과 표현). */
export function firstOfMonth(year: number, month: number): string {
  return toYmd(year, month, 1);
}

/** 같은 달(year·month)에 한 달을 더하거나 뺀 [year, month]. 12↔1 경계 처리. */
export function shiftMonth(year: number, month: number, delta: number): [number, number] {
  // 0-기반으로 환산해 산술 후 되돌린다(12월+1=다음해 1월 경계 안전).
  const zeroBased = (year * 12 + (month - 1)) + delta;
  return [Math.floor(zeroBased / 12), (zeroBased % 12) + 1];
}

/**
 * 선택 가능한 날짜인가 — `today <= date <= today + (horizonDays-1)`(과거·상한 초과 비활성, AC2).
 *
 * "YYYY-MM-DD" ISO 문자열은 사전식 비교 = 시간순 비교라 문자열 비교로 충분하다.
 */
export function isSelectableDate(
  date: string,
  today: string,
  horizonDays: number = RESERVATION_HORIZON_DAYS,
): boolean {
  const lastSelectable = addDays(today, horizonDays - 1);
  return date >= today && date <= lastSelectable;
}

/**
 * 슬롯 시작시각(서버 UTC ISO) → "14:00"(Asia/Seoul 벽시계, AC2).
 *
 * 서버 UTC 인스턴트를 KST 벽시계로 **표시만** 한다(슬롯 재계산 아님 — roomSummary 포맷 패턴).
 */
export function formatSlotLabel(slotStartUtc: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23", // 24시간 표기(00–23) — 오전/오후 없이 "14:00"
  }).format(new Date(slotStartUtc));
}

/** "YYYY-MM-DD" → "6월 18일"(다음 빈 날짜 제안·슬롯 부제 표기, AC3). */
export function formatDateKorean(date: string): string {
  const [, month, day] = parseYmd(date);
  return `${month}월 ${day}일`;
}

/** "YYYY-MM-DD" → "2026년 6월 18일"(달력 셀 a11y 라벨 — 스크린리더 한국어, AC2). */
export function formatDateAriaLabel(date: string): string {
  const [year, month, day] = parseYmd(date);
  return `${year}년 ${month}월 ${day}일`;
}

// ── 연속 슬롯 선택 순수 헬퍼 ──────────────────────────────────────────────────
//
// 선택은 **렌더된 `slots` 배열의 포함 구간 인덱스**로만 다룬다(시각 산술로 연속성 판정 금지 —
// 배열은 이미 시간순). `clampContiguousAvailable` 하나가 비연속 불허와 "구간에 점유가 끼면 막힘"을
// **동시에** 강제한다: 앵커에서 시작해 인접 `available` 슬롯으로만 자라고, 진행 방향 첫 비-`available`
// 슬롯 직전에서 멈춘다 → 떨어진 두 슬롯이 한 구간이 될 수 없다.

/** 렌더된 `slots` 배열에 대한 **포함 구간 인덱스**(`startIndex <= endIndex`). 선택 없음 = `null`. */
export type SlotSelection = { startIndex: number; endIndex: number };

/** `i` 가 범위 안이고 그 슬롯이 `available` 인가(경계·상태 가드 — `past`/`reserved`/범위 밖 = false). */
export function isAvailableIndex(slots: RoomSlot[], i: number): boolean {
  return i >= 0 && i < slots.length && slots[i].status === "available";
}

/**
 * 선택 구간의 **모든 슬롯이 여전히 `available`** 인가(stale 선택 무효화, AC2).
 *
 * 백그라운드 refetch로 슬롯이 `reserved`로 바뀌어도 **인덱스는 안 밀린다**(사라지지 않고 같은
 * 인덱스의 `status`만 변경). 그래서 bounds 가드만으로는 선택 구간 내용이 stale인 케이스가 생긴다.
 * 이 헬퍼가 선택 구간 `[startIndex, endIndex]`의 모든 슬롯이 `available`인지 확인해, 하나라도
 * 비-`available`(`reserved`/`past`)이면 `false`를 돌려준다(호출처가 선택을 무효화). 슬롯 재계산
 * 아님 — 서버가 준 `slot.status`를 **읽기만** 한다.
 */
export function isSelectionStillAvailable(
  slots: RoomSlot[],
  selection: SlotSelection,
): boolean {
  // 범위 밖 인덱스는 isAvailableIndex가 false → bounds 이상도 함께 stale로 처리(안전).
  for (let i = selection.startIndex; i <= selection.endIndex; i += 1) {
    if (!isAvailableIndex(slots, i)) return false;
  }
  return true;
}

/**
 * 앵커→대상 방향으로 **첫 비-`available` 슬롯 직전까지** 확장한 연속-가용 구간을 반환한다(AC2).
 *
 * - 앵커가 `available` 가 아니면 `null`(선택 시작 불가).
 * - 대상이 앵커보다 앞이어도(역방향) 대칭 처리한다.
 * - 진행 중 점유 슬롯을 만나면 그 직전에서 멈춘다 → **점유를 못 넘으므로** 비연속·점유 가로지르기가
 *   구조적으로 불가능하다(연속 + 구간 점유 차단을 단일 규칙으로 동시 충족).
 *
 * 반환 구간은 항상 `startIndex <= endIndex` 로 정규화한다.
 */
export function clampContiguousAvailable(
  slots: RoomSlot[],
  anchorIndex: number,
  targetIndex: number,
): SlotSelection | null {
  if (!isAvailableIndex(slots, anchorIndex)) return null;
  const step = targetIndex >= anchorIndex ? 1 : -1;
  let last = anchorIndex; // 앵커에서 막힘 없이 도달한 마지막 가용 인덱스.
  for (let i = anchorIndex + step; step > 0 ? i <= targetIndex : i >= targetIndex; i += step) {
    if (!isAvailableIndex(slots, i)) break; // 첫 점유/범위 밖에서 멈춤.
    last = i;
  }
  return {
    startIndex: Math.min(anchorIndex, last),
    endIndex: Math.max(anchorIndex, last),
  };
}

/**
 * 슬롯 시작시각(서버 UTC ISO) → "14시"(Asia/Seoul 벽시계 시(hour) — SR 구간 피드백용, AC2).
 *
 * `formatSlotLabel` 과 같은 표시 전용 변환(슬롯 재계산 아님). 한 자리 시는 "9시"(자연스러운 한국어).
 */
export function formatHourKorean(slotStartUtc: string): string {
  const hour = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    hourCycle: "h23", // 00–23 — formatSlotLabel 과 동일 규약(자정=00).
  }).format(new Date(slotStartUtc));
  return `${Number(hour)}시`;
}

/** 선택 구간의 마지막 슬롯 시작 + 1시간(UTC ISO) — 끝 라벨/끝 시각 표시용(슬롯 재계산 아님). */
function endInstantUtc(slots: RoomSlot[], selection: SlotSelection): string {
  const endStartMs = new Date(slots[selection.endIndex].slot_start).getTime();
  return new Date(endStartMs + 3_600_000).toISOString(); // +1h (벽시계 표시는 KST 변환이 담당).
}

/**
 * 선택 구간의 표시 라벨 묶음(AC2·AC3).
 *
 * - `rangeLabel` = "14:00–17:00" — 첫 슬롯 시작 ~ **마지막 슬롯 시작 + 1시간**의 KST 벽시계.
 * - `durationHours` = 선택 슬롯 수(`end - start + 1`).
 * - `announcement` = "14시부터 17시까지 선택됨" — 시작 시(hour) ~ 끝 슬롯 +1시간.
 */
export function selectionLabels(
  slots: RoomSlot[],
  selection: SlotSelection,
): { rangeLabel: string; durationHours: number; announcement: string } {
  const startUtc = slots[selection.startIndex].slot_start;
  const endUtc = endInstantUtc(slots, selection);
  return {
    rangeLabel: `${formatSlotLabel(startUtc)}–${formatSlotLabel(endUtc)}`,
    durationHours: selection.endIndex - selection.startIndex + 1,
    announcement: `${formatHourKorean(startUtc)}부터 ${formatHourKorean(endUtc)}까지 선택됨`,
  };
}

/** 선택 구간 총액 = 선택 슬롯 수(시간) × 시간당 가격(천단위 포맷은 표시 컴포넌트가 `formatPrice`). */
export function selectionTotalPrice(selection: SlotSelection, pricePerHour: number): number {
  return (selection.endIndex - selection.startIndex + 1) * pricePerHour;
}

/**
 * 선택 구간 → 점유할 `slot_start[]`(서버 UTC ISO 그대로) — 예약 POST 본문 추출(AC3).
 *
 * **순수 인덱스 슬라이스만** 한다(클라 슬롯 재계산 아님 — architecture.md L367). 렌더된 `slots`
 * 배열에서 `[startIndex, endIndex]` 포함 구간의 `slot_start`(서버가 준 UTC 인스턴트)를 그대로
 * 뽑아 `useCreateReservation` 이 본문에 싣는다. 가용성/연속성은 위 헬퍼·서버가 이미 보장했다.
 */
export function selectionSlotStarts(slots: RoomSlot[], selection: SlotSelection): string[] {
  return slots
    .slice(selection.startIndex, selection.endIndex + 1)
    .map((slot) => slot.slot_start);
}
