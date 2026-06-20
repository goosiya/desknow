import * as React from "react";

import { cn } from "@/lib/utils";

// shadcn 표준 Label(new-york). 추가 의존성을 피하려 Radix 대신 네이티브 <label>로 구현하되
// shadcn 토큰 클래스는 동일하게 적용한다(admin 로그인 폼 전용 — 단순 폼이라 Radix 불필요).
function Label({ className, ...props }: React.ComponentProps<"label">) {
  return (
    <label
      data-slot="label"
      className={cn(
        "flex items-center gap-2 text-sm leading-none font-medium select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
        className
      )}
      {...props}
    />
  );
}

export { Label };
