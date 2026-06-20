// 예약 에러 코드 판별 — 웹 reservation/errors.ts 복사 (Story 9.2 — AC3·AC4·AC5). SDK 는
// throwOnError 시 파싱된 에러 본문(`{detail:{code,message}}`)을 그대로 throw 하므로(hey-api
// client-fetch 실측), HTTP 상태가 에러 객체에 직접 실리지 않는다 → 백엔드 에러 계약(1.5
// ErrorResponse)의 `detail.code` 로 분기한다.
//
// 훅(onError 재조회)과 컴포넌트(특화 카피·selection 초기화)가 같은 판별을 써야 하므로 feature-local
// 공용 헬퍼로 추출한다(인라인 중복 회피). 코드/숫자는 화면에 노출하지 않고 분기에만 쓴다(UX-DR10).

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
 * 분기하고, 그 외 실패(404·5xx·기타)는 generic 처리를 유지한다(무회귀).
 */
export function isSlotConflict(error: unknown): boolean {
  return errorDetailCode(error) === "SLOT_CONFLICT";
}

/**
 * 취소 윈도우 경과(409 `CANCEL_WINDOW_PASSED`)인지 식별한다(AC4).
 *
 * FE가 6h 계산으로 취소 버튼을 활성 표시했더라도 **클럭 스큐**로 서버가 6h 경과를 판정해 409를
 * 돌려줄 수 있다. 이 경우 막다른 화면·에러코드 노출 대신 친절한 안내 + 목록 재조회(버튼 상태
 * 갱신)로 우아하게 처리한다.
 */
export function isCancelWindowPassed(error: unknown): boolean {
  return errorDetailCode(error) === "CANCEL_WINDOW_PASSED";
}

/**
 * 후기 작성 불가 — 이용 완료 안 됨(409 `RESERVATION_NOT_COMPLETED`)인지 식별한다(AC5).
 *
 * FE 게이팅(이용 완료 + 미작성 행에만 폼 노출)이 활성이었더라도 **클럭 스큐**로 서버가 미완료를
 * 판정해 409를 돌려줄 수 있다. 막다른 화면·에러코드 노출 대신 친절한 안내 + 목록 재조회로 처리한다.
 */
export function isReservationNotCompleted(error: unknown): boolean {
  return errorDetailCode(error) === "RESERVATION_NOT_COMPLETED";
}

/**
 * 후기 중복 — 이미 작성됨(409 `REVIEW_ALREADY_EXISTS`)인지 식별한다(AC5).
 *
 * 더블 클릭·경합으로 같은 예약에 두 번 작성 시도하면 서버가 `uq_reviews_reservation`로 막아 409를
 * 돌려준다. 막다른 화면 대신 "이미 후기를 남기셨어요" 안내 + 목록 재조회(has_review 갱신 → 폼
 * 숨김)로 처리한다(코드는 분기에만, 화면 미노출 — UX-DR10).
 */
export function isReviewAlreadyExists(error: unknown): boolean {
  return errorDetailCode(error) === "REVIEW_ALREADY_EXISTS";
}

/**
 * 미존재/비활성 룸 404(`ROOM_NOT_FOUND`)인지 식별한다(AC1).
 *
 * 룸 상세 진입 시 방이 사라졌거나 비활성이면 서버가 404 `ROOM_NOT_FOUND`를 돌려준다. 일반 실패와
 * 구분해 "그 방은 더 이상 없어요" 안내로 분기한다(나머지 비-2xx는 generic 재시도).
 */
export function isRoomNotFound(error: unknown): boolean {
  return errorDetailCode(error) === "ROOM_NOT_FOUND";
}
