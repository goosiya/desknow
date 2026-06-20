"use client";

// 챗봇 문서 인제스트 패널 (Story 8.4 — 트리거 + 처리 리포트 + 지식 문서 목록).
//
// 운영자가 (1) 현재 docs_corpus 지식 문서 목록과 적재 상태를 보고, (2) 인제스트를 트리거하고,
// (3) 처리 결과(성공/스킵/실패/정리)를 확인한다. 목록은 읽기 전용 useQuery(메뉴 진입만으로
// 인제스트가 돌지 않음), 트리거는 파괴적 useMutation(1단계 인라인 확인 — admin 모달 부재). 트리거가
// 성공하면 목록 쿼리를 무효화해 상태 배지(대기→인제스트됨, 변경됨→인제스트됨)를 갱신한다.
// 백엔드 호출은 생성 SDK 경유만(no-direct-fetch 가드).
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { AdminIngestDocument } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { INGEST_DOCUMENTS_QUERY_KEY, useIngestDocuments } from "./useIngestDocuments";
import { useTriggerIngest } from "./useTriggerIngest";

/** 상태별 배지 메타(점 색 + 라벨). 표시와 실제 인제스트 동작이 1:1 일치하도록 4상태를 모두 구분한다. */
const STATUS_META: Record<
  AdminIngestDocument["status"],
  { label: string; dotClass: string; textClass: string }
> = {
  // 디스크 + DB + 내용 동일(최신) — 다음 실행 시 스킵.
  ingested: { label: "인제스트됨", dotClass: "bg-success", textClass: "text-success" },
  // 디스크 + DB but 내용 변경 — 다음 실행 시 재임베딩(재인제스트 필요).
  stale: { label: "변경됨 · 재인제스트 필요", dotClass: "bg-destructive", textClass: "text-destructive" },
  // 디스크에만 — 미적재 신규(다음 실행 시 적재).
  pending: { label: "인제스트 대기", dotClass: "bg-muted-foreground", textClass: "text-muted-foreground" },
  // DB에만 — 디스크에서 사라짐(다음 실행 시 정리).
  orphan: { label: "정리 예정(파일 없음)", dotClass: "bg-pin-full", textClass: "text-pin-full" },
};

/** 리포트 섹션 1개(라벨 + 개수 + 경로 목록). 목록이 비면 렌더하지 않는다. */
function ReportSection({ label, paths }: { label: string; paths: string[] }) {
  if (paths.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <p className="text-sm font-medium">
        {label} <span className="text-muted-foreground">({paths.length})</span>
      </p>
      <ul className="flex flex-col gap-0.5 text-sm text-muted-foreground">
        {paths.map((path) => (
          <li key={path}>{path}</li>
        ))}
      </ul>
    </div>
  );
}

