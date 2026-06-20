// 핀 순수 로직 — 웹 pin.ts 복사 (Story 9.1 — 프레임워크 무관 · 단일 출처).
//
// 카카오/DOM/RN에 의존하지 않는 순수 함수만 둔다. 두 공개 GET 응답(좌표·가용성)을 room_id로
// 조인하고, 서버 집계값(remaining_slots)으로 핀의 상태·색·아이콘·라벨을 도출한다.
//
// ⚠️ 금지 안티패턴: **클라가 슬롯을 재계산하지 않는다.** pinStatus의 `>= 1`은 자명 분기일 뿐
//    슬롯 도출이 아니다(슬롯 계산은 서버 derive_slots가 1회 끝냄). 색 단독 금지 — pinVisual은
//    색과 아이콘을 함께 반환하고, pinAriaLabel이 텍스트 신호를 보장한다(색+아이콘+텍스트 3중).
import { colors } from "@desknow/ui";

import type { RoomAvailability, RoomMapItem } from "@/lib/api-client";

export type PinStatus = "available" | "full";

/** 좌표(RoomMapItem) + 가용성(remaining_slots)을 조인한 핀 모델. */
export type RoomPin = RoomMapItem & {
  remaining_slots: number;
  status: PinStatus;
};

export type PinVisual = {
  colorToken: "pinAvailable" | "pinFull";
  hex: string;
  icon: "check" | "x";
};

/** remaining_slots >= 1 → 예약 가능, 0 → 마감. 유일한 클라 분기(서버 집계값 사용). */
export function pinStatus(remainingSlots: number): PinStatus {
  return remainingSlots >= 1 ? "available" : "full";
}

/**
 * 룸 목록과 가용성을 room_id로 인메모리 조인한다.
 * 가용성에 없는 룸은 remaining_slots=0(마감)으로 취급한다(보수적 — 안전한 기본값).
 */
export function joinAvailability(
  rooms: RoomMapItem[],
  availability: RoomAvailability[],
): RoomPin[] {
  const slotsByRoom = new Map<string, number>();
  for (const a of availability) {
    slotsByRoom.set(a.room_id, a.remaining_slots);
  }
  return rooms.map((room) => {
    const remaining = slotsByRoom.get(room.room_id) ?? 0;
    return { ...room, remaining_slots: remaining, status: pinStatus(remaining) };
  });
}

/**
 * 핀의 색 토큰·hex·아이콘을 도출한다. 색 hex는 @desknow/ui 토큰에서 가져온다(하드코딩 금지 —
 * 토큰 단일 출처). 아이콘은 항상 동반한다(색 단독 신호 금지).
 */
export function pinVisual(status: PinStatus): PinVisual {
  if (status === "available") {
    return { colorToken: "pinAvailable", hex: colors.pinAvailable, icon: "check" };
  }
  return { colorToken: "pinFull", hex: colors.pinFull, icon: "x" };
}

/** 스크린리더 라벨: "{이름} 스터디룸, 예약 가능" / "{이름} 스터디룸, 오늘 마감". */
export function pinAriaLabel(name: string, status: PinStatus): string {
  const state = status === "available" ? "예약 가능" : "오늘 마감";
  return `${name} 스터디룸, ${state}`;
}
