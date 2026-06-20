import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { roomsGetRoom } from "@/lib/api-client";
import { RoomSheet } from "./RoomSheet";

// RoomSheet 컴포넌트 테스트 (Story 3.3 — AC1·AC2·AC3·AC4·AC5). roomsGetRoom SDK 를 모킹해
// 라이브 백엔드 없이 헤더/스켈레톤/1차·2차 콘텐츠/신선 배지/상세 Link/즐겨찾기/에러를 검증한다.
//
// ⚠️ vaul 물리 드래그 제스처(포인터 픽셀)는 jsdom 검증 밖(3.2 카카오 SDK 모킹 선례) —
//    열림·콘텐츠·a11y 라벨만 검증한다.
// FavoriteButton(3.7)이 RoomSheet 헤더에 실배선됨 → useSession(authMe)·useFavoriteIds 호출.
// 미로그인(authMe data undefined)으로 두면 즐겨찾기 조회는 비활성(enabled:false) — 외곽선 하트.
vi.mock("@/lib/api-client", () => ({
  roomsGetRoom: vi.fn(),
  authMe: vi.fn(() =>
    Promise.resolve({ data: undefined, response: new Response(null, { status: 401 }) }),
  ),
  favoritesListFavorites: vi.fn(() => Promise.resolve({ data: [] })),
  favoritesAddFavorite: vi.fn(() => Promise.resolve({ data: {} })),
  favoritesRemoveFavorite: vi.fn(() => Promise.resolve({ data: undefined })),
}));

const mockGet = vi.mocked(roomsGetRoom);

const SUMMARY = {
  room_id: "room-1",
  name: "강남 스터디룸",
  price_per_hour: 8000,
  capacity: 6,
  room_type: "open",
  amenities: ["wifi", "projector_tv"],
  // 요일 무관 안정성: todayBusinessHours 는 실제 오늘(KST) 요일 행을 고르므로, 어느 날 suite 를
  // 돌려도 "오늘 영업 09:00–22:00"이 뜨도록 7일 전체를 같은 시간으로 채운다(날짜 의존 플래키 제거).
  business_hours: Array.from({ length: 7 }, (_unused, weekday) => ({
    weekday,
    open_time: "09:00:00",
    close_time: "22:00:00",
  })),
  remaining_slots: 5,
  is_closed_today: false,
};

function resolveSummary(overrides: Partial<typeof SUMMARY> = {}) {
  mockGet.mockResolvedValue({ data: { ...SUMMARY, ...overrides } } as never);
}

function renderSheet(props: Partial<Parameters<typeof RoomSheet>[0]> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactNode = (
    <RoomSheet
      roomId="room-1"
      name="강남 스터디룸"
      open={true}
      onOpenChange={() => {}}
      {...props}
    />
  );
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RoomSheet 콘텐츠 (AC1·AC4)", () => {
  it("헤더 이름은 prop 으로 즉시 표시된다(신선 로딩 전 — 깜빡임 방지)", () => {
    mockGet.mockReturnValue(new Promise(() => {}) as never); // 펜딩 유지
    renderSheet();
    expect(screen.getByRole("dialog")).toHaveTextContent("강남 스터디룸");
  });

  it("로딩 중에는 1차/2차 자리 스켈레톤을 보여준다(AC5①)", () => {
    mockGet.mockReturnValue(new Promise(() => {}) as never);
    renderSheet();
    expect(screen.getByTestId("sheet-skeleton")).toBeInTheDocument();
  });

  it("로드 후 1차(가격·영업시간·배지) + 2차(부대시설·수용·형태)를 표시한다", async () => {
    resolveSummary();
    renderSheet();

    // 1차: 가격·영업시간.
    expect(await screen.findByText("8,000원")).toBeInTheDocument();
    expect(screen.getByText("09:00–22:00")).toBeInTheDocument();
    // 2차: 부대시설 라벨·수용·룸형태.
    expect(screen.getByText("와이파이")).toBeInTheDocument();
    expect(screen.getByText("빔프로젝터/TV")).toBeInTheDocument();
    expect(screen.getByText("최대 6인")).toBeInTheDocument();
    expect(screen.getByText("개방형")).toBeInTheDocument();
  });

  it("예약 가능 배지는 신선 remaining_slots 기준이다(fallback=available 이어도 신선=0 → 마감, 3.2 stale 회수)", async () => {
    resolveSummary({ remaining_slots: 0 }); // 신선 조회 결과 = 마감
    renderSheet({ fallbackStatus: "available" }); // 핀 스냅샷은 예약 가능이었음

    // 신선값(0)이 우선 → "마감" 으로 갱신된다.
    expect(await screen.findByText("오늘 마감")).toBeInTheDocument();
    expect(screen.queryByText("예약 가능")).not.toBeInTheDocument();
  });

  it("배지는 색 외 아이콘+텍스트를 동반한다(색 단독 금지 — AC4)", async () => {
    resolveSummary({ remaining_slots: 5 });
    renderSheet();
    const badge = await screen.findByText("예약 가능");
    expect(badge).toHaveTextContent("✓"); // 아이콘 글리프 동반
  });

  it("오늘 휴무면 영업시간 줄이 '오늘 휴무'다(배지-영업행 모순 방지 — code-review)", async () => {
    // 휴무라 서버가 is_closed_today=true·remaining_slots=0을 준다. 영업행은 그대로 있어도
    // "오늘 영업 09:00–22:00"이 아니라 "오늘 휴무"로 표시돼야 한다(배지 "마감"과 모순 방지).
    resolveSummary({ is_closed_today: true, remaining_slots: 0 });
    renderSheet();

    expect(await screen.findByText("오늘 휴무")).toBeInTheDocument();
    expect(screen.queryByText("09:00–22:00")).not.toBeInTheDocument();
    expect(screen.getByText("오늘 마감")).toBeInTheDocument();
  });
});

describe("RoomSheet 어포던스·이동 (AC2)", () => {
  it("상세 보기 Link 가 /rooms/{id} 로 향한다(스텁 라우트 — 4.2 채움)", async () => {
    resolveSummary();
    renderSheet({ roomId: "room-1" });
    const link = await screen.findByRole("link", { name: "상세 보기" });
    expect(link).toHaveAttribute("href", "/rooms/room-1");
  });

  it("즐겨찾기 하트가 헤더에 실배선된다(미로그인=외곽선 '추가' 라벨, 3.7)", () => {
    mockGet.mockReturnValue(new Promise(() => {}) as never);
    renderSheet();
    // 미로그인 기본 → aria-label "즐겨찾기 추가"(아직 즐겨찾기 안 됨).
    expect(
      screen.getByRole("button", { name: "즐겨찾기 추가" }),
    ).toBeInTheDocument();
  });
});

describe("RoomSheet 에러 (AC5)", () => {
  it("조회 실패 시 안내 + 다시 시도를 보여준다(막다른 화면 금지)", async () => {
    mockGet.mockRejectedValue(new Error("network"));
    renderSheet();
    expect(await screen.findByText("정보를 못 불러왔어요.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "다시 시도" }),
    ).toBeInTheDocument();
  });
});
