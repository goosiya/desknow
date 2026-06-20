// 챗봇 FAB + 패널 컴포넌트 테스트 (Story 7.3 → 7.4 스트리밍 — AC1·AC2·AC3). streamMessage·useSession
// 모킹. vaul 물리 드래그는 jsdom 밖(RoomSheet 선례) — FAB 오픈·제안 칩·스트리밍 전송·타이핑·에러·
// Esc 닫기만 검증.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { chatbotGetTranscript } from "@/lib/api-client";
import { streamMessage, type StreamEvent } from "./streamMessage";
import { ChatbotFabSlot } from "@/components/shell/ChatbotFabSlot";

vi.mock("@/lib/api-client", () => ({
  chatbotGetTranscript: vi.fn(),
  chatbotResetSession: vi.fn(() => Promise.resolve({ data: undefined })),
}));

vi.mock("./streamMessage", () => ({
  streamMessage: vi.fn(),
}));

// useSession 반환을 테스트별로 제어(로그인/로그아웃 분기 게이팅 검증용 — vi.hoisted 로 끌어올림).
const { sessionRef } = vi.hoisted(() => ({
  sessionRef: { current: { id: "u1", email: "a@b.com", role: "booker" } as unknown },
}));
vi.mock("@/features/auth/useSession", () => ({
  useSession: () => ({ data: sessionRef.current }),
}));

const mockStream = vi.mocked(streamMessage);
const mockGet = vi.mocked(chatbotGetTranscript);

/** 이벤트 배열을 스트림(async iterable)으로 — 호출마다 새 제너레이터 생성. */
function fromEvents(events: StreamEvent[]): () => AsyncGenerator<StreamEvent> {
  return async function* () {
    for (const ev of events) yield ev;
  };
}

function renderFab() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const ui: ReactNode = (
    <QueryClientProvider client={client}>
      <ChatbotFabSlot />
    </QueryClientProvider>
  );
  return render(ui);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockResolvedValue({ data: { messages: [] } } as never);
  // 각 테스트는 로그인 상태로 시작(로그아웃 테스트만 명시적으로 null 로 덮는다).
  sessionRef.current = { id: "u1", email: "a@b.com", role: "booker" };
});

