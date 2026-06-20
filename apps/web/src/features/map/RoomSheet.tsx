"use client";

// 룸 바텀시트 — vaul 드로어 (Story 3.3, AC1·AC2·AC3·AC5). 핀(3.2)/목록 항목(3.4)이 탭하면
// 떠오르는 면이다. 3.2 최소 셸을 신선 단일 조회 콘텐츠로 교체했다.
//
// vaul = Radix Dialog 기반 → 포커스 트랩·Esc·aria-modal·포커스 복귀·스크롤 잠금·reduced-motion
// 을 **상속**한다(직접 구현 0). 드래그/그래버는 vaul 제공. controlled(트리거 버튼 없이 핀 탭이
// 연다) — open + onOpenChange.
//
// **높이 = 콘텐츠 맞춤(KTH 2026-06-19):** 이전엔 snapPoints [0.4,1]로 처음 40%만 펼쳐 "상세 보기"
// 버튼이 잘려 보였다(드래그로 끌어올려야 보임). 이제 snapPoints를 제거해 **콘텐츠 높이에 맞춰 한 번에
// 열고**(주소·상세보기까지 다 보임), 화면보다 길면 내부 스크롤한다. 드래그 내려 닫기는 그대로다.
//
// ⚠️ 슬롯 anti-pattern 회피(architecture.md L362): 예약 가능 배지는 **서버 신선 remaining_slots**
//    (summaryStatus)로 도출한다 — 클라가 영업시간을 슬롯으로 재계산하지 않는다.
//    즐겨찾기 하트는 공유 FavoriteButton(Story 3.7)으로 실배선된다(토글·영속·미로그인 게이팅).
//    상세 페이지 실내용은 Story 4.2 소유(본 스토리는 스텁 라우트로 이동만).
import { useState } from "react";
import Link from "next/link";
import { MapPin } from "lucide-react";
import { Drawer } from "vaul";

import { FavoriteButton } from "@/features/favorites/FavoriteButton";
import type { PinStatus } from "./pin";
import { StatusBadge } from "./StatusBadge";
import {
  AMENITY_LABELS,
  ROOM_TYPE_LABELS,
  formatHours,
  formatPrice,
  labelFor,
  summaryStatus,
  todayBusinessHours,
} from "./roomSummary";
import { useRoomSummary } from "./useRoomSummary";

