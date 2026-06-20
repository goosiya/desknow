import {
  onlineManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  authMe,
  reservationsCancelReservation,
  reservationsListReservations,
} from "@/lib/api-client";
import { ReservationList } from "./ReservationList";

// ReservationList 테스트 (Story 4.8 — AC1·AC2·AC3). 상태 매트릭스 + 다가오는/지난 + 취소 버튼.
vi.mock("@/lib/api-client", () => ({
  authMe: vi.fn(),
  reservationsListReservations: vi.fn(),
  reservationsCancelReservation: vi.fn(() => Promise.resolve({ data: {} })),
  // Story 5.5: 이용 완료 행이 ReviewForm(useCreateReview)을 렌더하므로 대역 제공(제출 안 하면 미호출).
  reviewsCreateReview: vi.fn(() => Promise.resolve({ data: {} })),
  reviewsListRoomReviews: vi.fn(),
}));

// 공유 SDK 로더 모킹 — 행 렌더 시 실제 `<script>` 주입 금지(공유 동작은 KakaoShareButton.test 검증).
vi.mock("@/lib/kakao-share", () => ({ shareReservation: vi.fn() }));

const mockAuthMe = vi.mocked(authMe);
const mockList = vi.mocked(reservationsListReservations);
const mockCancel = vi.mocked(reservationsCancelReservation);

// 목록 응답 봉투 헬퍼 — 커서 페이징(F) 전환으로 SDK 응답이 배열이 아니라 `{ items, next_cursor }` 봉투다.
function page(items: unknown[], nextCursor: string | null = null) {
  return { data: { items, next_cursor: nextCursor } };
}

// now 결정성 — Date 만 fake(setTimeout 은 실제라 waitFor/act 정상). KST 2026-06-20 09:00.
const FIXED_NOW = new Date("2026-06-20T00:00:00Z");

function loggedIn() {
  mockAuthMe.mockResolvedValue({
    data: { id: "u1", role: "booker" },
    response: new Response(null, { status: 200 }),
  } as never);
}
function loggedOut() {
  mockAuthMe.mockResolvedValue({
    data: undefined,
    response: new Response(null, { status: 401 }),
  } as never);
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const ui: ReactNode = <ReservationList />;
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function setOnLine(value: boolean): void {
  Object.defineProperty(navigator, "onLine", { configurable: true, value });
}

// 예약 항목 빌더 — FIXED_NOW(2026-06-20T00:00:00Z) 기준 상대 시각.
function reservation(overrides: Record<string, unknown>) {
  return {
    id: "r1",
    room_id: "room-1",
    room_name: "강남룸",
    status: "confirmed",
    slot_starts: ["2026-06-20T10:00:00Z"], // now+10h = 다가오는·취소 가능(>6h)
    created_at: "2026-06-17T00:00:00Z",
    is_active: true,
    has_review: false, // Story 5.5 — 기본 미작성(이용 완료 행이면 작성 폼 노출)
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(FIXED_NOW);
  setOnLine(true);
  onlineManager.setOnline(true);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("상태 매트릭스 (AC3)", () => {
  it("미로그인 → 로그인 유도 + 링크", async () => {
    loggedOut();
    renderList();
    expect(
      await screen.findByText("로그인하면 예약 내역을 볼 수 있어요."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "로그인" })).toBeInTheDocument();
  });

  it("세션 판별 실패(5xx) → 오류/재시도(로그아웃 오인 금지)", async () => {
    mockAuthMe.mockResolvedValue({
      data: undefined,
      response: new Response(null, { status: 500 }),
    } as never);
    renderList();
    expect(
      await screen.findByText("로그인 상태를 확인하지 못했어요."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
  });

  it("로딩 → Skeleton", async () => {
    loggedIn();
    mockList.mockReturnValue(new Promise(() => {}) as never);
    renderList();
    expect(await screen.findByTestId("reservations-skeleton")).toBeInTheDocument();
  });

  it("에러 → 다시 시도", async () => {
    loggedIn();
    mockList.mockRejectedValue(new Error("boom"));
    renderList();
    expect(await screen.findByText("예약 내역을 못 불러왔어요.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
  });

  it("빈 → 찾기 유도", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([]) as never);
    renderList();
    expect(await screen.findByText("마음에 드는 곳을 찾아볼까요?")).toBeInTheDocument();
  });
});

const NETWORK_NOTICE = "네트워크 연결이 끊겼어요. 연결되면 다시 보여드릴게요.";

describe("네트워크 단절 (AC3 — 확정③)", () => {
  it("로그인 + 단절 + 캐시면 행 + NetworkNotice", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([reservation({})]) as never);
    renderList();
    await screen.findByRole("link", { name: /강남룸/ });

    act(() => {
      setOnLine(false);
      window.dispatchEvent(new Event("offline"));
    });

    expect(await screen.findByText(NETWORK_NOTICE)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /강남룸/ })).toBeInTheDocument();
  });
});

