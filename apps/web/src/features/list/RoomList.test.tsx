import {
  onlineManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { roomsSearchRooms } from "@/lib/api-client";
import { RoomList } from "./RoomList";
import type { RoomSearch } from "./useRoomSearch";

// RoomList 컴포넌트 테스트 (Story 3.4 지역 + 3.5 반경 — AC1·AC2·AC5). roomsSearchRooms SDK 를
// 모킹해 미활성 프롬프트/로딩/에러/빈/성공 행·행 탭을 검증한다. 검색 디스크립터(region/radius)별로
// 조회 파라미터·빈 카피가 분기되는지 단언한다(3.4 region 동작은 회귀 보존).
// FavoriteButton(3.7)이 RoomListRow에 실배선됨 → useSession(authMe)·useFavoriteIds 호출.
// 미로그인으로 두면 즐겨찾기 조회 비활성 — 외곽선 하트("즐겨찾기 추가" 라벨).
vi.mock("@/lib/api-client", () => ({
  roomsSearchRooms: vi.fn(),
  authMe: vi.fn(() =>
    Promise.resolve({ data: undefined, response: new Response(null, { status: 401 }) }),
  ),
  favoritesListFavorites: vi.fn(() =>
    Promise.resolve({ data: { items: [], next_cursor: null } }),
  ),
  favoritesAddFavorite: vi.fn(() => Promise.resolve({ data: {} })),
  favoritesRemoveFavorite: vi.fn(() => Promise.resolve({ data: undefined })),
}));

const mockSearch = vi.mocked(roomsSearchRooms);

const ROOM = {
  room_id: "room-1",
  name: "강남 스터디룸",
  price_per_hour: 8000,
  room_type: "open",
  amenities: ["wifi", "projector_tv"],
  remaining_slots: 5,
};

const REGION_SEARCH: RoomSearch = { kind: "region", regionCode: "1168000000" };
const RADIUS_SEARCH: RoomSearch = {
  kind: "radius",
  center: { lat: 37.5665, lng: 126.978 },
  radiusKm: 3,
};

function resolveRooms(rooms: unknown[]) {
  // 커서 페이징(F) 전환으로 SDK 응답이 배열이 아니라 `{ items, next_cursor }` 봉투다.
  mockSearch.mockResolvedValue({ data: { items: rooms, next_cursor: null } } as never);
}

function renderList(
  props: Partial<Parameters<typeof RoomList>[0]> = {},
): { onSelectRoom: ReturnType<typeof vi.fn> } {
  const onSelectRoom = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactNode = (
    <RoomList search={REGION_SEARCH} onSelectRoom={onSelectRoom} {...props} />
  );
  render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
  return { onSelectRoom };
}

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

describe("RoomList 상태 — 지역 (AC5, 3.4 회귀)", () => {
  it("지역 미선택이면 동네 선택 프롬프트를 보여주고 조회하지 않는다", () => {
    renderList({ search: { kind: "region", regionCode: undefined } });
    expect(
      screen.getByText("동네를 골라 주변 스터디룸을 찾아보세요."),
    ).toBeInTheDocument();
    expect(mockSearch).not.toHaveBeenCalled(); // enabled:!!regionCode
  });

  it("로딩이 지연되면 Skeleton 행을 보여준다(AC5① — 지연 표시)", async () => {
    mockSearch.mockReturnValue(new Promise(() => {}) as never); // 펜딩(영구 로딩)
    renderList();
    // 스켈레톤은 **지연 표시**라 즉시 뜨지 않는다(빠른 로딩 깜빡임 억제). 지연 후 등장을 findBy 로 대기.
    expect(screen.queryByTestId("list-skeleton")).toBeNull();
    expect(await screen.findByTestId("list-skeleton")).toBeInTheDocument();
  });

  it("조회 실패 시 안내 + 다시 시도를 보여준다(막다른 화면 금지 — AC5③)", async () => {
    mockSearch.mockRejectedValue(new Error("network"));
    renderList();
    expect(await screen.findByText("목록을 못 불러왔어요.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "다시 시도" }),
    ).toBeInTheDocument();
  });

  it("빈 결과면 '이 지역엔 등록된 곳이 없어요.' + 제안을 보여준다", async () => {
    resolveRooms([]);
    renderList();
    expect(
      await screen.findByText("이 지역엔 등록된 곳이 없어요."),
    ).toBeInTheDocument();
    expect(screen.getByText(/다른 동네를 골라보거나/)).toBeInTheDocument();
  });

  it("region 검색은 region_code 쿼리로 조회한다", async () => {
    resolveRooms([ROOM]);
    renderList();
    await screen.findByText("강남 스터디룸");
    expect(mockSearch).toHaveBeenCalledWith(
      expect.objectContaining({ query: { region_code: "1168000000" } }),
    );
  });
});

describe("RoomList 상태 — 반경 (Story 3.5 AC1·AC5)", () => {
  it("중심 좌표가 없으면 위치 확인 중 안내(조회 안 함)", () => {
    renderList({
      search: { kind: "radius", center: undefined, radiusKm: 3 },
    });
    expect(screen.getByText("현위치를 확인하고 있어요…")).toBeInTheDocument();
    expect(mockSearch).not.toHaveBeenCalled(); // enabled:!!center
  });

  it("radius 검색은 lat/lng/radius_km 쿼리로 조회한다(AC1)", async () => {
    resolveRooms([ROOM]);
    renderList({ search: RADIUS_SEARCH });
    await screen.findByText("강남 스터디룸");
    expect(mockSearch).toHaveBeenCalledWith(
      expect.objectContaining({
        query: { lat: 37.5665, lng: 126.978, radius_km: 3 },
      }),
    );
  });

  it("radius 빈 결과면 '이 근처엔 아직 없어요.' + 반경/지역 제안(AC5②)", async () => {
    resolveRooms([]);
    renderList({ search: RADIUS_SEARCH });
    expect(
      await screen.findByText("이 근처엔 아직 없어요."),
    ).toBeInTheDocument();
    expect(screen.getByText(/반경을 넓히거나/)).toBeInTheDocument();
  });

  it("radius 조회 실패 시 다시 시도를 보여준다(막다른 화면 금지)", async () => {
    mockSearch.mockRejectedValue(new Error("network"));
    renderList({ search: RADIUS_SEARCH });
    expect(await screen.findByText("목록을 못 불러왔어요.")).toBeInTheDocument();
  });
});

describe("RoomList 행 콘텐츠 (AC1 — 검색방식 무관 동일)", () => {
  it("행에 이름·가격·예약 배지·부대시설·룸형태를 보여준다", async () => {
    resolveRooms([ROOM]);
    renderList();

    expect(await screen.findByText("강남 스터디룸")).toBeInTheDocument();
    expect(screen.getByText("8,000원")).toBeInTheDocument();
    expect(screen.getByText("개방형")).toBeInTheDocument(); // 룸형태 라벨
    expect(screen.getByText("와이파이")).toBeInTheDocument(); // 부대시설 라벨
    expect(screen.getByText("빔프로젝터/TV")).toBeInTheDocument();
  });

  it("예약 가능 배지는 색 외 아이콘+텍스트를 동반한다(색 단독 금지)", async () => {
    resolveRooms([ROOM]); // remaining_slots=5 → 예약 가능
    renderList();
    const badge = await screen.findByText("예약 가능");
    expect(badge).toHaveTextContent("✓"); // 아이콘 글리프 동반
  });

  it("배지는 신선 remaining_slots 기준이다(0 → 마감)", async () => {
    resolveRooms([{ ...ROOM, remaining_slots: 0 }]);
    renderList();
    expect(await screen.findByText("오늘 마감")).toBeInTheDocument();
    expect(screen.queryByText("예약 가능")).not.toBeInTheDocument();
  });

  it("행 탭 → onSelectRoom 이 그 룸으로 호출된다(부모가 RoomSheet 오픈)", async () => {
    resolveRooms([ROOM]);
    const { onSelectRoom } = renderList();
    const row = await screen.findByRole("button", { name: /강남 스터디룸/ });
    await userEvent.click(row);
    expect(onSelectRoom).toHaveBeenCalledWith(
      expect.objectContaining({ room_id: "room-1" }),
    );
  });

  it("즐겨찾기 하트가 행에 실배선된다(미로그인=외곽선 '추가' 라벨, 3.7)", async () => {
    resolveRooms([ROOM]);
    renderList();
    expect(
      await screen.findByRole("button", { name: "즐겨찾기 추가" }),
    ).toBeInTheDocument();
  });
});

const NETWORK_NOTICE = "네트워크 연결이 끊겼어요. 연결되면 다시 보여드릴게요.";

describe("RoomList 네트워크 단절 (Story 3.8 — AC2)", () => {
  it("단절 시 캐시된 목록을 그대로 두고 NetworkNotice 를 얹는다", async () => {
    resolveRooms([ROOM]);
    renderList();
    // 온라인에서 캐시 적재.
    await screen.findByText("강남 스터디룸");

    act(() => {
      setOnLine(false);
      window.dispatchEvent(new Event("offline"));
    });

    expect(await screen.findByText(NETWORK_NOTICE)).toBeInTheDocument();
    expect(screen.getByText("강남 스터디룸")).toBeInTheDocument(); // 캐시 유지
  });

  it("단절이면 조회 실패 에러 카드 대신 단절을 우선 표시한다", async () => {
    mockSearch.mockRejectedValue(new Error("network"));
    renderList();
    // 온라인 에러 카드 등장.
    await screen.findByText("목록을 못 불러왔어요.");

    act(() => {
      setOnLine(false);
      window.dispatchEvent(new Event("offline"));
    });

    expect(await screen.findByText(NETWORK_NOTICE)).toBeInTheDocument();
    expect(screen.queryByText("목록을 못 불러왔어요.")).not.toBeInTheDocument();
  });
});

// 다음 페이지 항목(이름만 다른 룸) — 무한스크롤 통합용.
const ROOM2 = { ...ROOM, room_id: "room-2", name: "역삼 스터디룸" };

describe("RoomList 무한스크롤 (F — 커서 페이징)", () => {
  it("첫 페이지에 next_cursor 가 있으면 '더 보기'가 보이고, 클릭 시 둘째 페이지가 이어 렌더되며 마지막 페이지에서 sentinel 이 사라진다", async () => {
    // 페이지1(next_cursor 있음) → 페이지2(next_cursor=null=마지막)를 순차 반환.
    mockSearch
      .mockResolvedValueOnce({
        data: { items: [ROOM], next_cursor: "cursor-2" },
      } as never)
      .mockResolvedValueOnce({
        data: { items: [ROOM2], next_cursor: null },
      } as never);
    renderList();

    // 페이지1 항목 + '더 보기' sentinel 노출.
    expect(await screen.findByText("강남 스터디룸")).toBeInTheDocument();
    const more = await screen.findByRole("button", { name: "더 보기" });

    // '더 보기' 클릭 → 페이지2 로드(두 페이지 항목 모두 렌더).
    await userEvent.click(more);
    expect(await screen.findByText("역삼 스터디룸")).toBeInTheDocument();
    expect(screen.getByText("강남 스터디룸")).toBeInTheDocument();

    // 마지막 페이지(next_cursor=null) 도달 → sentinel 사라짐(더 없음).
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "더 보기" })).toBeNull(),
    );
    expect(mockSearch).toHaveBeenCalledTimes(2);
  });
});
