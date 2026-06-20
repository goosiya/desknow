// 예약 에러 코드 판별 (Story 4.6 — AC3). SDK 는 throwOnError 시 파싱된 에러 본문
// (`{detail:{code,message}}`)을 그대로 throw 하므로(hey-api client-fetch 실측), HTTP 상태가
// 에러 객체에 직접 실리지 않는다 → 백엔드 에러 계약(1.5 ErrorResponse)의 `detail.code` 로 분기한다.
//
// `features/detail/RoomDetail.tsx` 의 `isRoomNotFound`(detail.code === "ROOM_NOT_FOUND") 패턴을
// 미러한다. 훅(useCreateReservation onError 재조회)과 컴포넌트(ReservationPanel 특화 카피·selection
// 초기화)가 같은 판별을 써야 하므로 feature-local 공용 헬퍼로 추출한다(인라인 중복 회피).

/** 에러 본문에서 `detail.code` 문자열을 안전하게 추출한다(형태가 다르면 null). */
function errorDetailCode(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("detail" in error)) {
    return null;
  }
  const detail = (error as { detail?: unknown }).detail;
  if (typeof detail !== "object" || detail === null) {
    return null;
  }
  const code = (detail as { code?: unknown }).code;
  return typeof code === "string" ? code : null;
}

/**
 * 동시 예약 충돌(409 `SLOT_CONFLICT`)인지 식별한다(AC3).
 *
 * `SLOT_CONFLICT` 만 특화 UX(인접 빈 슬롯 재표시 + "먼저 잡았어요" 카피 + selection 초기화)로
 * 분기하고, 그 외 실패(404·5xx·기타)는 4.5 generic 처리를 유지한다(무회귀). 코드/숫자는 화면에
 * 노출하지 않고 분기에만 쓴다(UX-DR10 — 에러코드 노출 금지).
 */
export function isSlotConflict(error: unknown): boolean {
  return errorDetailCode(error) === "SLOT_CONFLICT";
}

/**
 * 취소 윈도우 경과(409 `CANCEL_WINDOW_PASSED`)인지 식별한다(Story 4.8 — AC2).
 *
 * FE가 6h 계산으로 취소 버튼을 활성 표시했더라도 **클럭 스큐**로 서버가 6h 경과를 판정해 409를
 * 돌려줄 수 있다. 이 경우 막다른 화면·에러코드 노출 대신 친절한 안내 + 목록 재조회(버튼 상태
 * 갱신)로 우아하게 처리한다(`isSlotConflict` 미러 — `errorDetailCode` 재사용). 코드 문자열은
 * 분기에만 쓰고 화면에 노출하지 않는다(UX-DR10 — 에러코드 노출 금지).
 */
export function isCancelWindowPassed(error: unknown): boolean {
  return errorDetailCode(error) === "CANCEL_WINDOW_PASSED";
}

/**
 * 후기 작성 불가 — 이용 완료 안 됨(409 `RESERVATION_NOT_COMPLETED`)인지 식별한다(Story 5.5 — AC2).
 *
 * FE 게이팅(이용 완료 + 미작성 행에만 폼 노출)이 활성이었더라도 **클럭 스큐**로 서버가 미완료를
 * 판정해 409를 돌려줄 수 있다. 이 경우 막다른 화면·에러코드 노출 대신 친절한 안내 + 목록 재조회로
 * 우아하게 처리한다(`errorDetailCode` 재사용). 코드 문자열은 분기에만 쓰고 화면에 노출하지 않는다.
 */
export function isReservationNotCompleted(error: unknown): boolean {
  return errorDetailCode(error) === "RESERVATION_NOT_COMPLETED";
}

/**
 * 후기 중복 — 이미 작성됨(409 `REVIEW_ALREADY_EXISTS`)인지 식별한다(Story 5.5 — AC2).
 *
 * 더블 클릭·경합으로 같은 예약에 두 번 작성 시도하면 서버가 `uq_reviews_reservation`로 막아 409를
 * 돌려준다. 막다른 화면 대신 "이미 후기를 남기셨어요" 안내 + 목록 재조회(has_review 갱신 → 폼 숨김)로
 * 처리한다(코드는 분기에만, 화면 미노출 — UX-DR10).
 */
export function isReviewAlreadyExists(error: unknown): boolean {
  return errorDetailCode(error) === "REVIEW_ALREADY_EXISTS";
}
