import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { adminListIngestDocuments, adminTriggerIngest } from "@/lib/api-client";
import { AdminIngestPanel } from "./AdminIngestPanel";

// 챗봇 인제스트 패널 테스트 (Story 8.4 — 문서 목록 + 트리거 + 리포트).
// adminListIngestDocuments(목록)·adminTriggerIngest(트리거) mock(배럴 경유).
vi.mock("@/lib/api-client", () => ({
  adminListIngestDocuments: vi.fn(),
  adminTriggerIngest: vi.fn(),
}));

const mockList = vi.mocked(adminListIngestDocuments);
const mockIngest = vi.mocked(adminTriggerIngest);

function docs(documents: Array<Record<string, unknown>> = []) {
  return {
    data: { documents, total: documents.length },
    response: new Response(null, { status: 200 }),
  } as never;
}

function report(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      succeeded: ["faq.md"],
      skipped: ["guide.md"],
      failed: [{ path: "broken.md", reason: "DocumentLoadError: 빈 문서" }],
      removed: ["old.md"],
      total: 3,
      ...overrides,
    },
    response: new Response(null, { status: 200 }),
  } as never;
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  // 기본: 빈 목록(개별 테스트가 필요 시 override).
  mockList.mockResolvedValue(docs());
});

describe("AdminIngestPanel", () => {
  it("트리거 전 안내 카피를 보인다", () => {
    render(<AdminIngestPanel />, { wrapper });

    expect(
      screen.getByText("docs_corpus 디렉터리에 배치된 문서를 인제스트해 챗봇 지식을 갱신합니다.")
    ).toBeInTheDocument();
    // 아직 트리거 호출 0(렌더만으로 인제스트되지 않음 — 목록 조회는 읽기 전용).
    expect(mockIngest).not.toHaveBeenCalled();
  });

  it("지식 문서 목록을 상태 배지와 함께 렌더한다", async () => {
    mockList.mockResolvedValue(
      docs([
        { source_path: "faq.md", chunk_count: 4, status: "ingested" },
        { source_path: "guide.md", chunk_count: 2, status: "stale" },
        { source_path: "new.md", chunk_count: 0, status: "pending" },
        { source_path: "gone.md", chunk_count: 1, status: "orphan" },
      ])
    );

    render(<AdminIngestPanel />, { wrapper });

    expect(await screen.findByText("faq.md")).toBeInTheDocument();
    expect(screen.getByText("인제스트됨")).toBeInTheDocument();
    expect(screen.getByText("변경됨 · 재인제스트 필요")).toBeInTheDocument();
    expect(screen.getByText("인제스트 대기")).toBeInTheDocument();
    expect(screen.getByText("정리 예정(파일 없음)")).toBeInTheDocument();
    expect(screen.getByText("4개 청크")).toBeInTheDocument();
  });

  it("문서가 없으면 빈 안내를 보인다", async () => {
    render(<AdminIngestPanel />, { wrapper });

    expect(
      await screen.findByText(/docs_corpus 디렉터리에 문서가 없습니다/)
    ).toBeInTheDocument();
  });

  it("실행 → 1단계 확인 → 뮤테이션 호출 → 성공 리포트 렌더", async () => {
    mockIngest.mockResolvedValue(report());
    const user = userEvent.setup();

    render(<AdminIngestPanel />, { wrapper });
    await user.click(screen.getByRole("button", { name: "인제스트 실행" }));

    // 확인 단계 — reconcile(삭제) 경고 카피.
    expect(
      screen.getByText(/corpus에 없는 문서의 기존 청크는\s+정리\(삭제\)됩니다/)
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "실행" }));

    await waitFor(() => expect(mockIngest).toHaveBeenCalledTimes(1));
    // 리포트: 성공/스킵/실패/정리 개수 + 실패 경로+사유.
    expect(await screen.findByText(/처리 문서 3개/)).toBeInTheDocument();
    expect(
      screen.getByText("broken.md — DocumentLoadError: 빈 문서")
    ).toBeInTheDocument();
    expect(screen.getByText("old.md")).toBeInTheDocument();
  });

  it("실행 실패(네트워크) → 에러 카피 표시", async () => {
    mockIngest.mockRejectedValue(new Error("network"));
    const user = userEvent.setup();

    render(<AdminIngestPanel />, { wrapper });
    await user.click(screen.getByRole("button", { name: "인제스트 실행" }));
    await user.click(screen.getByRole("button", { name: "실행" }));

    expect(
      await screen.findByText(/인제스트에 실패했어요\. 네트워크 연결이 끊겼을 수 있습니다\./)
    ).toBeInTheDocument();
  });
});
