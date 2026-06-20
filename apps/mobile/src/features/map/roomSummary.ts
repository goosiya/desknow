// 바텀시트 요약 순수 로직 — 웹 roomSummary.ts 복사 (Story 9.1 — 프레임워크 무관 · 단일 출처).
//
// 가격·영업시간 포맷, 오늘 요일 행 선택, 부대시설/룸형태 라벨 매핑을 담당한다.
//
// ⚠️ 금지 안티패턴: **클라가 슬롯을 재계산하지 않는다.** todayBusinessHours는 "오늘 요일 행을
//    고르는 날짜 포맷"일 뿐 슬롯 도출이 아니다(예약 가능 여부는 서버 remaining_slots가 결정).
import type { BusinessHoursPublic } from "@/lib/api-client";

import { pinStatus, type PinStatus } from "./pin";

/** 시간당 가격을 천단위 콤마 + "원"으로 포맷한다. 컴포넌트가 "/시간"을 부착한다. */
export function formatPrice(pricePerHour: number): string {
  return `${pricePerHour.toLocaleString("ko-KR")}원`;
}

/** "HH:MM:SS" → "HH:MM" 절단 후 "09:00–22:00"(en-dash)으로 포맷한다(영업시간 표시). */
export function formatHours(open: string, close: string): string {
  const hhmm = (t: string) => t.slice(0, 5); // "09:00:00" → "09:00"
  return `${hhmm(open)}–${hhmm(close)}`;
}

// KST(Asia/Seoul) 요일 약어 → date.weekday() 규약(월=0 … 일=6) 매핑. 서버 business_hours.weekday와
// 같은 규약으로 맞춘다(섞이면 다른 요일 행을 표시하게 됨).
const _KST_WEEKDAY: Record<string, number> = {
  Mon: 0,
  Tue: 1,
  Wed: 2,
  Thu: 3,
  Fri: 4,
  Sat: 5,
  Sun: 6,
};

/**
 * KST 기준 **오늘 요일**에 해당하는 영업시간 행을 고른다(없으면 null = "오늘 휴무"로 표시).
 *
 * ⚠️ 이것은 날짜 포맷(오늘 요일 선택)일 뿐 슬롯 재계산이 아니다 — 예약 가능 여부는 서버
 *    remaining_slots(summaryStatus)가 결정한다. now는 테스트 결정성을 위해 주입받으며, 미지정 시
 *    현재시각을 쓴다(프로세스 로컬 tz가 아니라 Asia/Seoul로 요일 판정).
 */
export function todayBusinessHours(
  hours: BusinessHoursPublic[],
  now: Date = new Date(),
): BusinessHoursPublic | null {
  const short = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    weekday: "short",
  }).format(now);
  const todayWeekday = _KST_WEEKDAY[short];
  if (todayWeekday === undefined) return null;
  return hours.find((h) => h.weekday === todayWeekday) ?? null;
}

/** 신선 remaining_slots로 예약 가능/마감을 도출한다 — pin.ts의 pinStatus 재사용(중복 금지). */
export function summaryStatus(remainingSlots: number): PinStatus {
  return pinStatus(remainingSlots);
}

/** 부대시설 코드 → 한국어 라벨(미지정 코드는 코드 원문 폴백 — 방어). */
export const AMENITY_LABELS: Record<string, string> = {
  parking: "주차",
  projector_tv: "빔프로젝터/TV",
  coffee: "커피머신",
  whiteboard: "화이트보드",
  wifi: "와이파이",
  etc: "기타",
};

/** 룸 형태 코드 → 한국어 라벨(미지정 코드는 코드 원문 폴백). */
export const ROOM_TYPE_LABELS: Record<string, string> = {
  open: "개방형",
  private: "독립룸",
};

/** 라벨 매핑 + 미지정 코드 원문 폴백(부대시설·룸형태 공용). */
export function labelFor(code: string, labels: Record<string, string>): string {
  return labels[code] ?? code;
}
