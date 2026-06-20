// 계정 관리 화면 (Story 8.1, AC4 — 실데이터 수직 슬라이스 · Story 8.2 — 비활성 액션 포함).
// 로그인→RBAC 게이트→실데이터 조회→계정 비활성(캐스케이드)을 end-to-end로 실증한다.
import { AccountsTable } from "@/features/accounts/AccountsTable";
import { AdminGate } from "@/features/auth/AdminGate";

export default function AccountsPage() {
  return (
    <AdminGate>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">계정 관리</h1>
          <p className="text-base leading-[1.6] text-muted-foreground">
            예약자·제공자 계정 목록입니다. 비활성화하면 해당 계정의 예약·공간이 함께 정리됩니다.
          </p>
        </div>
        <AccountsTable />
      </div>
    </AdminGate>
  );
}
