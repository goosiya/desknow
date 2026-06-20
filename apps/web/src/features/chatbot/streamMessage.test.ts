// streamMessage SSE fetch-stream 파서 테스트 (Story 7.4 — AC3·AC4·AC5).
// fetch/ReadableStream 을 모킹해 라이브 백엔드 없이 프레임 파싱·분할 프레임·종료/에러·프레이밍
// 견고성(토큰에 \n·공백·[DONE] 섞임)을 검증한다. baseUrl 은 getApiBaseUrl 모킹으로 고정.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { streamMessage, type StreamEvent } from "./streamMessage";

// authRefresh 는 vi.hoisted 로 끌어올려 mock 팩토리에서 참조한다(C② mid-session 401 회복).
const { authRefreshMock } = vi.hoisted(() => ({ authRefreshMock: vi.fn() }));
vi.mock("@/lib/api-client", () => ({
  getApiBaseUrl: () => "http://test-api",
  authRefresh: authRefreshMock,
}));

/** 청크 배열을 SSE 스트림 응답(Response 유사체)으로 만든다. sse-starlette처럼 \r\n 줄바꿈 사용. */
function sseResponse(
  chunks: string[],
  { ok = true, cancel }: { ok?: boolean; cancel?: () => Promise<void> } = {},
): Response {
  const encoder = new TextEncoder();
  let i = 0;
  const reader = {
    read: async () => {
      if (i < chunks.length) return { done: false, value: encoder.encode(chunks[i++]) };
      return { done: true, value: undefined };
    },
    // 소비처가 조기 종료/abort/정상 종료 시 호출 — 본문 스트림 정리(누수 방지). 미주입 시 no-op.
    cancel: cancel ?? (async () => {}),
  };
  return {
    ok,
    status: ok ? 200 : 401,
    body: ok ? { getReader: () => reader } : null,
  } as unknown as Response;
}

