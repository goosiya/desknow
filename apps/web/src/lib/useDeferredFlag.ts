import { useEffect, useState } from "react";

/**
 * `flag` 가 **`delayMs` 이상 연속 true** 일 때만 true 를 반환한다(짧은 깜빡임 억제).
 *
 * 로딩 스켈레톤 지연 표시용 — 빠른 로딩(대부분의 새로고침·캐시 적중)에선 스켈레톤이 아예 뜨지
 * 않아 "빈 행 N개가 깜빡였다 사라지는" 잔상이 없다. 느린 로딩(지연 초과)에서만 스켈레톤이 뜬다.
 * (KTH 2026-06-18 — 목록 새로고침마다 5개 행이 기본 표시되던 문제.)
 *
 * `flag` 가 false 가 되면 즉시 false(타이머 취소). flag false 의 즉시-false 처리는 effect 본문의
 * 동기 setState(set-state-in-effect 위반) 대신 **반환식 `flag && shown` + cleanup 리셋**으로
 * 한다 — flag 가 true→false 로 바뀌면 cleanup 이 타이머를 취소하고 shown 을 false 로 되돌려,
 * 다음 true 진입 때 다시 delayMs 만큼 지연되게 한다(재진입 즉시-true 방지).
 */
export function useDeferredFlag(flag: boolean, delayMs = 250): boolean {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!flag) return;
    const id = setTimeout(() => setShown(true), delayMs);
    return () => {
      clearTimeout(id);
      setShown(false);
    };
  }, [flag, delayMs]);
  return flag && shown;
}
