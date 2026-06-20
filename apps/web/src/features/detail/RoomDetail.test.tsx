import {
  onlineManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { loadKakaoMaps } from "@/lib/kakao-map";
import { roomsGetRoom, reviewsListRoomReviews } from "@/lib/api-client";
import { RoomDetail } from "./RoomDetail";

// RoomDetail 컴포넌트 테스트 (Story 4.2 — AC1·AC2·AC3·AC5). roomsGetRoom SDK 와 카카오 SDK 를
// 모킹해 라이브 백엔드/지도 없이 3단 위계·예약 전개·미니 지도·즐겨찾기·상태 분기를 검증한다.
//
// ⚠️ jsdom 한계: 실 지도 타일/물리 드래그는 검증 밖(3.2 카카오 SDK 모킹 선례) — loadKakaoMaps
//    호출·중심 좌표·에러 자리만 단언한다. FavoriteButton(3.7)이 헤더에 실배선되어 useSession
//    (authMe)·useFavoriteIds 를 호출하므로 미로그인(401)으로 둔다(외곽선 하트).
vi.mock("@/lib/kakao-map", () => ({ loadKakaoMaps: vi.fn() }));
vi.mock("@/lib/api-client", () => ({
  roomsGetRoom: vi.fn(),
  // 예약 전개(4.3/4.4) 시 ReservationPanel 이 useRoomSlots → roomsGetRoomSlots 를 호출하므로 모킹한다.
  // 4.4: available 슬롯 1칸을 줘 선택→요약(pricePerHour 전달) 흐름을 검증할 수 있게 한다.
  roomsGetRoomSlots: vi.fn(() =>
    Promise.resolve({
      data: {
        date: "2026-06-16",
        slots: [{ slot_start: "2026-06-16T05:00:00Z", status: "available" }], // 14:00 KST
        next_available_date: null,
      },
    }),
  ),
  authMe: vi.fn(() =>
    Promise.resolve({ data: undefined, response: new Response(null, { status: 401 }) }),
  ),
  favoritesListFavorites: vi.fn(() =>
    Promise.resolve({ data: { items: [], next_cursor: null } }),
  ),
  favoritesAddFavorite: vi.fn(() => Promise.resolve({ data: {} })),
  favoritesRemoveFavorite: vi.fn(() => Promise.resolve({ data: undefined })),
  // Story 5.5: 3차 후기 섹션이 useRoomReviews → reviewsListRoomReviews 를 호출하므로 모킹한다(기본 0건).
  // 커서 페이징(F) 전환으로 응답이 `{ items, next_cursor }` 봉투다.
  reviewsListRoomReviews: vi.fn(() =>
    Promise.resolve({ data: { items: [], next_cursor: null } }),
  ),
}));

const mockGet = vi.mocked(roomsGetRoom);
const mockLoad = vi.mocked(loadKakaoMaps);

// ── 카카오 SDK 가짜 — new Map 의 center(LatLng) 를 기록해 미니 지도 중심 좌표를 단언한다. ──
function installFakeKakao() {
  const mapCenters: Array<{ lat: number; lng: number }> = [];
  class LatLng {
    constructor(
      public lat: number,
      public lng: number,
    ) {}
  }
  class FakeMap {
    constructor(
      public container: HTMLElement,
      public options: { center: LatLng; level?: number },
    ) {
      mapCenters.push({ lat: options.center.lat, lng: options.center.lng });
    }
  }
  class CustomOverlay {
    private el: HTMLElement | null;
    private container: HTMLElement | null;
    constructor(opts: { content: HTMLElement; map?: FakeMap }) {
      this.el = opts.content;
      this.container = opts.map?.container ?? null;
      this.container?.appendChild(this.el);
    }
    setMap(map: FakeMap | null) {
      if (map === null && this.el) {
        this.el.remove();
        this.el = null;
      }
    }
  }
  const kakao = { maps: { load: (cb: () => void) => cb(), LatLng, Map: FakeMap, CustomOverlay } };
  mockLoad.mockImplementation(async () => {
    (window as unknown as { kakao: unknown }).kakao = kakao;
    return kakao as unknown as typeof globalThis.kakao;
  });
  return { mapCenters };
}

const SUMMARY = {
  room_id: "room-1",
  name: "강남 스터디룸",
  price_per_hour: 8000,
  capacity: 6,
  room_type: "open",
  amenities: ["wifi", "projector_tv"],
  // 요일 무관 안정성: 7일 전체 같은 시간으로 채워 어느 날 돌려도 "오늘 영업 09:00–22:00"이 뜨게 한다.
  business_hours: Array.from({ length: 7 }, (_unused, weekday) => ({
    weekday,
    open_time: "09:00:00",
    close_time: "22:00:00",
  })),
  remaining_slots: 5,
  is_closed_today: false,
  lat: 37.4979,
  lng: 127.0276,
};

function resolveSummary(overrides: Partial<typeof SUMMARY> = {}) {
  mockGet.mockResolvedValue({ data: { ...SUMMARY, ...overrides } } as never);
}

function renderDetail(roomId = "room-1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactNode = <RoomDetail roomId={roomId} />;
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function setOnLine(value: boolean): void {
  Object.defineProperty(navigator, "onLine", { configurable: true, value });
}

beforeEach(() => {
  vi.clearAllMocks();
  // clearAllMocks 는 구현(mockResolvedValue)을 지우지 않으므로, 후기 mock 을 매 테스트 기본 0건으로
  // 재설정한다(한 테스트의 override 가 다음 테스트로 새는 것 방지 — 후기 있음 테스트 누수 차단).
  vi.mocked(reviewsListRoomReviews).mockResolvedValue({
    data: { items: [], next_cursor: null },
  } as never);
  setOnLine(true);
  onlineManager.setOnline(true);
});

describe("RoomDetail 3단 정보 위계 (AC1)", () => {
  it("1차(가격·영업시간·배지)+2차(부대시설·수용·형태·미니 지도)+3차(후기 섹션)를 표시한다", async () => {
    installFakeKakao();
    resolveSummary();
    renderDetail();

    // 1차: 가격·오늘 영업시간·신선 배지.
    expect(await screen.findByText("8,000원")).toBeInTheDocument();
    expect(screen.getByText("09:00–22:00")).toBeInTheDocument();
    expect(screen.getByText("예약 가능")).toBeInTheDocument();
    // 2차: 부대시설 라벨·수용·룸형태·미니 지도 영역.
    expect(screen.getByText("와이파이")).toBeInTheDocument();
    expect(screen.getByText("빔프로젝터/TV")).toBeInTheDocument();
    expect(screen.getByText("최대 6인")).toBeInTheDocument();
    expect(screen.getByText("개방형")).toBeInTheDocument();
    expect(screen.getByTestId("location-map-container")).toBeInTheDocument();
    // 3차: 후기 섹션(Story 5.5 실배선 — 0건 빈 상태 카피).
    expect(
      await screen.findByText(/아직 후기가 없어요/),
    ).toBeInTheDocument();
  });

  it("후기가 있으면 3차 섹션에 별점·텍스트로 노출한다(Story 5.5 — AC4)", async () => {
    installFakeKakao();
    resolveSummary();
    const { reviewsListRoomReviews } = await import("@/lib/api-client");
    vi.mocked(reviewsListRoomReviews).mockResolvedValue({
      data: {
        items: [
          {
            id: "rev-1",
            rating: 5,
            text: "정말 조용해서 집중 잘 됐어요",
            created_at: "2026-06-17T00:00:00Z",
          },
        ],
        next_cursor: null,
      },
    } as never);
    renderDetail();

    expect(
      await screen.findByText("정말 조용해서 집중 잘 됐어요"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("별점 5점 만점에 5점")).toBeInTheDocument();
  });

  it("예약 가능 배지는 색 외 아이콘+텍스트를 동반한다(색 단독 금지 — AC1)", async () => {
    installFakeKakao();
    resolveSummary({ remaining_slots: 5 });
    renderDetail();

    const badge = await screen.findByText("예약 가능");
    expect(badge).toHaveTextContent("✓");
  });

  it("배지는 신선 remaining_slots 기준이다(0 → 마감)", async () => {
    installFakeKakao();
    resolveSummary({ remaining_slots: 0 });
    renderDetail();

    expect(await screen.findByText("오늘 마감")).toBeInTheDocument();
    expect(screen.queryByText("예약 가능")).not.toBeInTheDocument();
  });

  it("오늘 휴무면 영업시간 줄이 '오늘 휴무'다(배지-영업행 모순 방지)", async () => {
    installFakeKakao();
    resolveSummary({ is_closed_today: true, remaining_slots: 0 });
    renderDetail();

    expect(await screen.findByText("오늘 휴무")).toBeInTheDocument();
    expect(screen.queryByText("09:00–22:00")).not.toBeInTheDocument();
    expect(screen.getByText("오늘 마감")).toBeInTheDocument();
  });

  it("즐겨찾기 하트가 헤더에 실배선된다(미로그인=외곽선 '추가' 라벨, 3.7)", async () => {
    installFakeKakao();
    resolveSummary();
    renderDetail();

    expect(
      await screen.findByRole("button", { name: "즐겨찾기 추가" }),
    ).toBeInTheDocument();
  });
});

describe("RoomDetail 위치 미니 지도 (AC3)", () => {
  it("loadKakaoMaps 를 호출하고 룸 좌표를 중심으로 지도를 만든다", async () => {
    const { mapCenters } = installFakeKakao();
    resolveSummary();
    renderDetail();

    await screen.findByText("8,000원");
    await waitFor(() => expect(mockLoad).toHaveBeenCalled());
    await waitFor(() =>
      expect(mapCenters).toContainEqual({ lat: 37.4979, lng: 127.0276 }),
    );
  });

  it("지도 SDK 로드 실패 시 지도 영역만 graceful degrade 되고 상세 전체는 막히지 않는다(AC3)", async () => {
    mockLoad.mockRejectedValue(new Error("SDK 로드 실패"));
    resolveSummary();
    renderDetail();

    // 지도 영역만 에러 자리로 대체된다.
    expect(await screen.findByText("지도를 못 불러왔어요.")).toBeInTheDocument();
    // 나머지 정보(가격·후기)는 정상 표시 — 전체 화면이 막히지 않는다.
    expect(screen.getByText("8,000원")).toBeInTheDocument();
    expect(await screen.findByText(/아직 후기가 없어요/)).toBeInTheDocument();
  });
});

describe("RoomDetail 같은 페이지 예약 전개 (AC2)", () => {
  it("'예약 가능 시간 보기'를 누르면 같은 페이지에서 예약 패널(달력+슬롯)이 전개된다(페이지 이동 없음, 4.3)", async () => {
    installFakeKakao();
    resolveSummary();
    renderDetail();

    const button = await screen.findByRole("button", { name: "예약 가능 시간 보기" });
    // 전개 전: 예약 패널(달력) 없음.
    expect(screen.queryByText("날짜 선택")).not.toBeInTheDocument();
    expect(button).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(button);

    // 전개 후: 4.3 패널 내용물(달력 "날짜 선택" + "시간 선택")이 placeholder 를 치환한다.
    expect(screen.getByText("날짜 선택")).toBeInTheDocument();
    expect(screen.getByText("시간 선택")).toBeInTheDocument();
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("pricePerHour 가 패널로 전달돼 선택 요약 금액에 반영된다(4.4 — price_per_hour 모킹값)", async () => {
    installFakeKakao();
    resolveSummary({ price_per_hour: 8000 });
    renderDetail();

    fireEvent.click(await screen.findByRole("button", { name: "예약 가능 시간 보기" }));
    // 슬롯(14:00) 선택 → 요약에 1시간 × 8,000원 금액이 뜬다(pricePerHour 가 전달됐다는 증거).
    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    expect(await screen.findByText(/1시간 · 8,000원/)).toBeInTheDocument();
  });
});

describe("RoomDetail 상태 분기 (AC5)", () => {
  it("정보 로드 실패(일반) → '정보를 못 불러왔어요' + 다시 시도(막다른 화면 금지)", async () => {
    mockGet.mockRejectedValue(new Error("network"));
    renderDetail();

    expect(await screen.findByText("정보를 못 불러왔어요.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "찾기로 돌아가기" })).toBeInTheDocument();
  });

  it("404(ROOM_NOT_FOUND) → '그 방은 더 이상 없어요'(일반 실패와 구분)", async () => {
    // 생성 SDK 가 throwOnError 시 던지는 에러 본문 형태({detail:{code}}) 그대로 reject.
    mockGet.mockRejectedValue({ detail: { code: "ROOM_NOT_FOUND", message: "없음" } });
    renderDetail();

    expect(await screen.findByText("그 방은 더 이상 없어요")).toBeInTheDocument();
    expect(screen.queryByText("정보를 못 불러왔어요.")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "찾기로 돌아가기" })).toBeInTheDocument();
  });

  it("네트워크 단절 → NetworkNotice 표시·에러 미표시(단절을 에러로 오인 금지)", async () => {
    setOnLine(false);
    onlineManager.setOnline(false);
    // 단절 중에는 조회가 멈춰도(또는 실패해도) 에러로 덮지 않는다 — showError 게이팅.
    mockGet.mockRejectedValue(new Error("network"));
    renderDetail();

    expect(
      await screen.findByText("네트워크 연결이 끊겼어요. 연결되면 다시 보여드릴게요."),
    ).toBeInTheDocument();
    expect(screen.queryByText("정보를 못 불러왔어요.")).not.toBeInTheDocument();
  });
});
