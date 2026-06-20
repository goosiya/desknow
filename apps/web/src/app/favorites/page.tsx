// 즐겨찾기 페이지 (Story 3.7 — AC2·AC3·AC4). 저장한 룸 모아보기 + 상세 이동.
//
// FavoriteList가 4상태(로딩/에러/빈/목록) + 미로그인 게이팅을 모두 처리한다. 페이지는 제목과
// 셸만 둔다('use client' 경계는 FavoriteList 이하 — 데이터 훅 보유).
import { FavoriteList } from "@/features/favorites/FavoriteList";

export default function FavoritesPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">
        즐겨찾기
      </h1>
      <FavoriteList />
    </div>
  );
}
