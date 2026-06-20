"use client";

// 운영 확정 예약목록 데이터테이블 + 임의취소 액션 (Story 8.3, AC4·AC5 — AccountsTable 패턴 미러).
//
// 룸 이름·예약자 이메일·슬롯 시간·생성일을 표로 렌더하고 각 행에 "취소" 버튼(파괴적 작업 2단계
// 확인)을 둔다. 취소 성공 시 목록이 invalidate되어 취소된 예약이 confirmed 목록에서 사라진다.
// 운영자라 예약자 실 이메일을 그대로 노출한다(익명화 안 함 — 메모 anonymous-booker-label 예외).
// 로딩=스켈레톤·빈/에러 상태 처리. 백엔드 호출은 생성 SDK 경유만(no-direct-fetch 가드).
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  useAdminReservations,
  RESERVATIONS_PAGE_SIZE,
} from "./useAdminReservations";
import { useForceCancelReservation } from "./useForceCancelReservation";

type ReservationItem = {
  id: string;
  room_id: string;
  room_name: string;
  booker_id: string;
  booker_email: string;
  status: string;
  slot_starts: string[];
  created_at: string;
};

/** ...Z UTC ISO → 한국 로캘 날짜. timeZone Asia/Seoul 고정(미지정 시 뷰어 로컬로 ±1일 드리프트 —
 *  프로젝트 시간 규약 core/time.py = Asia/Seoul, AccountsTable.formatDate 동형). */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("ko-KR", {
        timeZone: "Asia/Seoul",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });
}

/** 슬롯 시작시각(...Z) → 한국 시간 "MM/DD HH:mm"(KST). 슬롯은 UTC로 저장되므로 표시 시 KST 변환. */
function formatSlot(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("ko-KR", {
        timeZone: "Asia/Seoul",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
}

export function AdminReservationsTable() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch, isPlaceholderData } =
    useAdminReservations(page);

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / RESERVATIONS_PAGE_SIZE));

  // 마지막 페이지의 확정 예약을 전부 취소하면 total이 줄어 현재 page가 범위를 벗어난다. 보정이
  // 없으면 앞 페이지엔 예약이 있는데도 "취소할 확정 예약이 없습니다" 빈 화면이 고정된다 → 신선
  // total 기준으로 마지막 페이지로 clamp한다. 렌더 중 조건부 setState(React 권장 "state 조정"
  // 패턴 — effect 불필요·즉시 재렌더로 수렴)이며, 보정 후 page==totalPages라 한 번만 발화한다.
  // data 도착 전(isLoading)·isPlaceholderData(전환 중 이전 데이터 유지)는 신선 total이 아니라 제외.
  if (data && !isPlaceholderData && page > totalPages) {
    setPage(totalPages);
  }

  if (isLoading) {
    return (
      <div className="h-48 animate-pulse rounded-lg border border-border bg-muted/40" />
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-lg border border-border p-6">
        <p className="text-sm text-muted-foreground">
          예약 목록을 불러오지 못했어요. 네트워크 연결이 끊겼을 수 있습니다.
        </p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          다시 시도
        </Button>
      </div>
    );
  }

  const { items } = data;

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">공간</th>
              <th className="px-4 py-2 font-medium">예약자</th>
              <th className="px-4 py-2 font-medium">이용 시간</th>
              <th className="px-4 py-2 font-medium">예약일</th>
              <th className="px-4 py-2 font-medium">작업</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr className="border-t border-border">
                <td className="px-4 py-6 text-muted-foreground" colSpan={5}>
                  취소할 확정 예약이 없습니다.
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <ReservationRow key={item.id} item={item as ReservationItem} />
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          총 {total}개 · {page} / {totalPages} 페이지
        </p>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1 || isPlaceholderData}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            이전
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages || isPlaceholderData}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            다음
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 예약 행. 취소 버튼 클릭 시 2단계 확인(파괴적 작업 — 슬롯 재활성·예약자 통지 경고)을 거친다.
 *  admin에 alert-dialog 컴포넌트가 없어 인라인 2단계로 갈음한다(AccountsTable 선례). */
function ReservationRow({ item }: { item: ReservationItem }) {
  const [confirming, setConfirming] = useState(false);
  const { mutate, isPending, isError, reset } = useForceCancelReservation();

  return (
    <tr className="border-t border-border align-top">
      <td className="px-4 py-3">{item.room_name}</td>
      <td className="px-4 py-3">{item.booker_email}</td>
      <td className="px-4 py-3">
        <div className="flex flex-col gap-0.5">
          {item.slot_starts.length === 0 ? (
            <span className="text-muted-foreground">-</span>
          ) : (
            item.slot_starts.map((slot) => (
              <span key={slot}>{formatSlot(slot)}</span>
            ))
          )}
        </div>
      </td>
      <td className="px-4 py-3">{formatDate(item.created_at)}</td>
      <td className="px-4 py-3">
        {confirming ? (
          <div className="flex flex-col gap-2">
            <p className="max-w-xs text-xs text-muted-foreground">
              이 예약을 취소하면 점유 슬롯이 다시 열리고 예약자에게 취소 통지가 전송됩니다. 취소하시겠어요?
            </p>
            <div className="flex gap-2">
              <Button
                variant="destructive"
                size="sm"
                disabled={isPending}
                onClick={() => mutate(item.id)}
              >
                {isPending ? "처리 중…" : "확인"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={isPending}
                onClick={() => {
                  setConfirming(false);
                  reset();
                }}
              >
                취소
              </Button>
            </div>
            {isError ? (
              // 404(RESERVATION_NOT_FOUND: 이미 취소됨)/네트워크 단절 — 막다른 화면 대신 인라인 안내.
              <p className="text-xs text-pin-full">
                취소에 실패했어요. 네트워크 연결이 끊겼거나 이미 처리된 예약일 수 있습니다.
              </p>
            ) : null}
          </div>
        ) : (
          <Button variant="outline" size="sm" onClick={() => setConfirming(true)}>
            취소
          </Button>
        )}
      </td>
    </tr>
  );
}
