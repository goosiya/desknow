"use client";

// 예약현황 모아보기 (Story 4.8 — AC1·AC3). 본인 예약을 다가오는/지난으로 구분해 나열한다.
//
// 막다른 화면 금지(NFR-5): FavoriteList 상태 매트릭스를 미러한다 — 세션 로딩→스켈레톤 · 세션
// 판별 실패→재시도 · 미로그인→로그인 유도 · 네트워크 단절→캐시 우선 + NetworkNotice · 로딩→
// Skeleton · 에러→재시도 · 빈→찾기 유도. 카피는 예약 맥락으로 교체.
//
// ⚠️ 다가오는/지난·취소 가능 분류는 render-time `now` 파생(reservations.ts 순수 함수) — effect 에서
//    setState 로 만들지 않는다(set-state-in-effect 함정, 3.5/3.6 선례). 3축 분리(미로그인≠단절≠세션
//    판별 실패)는 FavoriteList 그대로(로그아웃 오인 금지).
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { ReservationListItem } from "@/lib/api-client";
import { Skeleton } from "@/components/ui/skeleton";
import { InfiniteScrollSentinel } from "@/components/InfiniteScrollSentinel";
import { NetworkNotice } from "@/components/NetworkNotice";
import { useOnlineStatus } from "@/lib/useOnlineStatus";
import { useSession } from "@/features/auth/useSession";

import { useReservations } from "./useReservations";
import { ReservationRow } from "./ReservationRow";
import { isUpcoming } from "./reservations";

/** 로딩 자리 — shadcn Skeleton 4행(전역 스피너 금지). */
function ListSkeleton() {
  return (
    <div className="flex flex-col gap-2" data-testid="reservations-skeleton">
      {Array.from({ length: 4 }).map((_, i) => (
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

/** 한 섹션(다가오는/지난) — 헤더 + 행 목록. 비면 렌더하지 않는다(둘 다 비면 호출처가 빈 카드). */
function Section({
  title,
  items,
  now,
}: {
  title: string;
  items: ReservationListItem[];
  now: Date;
}) {
  if (items.length === 0) return null;
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold text-muted-foreground">{title}</h2>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <ReservationRow key={item.id} item={item} now={now} />
        ))}
      </ul>
    </section>
  );
}

/** 다가오는/지난 분할 렌더(단절-캐시 경로와 정상 경로 공용). */
function Sections({
  data,
  now,
}: {
  data: ReservationListItem[];
  now: Date;
}) {
  // 다가오는 = 빠른 순(earliest asc), 지난 = 서버 순(created_at desc) 유지.
  const upcoming = data
    .filter((item) => isUpcoming(item, now))
    .sort((a, b) => (a.slot_starts[0] ?? "").localeCompare(b.slot_starts[0] ?? ""));
  const past = data.filter((item) => !isUpcoming(item, now));
  return (
    <div className="flex flex-col gap-4">
      <Section title="다가오는 예약" items={upcoming} now={now} />
      <Section title="지난 예약" items={past} now={now} />
    </div>
  );
}

export function ReservationList() {
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
  } = useReservations();
  // 네트워크 단절 감지(3.8 확정③) — 네트워크 축이라 세션 판별과 독립.
  const isOnline = useOnlineStatus();
  // 다가오는/지난·6h 취소 가능 분류 기준 시각 — render-time 파생(effect setState 금지).
  const now = new Date();
  // 미로그인 CTA가 로그인 후 이 화면으로 돌아오도록 현재 경로를 ?next=로 싣는다.
  const pathname = usePathname();
  const loginHref = `/login?next=${encodeURIComponent(pathname ?? "/reservations")}`;

  // 세션 판별 중 — 스켈레톤(미로그인/목록 깜빡임 방지).
  if (sessionLoading) {
    return <ListSkeleton />;
  }

  // 세션 판별 실패(네트워크/5xx) — 로그아웃 UI 가 아니라 오류/재시도(막다른 화면 금지·로그아웃 오인 금지).
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

  // 세션 미확정(오프라인 콜드 진입) — user===undefined 면 로그인 여부 미확정이라 로그인 유도가 아니라
  // 단절 배너(로그인 사용자 오인 방지 — FavoriteList code-review 선례). null(캐시된 401)은 아래 유지.
  if (!isOnline && user === undefined) {
    return <NetworkNotice />;
  }

  // 미로그인(AC3) — 로그인 유도(막다른 화면 금지). 전용 로그인 화면은 별도 스토리.
  if (!user) {
    return (
      <PromptCard
        title="로그인하면 예약 내역을 볼 수 있어요."
        body="예약하신 스터디룸을 한 곳에서 확인하고 관리하세요."
        action={{ href: loginHref, label: "로그인" }}
      />
    );
  }

  // 네트워크 단절(3.8 확정③) — 여기 도달 = 로그인됨. 캐시된 목록 있으면 행 + NetworkNotice, 없으면
  // NetworkNotice 만(에러보다 우선·재연결 시 refetchOnReconnect 자동 재조회).
  if (!isOnline) {
    if (data && data.length > 0) {
      return (
        <div className="flex flex-col gap-2">
          <NetworkNotice />
          <Sections data={data} now={now} />
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
          예약 내역을 못 불러왔어요.
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

  // 빈: 찾기 유도(막다른 화면 금지, EXPERIENCE.md 빈 상태 카피 정신).
  if (!data || data.length === 0) {
    return (
      <PromptCard
        title="아직 예약이 없어요."
        body="마음에 드는 곳을 찾아볼까요?"
        action={{ href: "/", label: "스터디룸 찾기" }}
      />
    );
  }

  // 목록: 다가오는/지난 두 섹션 + 무한스크롤(하단 sentinel). 분류는 페이지 누적 data 전체에 적용.
  return (
    <>
      <Sections data={data} now={now} />
      <InfiniteScrollSentinel
        hasNextPage={hasNextPage}
        isFetchingNextPage={isFetchingNextPage}
        fetchNextPage={fetchNextPage}
      />
    </>
  );
}