async function collect(): Promise<StreamEvent[]> {
  const events: StreamEvent[] = [];
  for await (const ev of streamMessage({ message: "질문", deviceId: "device-aaaa-1111" })) {
    events.push(ev);
  }
  return events;
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("streamMessage", () => {
  it("delta 프레임을 순서대로 파싱하고 done으로 종료한다(AC3)", async () => {
    fetchMock.mockResolvedValue(
      sseResponse([
        'data: {"delta": "환불은 "}\r\n\r\n',
        'data: {"delta": "가능해요"}\r\n\r\n',
        "event: done\r\ndata: {}\r\n\r\n",
      ]),
    );

    const events = await collect();

    expect(events).toEqual([
      { type: "delta", text: "환불은 " },
      { type: "delta", text: "가능해요" },
      { type: "done" },
    ]);
  });

  it("청크 경계에 걸친 분할 프레임을 버퍼링해 재조립한다", async () => {
    // 한 프레임이 두 read에 걸쳐 도착(`\r\n\r\n` 경계도 분할).
    fetchMock.mockResolvedValue(
      sseResponse(['data: {"del', 'ta": "조각"}\r', "\n\r\n", "event: done\r\ndata: {}\r\n\r\n"]),
    );

    const events = await collect();

    expect(events).toEqual([{ type: "delta", text: "조각" }, { type: "done" }]);
  });

  it("event: error를 code/message로 파싱한다(AC4 인밴드 실패)", async () => {
    fetchMock.mockResolvedValue(
      sseResponse([
        'data: {"delta": "부분"}\r\n\r\n',
        'event: error\r\ndata: {"code": "LLM_PROVIDER_UNAVAILABLE", "message": "막힘"}\r\n\r\n',
      ]),
    );

    const events = await collect();

    expect(events).toEqual([
      { type: "delta", text: "부분" },
      { type: "error", code: "LLM_PROVIDER_UNAVAILABLE", message: "막힘" },
    ]);
  });

  it("토큰에 \\n·공백·[DONE]이 섞여도 정확히 재조립한다(프레이밍 견고성 — L129 회수)", async () => {
    // JSON 인코딩 덕에 와이어 data:는 단일 라인(실제 \n은 \\n으로 이스케이프)이라 프레임 무손상.
    const payload = ["줄1\n줄2", "  ", "[DONE]", " 끝"];
    const chunks = payload.map((d) => `data: ${JSON.stringify({ delta: d })}\r\n\r\n`);
    chunks.push("event: done\r\ndata: {}\r\n\r\n");
    fetchMock.mockResolvedValue(sseResponse(chunks));

    const events = await collect();

    const deltas = events.filter((e) => e.type === "delta").map((e) => (e as { text: string }).text);
    expect(deltas.join("")).toBe("줄1\n줄2  [DONE] 끝");
    expect(events.some((e) => e.type === "done")).toBe(true);
  });

  it("주석(keep-alive ping) 프레임은 무시한다", async () => {
    fetchMock.mockResolvedValue(
      sseResponse([
        ": ping\r\n\r\n",
        'data: {"delta": "x"}\r\n\r\n',
        "event: done\r\ndata: {}\r\n\r\n",
      ]),
    );

    const events = await collect();

    expect(events).toEqual([{ type: "delta", text: "x" }, { type: "done" }]);
  });

  it("스트림 시작 전 실패(non-OK 응답)는 error로 강등한다(AC4 막다른 화면 금지)", async () => {
    fetchMock.mockResolvedValue(sseResponse([], { ok: false }));

    const events = await collect();

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ type: "error", code: "STREAM_FAILED" });
  });

  it("네트워크 단절(fetch reject)도 error로 강등한다", async () => {
    fetchMock.mockRejectedValue(new TypeError("network down"));

    const events = await collect();

    expect(events).toEqual([
      { type: "error", code: "STREAM_FAILED", message: "스트림을 시작할 수 없습니다." },
    ]);
  });

  it("올바른 엔드포인트·자격증명·바디로 POST한다(AC3 쿠키 인증)", async () => {
    fetchMock.mockResolvedValue(sseResponse(["event: done\r\ndata: {}\r\n\r\n"]));

    await collect();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://test-api/api/v1/chatbot/stream",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "질문", device_id: "device-aaaa-1111" }),
      }),
    );
  });

  it("mid-session 401이면 authRefresh 후 stream을 1회 재시도해 회복한다(C②)", async () => {
    // 첫 시도 = access 토큰 만료로 401 → refresh 성공 → 재시도 = 정상 스트림.
    fetchMock
      .mockResolvedValueOnce(sseResponse([], { ok: false }))
      .mockResolvedValueOnce(
        sseResponse([
          'data: {"delta": "복구"}\r\n\r\n',
          "event: done\r\ndata: {}\r\n\r\n",
        ]),
      );
    authRefreshMock.mockResolvedValue({ response: { ok: true } });

    const events = await collect();

    expect(authRefreshMock).toHaveBeenCalledTimes(1);
    expect(authRefreshMock).toHaveBeenCalledWith({ body: {}, throwOnError: false });
    expect(fetchMock).toHaveBeenCalledTimes(2); // 최초 + 갱신 후 재시도
    expect(events).toEqual([{ type: "delta", text: "복구" }, { type: "done" }]);
  });

  it("refresh까지 401(refresh 토큰도 만료)이면 재시도 없이 강등한다(C②)", async () => {
    fetchMock.mockResolvedValue(sseResponse([], { ok: false }));
    authRefreshMock.mockResolvedValue({ response: { ok: false } });

    const events = await collect();

    expect(authRefreshMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1); // refresh 실패 → stream 재시도 안 함
    expect(events).toEqual([
      { type: "error", code: "STREAM_FAILED", message: "스트림을 시작할 수 없습니다." },
    ]);
  });

  it("재시도도 401이면 refresh를 1회만 시도하고 강등한다(무한 루프 방지 — C②)", async () => {
    fetchMock.mockResolvedValue(sseResponse([], { ok: false })); // 최초·재시도 모두 401
    authRefreshMock.mockResolvedValue({ response: { ok: true } });

    const events = await collect();

    expect(authRefreshMock).toHaveBeenCalledTimes(1); // refresh는 단 1회
    expect(fetchMock).toHaveBeenCalledTimes(2); // 최초 + 재시도 1회로 종료
    expect(events[0]).toMatchObject({ type: "error", code: "STREAM_FAILED" });
  });

  it("주입된 AbortSignal을 fetch에 전달한다(취소 핸들 — Review patch)", async () => {
    fetchMock.mockResolvedValue(sseResponse(["event: done\r\ndata: {}\r\n\r\n"]));
    const controller = new AbortController();

    const events: StreamEvent[] = [];
    for await (const ev of streamMessage({
      message: "질문",
      deviceId: "device-aaaa-1111",
      signal: controller.signal,
    })) {
      events.push(ev);
    }

    expect(fetchMock).toHaveBeenCalledWith(
      "http://test-api/api/v1/chatbot/stream",
      expect.objectContaining({ signal: controller.signal }),
    );
  });

  it("정상 종료·조기 break 모두 reader.cancel로 본문 스트림을 정리한다(누수 방지 — Review patch)", async () => {
    // (1) 정상 종료: 끝까지 소비하면 finally가 cancel을 호출.
    const cancelDone = vi.fn(async () => {});
    fetchMock.mockResolvedValue(
      sseResponse(['data: {"delta": "x"}\r\n\r\n', "event: done\r\ndata: {}\r\n\r\n"], {
        cancel: cancelDone,
      }),
    );
    await collect();
    expect(cancelDone).toHaveBeenCalledTimes(1);

    // (2) 조기 break: 소비처가 첫 이벤트 후 break해도 제너레이터 return() → finally cancel 호출.
    const cancelBreak = vi.fn(async () => {});
    fetchMock.mockResolvedValue(
      sseResponse(['data: {"delta": "a"}\r\n\r\n', 'data: {"delta": "b"}\r\n\r\n'], {
        cancel: cancelBreak,
      }),
    );
    for await (const ev of streamMessage({ message: "질문", deviceId: "device-aaaa-1111" })) {
      expect(ev).toBeDefined();
      break; // 첫 이벤트만 받고 중단 → 제너레이터 return() → finally cancel
    }
    expect(cancelBreak).toHaveBeenCalledTimes(1);
  });
});
