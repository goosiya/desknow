// 지역 목록 한 행 (Story 3.4 — AC1·AC2). 이름·가격·예약 배지·부대시설·룸형태 + 즐겨찾기.
//
// ⚠️ 슬롯 anti-pattern 회피(architecture.md L362): 예약 가능 배지는 **서버 신선
//    remaining_slots**(pinStatus 의 >=1 자명 분기)로 도출한다 — 클라가 슬롯을 재계산하지 않는다.
//    핀(3.2)·시트(3.3)와 같은 pin.ts/roomSummary.ts 순수 로직을 재사용한다(중복 금지).
//    즐겨찾기 하트는 공유 FavoriteButton(Story 3.7)으로 실배선된다(토글·영속·미로그인 게이팅).
import type { RoomListItem } from "@/lib/api-client";
import { FavoriteButton } from "@/features/favorites/FavoriteButton";
import { pinStatus, type PinStatus } from "@/features/map/pin";
import {
  AMENITY_LABELS,
  ROOM_TYPE_LABELS,
  formatPrice,
  labelFor,
} from "@/features/map/roomSummary";

/** 예약 가능/마감 배지 — 색 + 아이콘 + 텍스트 3중 신호(색 단독 금지, AC1·AC4 — RoomSheet 선례). */
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

type RoomListRowProps = {
  room: RoomListItem;
  /** 행 탭 → 부모가 RoomSheet(3.3) 오픈. 행과 하트는 형제 버튼(중첩 인터랙티브 금지 — a11y). */
  onSelect: (room: RoomListItem) => void;
};

export function RoomListRow({ room, onSelect }: RoomListRowProps) {
  // 신선 remaining_slots 의 자명 분기(서버 집계값 — 슬롯 재계산 0). 핀/시트와 동일 pinStatus.
  const status = pinStatus(room.remaining_slots);
  return (
    <li className="flex items-center gap-2 rounded-lg border border-border bg-card p-3">
      {/* 행 본문(클릭 영역). 하트와 분리된 형제 버튼이라 중첩 인터랙티브가 아니다. */}
      <button
        type="button"
        onClick={() => onSelect(room)}
        className="tap-target flex flex-1 flex-col items-start gap-1.5 text-left"
      >
        <span className="text-base font-semibold leading-[1.45] text-card-foreground">
          {room.name}
        </span>
        <span className="flex flex-wrap items-center gap-2">
          <StatusBadge status={status} />
          <span className="text-sm font-bold text-card-foreground">
            {formatPrice(room.price_per_hour)}
            <span className="font-normal text-muted-foreground">/시간</span>
          </span>
          <span className="text-xs text-muted-foreground">
            {labelFor(room.room_type, ROOM_TYPE_LABELS)}
          </span>
        </span>
        {room.amenities.length > 0 ? (
          <span className="flex flex-wrap gap-1.5">
            {room.amenities.map((code) => (
              <span
                key={code}
                className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground"
              >
                {labelFor(code, AMENITY_LABELS)}
              </span>
            ))}
          </span>
        ) : null}
      </button>
      {/* 목록 카드는 높이가 짧아 안내 팝오버를 하트 왼쪽(카드 안)으로 연다(아래로 열면 카드 밖 넘침). */}
      <FavoriteButton roomId={room.room_id} hintPlacement="left" />
    </li>
  );
}
