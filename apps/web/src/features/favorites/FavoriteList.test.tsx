import {
  onlineManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authMe, favoritesListFavorites } from "@/lib/api-client";
import { FavoriteList } from "./FavoriteList";

// FavoriteList 테스트 (Story 3.7 — AC2·AC3·AC4). 4상태 + 미로그인 게이팅 + 비활성 라벨·상세 차단.
vi.mock("@/lib/api-client", () => ({
  authMe: vi.fn(),
  favoritesListFavorites: vi.fn(),
  favoritesAddFavorite: vi.fn(() => Promise.resolve({ data: {} })),
  favoritesRemoveFavorite: vi.fn(() => Promise.resolve({ data: undefined })),
}));

const mockAuthMe = vi.mocked(authMe);
const mockList = vi.mocked(favoritesListFavorites);

// 목록 응답 봉투 헬퍼 — 커서 페이징(F) 전환으로 SDK 응답이 배열이 아니라 `{ items, next_cursor }` 봉투다.
function page(items: unknown[], nextCursor: string | null = null) {
  return { data: { items, next_cursor: nextCursor } };
}

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
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactNode = <FavoriteList />;
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const ACTIVE = {
  room_id: "a1",
  name: "강남룸",
  price_per_hour: 10000,
  room_type: "open",
  amenities: ["wifi"],
  remaining_slots: 3,
  is_active: true,
  favorited_at: "2026-06-16T00:00:00Z",
};
const INACTIVE = {
  room_id: "i1",
  name: "잠실룸",
  price_per_hour: 8000,
  room_type: "private",
  amenities: [],
  remaining_slots: 0,
  is_active: false,
  favorited_at: "2026-06-15T00:00:00Z",
};

// navigator.onLine 모킹(3.8 단절 — beforeEach 에서 기본 true 명시 복원).
function setOnLine(value: boolean): void {
  Object.defineProperty(navigator, "onLine", { configurable: true, value });
}

beforeEach(() => {
  vi.clearAllMocks();
  setOnLine(true);
  // TanStack onlineManager 전역 오프라인 누수 방지(매 테스트 온라인 리셋).
  onlineManager.setOnline(true);
});

describe("미로그인 게이팅 (AC4)", () => {
  it("로그인 유도 안내 + 로그인 링크(막다른 화면 금지)", async () => {
    loggedOut();
    renderList();

    expect(
      await screen.findByText("로그인하면 즐겨찾기를 모아볼 수 있어요."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "로그인" })).toBeInTheDocument();
  });

  it("세션 판별 실패(5xx) → 로그아웃 UI 아닌 오류/재시도(code-review)", async () => {
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
});

describe("4상태 (AC2)", () => {
  it("로딩 → Skeleton", async () => {
    loggedIn();
    mockList.mockReturnValue(new Promise(() => {}) as never); // 미해결
    renderList();
    expect(await screen.findByTestId("favorites-skeleton")).toBeInTheDocument();
  });

  it("에러 → 다시 시도(막다른 화면 금지)", async () => {
    loggedIn();
    mockList.mockRejectedValue(new Error("boom"));
    renderList();
    expect(await screen.findByText("즐겨찾기를 못 불러왔어요.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "다시 시도" }),
    ).toBeInTheDocument();
  });

  it("빈 → 즐겨찾기 유도 카피", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([]) as never);
    renderList();
    expect(
      await screen.findByText("마음에 든 곳을 즐겨찾기해두면 여기 모여요."),
    ).toBeInTheDocument();
  });
});

const NETWORK_NOTICE = "네트워크 연결이 끊겼어요. 연결되면 다시 보여드릴게요.";

describe("네트워크 단절 (Story 3.8 — 확정③)", () => {
  it("로그인 + 단절 + 캐시면 행 + NetworkNotice 를 표시한다", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([ACTIVE]) as never);
    renderList();
    // 온라인에서 캐시 적재.
    await screen.findByRole("link", { name: /강남룸/ });

    act(() => {
      setOnLine(false);
      window.dispatchEvent(new Event("offline"));
    });

    expect(await screen.findByText(NETWORK_NOTICE)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /강남룸/ })).toBeInTheDocument(); // 캐시 유지
  });

  it("미로그인 + 단절이면 로그인 유도가 유지된다(단절이 미로그인을 덮지 않음)", async () => {
    loggedOut();
    renderList();
    await screen.findByText("로그인하면 즐겨찾기를 모아볼 수 있어요.");

    act(() => {
      setOnLine(false);
      window.dispatchEvent(new Event("offline"));
    });

    // 단절 배너가 미로그인 안내를 덮지 않는다(축 분리 — 확정①). data===null(캐시된 401)은
    // 로그인 유도를 유지한다.
    expect(
      screen.getByText("로그인하면 즐겨찾기를 모아볼 수 있어요."),
    ).toBeInTheDocument();
    expect(screen.queryByText(NETWORK_NOTICE)).not.toBeInTheDocument();
  });

  it("세션 미확정(오프라인 콜드 진입)이면 로그인 유도 대신 NetworkNotice (로그인 사용자 오인 방지, code-review 2026-06-16)", async () => {
    // 오프라인 콜드 진입: onlineManager 오프라인으로 useSession 쿼리가 paused → user===undefined
    // (sessionLoading=false·sessionError=false). 로그인 여부 미확정이므로 로그인 유도가 아니라
    // 단절 배너를 보여야 한다(확정① 축 분리의 역방향 — undefined 만 단절 우선, null=캐시된 401은 제외).
    loggedIn(); // mock 은 설정하되 paused 라 실제 호출되지 않는다
    setOnLine(false);
    onlineManager.setOnline(false);
    renderList();

    expect(await screen.findByText(NETWORK_NOTICE)).toBeInTheDocument();
    expect(
      screen.queryByText("로그인하면 즐겨찾기를 모아볼 수 있어요."),
    ).not.toBeInTheDocument();
  });
});

describe("목록 + 비활성 라벨·상세 차단 (AC3)", () => {
  it("활성 행=상세 Link / 비활성 행='비활성' 라벨 + Link 미노출", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([ACTIVE, INACTIVE]) as never);
    renderList();

    // 활성 — 상세 링크 노출(/rooms/a1).
    const activeLink = await screen.findByRole("link", { name: /강남룸/ });
    expect(activeLink).toHaveAttribute("href", "/rooms/a1");

    // 비활성 — '비활성' 라벨 + 상세 링크 미노출(진입 차단).
    expect(screen.getByText("비활성")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /잠실룸/ })).toBeNull();
  });
});
