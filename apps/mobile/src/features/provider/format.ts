// provider 화면 포맷터 — 웹 ProviderReservations/ProviderReviews 추출 복사 (Story 9.3 — AC1·AC3).
//
// 프레임워크 무관 순수 함수(Intl 기반·RN 호환). 웹은 컴포넌트 모듈 내부에 두었던 것을 RN 미러에서
// 재사용하기 위해 feature-local 모듈로 추출했다(중복 인라인 금지). 와이어 시각은 UTC, 표시는 KST.

/** slot_starts(시간당 UTC 시작들) → KST "M월 D일 HH:MM–HH:MM"(첫 시작~마지막 시작+1h). */
export function formatSlots(slotStarts: string[]): string {
  if (slotStarts.length === 0) return "";
  const sorted = [...slotStarts].sort();
  const start = new Date(sorted[0]);
  const lastStart = new Date(sorted[sorted.length - 1]);
  const end = new Date(lastStart.getTime() + 60 * 60 * 1000); // 마지막 슬롯 끝 = 시작+1h
  const date = new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    timeZone: "Asia/Seoul",
  }).format(start);
  const hhmm = (d: Date) =>
    new Intl.DateTimeFormat("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Seoul",
    }).format(d);
  return `${date} ${hhmm(start)}–${hhmm(end)}`;
}

/** KST 날짜(YYYY년 M월 D일). 손상 입력은 빈 문자열(예외/NaN 노출 금지 — ReviewSection 동형). */
export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "Asia/Seoul",
  }).format(date);
}
