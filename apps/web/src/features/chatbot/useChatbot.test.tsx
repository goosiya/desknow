// useChatbot 훅 테스트 (Story 7.3 → 7.4 스트리밍 — AC3·AC4·AC5). streamMessage(SSE)·useSession 을
// 모킹해 라이브 백엔드 없이 옵티미스틱 전송·델타 누적·타이핑 인디케이터·에러 강등(부분 버블 제거·
// 사용자 버블 유지)·재전송·로그아웃(session→null) 초기화를 검증한다. transcript 재수화(GET)는 SDK 유지.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { chatbotGetTranscript, chatbotResetSession } from "@/lib/api-client";
import { streamMessage, type StreamEvent } from "./streamMessage";
import { useChatbot } from "./useChatbot";

vi.mock("@/lib/api-client", () => ({
  chatbotGetTranscript: vi.fn(),
  chatbotResetSession: vi.fn(),
}));

vi.mock("./streamMessage", () => ({
  streamMessage: vi.fn(),
}));

// useSession 은 mutable 홀더로 제어(로그인↔로그아웃 전이 검증). vi.hoisted 로 TDZ 회피.
const sessionHolder = vi.hoisted(() => ({ data: { id: "u1" } as unknown }));
vi.mock("@/features/auth/useSession", () => ({
  useSession: () => ({ data: sessionHolder.data }),
}));

const mockStream = vi.mocked(streamMessage);
const mockGet = vi.mocked(chatbotGetTranscript);
const mockReset = vi.mocked(chatbotResetSession);

const DEVICE_ID = "device-aaaa-1111";

/** 이벤트 배열을 스트림(async iterable)으로 — streamMessage 모킹 구현이 호출마다 새 제너레이터 생성. */
function fromEvents(events: StreamEvent[]): () => AsyncGenerator<StreamEvent> {
  return async function* () {
    for (const ev of events) yield ev;
  };
}

function setup(onSessionEnd?: () => void) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const removeSpy = vi.spyOn(client, "removeQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const view = renderHook(() => useChatbot({ deviceId: DEVICE_ID, onSessionEnd }), {
    wrapper,
  });
  return { ...view, removeSpy };
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionHolder.data = { id: "u1" };
  mockGet.mockResolvedValue({ data: { messages: [] } } as never);
  mockReset.mockResolvedValue({ data: undefined } as never);
});

