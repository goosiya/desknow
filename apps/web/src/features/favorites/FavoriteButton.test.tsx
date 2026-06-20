import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  authMe,
  favoritesAddFavorite,
  favoritesListFavorites,
} from "@/lib/api-client";
import { FavoriteButton } from "./FavoriteButton";

// FavoriteButton 테스트 (Story 3.7 — AC1·AC4). 미로그인 게이팅·활성/비활성 렌더·옵티미스틱·롤백.
vi.mock("@/lib/api-client", () => ({
  authMe: vi.fn(),
  favoritesListFavorites: vi.fn(() =>
    Promise.resolve({ data: { items: [], next_cursor: null } }),
  ),
  favoritesAddFavorite: vi.fn(() => Promise.resolve({ data: {} })),
  favoritesRemoveFavorite: vi.fn(() => Promise.resolve({ data: undefined })),
}));

const mockAuthMe = vi.mocked(authMe);
const mockList = vi.mocked(favoritesListFavorites);
const mockAdd = vi.mocked(favoritesAddFavorite);

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

function renderButton(roomId = "r1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactNode = <FavoriteButton roomId={roomId} />;
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  loggedOut();
  mockList.mockResolvedValue(page([]) as never);
});

describe("미로그인 게이팅 (AC4)", () => {
  it("클릭 시 토글하지 않고 '로그인하면 저장돼요' 안내를 노출한다", async () => {
    loggedOut();
    renderButton();

    const button = await screen.findByRole("button", { name: "즐겨찾기 추가" });
    await userEvent.click(button);

    expect(screen.getByText("로그인하면 저장돼요.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "로그인" })).toBeInTheDocument();
    expect(mockAdd).not.toHaveBeenCalled(); // 토글(옵티미스틱 호출) 안 함
  });
});

describe("렌더 상태 (AC1 — 채움+색+aria 3중)", () => {
  it("미즐겨찾기 → 외곽선 하트 + aria-pressed=false + '추가' 라벨", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([]) as never);
    renderButton("r1");

    const button = await screen.findByRole("button", { name: "즐겨찾기 추가" });
    expect(button).toHaveAttribute("aria-pressed", "false");
  });

  it("즐겨찾기됨 → 채운 하트 + aria-pressed=true + '해제' 라벨", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([{ room_id: "r1" }]) as never);
    renderButton("r1");

    const button = await screen.findByRole("button", { name: "즐겨찾기 해제" });
    expect(button).toHaveAttribute("aria-pressed", "true");
  });
});

describe("옵티미스틱 토글 (AC1)", () => {
  it("추가 클릭 → 즉시 aria-pressed=true(옵티미스틱) + add 호출", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([]) as never);
    mockAdd.mockReturnValue(new Promise(() => {}) as never); // 미해결 — 옵티미스틱 고정
    renderButton("r1");

    const button = await screen.findByRole("button", { name: "즐겨찾기 추가" });
    await userEvent.click(button);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "즐겨찾기 해제" }),
      ).toHaveAttribute("aria-pressed", "true"),
    );
    expect(mockAdd).toHaveBeenCalledWith({
      body: { room_id: "r1" },
      throwOnError: true,
    });
  });

  it("서버 실패 → 롤백(다시 '추가' 상태)", async () => {
    loggedIn();
    mockList.mockResolvedValue(page([]) as never);
    mockAdd.mockRejectedValue(new Error("server down"));
    renderButton("r1");

    const button = await screen.findByRole("button", { name: "즐겨찾기 추가" });
    await userEvent.click(button);

    // 옵티미스틱 후 실패 → 롤백되어 '추가'(미즐겨찾기)로 복귀.
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "즐겨찾기 추가" }),
      ).toHaveAttribute("aria-pressed", "false"),
    );
    expect(mockAdd).toHaveBeenCalled();
  });
});