describe("다가오는/지난 분리 + 상태 배지 (AC1)", () => {
  it("다가오는·지난 섹션을 구분 표시한다", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([
        reservation({ id: "up", room_name: "다가오는룸" }),
        reservation({
          id: "done",
          room_name: "지난룸",
          slot_starts: ["2026-06-19T00:00:00Z"], // 과거 → 이용 완료
        }),
        reservation({
          id: "cx",
          room_name: "취소룸",
          status: "cancelled",
          slot_starts: ["2026-06-21T00:00:00Z"],
        }),
      ]) as never);
    renderList();

    expect(await screen.findByText("다가오는 예약")).toBeInTheDocument();
    expect(screen.getByText("지난 예약")).toBeInTheDocument();
    expect(screen.getByText("확정")).toBeInTheDocument();
    expect(screen.getByText("이용 완료")).toBeInTheDocument();
    expect(screen.getByText("취소됨")).toBeInTheDocument();
  });

  it("취소/거절 예약은 스냅샷 시간을 표시한다(히스토리)", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([
        reservation({
          id: "cx",
          status: "cancelled",
          slot_starts: ["2026-06-21T05:00:00Z"], // KST 14:00
        }),
      ]) as never);
    renderList();
    // 취소돼도 날짜·시간 표시(슬롯 행 DELETE됐어도 스냅샷 잔존).
    expect(await screen.findByText(/6월 21일/)).toBeInTheDocument();
    expect(screen.getByText(/14:00–15:00/)).toBeInTheDocument();
  });
});

describe("취소 버튼 (AC2)", () => {
  it("6h 이상 남은 confirmed → 취소 버튼 활성, 클릭 시 취소 호출", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([reservation({})]) as never); // now+10h
    renderList();

    const button = await screen.findByRole("button", { name: "취소" });
    expect(button).toBeEnabled();

    fireEvent.click(button);
    await waitFor(() =>
      expect(mockCancel).toHaveBeenCalledWith(
        expect.objectContaining({
          path: { room_id: "room-1", reservation_id: "r1" },
          throwOnError: true,
        }),
      ),
    );
  });

  it("6h 미만 남은 confirmed → 취소 버튼 비활성 + 안내", async () => {
    loggedIn();
    mockList.mockResolvedValue(
      page([reservation({ slot_starts: ["2026-06-20T03:00:00Z"] })]) as never, // now+3h <6h
    );
    renderList();

    const button = await screen.findByRole("button", { name: "취소" });
    expect(button).toBeDisabled();
    expect(
      screen.getByText("이제 6시간이 안 남아서 취소가 어려워요."),
    ).toBeInTheDocument();
  });

  it("취소/거절/이용 완료엔 취소 버튼을 노출하지 않는다", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([
        reservation({ id: "cx", status: "cancelled" }),
        reservation({
          id: "done",
          slot_starts: ["2026-06-19T00:00:00Z"], // 과거 confirmed = 이용 완료
        }),
      ]) as never);
    renderList();

    await screen.findByText("지난 예약");
    expect(screen.queryByRole("button", { name: "취소" })).toBeNull();
  });
});

describe("카카오 공유 버튼 (Story 5.4 — AC3)", () => {
  it("다가오는 확정 예약에만 공유 버튼을 노출한다(이용 완료엔 미노출 — KTH 2026-06-18)", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([
        reservation({ id: "up", room_name: "다가오는룸" }), // 다가오는 confirmed
        reservation({
          id: "done",
          room_name: "지난룸",
          slot_starts: ["2026-06-19T00:00:00Z"], // 과거 confirmed = 이용 완료
        }),
      ]) as never);
    renderList();

    await screen.findByText("지난 예약");
    // 다가오는 확정만 공유 노출 — 이미 종료된 '이용 완료'는 공유가 무의미해 제외(과거 슬롯 공유 방지).
    const shareButtons = screen.getAllByRole("button", { name: "카카오톡으로 공유" });
    expect(shareButtons).toHaveLength(1);
    // 남은 1개는 '다가오는룸' 행에 속한다(지난룸 행엔 공유 미노출).
    const pastRow = screen.getByText("지난룸").closest("li");
    expect(pastRow).not.toBeNull();
    expect(
      pastRow!.querySelector('button[aria-label="카카오톡으로 공유"]') ??
        // 라벨이 텍스트로 들어가는 경우 대비 — 행 내 공유 버튼 부재 확인.
        [...pastRow!.querySelectorAll("button")].find((b) =>
          b.textContent?.includes("공유"),
        ),
    ).toBeFalsy();
  });

  it("취소/거절 예약엔 공유 버튼을 노출하지 않는다(확정만 — AC3)", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([
        reservation({ id: "cx", status: "cancelled" }),
        reservation({ id: "rj", status: "rejected" }),
      ]) as never);
    renderList();

    await screen.findByText("지난 예약");
    expect(screen.queryByRole("button", { name: "카카오톡으로 공유" })).toBeNull();
  });

  it("비활성 룸 확정 예약엔 공유 버튼을 노출하지 않는다(죽은 링크 방지 — 코드리뷰 P3)", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([reservation({ room_name: "비활성룸", is_active: false })]) as never);
    renderList();

    // 상세 Link 가 차단되는 비활성 룸은 공유로 수신자 404 링크를 내보내지 않는다(행 차단과 정합).
    expect(await screen.findByText("비활성룸")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "카카오톡으로 공유" })).toBeNull();
  });
});

