"use client";

// 운영 계정목록 데이터테이블 (Story 8.1, AC4 — 실데이터 수직 슬라이스 · Story 8.2 — 비활성 액션).
//
// 이메일·역할·활성여부·가입일을 표로 렌더하고 페이지네이션(이전/다음)을 제공한다. **8.2가 여기에
// "비활성" 액션 컬럼/버튼을 더한다(단방향 — 재활성 버튼 없음).** 운영자라 실 이메일을 그대로 노출한다
// (익명화 안 함 — 메모 anonymous-booker-label 예외). 로딩=스켈레톤·빈/에러 상태 처리.
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useAdminAccounts, ACCOUNTS_PAGE_SIZE } from "./useAdminAccounts";
import { useDeactivateAccount } from "./useDeactivateAccount";

const ROLE_LABELS: Record<string, string> = {
  booker: "예약자",
  provider: "제공자",
};

type AccountItem = {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
};

/** 가입일(...Z UTC ISO) → 한국 로캘 날짜 표시.
 *  timeZone을 Asia/Seoul로 고정한다 — 미지정 시 뷰어 머신 로컬 타임존으로 계산되어 UTC 일
 *  경계(예 ...T23:30:00Z) 값이 ±1일 드리프트한다(프로젝트 시간 규약 core/time.py = Asia/Seoul). */
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

export function AccountsTable() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, refetch, isPlaceholderData } =
    useAdminAccounts(page);

  if (isLoading) {
    return (
      <div className="h-48 animate-pulse rounded-lg border border-border bg-muted/40" />
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-lg border border-border p-6">
        <p className="text-sm text-muted-foreground">
          계정 목록을 불러오지 못했어요. 네트워크 연결이 끊겼을 수 있습니다.
        </p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          다시 시도
        </Button>
      </div>
    );
  }

  const { items, total } = data;
  const totalPages = Math.max(1, Math.ceil(total / ACCOUNTS_PAGE_SIZE));

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">이메일</th>
              <th className="px-4 py-2 font-medium">역할</th>
              <th className="px-4 py-2 font-medium">상태</th>
              <th className="px-4 py-2 font-medium">가입일</th>
              <th className="px-4 py-2 font-medium">작업</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr className="border-t border-border">
                <td className="px-4 py-6 text-muted-foreground" colSpan={5}>
                  표시할 계정이 없습니다.
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <AccountRow key={item.id} item={item as AccountItem} />
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

/** 계정 행. 활성 계정에만 비활성 버튼을 노출하고, 클릭 시 2단계 확인(파괴적 작업)을 거친다.
 *  비활성은 단방향이라 이미 비활성 행에는 버튼이 없다(재활성 없음 — KTH 2026-06-18). */
function AccountRow({ item }: { item: AccountItem }) {
  // 2단계 확인 상태(admin에 alert-dialog 컴포넌트 부재 → 인라인 확인으로 갈음).
  const [confirming, setConfirming] = useState(false);
  const { mutate, isPending, isError, reset } = useDeactivateAccount();

  const isProvider = item.role === "provider";

  return (
    <tr className="border-t border-border align-top">
      <td className="px-4 py-3">{item.email}</td>
      <td className="px-4 py-3">{ROLE_LABELS[item.role] ?? item.role}</td>
      <td className="px-4 py-3">
        {item.is_active ? (
          <span className="inline-flex items-center gap-1 text-success">● 활성</span>
        ) : (
          <span className="inline-flex items-center gap-1 text-pin-full">● 비활성</span>
        )}
      </td>
      <td className="px-4 py-3">{formatDate(item.created_at)}</td>
      <td className="px-4 py-3">
        {!item.is_active ? (
          // 비활성 단방향 — 이미 비활성 행엔 버튼 없이 비대화 텍스트만.
          <span className="text-xs text-muted-foreground">비활성됨</span>
        ) : confirming ? (
          <div className="flex flex-col gap-2">
            <p className="max-w-xs text-xs text-muted-foreground">
              {isProvider
                ? "이 제공자의 룸 노출이 중단되고 신규 예약이 차단됩니다(기존 예약은 유지). 비활성하시겠어요?"
                : "이 계정의 로그인이 차단됩니다. 비활성하시겠어요?"}
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
              // 404(ACCOUNT_NOT_FOUND)/네트워크 단절 등 — 막다른 화면 대신 인라인 안내.
              <p className="text-xs text-pin-full">
                비활성에 실패했어요. 네트워크 연결이 끊겼거나 이미 처리된 계정일 수 있습니다.
              </p>
            ) : null}
          </div>
        ) : (
          <Button variant="outline" size="sm" onClick={() => setConfirming(true)}>
            비활성
          </Button>
        )}
      </td>
    </tr>
  );
}
