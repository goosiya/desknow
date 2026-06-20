// 별점 표시 컴포넌트 (Story 5.5 — AC4 · review-accessibility.md L61).
//
// ⚠️ 색 단독 금지: 채움/빈 별 아이콘(형태) + 숫자 텍스트("4/5") + aria-label("별점 5점 만점에 4점")
//    **3중 신호**로 표시한다(FavoriteButton 하트 채움 패턴 동형). 별 자체는 aria-hidden,
//    그룹에 img role + aria-label 하나로 스크린리더가 읽는다(별 5개 중복 낭독 방지).
import { Star } from "lucide-react";

/** 별점(1~5) 표시 — 채운 별 rating개 + 빈 별 나머지 + 숫자 + SR aria-label(읽기 전용). */
export function StarRating({ rating }: { rating: number }) {
  // 방어: 서버 CHECK(1~5)가 보장하나 표시단에서도 범위를 클램프한다(깨진 데이터로 별 음수/초과 방지).
  const filled = Math.max(0, Math.min(5, Math.round(rating)));
  return (
    <span
      role="img"
      aria-label={`별점 5점 만점에 ${filled}점`}
      className="inline-flex items-center gap-1"
    >
      <span aria-hidden="true" className="inline-flex">
        {Array.from({ length: 5 }).map((_, i) => (
          <Star
            key={i}
            className={
              i < filled
                ? "size-4 fill-current text-accent"
                : "size-4 text-muted-foreground"
            }
          />
        ))}
      </span>
      {/* 숫자 텍스트 병행(색·형태 외 3중 신호) — 저시력·흑백 환경 대비. */}
      <span className="text-xs font-medium text-muted-foreground">{filled}/5</span>
    </span>
  );
}
