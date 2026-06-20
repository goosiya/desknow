// 스터디룸 목록 (Story 3.4 지역 + 3.5 반경 — AC1·AC5). 검색 디스크립터(지역/반경)를 받아
// 선택 조건의 룸을 신선 가용성과 함께 나열한다. 두 검색방식이 같은 행/상태 분기를 공유한다.
//
// 막다른 화면 금지(NFR-5, 3.2/3.3 정신 계승): 미활성=안내 프롬프트 · 로딩=Skeleton 4~6행 ·
// 에러="목록을 못 불러왔어요."+다시 시도 · 빈=검색방식별 제안. 카피는 친근한 해요체.
import type { RoomListItem } from "@/lib/api-client";
import { Skeleton } from "@/components/ui/skeleton";
import { InfiniteScrollSentinel } from "@/components/InfiniteScrollSentinel";
import { NetworkNotice } from "@/components/NetworkNotice";
import { useOnlineStatus } from "@/lib/useOnlineStatus";
import { useDeferredFlag } from "@/lib/useDeferredFlag";

import { useRoomSearch, type RoomSearch } from "./useRoomSearch";
import { RoomListRow } from "./RoomListRow";

type RoomListProps = {
  /** 조회 트리거 — 지역(regionCode) 또는 반경(center+radiusKm) 디스크립터. */
  search: RoomSearch;
  /** 행 탭 → 부모가 RoomSheet(3.3) 오픈. */
  onSelectRoom: (room: RoomListItem) => void;
};

/** 로딩 자리 — shadcn Skeleton 5행(전역 스피너 금지, AC5①). */
function ListSkeleton() {
  return (
    <div className="flex flex-col gap-2" data-testid="list-skeleton">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-20 w-full rounded-lg" />
      ))}
    </div>
  );
}

export function RoomList({ search, onSelectRoom }: RoomListProps) {
  const {
    data,
    isLoading,
    isError,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useRoomSearch(search);
  // 네트워크 단절 감지(3.8 AC2) — 검색방식(region/radius) 무관 공통 처리.
  const isOnline = useOnlineStatus();
  // 스켈레톤 **지연 표시**(KTH 2026-06-18) — 빠른 로딩엔 5개 행이 안 떠 깜빡임이 없고, 느린
  // 로딩에서만 스켈레톤이 뜬다. 지연 전(빠른 로딩 구간)엔 빈 영역 → 곧바로 데이터로 채워진다.
  const showSkeleton = useDeferredFlag(isLoading);

  const isRegion = search.kind === "region";
  // 미활성(조회 비활성): region=지역 미선택, radius=중심 좌표 미확보.
  const inactive = isRegion ? !search.regionCode : !search.center;

  // 미활성: 검색방식별 안내(막힘 아님, 초기/대기 상태). 반경의 위치 거부/미지원 안내는
  // ExploreView(AC3)가 RoomList 대신 처리하므로 여기 radius 분기는 "위치 확인 중" 방어용이다.
  if (inactive) {
    return (
      <p className="rounded-lg border border-border bg-card p-6 text-center text-sm leading-[1.6] text-muted-foreground">
        {isRegion
          ? "동네를 골라 주변 스터디룸을 찾아보세요."
          : "현위치를 확인하고 있어요…"}
      </p>
    );
  }

  // 네트워크 단절(3.8 AC2): **에러보다 우선**. 캐시된 목록(TanStack 메모리 잔존분)이 있으면
  // 행을 그대로 렌더하고 상단에 NetworkNotice 를 얹는다(단절을 "못 불러왔어요" 에러로 오인 금지).
  // 캐시가 없으면 NetworkNotice 만(막힘 아님 — 카피가 "연결되면 다시 보여드릴게요"로 다음을 안내).
  // 재연결 시 refetchOnReconnect(query-client 기본 true)가 자동 재조회한다.
  if (!isOnline) {
    if (data && data.length > 0) {
      return (
        <div className="flex flex-col gap-2">
          <NetworkNotice />
          <ul className="flex flex-col gap-2">
            {data.map((room) => (
              <RoomListRow
                key={room.room_id}
                room={room}
                onSelect={onSelectRoom}
              />
            ))}
          </ul>
        </div>
      );
    }
    return <NetworkNotice />;
  }

  // 로딩: Skeleton 행(AC5①) — 단, **지연 표시**라 빠른 로딩엔 스켈레톤 없이 곧장 데이터.
  // 지연 전 짧은 구간은 빈 영역(깜빡이는 5행 잔상 제거). 느린 로딩에서만 스켈레톤이 뜬다.
  if (isLoading) {
    return showSkeleton ? <ListSkeleton /> : null;
  }

  // 에러: 안내 + 다시 시도(막다른 화면 금지, AC5③). 단절은 위에서 이미 가로채므로 여기 도달 시
  // 온라인 상태의 진짜 조회 실패다(isOnline && isError 게이팅이 위 early-return 으로 충족됨).
  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card p-6 text-center">
        <p className="text-base font-medium text-card-foreground">
          목록을 못 불러왔어요.
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

  // 빈 결과: 검색방식별 제안(막다른 화면 금지, AC5②). region=다른 동네/지도(3.4 그대로),
  // radius=반경 확대/지역 전환(EXPERIENCE L133 "동네를 넓혀볼까요?").
  if (!data || data.length === 0) {
    return (
      <div className="flex flex-col gap-2 rounded-lg border border-border bg-card p-6 text-center">
        {isRegion ? (
          <>
            <p className="text-base font-medium text-card-foreground">
              이 지역엔 등록된 곳이 없어요.
            </p>
            <p className="text-sm leading-[1.6] text-muted-foreground">
              다른 동네를 골라보거나, 지도에서 주변을 넓혀볼 수 있어요.
            </p>
          </>
        ) : (
          <>
            <p className="text-base font-medium text-card-foreground">
              이 근처엔 아직 없어요.
            </p>
            <p className="text-sm leading-[1.6] text-muted-foreground">
              반경을 넓히거나 지역으로 찾아볼 수 있어요.
            </p>
          </>
        )}
      </div>
    );
  }

  // 성공: 룸 행 리스트(행/배지/시트 오픈은 RoomListRow — 검색방식 무관 동일, 무변경) + 무한스크롤.
  return (
    <>
      <ul className="flex flex-col gap-2">
        {data.map((room) => (
          <RoomListRow key={room.room_id} room={room} onSelect={onSelectRoom} />
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
