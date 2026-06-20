// 인제스트 지식베이스 문서 목록 쿼리. 백엔드 호출은 생성 SDK 경유만(1.9 가드).
//
// `GET /api/v1/admin/ingest/documents`(adminListIngestDocuments)로 현재 적재 현황을 조회한다.
// **읽기 전용**(OpenAI·DB 쓰기 0)이라 메뉴 진입만으로 인제스트가 돌지 않는다 — 트리거는 별도
// useTriggerIngest(POST). 인제스트 실행이 성공하면 컴포넌트가 이 쿼리를 무효화해 목록을 갱신한다.
import { useQuery } from "@tanstack/react-query";

import {
  adminListIngestDocuments,
  type AdminIngestDocumentList,
} from "@/lib/api-client";

/** 인제스트 문서 목록 쿼리 키(트리거 성공 시 무효화 대상). */
export const INGEST_DOCUMENTS_QUERY_KEY = ["admin", "ingest", "documents"];

export function useIngestDocuments() {
  return useQuery<AdminIngestDocumentList>({
    queryKey: INGEST_DOCUMENTS_QUERY_KEY,
    queryFn: async () => {
      const { data } = await adminListIngestDocuments({ throwOnError: true });
      // throwOnError:true면 성공 시 data가 보장된다(에러는 throw → 쿼리 isError).
      return data as AdminIngestDocumentList;
    },
  });
}