describe("ChatbotFabSlot / ChatbotPanel (스트리밍)", () => {
  it("FAB가 전역 노출되고 a11y 라벨을 보존한다(AC1)", () => {
    renderFab();
    expect(
      screen.getByRole("button", { name: "룸메이트 챗봇 열기" }),
    ).toBeInTheDocument();
  });

  it("미로그인이면 입력 대신 로그인 안내로 게이팅한다(AC5 — 401 위장 차단)", async () => {
    // useSession=null(미로그인) → 패널이 입력/전송 대신 로그인 안내·로그인 링크를 보인다.
    sessionRef.current = null;
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));

    expect(
      await screen.findByText("로그인하면 룸메이트와 대화할 수 있어요.", { exact: false }),
    ).toBeInTheDocument();
    const loginLink = screen.getByRole("link", { name: "로그인하기" });
    expect(loginLink).toHaveAttribute("href", "/login?next=/");
    // 미로그인은 전송 경로를 막는다 — 입력·전송 비활성(streamMessage 호출 0).
    expect(screen.getByRole("textbox", { name: "메시지 입력" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "전송" })).toBeDisabled();
    // 제안 칩(로그인 시 첫 진입)도 노출되지 않는다.
    expect(screen.queryByRole("button", { name: "환불 규정?" })).toBeNull();
  });

  it("미로그인 입력이 차단되어 streamMessage가 호출되지 않는다(전송 no-op)", async () => {
    sessionRef.current = null;
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    // 비활성 입력이라 타이핑/전송이 불가 — 강제로 form submit 을 시도해도 send 가 no-op(미인증 가드).
    const input = await screen.findByRole("textbox", { name: "메시지 입력" });
    expect(input).toBeDisabled();
    expect(mockStream).not.toHaveBeenCalled();
  });

  it("FAB 탭 시 대화 패널이 열리고 첫 진입 제안 칩 2종이 보인다(AC1·AC2)", async () => {
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));

    expect(await screen.findByText("룸메이트")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "환불 규정?" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "강남 오후 3시 빈 방" }),
    ).toBeInTheDocument();
  });

  it("제안 칩 탭 시 그 텍스트가 스트리밍 전송되고 사용자·봇 버블이 점진 렌더된다(AC2·AC3)", async () => {
    mockStream.mockImplementation(
      fromEvents([
        { type: "delta", text: "환불은 " },
        { type: "delta", text: "24시간 전까지 가능해요" },
        { type: "done" },
      ]),
    );
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    await user.click(await screen.findByRole("button", { name: "환불 규정?" }));

    expect(mockStream).toHaveBeenCalledWith(
      expect.objectContaining({ message: "환불 규정?" }),
    );
    // 사용자 버블 + 누적된 봇 응답 버블.
    expect(await screen.findByText("환불은 24시간 전까지 가능해요")).toBeInTheDocument();
    expect(screen.getByText("환불 규정?")).toBeInTheDocument();
  });

  it("첫 토큰 전 타이핑 인디케이터를 보인다(AC3 — 스트리밍)", async () => {
    // 첫 델타 전 멈춘 스트림으로 pending(awaiting first token) 상태를 관찰.
    mockStream.mockImplementation(async function* () {
      await new Promise(() => {});
    });
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    const input = await screen.findByLabelText("메시지 입력");
    await user.type(input, "안녕");
    await user.click(screen.getByRole("button", { name: "전송" }));

    expect(await screen.findByTestId("chatbot-typing")).toBeInTheDocument();
  });

  it("스트림 실패 시 에러 카피 + 다시 보내기를 보인다(AC4 graceful degrade)", async () => {
    mockStream.mockImplementation(
      fromEvents([{ type: "error", code: "LLM_PROVIDER_UNAVAILABLE", message: "막힘" }]),
    );
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    await user.click(await screen.findByRole("button", { name: "환불 규정?" }));

    expect(
      await screen.findByText("잠깐 답이 막혔어요. 다시 물어봐 주실래요?"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "다시 보내기" }),
    ).toBeInTheDocument();
  });

  // Esc 닫기·포커스 복귀는 vaul/Radix 상속 동작이고, vaul은 종료 애니메이션 동안 콘텐츠를 DOM에
  // 유지한다(jsdom엔 transitionend 없음 — RoomSheet 선례로 물리 제스처/애니메이션은 jsdom 밖).
  // 따라서 콘텐츠 제거가 아니라 트리거의 open/closed 상태 전이(Radix data-state)로 닫힘을 검증한다.
  it("어시스턴트 답변의 룸 상세 경로를 클릭 가능한 링크로 렌더한다(7.6 AC6)", async () => {
    const roomId = "11111111-1111-1111-1111-111111111111";
    mockStream.mockImplementation(
      fromEvents([
        { type: "delta", text: `추천이에요: /rooms/${roomId} 확인해보세요` },
        { type: "done" },
      ]),
    );
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    await user.click(await screen.findByRole("button", { name: "환불 규정?" }));

    const link = await screen.findByRole("link", { name: `/rooms/${roomId}` });
    expect(link).toHaveAttribute("href", `/rooms/${roomId}`);
  });

  it("마크다운 링크 [상세보기](/rooms/uuid)는 라벨만 링크로 렌더하고 URL은 숨긴다(KTH)", async () => {
    const roomId = "22222222-2222-2222-2222-222222222222";
    mockStream.mockImplementation(
      fromEvents([
        { type: "delta", text: `강남 스터디룸 A - [상세보기](/rooms/${roomId})` },
        { type: "done" },
      ]),
    );
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    await user.click(await screen.findByRole("button", { name: "환불 규정?" }));

    // "상세보기"가 링크(href=/rooms/uuid)이고, raw URL 은 화면에 노출되지 않는다.
    const link = await screen.findByRole("link", { name: "상세보기" });
    expect(link).toHaveAttribute("href", `/rooms/${roomId}`);
    expect(screen.queryByText(`/rooms/${roomId}`, { exact: false })).toBeNull();
  });

  it("마크다운 [더보기](/) 는 '더보기'만 홈 링크로 렌더하고 / 는 노출하지 않는다(KTH)", async () => {
    mockStream.mockImplementation(
      fromEvents([
        { type: "delta", text: "더 많은 후보는 [더보기](/) 를 눌러요" },
        { type: "done" },
      ]),
    );
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    await user.click(await screen.findByRole("button", { name: "환불 규정?" }));

    const link = await screen.findByRole("link", { name: "더보기" });
    expect(link).toHaveAttribute("href", "/");
    // 별도의 "/" 링크가 새지 않는다(과거 버그: 경로 단독 `/` 미매칭으로 / 가 따로 링크됨).
    expect(screen.queryByRole("link", { name: "/" })).toBeNull();
  });

  it("내부 화이트리스트 밖 마크다운 링크는 라벨만 평문으로(링크 금지·URL 숨김 — 신뢰 경계)", async () => {
    mockStream.mockImplementation(
      fromEvents([
        { type: "delta", text: "여기 [클릭](/evil/path) 하세요" },
        { type: "done" },
      ]),
    );
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    await user.click(await screen.findByRole("button", { name: "환불 규정?" }));

    // 라벨은 평문으로 남고, 어떤 링크도·raw URL 도 만들어지지 않는다.
    expect(await screen.findByText("클릭", { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByText("/evil/path", { exact: false })).toBeNull();
  });

  it("LLM이 낸 외부 URL은 링크화하지 않는다(신뢰 경계 — 평문 유지)", async () => {
    mockStream.mockImplementation(
      fromEvents([
        { type: "delta", text: "여기 보세요 https://evil.example.com/phish" },
        { type: "done" },
      ]),
    );
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    await user.click(await screen.findByRole("button", { name: "환불 규정?" }));

    // 텍스트는 보이되 어떤 <a> 링크도 만들어지지 않는다(오픈리다이렉트·피싱 방지).
    expect(
      await screen.findByText("여기 보세요 https://evil.example.com/phish"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("한글 사이 슬래시는 홈 링크로 오링크화하지 않는다(리뷰 patch — \\w ASCII 한계)", async () => {
    mockStream.mockImplementation(
      fromEvents([
        { type: "delta", text: "예약/취소/환불 규정을 확인하세요" },
        { type: "done" },
      ]),
    );
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    await user.click(await screen.findByRole("button", { name: "환불 규정?" }));

    // 한글로 둘러싸인 슬래시는 평문 — 어떤 링크도 생성되지 않는다.
    expect(
      await screen.findByText("예약/취소/환불 규정을 확인하세요"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("외부 URL에 박힌 /rooms 경로는 내부 링크로 추출하지 않는다(리뷰 patch — 부분매칭 차단)", async () => {
    const roomId = "11111111-1111-1111-1111-111111111111";
    const text = `링크: https://evil.example.com/rooms/${roomId}`;
    mockStream.mockImplementation(
      fromEvents([{ type: "delta", text }, { type: "done" }]),
    );
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    await user.click(await screen.findByRole("button", { name: "환불 규정?" }));

    // 외부 URL 내부의 /rooms/{uuid} 부분은 내부 링크로 떼어내지 않는다(선행 경계).
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("더보기 단독 슬래시(/)는 홈 링크로 렌더한다(의도된 내부 경로)", async () => {
    mockStream.mockImplementation(
      fromEvents([
        { type: "delta", text: "더보기 (/) 에서 확인하세요" },
        { type: "done" },
      ]),
    );
    const user = userEvent.setup();
    renderFab();

    await user.click(screen.getByRole("button", { name: "룸메이트 챗봇 열기" }));
    await user.click(await screen.findByRole("button", { name: "환불 규정?" }));

    const link = await screen.findByRole("link", { name: "/" });
    expect(link).toHaveAttribute("href", "/");
  });

  it("닫기 버튼으로 패널을 닫는다(AC2 — open→closed 전이)", async () => {
    const user = userEvent.setup();
    renderFab();
    const fab = screen.getByRole("button", { name: "룸메이트 챗봇 열기" });

    await user.click(fab);
    await waitFor(() => expect(fab).toHaveAttribute("data-state", "open"));

    await user.click(screen.getByRole("button", { name: "챗봇 닫기" }));
    await waitFor(() => expect(fab).toHaveAttribute("data-state", "closed"));
  });
});
