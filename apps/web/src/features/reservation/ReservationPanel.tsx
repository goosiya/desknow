"use client";

// 예약 패널 — 달력 + 슬롯 피커 조립 (Story 4.3 — AC2·AC3·AC4). 4.2 가 RoomDetail 예약 전개 영역에
// 남긴 "예약 준비 중" placeholder 를 실제 달력+슬롯으로 채운다(RoomDetail 이 reservationOpen 일 때
// 이 패널을 조건부 렌더 → 전개 시에만 슬롯 조회).
//
// ⚠️ 부분 degrade(AC4): 슬롯 실패/로딩/단절은 **슬롯 영역만** 영향 — 달력은 즉시·항상 표시(클라
//    계산). 단절은 `isOnline && isError` 게이팅으로 에러로 오인하지 않는다(4.2 동형). 404 는 상세
//    본문 가드(4.2) 하위라 여기서 중복 처리하지 않는다.
//
// ⚠️ 경계: 날짜 선택=4.3, 슬롯 **선택**=4.4(연속 구간 + 하단 선택 요약). 4.5 는 그 `selection` 을
//    읽어 `예약하기` CTA·POST 제출·"예약이 완료됐어요!" 성공 배너·selection 초기화·슬롯/핀
//    invalidate·generic 실패+재시도를 배선한다(결제 없음 — FR-14).
//    **Story 4.6(구현됨):** `SLOT_CONFLICT`(409)만 특화 처리 — "먼저 잡았어요" 카피 + 슬롯 재조회로
//    인접 빈 슬롯 즉시 재표시(훅 onError, Task 3) + stale selection 초기화. 그 외 실패는 4.5 generic
//    그대로(무회귀). 재조회의 *데이터 정확도*(방금 점유된 슬롯 비활성 표시)는 4.9 차감 배선이 완성한다.
import { useState } from "react";

import { NetworkNotice } from "@/components/NetworkNotice";
import { formatPrice } from "@/features/map/roomSummary";
import { useOnlineStatus } from "@/lib/useOnlineStatus";
import { Calendar } from "./Calendar";
import { isSlotConflict } from "./errors";
import { KakaoShareButton } from "./KakaoShareButton";
import { SlotGrid } from "./SlotGrid";
import {
  formatDateKorean,
  isSelectionStillAvailable,
  kstToday,
  selectionLabels,
  selectionSlotStarts,
  selectionTotalPrice,
  type SlotSelection,
} from "./slots";
import { useCreateReservation } from "./useCreateReservation";
import { useRoomSlots } from "./useRoomSlots";

type ReservationPanelProps = {
  roomId: string;
  /** 시간당 가격(범위 결정 #2) — RoomDetail 이 useRoomSummary.data.price_per_hour 전달(추가 조회 0). */
  pricePerHour: number;
  /** 룸 이름 — 즉시예약 성공 배너 카카오 공유 텍스트용(5.4). RoomDetail 이 data.name 전달(추가 조회 0). */
  roomName: string;
};

