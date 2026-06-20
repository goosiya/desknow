// 챗봇 인제스트 화면 (Story 8.4, AC4·AC5). 8.1 ComingSoon 골격을 실 트리거+리포트 패널로 교체.
// 운영자가 docs_corpus 문서 인제스트를 트리거하고 처리 결과(성공/스킵/실패/정리)를 확인한다.
import { AdminIngestPanel } from "@/features/ingest/AdminIngestPanel";
import { AdminGate } from "@/features/auth/AdminGate";

export default function IngestPage() {
  return (
    <AdminGate>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold leading-[1.4] tracking-[-0.01em]">챗봇 인제스트</h1>
          <p className="text-base leading-[1.6] text-muted-foreground">
            docs_corpus 디렉터리의 문서를 챗봇 지식으로 적재합니다. 동일 문서는 건너뛰고, corpus에서
            사라진 문서의 기존 청크는 정리됩니다.
          </p>
        </div>
        <AdminIngestPanel />
      </div>
    </AdminGate>
  );
}
