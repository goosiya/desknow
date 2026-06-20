// 챗봇 문서 인제스트 트리거 뮤테이션 (Story 8.4, AC4). 백엔드 호출은 생성 SDK 경유만(1.9 가드).
//
// `POST /api/v1/admin/ingest`(adminTriggerIngest)를 호출해 docs_corpus 문서를 멱등 인제스트하고
// 처리 리포트(성공/스킵/실패/정리)를 받는다. 멱등(sha256)·부분실패 격리·stale 청크 reconcile은
// 전부 백엔드가 보장하므로 여기선 호출 + 리포트 반환만 한다. 인제스트 이력 쿼리가 없어
// invalidateQueries는 불필요하다(단발 액션 — useForceCancelReservation의 목록 무효화와 대비).
import { useMutation } from "@tanstack/react-query";

import { adminTriggerIngest } from "@/lib/api-client";

/**
 * 인제스트 트리거 뮤테이션. throwOnError로 비-2xx를 throw → 컴포넌트가 isError로 에러 카피 표시.
 *
 * - `mutationFn`: adminTriggerIngest(SDK) — 인자 없음(고정 docs_corpus 디렉터리). `data`(리포트)를
 *   반환해 컴포넌트가 성공/스킵/실패/정리 목록을 렌더한다(useForceCancelReservation data 반환 미러).
 * - 동기 백엔드라 응답이 곧 처리 완료다(폴링 없음). 네트워크 실패는 throw되어 컴포넌트 isError 처리.
 */
export function useTriggerIngest() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await adminTriggerIngest({ throwOnError: true });
      return data;
    },
  });
}
