"use client";

// 세그먼트 컨트롤 — 하나의 테두리 프레임 안에 옵션 버튼을 묶는 토글(상단 지도/목록 토글과 같은 톤).
// 목록의 "지역/내 반경" 검색방식 토글과 "반경 km" 프리셋에 공용으로 쓴다(KTH 2026-06-19 — 인라인
// 산재 스타일 제거, 단일 컴포넌트로 톤·높이 일관). 프레임 컨테이너를 h-9(=지역 콤보 SelectTrigger
// 36px)로 고정하고 버튼이 h-full 로 프레임 안을 꽉 채워, 콤보와 외곽 높이가 일치하면서 버튼이
// 작아 보이지 않는다.
//
// variant:
//   - "tabs"  → role="group" + 각 버튼 aria-pressed (검색방식 전환 토글)
//   - "radio" → role="radiogroup" + 각 버튼 role="radio" aria-checked (반경 프리셋)
import { cn } from "@/lib/utils";

export type SegmentOption = {
  /** 선택값(문자열). 숫자 값은 호출부가 String() 으로 직렬화해 넘긴다. */
  value: string;
  /** 버튼에 보이는 라벨. */
  label: string;
  /** 접근 이름(라벨과 다를 때만 — 예: "반경 5km"). 미지정이면 label 이 곧 접근 이름. */
  ariaLabel?: string;
};

type SegmentedControlProps = {
  options: SegmentOption[];
  value: string;
  onChange: (value: string) => void;
  /** 그룹 접근 이름(role group/radiogroup 의 aria-label). */
  ariaLabel: string;
  /** tabs=aria-pressed 토글 / radio=라디오 그룹. 기본 tabs. */
  variant?: "tabs" | "radio";
  className?: string;
};

export function SegmentedControl({
  options,
  value,
  onChange,
  ariaLabel,
  variant = "tabs",
  className,
}: SegmentedControlProps) {
  const isRadio = variant === "radio";
  return (
    <div
      role={isRadio ? "radiogroup" : "group"}
      aria-label={ariaLabel}
      // 프레임 = 상단 지도/목록 토글과 같은 톤(테두리 + rounded). h-9 고정으로 지역 콤보(36px)와 외곽 일치.
      className={cn(
        "inline-flex h-9 items-stretch rounded-md border border-border p-px",
        className,
      )}
    >
      {options.map((opt) => {
        const selected = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role={isRadio ? "radio" : undefined}
            aria-pressed={isRadio ? undefined : selected}
            aria-checked={isRadio ? selected : undefined}
            aria-label={opt.ariaLabel}
            onClick={() => onChange(opt.value)}
            // h-full 로 프레임 안을 꽉 채운다(떠 보이는 작은 버튼 방지). 색은 토큰만(1.6 parity).
            className={cn(
              "inline-flex h-full items-center justify-center rounded-sm px-4 text-sm font-medium transition-colors",
              selected
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
