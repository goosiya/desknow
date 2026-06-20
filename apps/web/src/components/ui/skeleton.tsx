import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      // ⚠️ bg-accent 는 만다린 테마에서 밝은 오렌지(#FFC24D)라 로딩 중 목록/카드가 오렌지로
      // 깜빡였다(KTH 2026-06-18). 스켈레톤은 은은해야 하므로 muted(연한 크림 #F4EDDF)로 교체(앱 전역).
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  )
}

export { Skeleton }
