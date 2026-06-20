// 예약 임의취소 화면 (Story 8.3, AC4·AC5). 8.1 ComingSoon 골격을 실 목록+취소 테이블로 교체.
// 운영자가 확정 예약을 보고 예외 상황의 예약을 임의 취소한다(슬롯 재활성 + 예약자 통지).
import { AdminReservationsTable } from "@/features/reservations/AdminReservationsTable";
import { AdminGate } from "@/features/auth/AdminGate";

export default function ReservationsPage() {
  return (
    <AdminGate>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">예약 임의취소</h1>
          <p className="text-base leading-[1.6] text-muted-foreground">
            확정 예약 목록입니다. 예외 상황의 예약을 취소하면 점유 슬롯이 다시 열리고 예약자에게
            취소 통지가 전송됩니다.
          </p>
        </div>
        <AdminReservationsTable />
      </div>
    </AdminGate>
  );
}