/** 지식 문서 목록 — corpus 디스크∪DB의 문서를 적재 상태와 함께 표시(읽기 전용). */
function DocumentList() {
  const { data, isLoading, isError } = useIngestDocuments();

  if (isLoading) {
    return (
      <p className="text-sm leading-[1.6] text-muted-foreground">문서 목록을 불러오는 중…</p>
    );
  }
  if (isError || !data) {
    return (
      <p className="text-sm leading-[1.6] text-pin-full">
        문서 목록을 불러오지 못했어요. 네트워크 연결이 끊겼을 수 있습니다.
      </p>
    );
  }
  if (data.total === 0) {
    return (
      <p className="text-sm leading-[1.6] text-muted-foreground">
        docs_corpus 디렉터리에 문서가 없습니다. 문서를 추가한 뒤 인제스트를 실행하세요.
      </p>
    );
  }

  return (
    <ul className="flex flex-col divide-y divide-border">
      {data.documents.map((doc) => {
        const meta = STATUS_META[doc.status];
        return (
          <li
            key={doc.source_path}
            className="flex items-center justify-between gap-3 py-2.5"
          >
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="truncate text-sm font-medium">{doc.source_path}</span>
              {doc.chunk_count > 0 ? (
                <span className="text-xs text-muted-foreground">{doc.chunk_count}개 청크</span>
              ) : null}
            </div>
            <span
              className={`flex shrink-0 items-center gap-1.5 text-xs font-medium ${meta.textClass}`}
            >
              <span className={`size-2 rounded-full ${meta.dotClass}`} aria-hidden />
              {meta.label}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function AdminIngestPanel() {
  const [confirming, setConfirming] = useState(false);
  const queryClient = useQueryClient();
  const { mutate, data, isPending, isError, reset } = useTriggerIngest();

  return (
    <div className="flex flex-col gap-6">
      {/* ── 지식 문서 목록(읽기 전용 — 메뉴 진입 시 현재 적재 현황) ── */}
      <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-6">
        <div className="flex flex-col gap-1">
          <h2 className="text-base font-semibold leading-[1.4]">지식 문서</h2>
          <p className="text-sm leading-[1.6] text-muted-foreground">
            docs_corpus 디렉터리의 문서와 챗봇 지식 적재 상태입니다. 인제스트를 실행하면 변경·신규
            문서가 적재되고 사라진 문서는 정리됩니다.
          </p>
        </div>
        <DocumentList />
      </div>

      {/* ── 트리거 + 1단계 파괴적 확인 ── */}
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-6">
        {confirming ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm leading-[1.6] text-muted-foreground">
              인제스트를 실행하면 docs_corpus 문서를 임베딩하고, corpus에 없는 문서의 기존 청크는
              정리(삭제)됩니다. 실행하시겠어요?
            </p>
            <div className="flex gap-2">
              <Button
                variant="destructive"
                size="sm"
                disabled={isPending}
                // 성공하면 확인 게이트를 닫는다 — 안 닫으면 파괴적 "실행" 버튼이 재무장된 채 남아
                // 재확인 없이 재인제스트(OpenAI 과금 + reconcile DELETE)가 한 번 더 발동될 수 있다.
                // 성공 시 문서 목록 쿼리를 무효화해 상태 배지(대기/변경됨→인제스트됨)를 갱신한다.
                onClick={() =>
                  mutate(undefined, {
                    onSuccess: () => {
                      setConfirming(false);
                      queryClient.invalidateQueries({ queryKey: INGEST_DOCUMENTS_QUERY_KEY });
                    },
                  })
                }
              >
                {isPending ? "인제스트 실행 중…" : "실행"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={isPending}
                onClick={() => {
                  setConfirming(false);
                  reset();
                }}
              >
                취소
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-start gap-3">
            <p className="text-sm leading-[1.6] text-muted-foreground">
              docs_corpus 디렉터리에 배치된 문서를 인제스트해 챗봇 지식을 갱신합니다.
            </p>
            <Button
              variant="default"
              size="sm"
              // 새 실행을 시작할 때 직전 리포트/에러를 비운다 — 안 그러면 옛 결과가 다음 실행 위에
              // 잔존해 운영자가 과거 리포트를 새 결과로 오인한다(reset이 data·isError를 모두 클리어).
              onClick={() => {
                reset();
                setConfirming(true);
              }}
            >
              인제스트 실행
            </Button>
          </div>
        )}

        {isError ? (
          // 네트워크 단절 등 — 막다른 화면 대신 인라인 안내(에러코드·상태 미노출, AC5).
          <p className="text-sm leading-[1.6] text-pin-full">
            인제스트에 실패했어요. 네트워크 연결이 끊겼을 수 있습니다.
          </p>
        ) : null}
      </div>

      {/* ── 결과 리포트(실행 후) ── */}
      {/* 에러 시에는 리포트를 숨긴다 — 직전 성공 리포트가 실패 배너와 동시 표시돼 오인되는 것을 막음. */}
      {data && !isError ? (
        <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-6">
          <p className="text-sm leading-[1.6]">
            처리 문서 {data.total}개 — 성공 {data.succeeded.length} / 스킵{" "}
            {data.skipped.length} / 실패 {data.failed.length} / 정리 {data.removed.length}
          </p>
          <ReportSection label="성공" paths={data.succeeded} />
          <ReportSection label="스킵(내용 동일)" paths={data.skipped} />
          {data.failed.length > 0 ? (
            <div className="flex flex-col gap-1">
              <p className="text-sm font-medium">
                실패 <span className="text-muted-foreground">({data.failed.length})</span>
              </p>
              <ul className="flex flex-col gap-0.5 text-sm text-pin-full">
                {data.failed.map((f) => (
                  <li key={f.path}>
                    {f.path} — {f.reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <ReportSection label="정리(corpus에 없어 삭제)" paths={data.removed} />
        </div>
      ) : null}
    </div>
  );
}
