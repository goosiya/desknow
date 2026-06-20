"use client";

// 즐겨찾기 모아보기 (Story 3.7 — AC2·AC3·AC4). 저장한 룸을 나열하고 각 행에서 상세로 이동한다.
//
// 막다른 화면 금지(NFR-5, 3.4 정신 계승): 미로그인=로그인 유도 · 로딩=Skeleton · 에러=다시 시도 ·
// 빈="마음에 든 곳을 즐겨찾기해두면 여기 모여요." · 목록=FavoriteRow. 카피는 친근한 해요체.
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Skeleton } from "@/components/ui/skeleton";
import { InfiniteScrollSentinel } from "@/components/InfiniteScrollSentinel";
import { NetworkNotice } from "@/components/NetworkNotice";
import { useOnlineStatus } from "@/lib/useOnlineStatus";
import { useSession } from "@/features/auth/useSession";

import { useFavorites } from "./useFavorites";
import { FavoriteRow } from "./FavoriteRow";

/** 로딩 자리 — shadcn Skeleton 5행(전역 스피너 금지). */
function ListSkeleton() {
  return (
    <div className="flex flex-col gap-2" data-testid="favorites-skeleton">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-20 w-full rounded-lg" />
      ))}
    </div>
  );
}

/** 안내 카드(빈/미로그인 공용 셸) — 제목 + 본문 + 행동 링크. */
function PromptCard({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action: { href: string; label: string };
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-6 text-center">
      <p className="text-base font-medium text-card-foreground">{title}</p>
      <p className="text-sm leading-[1.6] text-muted-foreground">{body}</p>
      <Link
        href={action.href}
        className="tap-target mt-1 inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
      >
        {action.label}
      </Link>
    </div>
  );
}

export function FavoriteList() {
  const {
    data: user,
    isLoading: sessionLoading,
    isError: sessionError,
    refetch: refetchSession,
  } = useSession();
  const {
    data,
    isLoading,
    isError,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useFavorites();
  // 네트워크 단절 감지(3.8 확정③) — **네트워크 축**이라 세션 판별과 독립이다.
  const isOnline = useOnlineStatus();
  // 미로그인 CTA가 로그인 후 이 화면으로 돌아오도록 현재 경로를 ?next=로 싣는다.
  const pathname = usePathname();
  const loginHref = `/login?next=${encodeURIComponent(pathname ?? "/favorites")}`;

  // 세션 판별 중 — 스켈레톤(미로그인/목록 깜빡임 방지).
  if (sessionLoading) {
    return <ListSkeleton />;
  }

  // 세션 판별 실패(네트워크/5xx) — 로그아웃 UI가 아니라 오류/재시도(막다른 화면 금지).
  // 미로그인(401→user=null)과 구분: 일시 장애를 로그아웃으로 오인 표시하지 않는다(code-review).
  if (sessionError) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card p-6 text-center">
        <p className="text-base font-medium text-card-foreground">
          로그인 상태를 확인하지 못했어요.
        </p>
        <button
          type="button"
          onClick={() => refetchSession()}
          className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
        >
          다시 시도
        </button>
      </div>
    );
  }

  // 세션 미확정 + 네트워크 단절(3.8 code-review 2026-06-16): 오프라인 콜드 진입 시 useSession
  // 쿼리가 paused 되어 `user === undefined`(미조회)가 된다 — 이때 로그인 여부를 모르므로 아래
  // `!user` 로그인 유도를 띄우면 **로그인 사용자(단지 오프라인)를 로그아웃으로 오인 표시**한다
  // (확정① "단절≠미로그인" 축 분리의 역방향 완성). `data === null`(캐시된 401=진짜 미로그인)은
  // 아래 `!user` 분기가 그대로 로그인 유도를 유지하므로 여기서 가로채지 않는다(undefined 만 단절 우선).
  if (!isOnline && user === undefined) {
    return <NetworkNotice />;
  }

  // 미로그인(AC4) — 로그인 유도(막다른 화면 금지). 전용 로그인 화면은 별도 스토리.
  if (!user) {
    return (
      <PromptCard
        title="로그인하면 즐겨찾기를 모아볼 수 있어요."
        body="마음에 든 스터디룸을 저장해두고 다음에 빠르게 다시 찾아보세요."
        action={{ href: loginHref, label: "로그인" }}
      />
    );
  }

  // 네트워크 단절(3.8 확정③): 여기 도달했다는 건 **로그인됨**(위 !user 가 미로그인을 이미
  // 가로챔)이라는 뜻 — 단절이 미로그인을 덮지 않는다(확정① 모호성 회피의 핵심). 캐시된 즐겨찾기
  // (TanStack 메모리 잔존분)가 있으면 행 + NetworkNotice, 없으면 NetworkNotice 만. 에러보다 우선.
  // 재연결 시 refetchOnReconnect(기본 true)가 자동 재조회.
  if (!isOnline) {
    if (data && data.length > 0) {
      return (
        <div className="flex flex-col gap-2">
          <NetworkNotice />
          <ul className="flex flex-col gap-2">
            {data.map((favorite) => (
              <FavoriteRow key={favorite.room_id} favorite={favorite} />
            ))}
          </ul>
        </div>
      );
    }
    return <NetworkNotice />;
  }

  // 로딩: Skeleton 행.
  if (isLoading) {
    return <ListSkeleton />;
  }

  // 에러: 안내 + 다시 시도(막다른 화면 금지). 단절은 위에서 가로채므로 여기는 온라인 진짜 실패.
  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card p-6 text-center">
        <p className="text-base font-medium text-card-foreground">
          즐겨찾기를 못 불러왔어요.
        </p>
        <button
          type="button"
          onClick={() => refetch()}
          className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
        >
          다시 시도
        </button>
      </div>
    );
  }

  // 빈: 즐겨찾기 유도(막다른 화면 금지, EXPERIENCE.md:99).
  if (!data || data.length === 0) {
    return (
      <PromptCard
        title="아직 즐겨찾기한 곳이 없어요."
        body="마음에 든 곳을 즐겨찾기해두면 여기 모여요."
        action={{ href: "/", label: "스터디룸 찾기" }}
      />
    );
  }

  // 목록: 단일 컬럼(즐겨찾기는 lg 2열 대상 아님 — deferred L76은 탐색 페이지 한정) + 무한스크롤.
  return (
    <>
      <ul className="flex flex-col gap-2">
        {data.map((favorite) => (
          <FavoriteRow key={favorite.room_id} favorite={favorite} />
        ))}
      </ul>
      <InfiniteScrollSentinel
        hasNextPage={hasNextPage}
        isFetchingNextPage={isFetchingNextPage}
        fetchNextPage={fetchNextPage}
      />
    </>
  );
}