type RoomSheetProps = {
  roomId: string;
  name: string;
  /** 핀/목록 항목이 준 상태(신선 로딩 전 초기 배지 — 깜빡임 방지). 로드되면 신선값으로 대체. */
  fallbackStatus?: PinStatus;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/** 콘텐츠 자리 스켈레톤(헤더 이름은 prop 으로 즉시 — 1차/2차만 스켈레톤, AC5①). */
function ContentSkeleton({ fallbackStatus }: { fallbackStatus?: PinStatus }) {
  return (
    <div className="mt-4 flex flex-col gap-3" data-testid="sheet-skeleton">
      {fallbackStatus ? (
        <StatusBadge status={fallbackStatus} />
      ) : (
        <div className="h-7 w-24 animate-pulse rounded-full bg-muted" />
      )}
      <div className="h-8 w-32 animate-pulse rounded bg-muted" />
      <div className="h-5 w-40 animate-pulse rounded bg-muted" />
    </div>
  );
}

export function RoomSheet({
  roomId,
  name,
  fallbackStatus,
  open,
  onOpenChange,
}: RoomSheetProps) {
  const { data, isLoading, isError, refetch } = useRoomSummary(roomId);

  // 닫힘 애니메이션 중 깜빡임 방지(code-review): 닫으면 MapView가 selectedRoom=null로 만들어 roomId가
  // ""가 되고(신선도 메커니즘 — 재오픈 시 refetch 유지) data/name이 사라진다. vaul exit 트랜지션이
  // 끝나기 전 헤더가 빈 이름+스켈레톤으로 깜빡이므로, roomId가 있을 때의 마지막 값을 보관해 닫히는
  // 동안 직전 룸 콘텐츠를 그대로 슬라이드 아웃시킨다(표시 전용 — enable/refetch 로직 무변경).
  // roomId가 있을 때만 직전 룸을 갱신한다(React 공식 "렌더 중 파생 상태 조정" 패턴 — 이전 렌더 정보
  // 보관). roomId가 ""(닫힘)이면 갱신을 건너뛰어 마지막 열린 룸이 유지된다.
  const [lastRoom, setLastRoom] = useState({ roomId, name, data });
  if (
    roomId &&
    (lastRoom.roomId !== roomId ||
      lastRoom.name !== name ||
      lastRoom.data !== data)
  ) {
    setLastRoom({ roomId, name, data });
  }
  const shownRoomId = roomId || lastRoom.roomId;
  const shownName = roomId ? name : lastRoom.name;
  const shownData = roomId ? data : lastRoom.data;

  // 배지 상태: 로드되면 신선 remaining_slots(summaryStatus), 아니면 fallback(핀 스냅샷, AC4).
  const status: PinStatus | undefined = shownData
    ? summaryStatus(shownData.remaining_slots)
    : fallbackStatus;
  const todayHours = shownData ? todayBusinessHours(shownData.business_hours) : null;

  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange}>
      <Drawer.Portal>
        {/* 오버레이 — 클릭 시 닫힘(vaul). 떠오름 위계 외 장식 그림자 금지. */}
        <Drawer.Overlay className="fixed inset-0 z-30 bg-foreground/20" />
        {/* 떠오르는 유일 면: 상단만 rounded.xl · elevation.sheet · bg-card(AC3). 콘텐츠 높이에 맞춰
            열리되 화면의 88%를 넘지 않는다(넘으면 내부 스크롤). h-full 미사용(스냅 제거 — 콘텐츠 맞춤). */}
        <Drawer.Content className="fixed inset-x-0 bottom-0 z-40 mx-auto flex max-h-[88dvh] w-full max-w-6xl flex-col rounded-t-xl border-t border-border bg-card shadow-sheet focus:outline-none">
          {/* 그래버(handle) — 드래그로 펼침/접힘/닫기(AC2). */}
          <Drawer.Handle className="mx-auto mt-3 h-1.5 w-12 shrink-0 rounded-full bg-border" />

          <div className="overflow-y-auto p-5">
            {/* 헤더: 이름(Title — Radix a11y 필수) · 즐겨찾기 · 닫기. 이름은 prop 으로 즉시 표시. */}
            <div className="flex items-start justify-between gap-2">
              <Drawer.Title className="text-xl font-semibold leading-[1.45] text-card-foreground">
                {shownName}
              </Drawer.Title>
              <div className="flex shrink-0 items-center gap-1">
                <FavoriteButton roomId={shownRoomId} />
                <Drawer.Close
                  aria-label="닫기"
                  className="tap-target inline-flex items-center justify-center rounded-md px-2 text-muted-foreground hover:bg-muted"
                >
                  <span aria-hidden="true">✕</span>
                </Drawer.Close>
              </div>
            </div>
            {/* Radix Dialog 설명(aria-describedby) — 콘솔 경고 회피용 시각 비표시. */}
            <Drawer.Description className="sr-only">
              {shownName} 스터디룸의 가격·영업시간·예약 가능 여부 요약이에요.
            </Drawer.Description>

            {isError ? (
              // AC5②: 조회 실패 — 막다른 화면 금지(안내 + 다시 시도).
              <div className="mt-4 flex flex-col items-start gap-3">
                <p className="text-sm leading-[1.6] text-muted-foreground">
                  정보를 못 불러왔어요.
                </p>
                <button
                  type="button"
                  onClick={() => refetch()}
                  className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
                >
                  다시 시도
                </button>
              </div>
            ) : isLoading || !shownData ? (
              <ContentSkeleton fallbackStatus={fallbackStatus} />
            ) : (
              <>
                {/* ── 기본 정보: 예약 배지 · 가격 · 영업시간 · 주소 ── */}
                <div className="mt-4 flex flex-col gap-2">
                  {status ? <StatusBadge status={status} /> : null}
                  <p className="flex items-baseline gap-1">
                    <span className="text-2xl font-bold text-card-foreground">
                      {formatPrice(shownData.price_per_hour)}
                    </span>
                    <span className="text-sm text-muted-foreground">/ 시간</span>
                  </p>
                  {/* 휴무면 "오늘 휴무"(서버 is_closed_today) — weekday 영업행이 있어도 배지("마감")와
                      모순되지 않게 한다(code-review). 휴무 아님 + 영업행 있음 → "오늘 영업 HH:MM". */}
                  {shownData.is_closed_today || !todayHours ? (
                    <p className="text-sm font-medium text-card-foreground">
                      오늘 휴무
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      오늘 영업{" "}
                      <span className="font-medium text-card-foreground">
                        {formatHours(todayHours.open_time, todayHours.close_time)}
                      </span>
                    </p>
                  )}
                  {/* 주소(provider 입력 — idea.md L36). 미입력이면 줄을 생략한다. */}
                  {shownData.address ? (
                    <p className="flex items-start gap-1.5 text-sm leading-[1.6] text-muted-foreground">
                      <MapPin className="mt-0.5 size-4 shrink-0" aria-hidden />
                      <span>{shownData.address}</span>
                    </p>
                  ) : null}
                </div>

                <hr className="my-4 border-border" />

                {/* ── 부가 정보: 부대시설 · 수용 · 룸 형태 ── */}
                <div className="flex flex-col gap-3">
                  {shownData.amenities.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {shownData.amenities.map((code) => (
                        <span
                          key={code}
                          className="rounded-full bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground"
                        >
                          {labelFor(code, AMENITY_LABELS)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <dl className="flex flex-col gap-1 text-sm text-muted-foreground">
                    <div className="flex gap-2">
                      <dt>수용</dt>
                      <dd className="font-medium text-card-foreground">
                        최대 {shownData.capacity}인
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt>룸 형태</dt>
                      <dd className="font-medium text-card-foreground">
                        {labelFor(shownData.room_type, ROOM_TYPE_LABELS)}
                      </dd>
                    </div>
                  </dl>
                </div>

                {/* ── 하단: 상세 보기(스텁 라우트 — 4.2가 실제 상세·예약 UI로 채움) ── */}
                <Link
                  href={`/rooms/${shownRoomId}`}
                  className="tap-target mt-5 inline-flex w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
                >
                  상세 보기
                </Link>
              </>
            )}
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