export function ReservationPanel({ roomId, pricePerHour, roomName }: ReservationPanelProps) {
  // "오늘"·초기 선택일은 useState 초기값으로 한 번 계산(effect 에서 setState 금지 — 3.5/3.6 함정).
  const [today] = useState(() => kstToday());
  const [selectedDate, setSelectedDate] = useState(today);
  // 연속 슬롯 선택(4.4 소유 · 4.5 가 읽음). 선택 없음 = null.
  const [selection, setSelection] = useState<SlotSelection | null>(null);
  // 날짜 변경 시 선택 리셋(AC3) — effect setState 금지(3.5/3.6). Calendar 의 prevValue 렌더-중-조정
  // 패턴을 재사용해 selectedDate 변화를 감지하고 selection 을 비운다(이전 날 선택은 무효).
  const [prevDate, setPrevDate] = useState(selectedDate);
  if (selectedDate !== prevDate) {
    setPrevDate(selectedDate);
    setSelection(null);
  }

  // 네트워크 단절 감지(3.8/4.2) — 단절을 슬롯 에러로 오인 표시하지 않도록 최우선 게이팅.
  const isOnline = useOnlineStatus();
  const { data, isError, refetch } = useRoomSlots(roomId, selectedDate);

  // 단절은 NetworkNotice 가 우선 처리 + 읽기 캐시 유지. isOnline && 게이팅으로 단절을 에러로
  // 덮지 않는다(RoomDetail L76 선례 동형).
  const showError = isOnline && isError;
  // 선택일의 available 슬롯이 0개(휴무·전부 지난 시간·전부 예약)면 빈 날 안내(AC3).
  const availableCount = data
    ? data.slots.filter((slot) => slot.status === "available").length
    : 0;
  const isEmptyDay = data !== undefined && availableCount === 0;
  // 다음 빈 날짜 — narrowed string|null 로 추출(code-review P2). 가드 내부 `as string` 캐스트를
  // 없애 향후 가드 수정 시 null 누출이 타입으로 잡히게 한다(closure 안에서도 안전).
  const nextAvailableDate = data?.next_available_date ?? null;
  // 선택 유효성 가드(렌더-중 파생 — set-state-in-effect 금지, 반복함정 #7). 두 겹:
  //  ① bounds: refetch 로 슬롯 배열이 줄면 selection 인덱스가 범위를 벗어나 selectionLabels 의
  //     무가드 slots[index] 접근이 렌더 중 throw(에러 바운더리 없음 → 화이트스크린)할 수 있다.
  //  ② content(Story 4.9 — AC5·의무회수 L214·L224): 4.9 차감 후 백그라운드 refetch 로 선택 구간
  //     슬롯이 `reserved` 로 바뀌면 **인덱스는 안 밀리지만**(사라지지 않고 status 만 변경) 내용이
  //     stale 이다 → isSelectionStillAvailable 로 구간 전체가 여전히 available 인지 확인한다.
  // 하나라도 위반이면 safeSelection=null → CTA·요약이 사라지고(선택 비워짐) 아래 안내가 뜬다.
  const safeSelection =
    selection &&
    data &&
    selection.startIndex >= 0 &&
    selection.endIndex < data.slots.length &&
    isSelectionStillAvailable(data.slots, selection)
      ? selection
      : null;

  // 즉시 예약 확정 뮤테이션(AC4·AC5). selectedDate 는 성공 후 invalidate 대상 슬롯 키에 쓴다.
  const createReservation = useCreateReservation(roomId);

  // 성공/실패 배너는 다음 조작(날짜·슬롯 변경) 시 리셋한다 — effect setState 금지(3.5/3.6 함정),
  // 이벤트 핸들러에서 mutation.reset() 호출(렌더 중 reset 아님).
  function resetSubmitFeedback() {
    if (createReservation.isSuccess || createReservation.isError) {
      createReservation.reset();
    }
  }

  // 날짜 변경 — 제출 피드백 리셋 후 날짜 전환(selection 리셋은 위 prevDate 렌더-중-조정이 처리).
  function handleDateChange(next: string) {
    resetSubmitFeedback();
    setSelectedDate(next);
  }

  // 슬롯 선택 변경 — 제출 피드백 리셋 후 선택 갱신(성공/실패 배너를 새 선택 전에 비운다).
  function handleSelect(next: SlotSelection | null) {
    resetSubmitFeedback();
    setSelection(next);
  }

  // 단절 일관성(AC5) — 단절을 서버 에러로 오인 표시하지 않는다(NetworkNotice 가 단절을 우선 처리).
  // 슬롯 `showError = isOnline && isError` 선례 동형: 오프라인 제출 실패는 generic 배너 대신 상단
  // 단절 배너로 일원화한다(이중·혼동 메시지 회피). 재연결 시 다시 시도 경로가 살아난다.
  const showSubmitError = isOnline && createReservation.isError;
  // Story 4.6 — 실패를 두 갈래로 분기한다(렌더 중 파생 — 상태 추가/effect setState 0).
  //  · SLOT_CONFLICT(409): 특화 카피 + selection 초기화(슬롯 재조회는 훅 onError 가 처리).
  //  · 그 외(404·5xx 등): 4.5 generic 안내 + selection 유지 + "다시 시도"(무회귀).
  // 단절은 양쪽 모두 isOnline 게이팅으로 제외(NetworkNotice 우선 — AC4).
  const showSlotConflict = showSubmitError && isSlotConflict(createReservation.error);
  const showGenericError = showSubmitError && !showSlotConflict;

  // Story 4.9 — stale 선택 무효화(AC5·의무회수 L214·L224). 선택이 있었는데 재조회로 더는
  // available 이 아니게 되면(safeSelection 이 null 로 떨어짐) 중립 안내를 띄운다(렌더-중 파생 —
  // set-state-in-effect 금지). 우선순위: 제출 conflict(showSlotConflict) > stale 무효화 — conflict
  // 카피와 **동시 표출 금지**(아래 gating). 데이터 없거나(로딩) 선택이 원래 없으면 무효화도 없다.
  const selectionInvalidated =
    selection !== null && safeSelection === null && data !== undefined && !showSlotConflict;

  // 예약 확정 제출(AC4) — 선택 구간을 slot_start[] 로 추출해 POST. 성공 시 선택 초기화(컴포넌트 상태)
  // + 정확 키 invalidate(훅 onSuccess). 결제 단계 없음(FR-14). 제출 중 이중 제출은 isPending 가드.
  function handleSubmit() {
    if (!safeSelection || !data) return;
    const slotStarts = selectionSlotStarts(data.slots, safeSelection);
    createReservation.mutate(
      { slotStarts, selectedDate },
      {
        onSuccess: () => setSelection(null),
        // Story 4.6 — SLOT_CONFLICT 면 stale selection 을 비워 새로고침된 그리드에서 재선택을 유도한다
        // (막다른 화면 금지). selection 초기화는 mutation 콜백에서(effect setState 금지 — 3.5/3.6 함정).
        // 특화 카피는 selection 무관하게 슬롯 영역에서 보이고(아래 렌더), 슬롯 재조회는 훅 onError(Task 3).
        onError: (error) => {
          if (isSlotConflict(error)) setSelection(null);
        },
      },
    );
  }

  return (
    <div className="flex w-full flex-col gap-5">
      {/* 단절: 에러보다 우선 — 배너 + 읽기 캐시 유지(연결되면 자동 재조회). */}
      {!isOnline && <NetworkNotice />}

      {/* 달력은 즉시·항상 표시(클라 계산 — 슬롯 상태와 무관하게 조작 가능, 막다른 화면 금지). */}
      <div className="flex flex-col gap-2">
        <p className="text-sm font-semibold text-foreground">날짜 선택</p>
        <Calendar value={selectedDate} onChange={handleDateChange} today={today} />
      </div>

      {/* 슬롯 영역(부분 degrade — 실패/로딩/단절은 이 영역만). */}
      <div className="flex flex-col gap-2">
        <p className="text-sm font-semibold text-foreground">시간 선택</p>
        {showError ? (
          // 비-2xx 실패 — 슬롯 영역만 "시간표를 못 불러왔어요" + 다시 시도(달력·상세는 정상).
          <div className="flex flex-col items-start gap-2 rounded-lg border border-border bg-muted/50 p-4">
            <p className="text-sm font-medium text-foreground">
              시간표를 못 불러왔어요.
            </p>
            <button
              type="button"
              onClick={() => refetch()}
              className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
            >
              다시 시도
            </button>
          </div>
        ) : data !== undefined ? (
          isEmptyDay ? (
            // AC3: 빈 날 안내 + 다음 빈 날짜 제안(막다른 화면 금지 — 달력은 계속 조작 가능).
            <div
              role="status"
              className="flex flex-col items-start gap-3 rounded-lg border border-border bg-muted/50 p-4"
            >
              <p className="text-sm leading-[1.6] text-foreground">
                이 날은 다 찼어요. 다른 날을 골라보세요.
              </p>
              {nextAvailableDate ? (
                <button
                  type="button"
                  onClick={() => handleDateChange(nextAvailableDate)}
                  className="tap-target inline-flex items-center justify-center rounded-md border border-border bg-card px-4 text-sm font-medium text-card-foreground"
                >
                  {formatDateKorean(nextAvailableDate)}은 자리가 있어요
                </button>
              ) : null}
            </div>
          ) : (
            // 정상 — 그날 슬롯 선택 그리드 + 하단 선택 요약(선택 시에만).
            <div className="flex flex-col gap-4">
              <SlotGrid
                slots={data.slots}
                date={selectedDate}
                selection={safeSelection}
                onSelect={handleSelect}
              />
              {/* Story 4.6 — SLOT_CONFLICT 특화 안내(AC3). selection 은 초기화되므로(요약·CTA 사라짐)
                  이 카피는 **selection 무관하게 슬롯 영역에서** 보여야 한다(요약 블록 밖). 슬롯은 훅
                  onError 가 재조회 → 새로고침된 그리드에서 재선택 유도(막다른 화면 금지). 에러코드
                  노출 금지(고정 한국어 카피). 색 단독 금지(role=status 텍스트 병행). */}
              {showSlotConflict ? (
                <p
                  role="status"
                  aria-live="polite"
                  className="text-sm leading-[1.6] text-foreground"
                >
                  앗, 방금 다른 분이 먼저 잡았어요. 가까운 빈 시간을 다시 보여드릴게요.
                </p>
              ) : null}
              {/* 선택 요약 바(AC3 — 범위·날짜·시간·금액) + `예약하기` CTA·제출 피드백.
                  성공 시 "예약이 완료됐어요!" 인라인 배너(selection 은 초기화됨 → 요약 사라짐).
                  선택 있을 때만 CTA 등장(dead 버튼 금지). generic 실패는 안내+재시도(막다른 화면 금지).
                  SLOT_CONFLICT 는 위 특화 카피 + selection 초기화로 처리되므로 이 블록을 타지 않는다. */}
              {createReservation.isSuccess ? (
                // UJ-1 climax(5.4 AC3) — 즉시예약 성공 직후 카카오 공유 진입점. 공유 데이터는 방금
                // 받은 응답(createReservation.data.slot_starts) + roomName prop 에서 합성(추가 조회 0).
                <div
                  role="status"
                  aria-live="polite"
                  className="flex flex-col items-start gap-3 rounded-lg border border-border bg-secondary p-4 text-sm font-medium leading-[1.6] text-secondary-foreground"
                >
                  예약이 완료됐어요!
                  {createReservation.data ? (
                    <KakaoShareButton
                      roomName={roomName}
                      slotStarts={createReservation.data.slot_starts}
                      roomId={roomId}
                    />
                  ) : null}
                </div>
              ) : safeSelection ? (
                (() => {
                  const labels = selectionLabels(data.slots, safeSelection);
                  const total = selectionTotalPrice(safeSelection, pricePerHour);
                  return (
                    <div className="flex flex-col gap-3">
                      <div
                        role="status"
                        aria-live="polite"
                        className="flex flex-col gap-0.5 rounded-lg border border-border bg-card p-4"
                      >
                        <p className="text-sm font-semibold text-foreground">
                          {`${labels.rangeLabel} · ${formatDateKorean(selectedDate)} · ${labels.durationHours}시간 · ${formatPrice(total)}`}
                        </p>
                        <span className="sr-only">{labels.announcement}</span>
                      </div>
                      {/* generic 실패 안내(404·5xx 등 — 에러코드 노출 금지·고정 카피) — selection 유지
                          → 아래 버튼이 "다시 시도"로 재제출(막다른 화면 금지). SLOT_CONFLICT 는 여기로
                          오지 않는다(위 특화 카피 + selection 초기화). */}
                      {showGenericError ? (
                        <p
                          role="alert"
                          className="text-sm leading-[1.6] text-destructive"
                        >
                          예약을 완료하지 못했어요. 다시 시도해 주세요.
                        </p>
                      ) : null}
                      {/* 예약 확정 CTA(AC4) — 선택 있을 때만. 제출 중 disabled + "예약 중…"(이중 제출
                          방지). 실패 후엔 "다시 시도"로 재제출. 색 토큰만·tap-target(≥44px). */}
                      <button
                        type="button"
                        onClick={handleSubmit}
                        disabled={createReservation.isPending}
                        className="tap-target inline-flex w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
                      >
                        {createReservation.isPending
                          ? "예약 중…"
                          : showGenericError
                            ? "다시 시도"
                            : "예약하기"}
                      </button>
                    </div>
                  );
                })()
              ) : selectionInvalidated ? (
                // Story 4.9 — stale 선택 무효화 안내(AC5). 선택이 방금 예약됨 등으로 무효화되어
                // 비워졌음을 알리고 재선택을 유도한다(막다른 화면 금지·중립 카피·에러코드 노출 금지).
                // conflict 카피와 동시 표출 금지는 selectionInvalidated 의 !showSlotConflict 가 보장.
                <p
                  role="status"
                  aria-live="polite"
                  className="text-sm leading-[1.6] text-foreground"
                >
                  선택한 시간 중 일부가 방금 예약됐어요. 다시 선택해 주세요.
                </p>
              ) : (
                <p className="text-sm leading-[1.6] text-muted-foreground">
                  시간을 선택해 주세요.
                </p>
              )}
            </div>
          )
        ) : isOnline ? (
          // 로딩 — 슬롯 그리드 스켈레톤(달력은 위에서 이미 표시).
          <div
            data-testid="slots-skeleton"
            className="grid grid-cols-3 gap-2"
            aria-hidden="true"
          >
            {Array.from({ length: 6 }, (_unused, index) => (
              <div key={index} className="h-12 animate-pulse rounded-md bg-muted" />
            ))}
          </div>
        ) : (
          // 단절 + 캐시 없음(콜드): 배너(위)만 두고 막다른 화면을 만들지 않는다.
          <p className="text-sm leading-[1.6] text-muted-foreground">
            연결되면 시간표를 보여드릴게요.
          </p>
        )}
      </div>
    </div>
  );
}
