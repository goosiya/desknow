// 즐겨찾기 목록 한 행 (Story 3.7 — AC2·AC3). 이름·가격·예약 배지·부대시설 + 상세 이동 + 하트.
//
// ⚠️ 슬롯 anti-pattern 회피(architecture.md L362): 예약 배지는 서버 신선 remaining_slots(pinStatus
//    자명 분기)로 도출 — 클라 슬롯 재계산 0. pin.ts/roomSummary.ts 순수 로직 재사용(중복 금지).
// AC3: 비활성 룸(is_active=false) → '비활성' 라벨 + 상세 Link 차단(막다른 화면 금지 — 라벨로 안내).
import Link from "next/link";

import type { FavoriteRoomItem } from "@/lib/api-client";
import { pinStatus, type PinStatus } from "@/features/map/pin";
import {
  AMENITY_LABELS,
  ROOM_TYPE_LABELS,
  formatPrice,
  labelFor,
} from "@/features/map/roomSummary";

import { FavoriteButton } from "./FavoriteButton";

/** 예약 가능/마감 배지 — 색 + 아이콘 + 텍스트 3중 신호(색 단독 금지 — RoomListRow 선례). */
function StatusBadge({ status }: { status: PinStatus }) {
  if (status === "available") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium text-success">
        <span aria-hidden="true">✓</span> 예약 가능
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-pin-full">
      {/* 룸 폐업이 아니라 오늘 자리 마감(remaining_slots=0) — 명확화(KTH 2026-06-18, StatusBadge 일관). */}
      <span aria-hidden="true">✕</span> 오늘 마감
    </span>
  );
}

/** 비활성 룸 라벨 — 색 + 텍스트(상세 진입 차단 안내, AC3). */
function InactiveBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
      <span aria-hidden="true">⊘</span> 비활성
    </span>
  );
}

/** 행 본문(이름·배지·가격·룸형태·부대시설) — 활성 행은 Link, 비활성 행은 비대화형 div로 감싼다. */
function RowBody({ favorite }: { favorite: FavoriteRoomItem }) {
  const status = pinStatus(favorite.remaining_slots);
  return (
    <>
      <span className="text-base font-semibold leading-[1.45] text-card-foreground">
        {favorite.name || "이름 없음"}
      </span>
      <span className="flex flex-wrap items-center gap-2">
        {/* 비활성이면 예약 배지 대신 '비활성' 라벨(AC3 — 모순 방지). */}
        {favorite.is_active ? <StatusBadge status={status} /> : <InactiveBadge />}
        <span className="text-sm font-bold text-card-foreground">
          {formatPrice(favorite.price_per_hour)}
          <span className="font-normal text-muted-foreground">/시간</span>
        </span>
        <span className="text-xs text-muted-foreground">
          {labelFor(favorite.room_type, ROOM_TYPE_LABELS)}
        </span>
      </span>
      {favorite.amenities.length > 0 ? (
        <span className="flex flex-wrap gap-1.5">
          {favorite.amenities.map((code) => (
            <span
              key={code}
              className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground"
            >
              {labelFor(code, AMENITY_LABELS)}
            </span>
          ))}
        </span>
      ) : null}
    </>
  );
}

export function FavoriteRow({ favorite }: { favorite: FavoriteRoomItem }) {
  return (
    <li className="flex items-center gap-2 rounded-lg border border-border bg-card p-3">
      {favorite.is_active ? (
        // 활성 — 상세(4.2 스텁) 진입 가능. 하트와 분리된 형제(중첩 인터랙티브 금지 — a11y).
        <Link
          href={`/rooms/${favorite.room_id}`}
          className="tap-target flex flex-1 flex-col items-start gap-1.5 text-left"
        >
          <RowBody favorite={favorite} />
        </Link>
      ) : (
        // 비활성 — 상세 진입 차단(Link 미노출). 라벨로 상태 안내(막다른 화면 금지, AC3).
        <div className="flex flex-1 flex-col items-start gap-1.5 text-left">
          <RowBody favorite={favorite} />
        </div>
      )}
      <FavoriteButton roomId={favorite.room_id} />
    </li>
  );
}
