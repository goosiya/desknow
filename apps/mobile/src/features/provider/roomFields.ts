// 룸폼 순수 상수·변환 — 웹 RoomForm.tsx 추출 복사 (Story 9.3 — AC4). 프레임워크 무관(검증 순서는
// RoomForm.tsx 컴포넌트가 동일 순서로 적용). business_hours.weekday 규약 = 월0~일6(서버 동형).

import type { ProviderRoomDetail } from "@/lib/api-client";

/** 요일 라벨 — index = date.weekday()(월=0 … 일=6). 서버 business_hours.weekday 규약과 동일. */
export const WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"] as const;

/** 부대시설 코드(룸폼 토글 — roomSummary.AMENITY_LABELS로 라벨 매핑). */
export const AMENITY_CODES = [
  "wifi",
  "whiteboard",
  "parking",
  "projector_tv",
  "coffee",
  "etc",
] as const;

/** 룸 형태(roomSummary.ROOM_TYPE_LABELS로 라벨 매핑). */
export const ROOM_TYPES = ["open", "private"] as const;

/** 영업시간 입력 한 요일 — on(영업)/open/close("HH:MM"). 제출 시 on인 요일만 페이로드로 변환. */
export type DayHours = { on: boolean; open: string; close: string };

/** "09:00:00" → "09:00"(시간 입력 표시용). */
export function toHHMM(t: string): string {
  return t.slice(0, 5);
}

/** 초기 영업시간 — 보유 룸의 business_hours(영업일만 존재)를 7요일 행으로 펼친다. 없으면 매일 09–22. */
export function initialHours(room: ProviderRoomDetail | null): DayHours[] {
  return WEEKDAYS.map((_, weekday) => {
    const found = room?.business_hours.find((h) => h.weekday === weekday);
    if (found) {
      return { on: true, open: toHHMM(found.open_time), close: toHHMM(found.close_time) };
    }
    // 신규는 매일 09–22 기본, 수정인데 그 요일이 없으면 휴무로.
    return { on: room === null, open: "09:00", close: "22:00" };
  });
}
