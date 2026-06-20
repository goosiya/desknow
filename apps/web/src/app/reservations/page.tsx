// 예약현황 화면 (Story 4.8 — 1.6 placeholder → 실 화면). 본인 예약을 다가오는/지난으로 본다.
//
// 셸 헤더("예약현황")는 서버 컴포넌트로 유지하고, 'use client' 경계·상태 매트릭스는 ReservationList
// 가 가진다(FavoriteList 패턴 — 페이지는 얇게, 인증/쿼리는 feature 가 소유).
import { ReservationList } from "@/features/reservation/ReservationList";

export default function ReservationsPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">예약현황</h1>
      <ReservationList />
    </div>
  );
}
