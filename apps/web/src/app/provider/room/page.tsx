// 스터디룸 등록/수정 페이지 (provider 웹 표면 — idea.md L36). 셸 헤더/네비는 layout 이 제공한다.
// 인증/생성·수정 분기·주소검색은 RoomForm('use client')이 소유한다(페이지는 얇게).
import { RoomForm } from "@/features/provider/RoomForm";

export default function ProviderRoomPage() {
  return <RoomForm />;
}
