"use client";

// 공유 즐겨찾기 하트 (Story 3.7 — AC1·AC4). 바텀시트(3.3)·목록(3.4)·즐겨찾기 페이지가 같은
// 컴포넌트로 토글을 배선한다("어디서든"의 web 충족 = 시트+목록; 상세 4.2가 동일 컴포넌트 graft).
//
// ⚠️ 색 단독 금지(architecture.md L300): 채움(형태) + 색 + aria 3중 신호.
//    활성=destructive 채운 하트 / 비활성=muted-foreground 외곽선 하트 + aria-pressed + 상태 라벨.
// ⚠️ 미로그인 게이팅(AC4): 하트는 보이되 클릭 시 토글하지 않고 "로그인하면 저장돼요" 안내(막다른
//    화면 금지). 옵티미스틱 호출 안 함.
import { useState } from "react";
import Link from "next/link";
import { Heart } from "lucide-react";

import { useSession } from "@/features/auth/useSession";
import { useFavoriteIds, useToggleFavorite } from "./useFavorites";

// hintPlacement: 안내 팝오버 배치. 기본 "below"(하트 아래 — 시트/상세). 목록 카드는 높이가 짧아
// 아래로 열면 카드 밖으로 넘치므로 "left"(하트 왼쪽·수직중앙 — 카드 안)로 연다.
export function FavoriteButton({
  roomId,
  hintPlacement = "below",
}: {
  roomId: string;
  hintPlacement?: "below" | "left";
}) {
  const { data: user, isError: sessionError } = useSession();
  const isLoggedIn = !!user;
  const { data: favoriteIds } = useFavoriteIds();
  const isFavorited = favoriteIds?.has(roomId) ?? false;
  const toggle = useToggleFavorite();
  const [showLoginHint, setShowLoginHint] = useState(false);

  // 로그인되면 잔존 hint 초기화(code-review) — 미로그인 클릭으로 켜둔 뒤 로그인하면, 이후 세션이
  // 다시 null로 깜빡일 때 클릭 없이 hint가 유령 재노출되는 것을 막는다. set-state-in-effect 가드를
  // 피해 "렌더 중 파생 상태 조정"(React 공식 패턴, RoomSheet 선례)으로 직전 로그인 상태와 비교한다.
  const [prevLoggedIn, setPrevLoggedIn] = useState(isLoggedIn);
  if (prevLoggedIn !== isLoggedIn) {
    setPrevLoggedIn(isLoggedIn);
    if (isLoggedIn && showLoginHint) setShowLoginHint(false);
  }

  function handleClick() {
    // 빈 roomId 방어(code-review) — 닫히는 RoomSheet의 빈 shownRoomId 등으로 유령 토글/422 방지.
    if (!roomId) {
      return;
    }
    // 세션 판별 실패(네트워크/5xx) — 미로그인으로 오인해 로그인 유도하지 않고 보류(상위 화면이 안내).
    if (sessionError) {
      return;
    }
    if (!isLoggedIn) {
      // AC4: 토글 대신 로그인 유도(옵티미스틱 호출 안 함).
      setShowLoginHint(true);
      return;
    }
    toggle.mutate({ roomId, next: !isFavorited });
  }

  return (
    <div className="relative inline-flex">
      <button
        type="button"
        onClick={handleClick}
        aria-pressed={isFavorited}
        aria-label={isFavorited ? "즐겨찾기 해제" : "즐겨찾기 추가"}
        className="tap-target inline-flex shrink-0 items-center justify-center rounded-md px-2 hover:bg-muted"
      >
        {isFavorited ? (
          // 활성 — 채운 하트 + destructive(채움=형태 신호, 색 단독 아님).
          <Heart
            aria-hidden="true"
            fill="currentColor"
            className="size-5 text-destructive"
          />
        ) : (
          // 비활성 — 외곽선 하트 + muted-foreground.
          <Heart aria-hidden="true" className="size-5 text-muted-foreground" />
        )}
      </button>

      {showLoginHint && !isLoggedIn ? (
        // 미로그인 안내(AC4 — 막다른 화면 금지: 닫기 + 로그인 링크). 전용 로그인 화면은 별도 스토리.
        <div
          role="status"
          className={`absolute z-50 w-48 rounded-md border border-border bg-card p-3 text-xs shadow-sheet ${
            hintPlacement === "left"
              ? "right-full top-1/2 mr-1 -translate-y-1/2"
              : "right-0 top-full mt-1"
          }`}
        >
          <p className="leading-[1.6] text-card-foreground">
            로그인하면 저장돼요.
          </p>
          <div className="mt-2 flex items-center gap-3">
            <Link href="/login" className="font-medium text-primary">
              로그인
            </Link>
            <button
              type="button"
              onClick={() => setShowLoginHint(false)}
              className="text-muted-foreground"
            >
              닫기
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