describe("useChatbot (스트리밍)", () => {
  it("전송 시 사용자 버블을 옵티미스틱 append하고 델타를 누적해 어시스턴트 버블을 렌더한다(AC3)", async () => {
    mockStream.mockImplementation(
      fromEvents([
        { type: "delta", text: "환불은 " },
        { type: "delta", text: "24시간 전까지 " },
        { type: "delta", text: "가능해요" },
        { type: "done" },
      ]),
    );
    const { result } = setup();

    act(() => result.current.send("환불 규정?"));

    // 옵티미스틱: 사용자 버블 즉시.
    await waitFor(() =>
      expect(result.current.messages).toContainEqual({
        role: "user",
        content: "환불 규정?",
      }),
    );
    // 델타 누적: 어시스턴트 버블이 합쳐진 전체 응답으로 렌더.
    await waitFor(() =>
      expect(result.current.messages).toContainEqual({
        role: "assistant",
        content: "환불은 24시간 전까지 가능해요",
      }),
    );
    // 스트림 종료 후 인디케이터·스트리밍 상태 해제.
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.isSending).toBe(false);
    // signal(AbortSignal)이 함께 전달되므로 message·deviceId만 부분 매칭한다(취소 핸들 주입).
    expect(mockStream).toHaveBeenCalledWith(
      expect.objectContaining({ message: "환불 규정?", deviceId: DEVICE_ID }),
    );
  });

  it("첫 델타 전에는 타이핑 인디케이터(isSending)를 노출한다(AC3)", async () => {
    // 첫 델타를 보내지 않고 멈춘 스트림 → isSending 이 true 로 유지됨을 관찰.
    mockStream.mockImplementation(async function* () {
      await new Promise(() => {}); // 첫 토큰 전 영구 대기
    });
    const { result } = setup();

    act(() => result.current.send("안녕"));

    await waitFor(() => expect(result.current.isSending).toBe(true));
    expect(result.current.isStreaming).toBe(true);
    // 첫 델타 전이라 어시스턴트 버블 없음, 사용자 버블만.
    expect(result.current.messages).toEqual([{ role: "user", content: "안녕" }]);
  });

  it("스트림 error 시 부분 어시스턴트 버블을 제거하고 사용자 버블은 유지한다(AC4)", async () => {
    mockStream.mockImplementation(
      fromEvents([
        { type: "delta", text: "부분 답" },
        { type: "error", code: "LLM_PROVIDER_UNAVAILABLE", message: "막힘" },
      ]),
    );
    const { result } = setup();

    act(() => result.current.send("안녕"));

    await waitFor(() => expect(result.current.isError).toBe(true));
    // 사용자 버블 유지(재전송용).
    expect(result.current.messages).toContainEqual({ role: "user", content: "안녕" });
    // 부분 어시스턴트 버블은 제거됨(막다른 화면 금지).
    expect(result.current.messages.some((m) => m.role === "assistant")).toBe(false);
    expect(result.current.isStreaming).toBe(false);
  });

  it("시작 전 실패(error 이벤트만)도 사용자 버블 유지 + isError(재전송 가능)", async () => {
    mockStream.mockImplementation(
      fromEvents([{ type: "error", code: "STREAM_FAILED", message: "막힘" }]),
    );
    const { result } = setup();

    act(() => result.current.send("안녕"));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.messages).toContainEqual({ role: "user", content: "안녕" });
    expect(result.current.messages.some((m) => m.role === "assistant")).toBe(false);
  });

  it("빈 응답(done만·델타 0개)은 막다른 화면 대신 graceful 에러로 강등한다(Review patch)", async () => {
    // 비스트리밍 모델·빈 LLM 응답 등으로 델타가 하나도 안 오고 done만 오는 경우 — 무응답·무에러·
    // 재전송 부재 막다른 상태가 되지 않게 isError로 강등(사용자 버블 유지·재전송 노출).
    mockStream.mockImplementation(fromEvents([{ type: "done" }]));
    const { result } = setup();

    act(() => result.current.send("안녕"));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.messages).toContainEqual({ role: "user", content: "안녕" });
    expect(result.current.messages.some((m) => m.role === "assistant")).toBe(false);
    expect(result.current.isStreaming).toBe(false);
  });

  it("done 없이 종료(서버측 절단)하면 부분 응답을 완성으로 오인하지 않고 강등한다(Review patch)", async () => {
    // 서버가 done/error 프레임 없이 연결을 닫으면(비-DomainError 예외 등) 절단된 부분 응답이 남는다.
    // 명시 done 미수신 → graceful 에러로 강등(부분 어시스턴트 제거·사용자 버블 유지·재전송).
    mockStream.mockImplementation(
      fromEvents([
        { type: "delta", text: "부분 답인" },
        { type: "delta", text: "데 끊김" },
      ]),
    );
    const { result } = setup();

    act(() => result.current.send("안녕"));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.messages).toContainEqual({ role: "user", content: "안녕" });
    expect(result.current.messages.some((m) => m.role === "assistant")).toBe(false);
  });

  it("재전송(retry)은 사용자 버블을 중복 append하지 않는다", async () => {
    mockStream.mockImplementationOnce(
      fromEvents([{ type: "error", code: "STREAM_FAILED", message: "막힘" }]),
    );
    mockStream.mockImplementationOnce(
      fromEvents([{ type: "delta", text: "다시 답변" }, { type: "done" }]),
    );
    const { result } = setup();

    act(() => result.current.send("질문"));
    await waitFor(() => expect(result.current.isError).toBe(true));

    act(() => result.current.retry());
    await waitFor(() =>
      expect(result.current.messages.some((m) => m.role === "assistant")).toBe(true),
    );

    // 사용자 버블은 한 번만(재전송이 중복 append 안 함).
    const userBubbles = result.current.messages.filter((m) => m.role === "user");
    expect(userBubbles).toHaveLength(1);
    // 재전송도 같은 텍스트로 스트림(lastFailedText 정확성).
    expect(mockStream).toHaveBeenLastCalledWith(
      expect.objectContaining({ message: "질문", deviceId: DEVICE_ID }),
    );
  });

  it("로그아웃(session→null 전이) 시 캐시 제거 + 패널 닫기 + 서버 thread 폐기(AC5)", async () => {
    mockStream.mockImplementation(
      fromEvents([{ type: "delta", text: "응답" }, { type: "done" }]),
    );
    const onSessionEnd = vi.fn();
    const { result, rerender, removeSpy } = setup(onSessionEnd);

    // 로그인 상태에서 대화 발생.
    act(() => result.current.send("안녕"));
    await waitFor(() =>
      expect(result.current.messages.some((m) => m.role === "assistant")).toBe(true),
    );

    // 세션 종료(refresh 무효화 → authMe 401 → data=null) 전이.
    sessionHolder.data = null;
    rerender();

    await waitFor(() => expect(onSessionEnd).toHaveBeenCalled());
    expect(removeSpy).toHaveBeenCalledWith({ queryKey: ["chatbot"] });
    expect(mockReset).toHaveBeenCalledWith(
      expect.objectContaining({ query: { device_id: DEVICE_ID } }),
    );
  });

  it("미로그인 상태로 시작하면 초기화를 발화하지 않는다(전이 아님)", async () => {
    sessionHolder.data = null;
    const onSessionEnd = vi.fn();
    setup(onSessionEnd);

    await new Promise((r) => setTimeout(r, 30));
    expect(onSessionEnd).not.toHaveBeenCalled();
    expect(mockReset).not.toHaveBeenCalled();
  });

  it("transcript 재수화(GET)로 서버 이력을 노출한다(AC4 보존)", async () => {
    mockGet.mockResolvedValue({
      data: { messages: [{ role: "user", content: "이전 질문" }] },
    } as never);
    const { result } = setup();

    await waitFor(() =>
      expect(result.current.messages).toContainEqual({ role: "user", content: "이전 질문" }),
    );
    expect(mockGet).toHaveBeenCalledWith(
      expect.objectContaining({ query: { device_id: DEVICE_ID } }),
    );
  });
});