describe("후기 작성 게이팅 (Story 5.5 — AC5)", () => {
  it("이용 완료 + 미작성 → 후기 작성 폼(별점·후기 버튼) 노출", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([
        reservation({
          id: "done",
          slot_starts: ["2026-06-19T00:00:00Z"], // 과거 confirmed = 이용 완료
          has_review: false,
        }),
      ]) as never);
    renderList();

    await screen.findByText("지난 예약");
    expect(screen.getByRole("radio", { name: "별점 5점" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "후기 남기기" })).toBeInTheDocument();
  });

  it("이용 완료 + 작성됨 → 내 후기(별점·내용)+사장님 답글 표시·작성 폼 미노출", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([
        reservation({
          id: "done",
          slot_starts: ["2026-06-19T00:00:00Z"],
          has_review: true,
          review: {
            id: "rv1",
            rating: 5,
            text: "조용하고 좋았어요",
            created_at: "2026-06-19T01:00:00Z",
            reply: { text: "감사합니다!", created_at: "2026-06-19T02:00:00Z" },
          },
        }),
      ]) as never);
    renderList();

    await screen.findByText("지난 예약");
    // 내 후기 내용(별점 + 텍스트) 노출 — "후기 완료" 텍스트만 보이던 것을 실제 내용으로.
    expect(screen.getByText("내 후기")).toBeInTheDocument();
    expect(screen.getByLabelText("별점 5점 만점에 5점")).toBeInTheDocument();
    expect(screen.getByText("조용하고 좋았어요")).toBeInTheDocument();
    // 사장님 답글도 함께 노출.
    expect(screen.getByText("사장님 답글")).toBeInTheDocument();
    expect(screen.getByText("감사합니다!")).toBeInTheDocument();
    // 작성 폼은 미노출(이미 작성됨 — 죽은 버튼 0).
    expect(screen.queryByRole("button", { name: "후기 남기기" })).toBeNull();
  });

  it("다가오는 확정 예약엔 후기 폼을 노출하지 않는다(이용 완료 전)", async () => {
    loggedIn();
    mockList.mockResolvedValue(
      page([reservation({ id: "up", has_review: false })]) as never, // now+10h = 다가오는
    );
    renderList();

    await screen.findByText("다가오는 예약");
    expect(screen.queryByRole("button", { name: "후기 남기기" })).toBeNull();
  });

  it("취소/거절 예약엔 후기 폼을 노출하지 않는다", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([
        reservation({ id: "cx", status: "cancelled", slot_starts: ["2026-06-19T00:00:00Z"] }),
        reservation({ id: "rj", status: "rejected", slot_starts: ["2026-06-19T00:00:00Z"] }),
      ]) as never);
    renderList();

    await screen.findByText("지난 예약");
    expect(screen.queryByRole("button", { name: "후기 남기기" })).toBeNull();
  });
});

describe("비활성 룸 상세 차단 (AC1)", () => {
  it("비활성 룸 예약은 상세 Link 미노출(이름은 표시)", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([reservation({ room_name: "비활성룸", is_active: false })]) as never);
    renderList();

    expect(await screen.findByText("비활성룸")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /비활성룸/ })).toBeNull();
  });
});

describe("무한스크롤 (F — 커서 페이징)", () => {
  it("첫 페이지에 next_cursor 가 있으면 '더 보기'가 보이고, 클릭 시 둘째 페이지가 이어 렌더되며 마지막 페이지에서 sentinel 이 사라진다", async () => {
    loggedIn();
    // 페이지1(next_cursor 있음) → 페이지2(next_cursor=null=마지막)를 순차 반환.
    mockList
      .mockResolvedValueOnce(
        page([reservation({ id: "r1", room_name: "1페이지룸" })], "cursor-2") as never,
      )
      .mockResolvedValueOnce(
        page([reservation({ id: "r2", room_name: "2페이지룸" })], null) as never,
      );
    renderList();

    // 페이지1 항목 + '더 보기' sentinel 노출.
    expect(await screen.findByText("1페이지룸")).toBeInTheDocument();
    const more = await screen.findByRole("button", { name: "더 보기" });

    // '더 보기' 클릭 → 페이지2 로드(두 페이지 항목 모두 렌더).
    fireEvent.click(more);
    expect(await screen.findByText("2페이지룸")).toBeInTheDocument();
    expect(screen.getByText("1페이지룸")).toBeInTheDocument();

    // 마지막 페이지(next_cursor=null) 도달 → sentinel 사라짐(더 없음).
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "더 보기" })).toBeNull(),
    );
    expect(mockList).toHaveBeenCalledTimes(2);
  });
});
