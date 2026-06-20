import {
  onlineManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { loadKakaoMaps } from "@/lib/kakao-map";
import {
  roomsAggregateAvailability,
  roomsGetRoom,
  roomsListRooms,
} from "@/lib/api-client";
import { MapView } from "./MapView";

// MapView 컴포넌트 상태 테스트 (Story 3.2·3.3 — AC2·AC4·AC5; 3.6 위치 통합 — AC4·AC5).
// 3.6: MapView 는 더 이상 navigator.geolocation 을 직접 호출하지 않는다 — 위치 좌표/거부는
// coords/locationDenied prop 으로 주입된다(ExploreView 단일 소유). 카카오 SDK·SDK 함수를 모킹해
// 라이브 로딩 없이 상태 분기·setCenter(현위치 중심)·마커 생성·핀→시트를 검증한다(e2e 는 수동/후속).

vi.mock("@/lib/kakao-map", () => ({ loadKakaoMaps: vi.fn() }));
vi.mock("@/lib/api-client", () => ({
  roomsListRooms: vi.fn(),
  roomsAggregateAvailability: vi.fn(),
  roomsGetRoom: vi.fn(),
  // FavoriteButton(3.7) — RoomSheet 헤더 실배선. 미로그인(401)으로 즐겨찾기 조회 비활성.
  authMe: vi.fn(() =>
    Promise.resolve({ data: undefined, response: new Response(null, { status: 401 }) }),
  ),
  favoritesListFavorites: vi.fn(() => Promise.resolve({ data: [] })),
  favoritesAddFavorite: vi.fn(() => Promise.resolve({ data: {} })),
  favoritesRemoveFavorite: vi.fn(() => Promise.resolve({ data: undefined })),
}));

const mockLoad = vi.mocked(loadKakaoMaps);
const mockList = vi.mocked(roomsListRooms);
const mockAvail = vi.mocked(roomsAggregateAvailability);
const mockGetRoom = vi.mocked(roomsGetRoom);

// ── 카카오 SDK 가짜(no-op) — CustomOverlay 가 content(접근성 핀 버튼)를 지도 컨테이너에 붙여
//    스크린리더 트리·클릭을 검증할 수 있게 한다(RTL cleanup 이 컨테이너째 정리). setCenter 호출은
//    배열에 기록해 coords prop 주입 시 현위치 중심 이동을 단언한다(3.6 AC1·AC4). ──
function makeFakeKakao() {
  const setCenterCalls: Array<{ lat: number; lng: number }> = [];
  // 지도 생성 시점의 초기 중심(생성자 options.center) 기록 — "처음부터 내 위치/서울로 생성"을
  // 검증한다(setCenter 로 옮기는 것과 구분; 보류 구조에서는 생성 center 자체가 정답이어야 함).
  const mapInitCenters: Array<{ lat: number; lng: number }> = [];
  class LatLng {
    constructor(
      public lat: number,
      public lng: number,
    ) {}
  }
  class FakeMap {
    constructor(
      public container: HTMLElement,
      public options: unknown,
    ) {
      const center = (options as { center?: LatLng })?.center;
      if (center) mapInitCenters.push({ lat: center.lat, lng: center.lng });
    }
    setCenter(latlng: LatLng) {
      setCenterCalls.push({ lat: latlng.lat, lng: latlng.lng });
    }
    setLevel() {}
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
  return {
    kakao: { maps: { load: (cb: () => void) => cb(), LatLng, Map: FakeMap, CustomOverlay } },
    setCenterCalls,
    mapInitCenters,
  };
}

function installFakeKakao() {
  const { kakao, setCenterCalls, mapInitCenters } = makeFakeKakao();
  mockLoad.mockImplementation(async () => {
    (window as unknown as { kakao: unknown }).kakao = kakao;
    return kakao as unknown as typeof globalThis.kakao;
  });
  return { setCenterCalls, mapInitCenters };
}

// SDK 모킹 헬퍼 — throwOnError:true 경로라 { data } 형태로 resolve.
function resolveRooms(rooms: unknown[]) {
  mockList.mockResolvedValue({ data: rooms } as never);
}
function resolveAvailability(items: unknown[]) {
  mockAvail.mockResolvedValue({ data: items } as never);
}

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

// navigator.onLine 모킹(3.8 단절 — clearAllMocks 가 못 지우는 정의는 beforeEach 에서 명시 복원).
function setOnLine(value: boolean): void {
  Object.defineProperty(navigator, "onLine", { configurable: true, value });
}

beforeEach(() => {
  vi.clearAllMocks();
  setOnLine(true); // 기본 연결됨 — 단절 케이스는 각 테스트가 재정의
  // TanStack onlineManager 는 'offline' 이벤트로 전역 오프라인이 되면 다음 테스트의 쿼리를
  // paused 로 만든다(누수). 매 테스트 시작 시 온라인으로 리셋한다.
  onlineManager.setOnline(true);
});

describe("MapView 상태 분기 (AC5)", () => {
  it("로딩 중에는 스켈레톤 + placeholder 를 보여준다(전역 스피너 금지)", () => {
    // 지도 로더·쿼리를 모두 펜딩 유지 → 로딩 상태 고정(비동기 setState 없음 = act 경고 없음).
    mockLoad.mockReturnValue(new Promise(() => {}) as never);
    mockList.mockReturnValue(new Promise(() => {}) as never);
    mockAvail.mockReturnValue(new Promise(() => {}) as never);

    renderWithClient(<MapView />);

    expect(screen.getByTestId("map-skeleton")).toBeInTheDocument();
  });

  it("주변 활성 룸이 0개면 빈 상태 안내를 보여준다(막다른 화면 금지)", async () => {
    installFakeKakao();
    resolveRooms([]);
    resolveAvailability([]);

    renderWithClient(<MapView />);

    expect(await screen.findByText("이 근처엔 아직 없어요.")).toBeInTheDocument();
  });

  it("지도 로드 실패 시 안내 + 재시도 버튼을 보여준다", async () => {
    mockLoad.mockRejectedValue(new Error("SDK 로드 실패"));
    resolveRooms([]);
    resolveAvailability([]);

    renderWithClient(<MapView />);

    expect(await screen.findByText("지도를 못 불러왔어요.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "다시 시도" }),
    ).toBeInTheDocument();
  });
});

describe("MapView 위치 prop (Story 3.6 — AC1·AC4·AC5)", () => {
  it("coords prop 주입 시 현위치로 지도 중심을 옮긴다(AC1 — 현위치 중심)", async () => {
    const { setCenterCalls } = installFakeKakao();
    resolveRooms([]);
    resolveAvailability([]);

    renderWithClient(<MapView coords={{ lat: 37.5, lng: 127.01 }} />);

    // 지도 준비 후 coords effect 가 해당 좌표로 setCenter 를 호출한다(서울 폴백이 아닌 현위치).
    await waitFor(() =>
      expect(setCenterCalls).toContainEqual({ lat: 37.5, lng: 127.01 }),
    );
  });

  it("locationDenied prop true 면 거부 배너를 표시한다(AC5④ — 서울 폴백)", async () => {
    const { setCenterCalls } = installFakeKakao();
    resolveRooms([{ room_id: "a", name: "강남", lat: 37.5, lng: 127.0 }]);
    resolveAvailability([{ room_id: "a", remaining_slots: 2 }]);

    renderWithClient(<MapView locationDenied />);

    // 거부 안내가 뜨고, 핀은 그대로 표시된다(막다른 화면 아님).
    expect(
      await screen.findByText("현재 위치를 못 받았어요. 동네를 골라서 찾아볼게요."),
    ).toBeInTheDocument();
    expect(
      await screen.findByLabelText("강남 스터디룸, 예약 가능"),
    ).toBeInTheDocument();
    // 좌표 미주입이므로 현위치 이동 없음(서울 기본 중심 유지).
    expect(setCenterCalls).toHaveLength(0);
  });

  it("coords·locationDenied 모두 없으면 서울 중심 유지·배너 없음", async () => {
    const { setCenterCalls } = installFakeKakao();
    resolveRooms([{ room_id: "a", name: "강남", lat: 37.5, lng: 127.0 }]);
    resolveAvailability([{ room_id: "a", remaining_slots: 2 }]);

    renderWithClient(<MapView />);

    // 핀 등장으로 지도 준비 완료 확인.
    expect(
      await screen.findByLabelText("강남 스터디룸, 예약 가능"),
    ).toBeInTheDocument();
    // setCenter 미호출(서울 기본 중심) + 거부 배너 없음.
    expect(setCenterCalls).toHaveLength(0);
    expect(
      screen.queryByText("현재 위치를 못 받았어요. 동네를 골라서 찾아볼게요."),
    ).not.toBeInTheDocument();
  });

  it("MapView 는 navigator.geolocation 을 직접 호출하지 않는다(위치 단일 소유 — AC4)", async () => {
    const { setCenterCalls } = installFakeKakao();
    resolveRooms([]);
    resolveAvailability([]);
    const getCurrentPosition = vi.fn();
    Object.defineProperty(navigator, "geolocation", {
      value: { getCurrentPosition },
      configurable: true,
      writable: true,
    });

    renderWithClient(<MapView coords={{ lat: 37.5, lng: 127.01 }} />);

    // 현위치 중심 이동은 prop 경로로만 일어나고, geolocation API 는 호출되지 않는다.
    await waitFor(() =>
      expect(setCenterCalls).toContainEqual({ lat: 37.5, lng: 127.01 }),
    );
    expect(getCurrentPosition).not.toHaveBeenCalled();
  });
});

describe("MapView 위치 확보 후 생성 (pendingLocation — KTH 2026-06-19)", () => {
  const SEOUL = { lat: 37.5665, lng: 126.978 };

  it("pendingLocation=true 면 좌표가 있어도 지도를 생성하지 않는다(보류·스켈레톤 유지)", async () => {
    const { mapInitCenters } = installFakeKakao();
    resolveRooms([{ room_id: "a", name: "강남", lat: 37.5, lng: 127.0 }]);
    resolveAvailability([{ room_id: "a", remaining_slots: 2 }]);

    // coords 가 있어도 pending 이면 보류(측정 미완 상태를 모사) — 서울/엉뚱한 곳 선렌더 금지.
    renderWithClient(<MapView pendingLocation coords={{ lat: 37.56, lng: 127.19 }} />);

    // SDK 는 병렬 prefetch 로 로드되지만(측정과 무관), 지도 생성은 일어나지 않는다.
    await waitFor(() => expect(mockLoad).toHaveBeenCalled());
    expect(mapInitCenters).toHaveLength(0);
    expect(screen.getByTestId("map-skeleton")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("강남 스터디룸, 예약 가능"),
    ).not.toBeInTheDocument();
  });

  it("pendingLocation=false + coords 면 처음부터 그 좌표로 생성한다(서울 미경유)", async () => {
    const { mapInitCenters } = installFakeKakao();
    resolveRooms([]);
    resolveAvailability([]);

    renderWithClient(
      <MapView pendingLocation={false} coords={{ lat: 37.56, lng: 127.19 }} />,
    );

    await waitFor(() =>
      expect(mapInitCenters).toContainEqual({ lat: 37.56, lng: 127.19 }),
    );
    // 서울 폴백으로 생성한 적이 없다(선렌더→점프 제거).
    expect(mapInitCenters).not.toContainEqual(SEOUL);
  });

  it("pendingLocation=false + 좌표 없음이면 서울 폴백으로 생성한다(권한 없음/거부 확정)", async () => {
    const { mapInitCenters } = installFakeKakao();
    resolveRooms([]);
    resolveAvailability([]);

    renderWithClient(<MapView pendingLocation={false} />);

    await waitFor(() => expect(mapInitCenters).toContainEqual(SEOUL));
  });

  it("pendingLocation 이 true→false 로 풀리면 그때 내 위치로 생성한다", async () => {
    const { mapInitCenters } = installFakeKakao();
    resolveRooms([]);
    resolveAvailability([]);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const coords = { lat: 37.56, lng: 127.19 };

    const { rerender } = render(
      <QueryClientProvider client={client}>
        <MapView pendingLocation coords={coords} />
      </QueryClientProvider>,
    );
    // 보류 중 — 생성 안 됨.
    await waitFor(() => expect(mockLoad).toHaveBeenCalled());
    expect(mapInitCenters).toHaveLength(0);

    // 위치 확보 → 보류 해제 → 그제서야 내 위치로 생성.
    rerender(
      <QueryClientProvider client={client}>
        <MapView pendingLocation={false} coords={coords} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(mapInitCenters).toContainEqual(coords));
    expect(mapInitCenters).not.toContainEqual(SEOUL);
  });
});

describe("MapView 핀 렌더·접근성·시트 (AC2·AC3·AC4)", () => {
  it("핀이 색+아이콘+aria 라벨로 렌더된다(색 단독 신호 금지)", async () => {
    installFakeKakao();
    resolveRooms([
      { room_id: "a", name: "강남", lat: 37.5, lng: 127.0 },
      { room_id: "b", name: "홍대", lat: 37.55, lng: 126.92 },
    ]);
    resolveAvailability([
      { room_id: "a", remaining_slots: 3 }, // 예약 가능
      { room_id: "b", remaining_slots: 0 }, // 마감
    ]);

    renderWithClient(<MapView />);

    const availablePin = await screen.findByLabelText("강남 스터디룸, 예약 가능");
    const fullPin = await screen.findByLabelText("홍대 스터디룸, 오늘 마감");
    expect(availablePin).toBeInTheDocument();
    expect(fullPin).toBeInTheDocument();
    // 색-독립 신호: aria 라벨(텍스트)과 아이콘 글리프가 색과 무관하게 존재한다.
    expect(availablePin).toHaveTextContent("✓");
    expect(fullPin).toHaveTextContent("✕");
    // 키보드 도달 가능한 버튼 요소다(role=button).
    expect(availablePin.tagName).toBe("BUTTON");
  });

  it("핀을 클릭하면 해당 룸 바텀시트가 열리고 신선 요약을 불러온다(AC3·AC4)", async () => {
    installFakeKakao();
    resolveRooms([{ room_id: "a", name: "강남", lat: 37.5, lng: 127.0 }]);
    resolveAvailability([{ room_id: "a", remaining_slots: 3 }]);
    // 핀 탭 시 RoomSheet 가 단일 룸 신선 요약을 가져온다(3.3).
    mockGetRoom.mockResolvedValue({
      data: {
        room_id: "a",
        name: "강남",
        price_per_hour: 8000,
        capacity: 4,
        room_type: "open",
        amenities: ["wifi"],
        business_hours: [{ weekday: 0, open_time: "09:00:00", close_time: "22:00:00" }],
        remaining_slots: 3,
        is_closed_today: false,
      },
    } as never);

    renderWithClient(<MapView />);

    const pin = await screen.findByLabelText("강남 스터디룸, 예약 가능");
    fireEvent.click(pin);

    const sheet = await screen.findByRole("dialog");
    expect(sheet).toHaveTextContent("강남"); // 헤더 이름 즉시
    // 신선 요약 콘텐츠가 채워진다(가격·예약 가능 배지).
    expect(await screen.findByText("8,000원")).toBeInTheDocument();
    expect(screen.getByText("예약 가능")).toBeInTheDocument();
    // 닫기 → vaul onOpenChange(false) → selectedRoom=null → 시트 닫힘 상태로 전이.
    // (jsdom 은 exit 트랜지션 종료 이벤트를 안 내보내 즉시 언마운트되진 않으므로 data-state 로 단언.)
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(sheet).toHaveAttribute("data-state", "closed"));
  });
});

const NETWORK_NOTICE = "네트워크 연결이 끊겼어요. 연결되면 다시 보여드릴게요.";

describe("MapView 네트워크 단절 (Story 3.8 — AC1)", () => {
  it("단절 전이 시 NetworkNotice 를 띄우고 마지막 핀 캐시를 유지한다(에러 오버레이 미표시)", async () => {
    installFakeKakao();
    resolveRooms([{ room_id: "a", name: "강남", lat: 37.5, lng: 127.0 }]);
    resolveAvailability([{ room_id: "a", remaining_slots: 2 }]);

    renderWithClient(<MapView />);

    // 온라인 상태에서 핀이 로드된다(TanStack 캐시에 잔존).
    await screen.findByLabelText("강남 스터디룸, 예약 가능");

    // 네트워크 단절 전이.
    act(() => {
      setOnLine(false);
      window.dispatchEvent(new Event("offline"));
    });

    // 단절 배너 등장 + 마지막 핀은 그대로(캐시 유지) + 에러 오버레이 없음.
    expect(await screen.findByText(NETWORK_NOTICE)).toBeInTheDocument();
    expect(
      screen.getByLabelText("강남 스터디룸, 예약 가능"),
    ).toBeInTheDocument();
    expect(screen.queryByText("지도를 못 불러왔어요.")).not.toBeInTheDocument();
  });

  it("최초부터 단절이면 에러로 오인하지 않고 NetworkNotice 만 표시한다(showError 게이팅)", async () => {
    setOnLine(false);
    mockLoad.mockRejectedValue(new Error("SDK 로드 실패")); // 지도 로드 실패(=단절)
    resolveRooms([]);
    resolveAvailability([]);

    renderWithClient(<MapView />);

    // 단절이 "지도를 못 불러왔어요" 에러로 덮이지 않는다.
    expect(await screen.findByText(NETWORK_NOTICE)).toBeInTheDocument();
    expect(screen.queryByText("지도를 못 불러왔어요.")).not.toBeInTheDocument();
  });

  it("최초 단절로 지도 로드 실패 후 재연결되면 자동 재시도로 지도를 복구한다(code-review 2026-06-16)", async () => {
    // 1) 오프라인 콜드: 지도 SDK 로드가 실패해 mapStatus=error 이나, 단절이라 배너만 보인다.
    setOnLine(false);
    const { kakao } = makeFakeKakao();
    let loadCalls = 0;
    mockLoad.mockImplementation(async () => {
      loadCalls += 1;
      if (loadCalls === 1) throw new Error("offline SDK fail");
      // 2) 재연결 후 자동 재시도: 정상 로드.
      (window as unknown as { kakao: unknown }).kakao = kakao;
      return kakao as unknown as typeof globalThis.kakao;
    });
    resolveRooms([{ room_id: "a", name: "강남", lat: 37.5, lng: 127.0 }]);
    resolveAvailability([{ room_id: "a", remaining_slots: 2 }]);

    renderWithClient(<MapView />);

    // 최초 단절: 배너만(에러 오버레이 아님 — 수동 재시도 강요 금지).
    expect(await screen.findByText(NETWORK_NOTICE)).toBeInTheDocument();
    expect(screen.queryByText("지도를 못 불러왔어요.")).not.toBeInTheDocument();

    // 재연결 전이 → 단절 동안 error 였던 지도를 자동 재시도해 복구(핀 등장).
    act(() => {
      setOnLine(true);
      window.dispatchEvent(new Event("online"));
    });

    expect(
      await screen.findByLabelText("강남 스터디룸, 예약 가능"),
    ).toBeInTheDocument();
    expect(loadCalls).toBeGreaterThanOrEqual(2); // 최초 + 재연결 자동 재시도
  });
});

describe("MapView 빈/에러 다음-행동 액션 (Story 3.8 — AC1)", () => {
  it("빈 상태의 두 액션 버튼이 onSwitchToList 를 호출한다(반경/지역 전환)", async () => {
    installFakeKakao();
    resolveRooms([]); // 빈 결과
    resolveAvailability([]);
    const onSwitchToList = vi.fn();

    renderWithClient(<MapView onSwitchToList={onSwitchToList} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "지역으로 찾기" }),
    );
    expect(onSwitchToList).toHaveBeenCalledWith("region");

    fireEvent.click(
      screen.getByRole("button", { name: "반경으로 넓혀보기" }),
    );
    expect(onSwitchToList).toHaveBeenCalledWith("radius");
  });

  it("에러 상태의 '목록으로 보기' 가 onSwitchToList('region') 를 호출한다", async () => {
    mockLoad.mockRejectedValue(new Error("SDK 로드 실패"));
    resolveRooms([]);
    resolveAvailability([]);
    const onSwitchToList = vi.fn();

    renderWithClient(<MapView onSwitchToList={onSwitchToList} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "목록으로 보기" }),
    );
    expect(onSwitchToList).toHaveBeenCalledWith("region");
  });
});
