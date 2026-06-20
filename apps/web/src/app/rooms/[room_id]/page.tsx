// 룸 상세 라우트 (Story 4.2 — 3.3 스텁을 실제 상세로 교체).
//
// 바텀시트(3.3)·목록(3.4)의 "상세 보기"가 /rooms/{room_id} 로 이동한다. 실제 상세 화면(3단 정보
// 위계 · 위치 미니 지도 · 같은 페이지 예약 전개 + placeholder · 후기 placeholder · 상태 분기)은
// 클라이언트 컴포넌트 RoomDetail 이 책임진다. AppShell(layout)이 자동 래핑한다.
//
// Next 16: 동적 라우트 `params` 는 Promise 다 — 서버 컴포넌트에서 await 로 room_id 를 소비해
// 클라이언트 RoomDetail 에 전달한다(3.3 스텁 주석이 예고한 await params 소비).
import { RoomDetail } from "@/features/detail/RoomDetail";

export default async function RoomDetailPage({
  params,
}: {
  params: Promise<{ room_id: string }>;
}) {
  const { room_id } = await params;
  return <RoomDetail roomId={room_id} />;
}
