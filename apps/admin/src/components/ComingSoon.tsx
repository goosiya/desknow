// 운영 화면 빈 골격 (Story 8.1). /reservations(8.3)·/ingest(8.4)는 셸만 두고 실 동작은 후속.
// 데이터테이블/폼 레이아웃 자리 + "준비 중" 빈 상태 카피를 보인다(실 쓰기 동작 없음 — 스코프).
export function ComingSoon({ title, note }: { title: string; note: string }) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">{title}</h1>
        <p className="text-base leading-[1.6] text-muted-foreground">{note}</p>
      </div>
      <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-border bg-card text-sm text-muted-foreground">
        준비 중입니다.
      </div>
    </div>
  );
}
