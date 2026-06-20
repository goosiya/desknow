"use client";

// 룸 상세 화면 (Story 4.2 — AC1·AC2·AC3·AC5). 3.3 스텁 라우트를 실제 상세로 채운다.
//
// 데이터·순수 로직·즐겨찾기·네트워크 단절·미니 지도가 **모두 이미 존재**한다 — 4.2는 이들을
// 상세 레이아웃(3단 정보 위계 + 같은 페이지 예약 전개 + 후기 placeholder + 상태 분기)으로 조립한다.
// 데이터 = 바텀시트(3.3)와 동일한 `useRoomSummary`(키 ["rooms", roomId]·열 때마다 신선) 재사용.
//
// ⚠️ 슬롯 anti-pattern 회피(architecture.md L362): 예약 가능 배지는 **서버 신선 remaining_slots**
//    (summaryStatus)로 도출한다 — 클라가 영업시간을 슬롯으로 재계산하지 않는다.
// ⚠️ 막다른 화면 금지(NFR-5, 3.8 패턴): 로딩=스켈레톤 / 실패=재시도+찾기로 / 404="그 방은 더
//    이상 없어요" / 네트워크 단절=NetworkNotice(읽기 캐시 유지). 단절을 에러로 오인 표시하지 않는다.
import { useState } from "react";
import Link from "next/link";

import { NetworkNotice } from "@/components/NetworkNotice";
import { FavoriteButton } from "@/features/favorites/FavoriteButton";
import { StatusBadge } from "@/features/map/StatusBadge";
import {
  AMENITY_LABELS,
  ROOM_TYPE_LABELS,
  formatHours,
  formatPrice,
  labelFor,
  summaryStatus,
  todayBusinessHours,
} from "@/features/map/roomSummary";
import { useRoomSummary } from "@/features/map/useRoomSummary";
import { ReservationPanel } from "@/features/reservation/ReservationPanel";
import { useOnlineStatus } from "@/lib/useOnlineStatus";
import { ReviewSection } from "./ReviewSection";
import { RoomLocationMap } from "./RoomLocationMap";

type RoomDetailProps = {
  roomId: string;
};

/**
 * 미존재/비활성 룸 404(`ROOM_NOT_FOUND`)를 일반 실패와 구분한다.
 *
 * 생성 SDK 는 throwOnError 시 파싱된 에러 본문(`{detail:{code,message}}`)을 그대로 throw 하므로
 * (hey-api client-fetch 실측), 그 `detail.code` 로 404 를 식별한다. HTTP 상태가 에러 객체에 직접
 * 실리지 않으므로 백엔드 에러 계약(1.5 ErrorResponse)의 코드로 분기한다(2.3 ROOM_NOT_FOUND 기존).
 */
function isRoomNotFound(error: unknown): boolean {
  if (typeof error !== "object" || error === null || !("detail" in error)) {
    return false;
  }
  const detail = (error as { detail?: unknown }).detail;
  return (
    typeof detail === "object" &&
    detail !== null &&
    (detail as { code?: unknown }).code === "ROOM_NOT_FOUND"
  );
}

/** "찾기로 돌아가기" 링크 — 막다른 화면 방지 공용(404·실패 분기에서 재사용). */
function BackToExploreLink() {
  return (
    <Link
      href="/"
      className="tap-target inline-flex items-center justify-center rounded-md border border-border bg-card px-4 text-sm font-medium text-card-foreground"
    >
      찾기로 돌아가기
    </Link>
  );
}

