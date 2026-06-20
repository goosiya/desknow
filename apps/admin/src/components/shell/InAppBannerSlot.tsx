// 인앱 배너 자리 (Story 1.6 — 슬롯만). 관리자에서는 임의취소 통지 등의 자리.
// 배너 데이터·dismiss 영속은 Epic 5에서 구현한다. 비어 있을 땐 공간을 차지하지 않는다.
export function InAppBannerSlot() {
  return <div id="in-app-banner-slot" aria-live="polite" className="empty:hidden" />;
}