export function RoomDetail({ roomId }: RoomDetailProps) {
  const { data, isError, error, refetch } = useRoomSummary(roomId);
  // 네트워크 단절 감지(3.8) — 단절을 일반 에러로 오인 표시하지 않도록 최우선 게이팅한다.
  const isOnline = useOnlineStatus();
  // 같은 페이지 내 예약 전개 토글(AC2) — URL/라우트 변경 0, 섹션만 펼친다.
  const [reservationOpen, setReservationOpen] = useState(false);

  // 단절은 NetworkNotice 가 우선 처리하고 마지막 캐시(TanStack 메모리)를 유지한다. `isOnline &&`
  // 게이팅으로 단절을 "정보를 못 불러왔어요"로 덮지 않는다(MapView L164 선례 동형).
  const showError = isOnline && isError;
  const notFound = showError && isRoomNotFound(error);

  // 1차 배지 상태 — 신선 remaining_slots(summaryStatus). 로드 전에는 미표시(스켈레톤).
  const status = data ? summaryStatus(data.remaining_slots) : undefined;
  const todayHours = data ? todayBusinessHours(data.business_hours) : null;

  return (
    <article className="mx-auto w-full max-w-3xl">
      {/* 3.8 네트워크 단절: 에러보다 우선 — 상단 배너 + 읽기 캐시 유지(연결되면 자동 재조회). */}
      {!isOnline && <NetworkNotice className="mb-6" />}

      {showError ? (
        notFound ? (
          // AC5 404: 미존재/비활성 룸 — 막다른 화면 금지(안내 + 찾기로).
          <div className="flex flex-col items-start gap-4 py-8">
            <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em] text-foreground">
              그 방은 더 이상 없어요
            </h1>
            <p className="text-base leading-[1.6] text-muted-foreground">
              찾으시는 스터디룸이 사라졌거나 잠시 닫혔어요. 다른 후보를 둘러봐 주세요.
            </p>
            <BackToExploreLink />
          </div>
        ) : (
          // AC5 정보 로드 실패(비-2xx) — 다시 시도 + 찾기로(막다른 화면 금지).
          <div className="flex flex-col items-start gap-4 py-8">
            <p className="text-base font-medium leading-[1.6] text-foreground">
              정보를 못 불러왔어요.
            </p>
            <p className="text-sm leading-[1.6] text-muted-foreground">
              잠시 후 다시 시도하거나, 찾기로 돌아갈 수 있어요.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => refetch()}
                className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
              >
                다시 시도
              </button>
              <BackToExploreLink />
            </div>
          </div>
        )
      ) : data ? (
        // ── 정상: 3단 정보 위계(여백 우선 — spacing.6~8) ──
        <div className="flex flex-col gap-8">
          {/* 헤더: 이미지 자리 placeholder(Room 에 이미지 필드 없음 — 없는 데이터 만들지 않음) ·
              제목 · 메타 · 즐겨찾기(3.7 FavoriteButton 실배선 재사용). */}
          <header className="flex flex-col gap-4">
            <div
              data-testid="room-image-placeholder"
              className="flex h-40 w-full items-center justify-center rounded-lg border border-border bg-muted text-sm text-muted-foreground"
            >
              사진은 준비 중이에요
            </div>
            <div className="flex items-start justify-between gap-2">
              <div className="flex flex-col gap-1">
                <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em] text-foreground">
                  {data.name}
                </h1>
                <p className="text-sm text-muted-foreground">
                  {labelFor(data.room_type, ROOM_TYPE_LABELS)} · 최대 {data.capacity}인
                </p>
              </div>
              <FavoriteButton roomId={roomId} />
            </div>
          </header>

          {/* ── 1차(가장 우선): 가격 · 오늘 영업시간 · 예약 가능 배지(신선 remaining_slots) ── */}
          <section aria-label="가격·영업시간·예약 가능" className="flex flex-col gap-3">
            {status ? <StatusBadge status={status} /> : null}
            <p className="flex items-baseline gap-1">
              <span className="text-3xl font-bold text-foreground">
                {formatPrice(data.price_per_hour)}
              </span>
              <span className="text-base text-muted-foreground">/ 시간</span>
            </p>
            {/* 휴무면 "오늘 휴무"(서버 is_closed_today) — 영업행이 있어도 배지("마감")와 모순되지
                않게 한다(3.3 회수 패턴 동일). 휴무 아님 + 영업행 있음 → "오늘 영업 HH:MM–HH:MM". */}
            {data.is_closed_today || !todayHours ? (
              <p className="text-sm font-medium text-foreground">오늘 휴무</p>
            ) : (
              <p className="text-sm text-muted-foreground">
                오늘 영업{" "}
                <span className="font-medium text-foreground">
                  {formatHours(todayHours.open_time, todayHours.close_time)}
                </span>
              </p>
            )}

            {/* 같은 페이지 내 예약 전개(AC2) — 페이지 이동 0. 펼침은 즉시 전환이라 모션이 없어
                prefers-reduced-motion 을 본질적으로 존중한다(부가 모션 도입 안 함). */}
            <div className="mt-2">
              <button
                type="button"
                onClick={() => setReservationOpen((open) => !open)}
                aria-expanded={reservationOpen}
                aria-controls="reservation-section"
                className="tap-target inline-flex w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
              >
                {/* 펼치기 토글 — 실제 예약 확정 CTA(ReservationPanel '예약하기')와 라벨이 겹쳐
                    "예약하기"가 두 개로 보이던 혼란 제거. 이 버튼은 가용 시간(달력+슬롯)을 여는 진입점. */}
                예약 가능 시간 보기
              </button>
            </div>
            {reservationOpen && (
              // 전개 영역 = 달력 + 슬롯 피커(Story 4.3 가 4.2 placeholder 를 채움). 슬롯 선택·
              // 연속 범위=4.4 · 즉시 예약 확정=4.5 가 이 패널을 이어서 확장한다(seam). 전개 메커니즘
              // (reservationOpen·aria-expanded/controls·id)은 4.2 그대로 보존하고 내용물만 채운다.
              <section
                id="reservation-section"
                aria-label="예약"
                className="mt-2 rounded-lg border border-border bg-muted/50 p-6"
              >
                <ReservationPanel
                  roomId={roomId}
                  pricePerHour={data.price_per_hour}
                  roomName={data.name}
                />
              </section>
            )}
          </section>

          {/* ── 2차: 부대시설 · 수용 · 룸 형태 · 위치 미니 지도 ── */}
          <section aria-label="시설·위치" className="flex flex-col gap-6">
            {data.amenities.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {data.amenities.map((code) => (
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
                <dd className="font-medium text-foreground">최대 {data.capacity}인</dd>
              </div>
              <div className="flex gap-2">
                <dt>룸 형태</dt>
                <dd className="font-medium text-foreground">
                  {labelFor(data.room_type, ROOM_TYPE_LABELS)}
                </dd>
              </div>
            </dl>
            {/* 위치 미니 지도(AC3) — 저장 좌표 중심 단일 핀. 주소 텍스트는 모델 미저장이라 미표시. */}
            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium text-foreground">위치</p>
              <RoomLocationMap lat={data.lat} lng={data.lng} name={data.name} />
            </div>
          </section>

          {/* ── 3차: 후기 섹션(Story 5.5 — reviews API 실배선·익명·별점 a11y·빈 상태) ── */}
          <ReviewSection roomId={roomId} />
        </div>
      ) : isOnline ? (
        // AC5 로딩: 상세 스켈레톤(정보 자리). 단절 시에는 표시하지 않는다(아래 분기).
        <div data-testid="detail-skeleton" className="flex flex-col gap-8">
          <div className="h-40 w-full animate-pulse rounded-lg bg-muted" />
          <div className="flex flex-col gap-3">
            <div className="h-7 w-24 animate-pulse rounded-full bg-muted" />
            <div className="h-9 w-40 animate-pulse rounded bg-muted" />
            <div className="h-5 w-48 animate-pulse rounded bg-muted" />
          </div>
          <div className="h-44 w-full animate-pulse rounded-lg bg-muted" />
        </div>
      ) : (
        // 네트워크 단절 + 캐시 없음(콜드): 배너(위)만 두고 막다른 화면을 만들지 않는다 —
        // 연결되면 refetchOnReconnect(query-client 기본)가 자동 재조회한다.
        <p className="py-8 text-sm leading-[1.6] text-muted-foreground">
          연결되면 상세 정보를 보여드릴게요.
        </p>
      )}
    </article>
  );
}
