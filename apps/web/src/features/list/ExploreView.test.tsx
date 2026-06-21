import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { loadKakaoMaps } from "@/lib/kakao-map";
import { roomsSearchRooms } from "@/lib/api-client";
import { ExploreView } from "./ExploreView";

// ExploreView 토글 테스트 (Story 3.4 — AC2·AC5). 지도↔목록 전환·토글 접근 이름·전환 후 선택 지역
// 보존을 검증한다. 카카오 SDK(MapView 경로)·rooms SDK 를 모킹한다(3.2 선례). 카카오는 펜딩으로
// 둬 지도 모드가 스켈레톤에 머물게 한다(물리 지도 렌더는 범위 밖 — 토글·상태 보존만 검증).
vi.mock("@/lib/kakao-map", () => ({
  loadKakaoMaps: vi.fn(() => new Promise(() => {})),
}));
vi.mock("@/lib/api-client", () => ({
  roomsListRooms: vi.fn(() => Promise.resolve({ data: [] })),
  roomsAggregateAvailability: vi.fn(() => Promise.resolve({ data: [] })),
  roomsGetRoom: vi.fn(() => new Promise(() => {})),
  roomsListRegions: vi.fn(),
  roomsSearchRooms: vi.fn(() =>
    Promise.resolve({ data: { items: [], next_cursor: null } }),
  ),
  // FavoriteButton(3.7) — RoomListRow 실배선. 미로그인(401)으로 즐겨찾기 조회 비활성.
  authMe: vi.fn(() =>
    Promise.resolve({ data: undefined, response: new Response(null, { status: 401 }) }),
  ),
  favoritesListFavorites: vi.fn(() =>
    Promise.resolve({ data: { items: [], next_cursor: null } }),
  ),
  favoritesAddFavorite: vi.fn(() => Promise.resolve({ data: {} })),
  favoritesRemoveFavorite: vi.fn(() => Promise.resolve({ data: undefined })),
}));

const mockLoad = vi.mocked(loadKakaoMaps);
const mockSearch = vi.mocked(roomsSearchRooms);

// navigator.geolocation 모킹 (Story 3.5 — 반경 검색방식 위치 신호). granted=성공 콜백 즉시 호출,
// denied=에러 콜백, unsupported=geolocation 자체 제거. configurable 로 테스트 간 재정의 허용.
function mockGeolocation(
  mode: "granted" | "denied" | "unsupported",
  coords: { lat: number; lng: number } = { lat: 37.5665, lng: 126.978 },
): void {
  if (mode === "unsupported") {
    Object.defineProperty(navigator, "geolocation", {
      value: undefined,
      configurable: true,
      writable: true,
    });
    return;
  }
  const getCurrentPosition = vi.fn(
    (
      success: PositionCallback,
      error?: PositionErrorCallback | null,
    ) => {
      if (mode === "granted") {
        success({
          coords: { latitude: coords.lat, longitude: coords.lng },
        } as GeolocationPosition);
      } else {
        error?.({ code: 1, message: "denied" } as GeolocationPositionError);
      }
    },
  );
  Object.defineProperty(navigator, "geolocation", {
    value: { getCurrentPosition },
    configurable: true,
    writable: true,
  });
}

// navigator.permissions 모킹 (위치 권한 선확인 개편). state 를 가진 PermissionStatus 를 반환한다.
// 미설정(undefined)이면 useGeolocation 이 레거시 자동 측정으로 폴백한다(기존 테스트 보존).
function mockPermissions(state: "granted" | "prompt" | "denied"): void {
  const status = {
    state,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
  Object.defineProperty(navigator, "permissions", {
    value: { query: vi.fn(() => Promise.resolve(status)) },
    configurable: true,
    writable: true,
  });
}

// 지도 ready 를 위한 최소 가짜 카카오(빈 상태 버튼 노출 검증용 — pending 기본을 덮어쓴다).
function installFakeKakao(): void {
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
    ) {}
    setCenter() {}
    setLevel() {}
  }
  class CustomOverlay {
    constructor(public opts: unknown) {}
    setMap() {}
  }
  const kakao = {
    maps: { load: (cb: () => void) => cb(), LatLng, Map: FakeMap, CustomOverlay },
  };
  mockLoad.mockImplementation(async () => {
    (window as unknown as { kakao: unknown }).kakao = kakao;
    return kakao as unknown as typeof globalThis.kakao;
  });
}

const GROUPS = [
  {
    code: "1168000000",
    name: "서울특별시 강남구",
    room_count: 1,
    dongs: [{ code: "1168010100", name: "역삼동", room_count: 1 }],
  },
];

function renderExplore() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactNode = <ExploreView />;
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(async () => {
  vi.clearAllMocks();
  mockLoad.mockReturnValue(new Promise(() => {}) as never);
  const { roomsListRegions } = await import("@/lib/api-client");
  vi.mocked(roomsListRegions).mockResolvedValue({ data: GROUPS } as never);
  mockSearch.mockResolvedValue({ data: { items: [], next_cursor: null } } as never);
  // 3.6: 위치를 마운트 즉시 요청하므로 기본은 허용(지도 유지) — 거부/미지원 우회 케이스는
  // 각 테스트가 mockGeolocation 으로 재정의한다.
  mockGeolocation("granted");
  // 권한 선확인 개편: 기본은 Permissions API 미설정(undefined) → 레거시 자동 측정 폴백(기존 테스트
  // 동작 보존). prompt 경로를 검증하는 테스트만 mockPermissions 로 재정의한다.
  Object.defineProperty(navigator, "permissions", {
    value: undefined,
    configurable: true,
    writable: true,
  });
  // 3.8: MapView 가 navigator.onLine 을 읽으므로 기본 연결됨으로 둔다.
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
});

describe("ExploreView 토글 (AC5)", () => {
  it("지도/목록 토글이 접근 이름과 aria-pressed 를 가진다(NFR-5)", async () => {
    renderExplore();
    // 3.6: 위치를 마운트 즉시 요청하므로 비동기 상태 정착(허용=지도 유지)을 기다린 뒤 단언한다.
    await screen.findByRole("region", { name: "스터디룸 찾기 지도" });
    const mapBtn = screen.getByRole("button", { name: "지도" });
    const listBtn = screen.getByRole("button", { name: "목록" });
    expect(mapBtn).toHaveAttribute("aria-pressed", "true"); // 초기 지도
    expect(listBtn).toHaveAttribute("aria-pressed", "false");
  });

  it("지도↔목록을 전환한다(같은 화면 안에서 뷰 교체)", async () => {
    const user = userEvent.setup();
    renderExplore();

    // 초기: 지도 뷰(스터디룸 찾기 지도 섹션). 콤보 없음.
    expect(
      screen.getByRole("region", { name: "스터디룸 찾기 지도" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "시/군/구 선택" }),
    ).not.toBeInTheDocument();

    // 목록으로 전환 → 콤보 등장, 지도 사라짐.
    await user.click(screen.getByRole("button", { name: "목록" }));
    expect(
      await screen.findByRole("combobox", { name: "시/군/구 선택" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "스터디룸 찾기 지도" }),
    ).not.toBeInTheDocument();

    // 다시 지도로.
    await user.click(screen.getByRole("button", { name: "지도" }));
    expect(
      screen.getByRole("region", { name: "스터디룸 찾기 지도" }),
    ).toBeInTheDocument();
  });

  it("목록→지도→목록 토글 시 선택 지역이 보존된다(AC5)", async () => {
    const user = userEvent.setup();
    renderExplore();

    // 목록으로 전환하고 강남구 선택.
    await user.click(screen.getByRole("button", { name: "목록" }));
    const sigungu = await screen.findByRole("combobox", {
      name: "시/군/구 선택",
    });
    await waitFor(() => expect(sigungu).not.toBeDisabled());
    await user.click(sigungu);
    await user.click(
      await screen.findByRole("option", { name: /서울특별시 강남구/ }),
    );

    // 선택 → 강남구 코드로 목록 조회 트리거.
    await waitFor(() =>
      expect(mockSearch).toHaveBeenCalledWith(
        expect.objectContaining({ query: { region_code: "1168000000" } }),
      ),
    );

    // 지도로 갔다가 다시 목록 → 콤보가 여전히 강남구를 표시한다(상태 보존).
    await user.click(screen.getByRole("button", { name: "지도" }));
    await user.click(screen.getByRole("button", { name: "목록" }));

    const sigunguAgain = await screen.findByRole("combobox", {
      name: "시/군/구 선택",
    });
    await waitFor(() =>
      expect(sigunguAgain).toHaveTextContent("서울특별시 강남구"),
    );
  });
});

describe("ExploreView 지도 위치 권한 (개편 2026-06-18 — 선확인·내 반경)", () => {
  it("권한 prompt 면 자동 측정하지 않고(프롬프트 금지) 지도 유지 + 안내 버튼을 보인다", async () => {
    mockPermissions("prompt");
    mockGeolocation("granted"); // 측정되면 granted 지만, prompt 라 자동 호출되지 않아야 한다.
    renderExplore();

    // 지도는 유지(자동 우회 없음).
    expect(
      await screen.findByRole("region", { name: "스터디룸 찾기 지도" }),
    ).toBeInTheDocument();
    // ★자동 측정(프롬프트) 금지 — getCurrentPosition 미호출.
    const geolocation = navigator.geolocation as unknown as {
      getCurrentPosition: ReturnType<typeof vi.fn>;
    };
    expect(geolocation.getCurrentPosition).not.toHaveBeenCalled();
    // 토글 아래 안내(허용 유도) 버튼.
    expect(
      screen.getByRole("button", {
        name: /여기를 눌러 위치 권한을 허용해 주세요/,
      }),
    ).toBeInTheDocument();
    // 아직 권한 없으니 '내 반경' 버튼은 없다.
    expect(screen.queryByRole("button", { name: "내 반경" })).not.toBeInTheDocument();
  });

  it("prompt 안내 버튼을 누르면 측정을 요청한다(프롬프트)", async () => {
    const user = userEvent.setup();
    mockPermissions("prompt");
    mockGeolocation("granted");
    renderExplore();

    const hint = await screen.findByRole("button", {
      name: /여기를 눌러 위치 권한을 허용해 주세요/,
    });
    await user.click(hint);

    const geolocation = navigator.geolocation as unknown as {
      getCurrentPosition: ReturnType<typeof vi.fn>;
    };
    await waitFor(() =>
      expect(geolocation.getCurrentPosition).toHaveBeenCalled(),
    );
  });

  it("위치 거부 시에도 지도가 유지되고(자동 우회 없음) 안내 문구가 뜬다", async () => {
    mockGeolocation("denied");
    renderExplore();

    // 지도 유지 — 지역으로 자동 우회하지 않는다.
    expect(
      await screen.findByRole("region", { name: "스터디룸 찾기 지도" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "시/군/구 선택" }),
    ).not.toBeInTheDocument();
    // 토글 아래 안내(설정 유도).
    expect(
      await screen.findByText(/위치 권한이 꺼져 있어요/),
    ).toBeInTheDocument();
  });

  it("위치 거부 시 안내 칩을 누르면 설정 방법(자물쇠) 카드를 펼친다", async () => {
    const user = userEvent.setup();
    mockGeolocation("denied");
    renderExplore();

    const chip = await screen.findByRole("button", {
      name: /여기를 눌러 위치 권한을 허용해 주세요/,
    });
    // 펼치기 전엔 단계 안내가 없다.
    expect(screen.queryByText(/자물쇠/)).not.toBeInTheDocument();
    await user.click(chip);
    // 클릭 시 '자물쇠 → 위치 → 허용' 단계 + 새로고침 버튼이 펼쳐진다.
    expect(await screen.findByText(/자물쇠/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "새로고침" })).toBeInTheDocument();
  });

  it("위치 허용 시 지도 유지 + '내 반경' 버튼을 보인다", async () => {
    mockGeolocation("granted", { lat: 37.5, lng: 127.0 });
    renderExplore();

    expect(
      await screen.findByRole("region", { name: "스터디룸 찾기 지도" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "내 반경" }),
    ).toBeInTheDocument();
  });

  it("'내 반경' 클릭 시 현위치 측정을 다시 요청한다(재중심)", async () => {
    const user = userEvent.setup();
    mockGeolocation("granted", { lat: 37.5, lng: 127.0 });
    renderExplore();

    const recenter = await screen.findByRole("button", { name: "내 반경" });
    const geolocation = navigator.geolocation as unknown as {
      getCurrentPosition: ReturnType<typeof vi.fn>;
    };
    const before = geolocation.getCurrentPosition.mock.calls.length;
    await user.click(recenter);
    await waitFor(() =>
      expect(geolocation.getCurrentPosition.mock.calls.length).toBeGreaterThan(
        before,
      ),
    );
  });
});

describe("ExploreView 검색방식 지역↔반경 (Story 3.5 — AC1·AC2·AC3)", () => {
  it("목록 모드에 지역|반경 검색방식 토글이 접근 이름·aria-pressed 로 있다(NFR-5)", async () => {
    const user = userEvent.setup();
    mockGeolocation("denied");
    renderExplore();
    await user.click(screen.getByRole("button", { name: "목록" }));

    const region = await screen.findByRole("button", { name: "지역" });
    const radius = screen.getByRole("button", { name: "내 반경" });
    expect(region).toHaveAttribute("aria-pressed", "true"); // 기본 지역
    expect(radius).toHaveAttribute("aria-pressed", "false");
  });

  it("반경 전환 + 위치 허용 시 lat/lng/radius_km 로 조회한다(AC1)", async () => {
    const user = userEvent.setup();
    mockGeolocation("granted", { lat: 37.5, lng: 127.0 });
    mockSearch.mockResolvedValue({ data: { items: [], next_cursor: null } } as never);
    renderExplore();

    await user.click(screen.getByRole("button", { name: "목록" }));
    await user.click(await screen.findByRole("button", { name: "내 반경" }));

    // 반경 컨트롤(radiogroup) 등장 + 현위치 좌표·기본 3km 로 조회.
    expect(
      await screen.findByRole("radiogroup", { name: "반경 선택" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(mockSearch).toHaveBeenCalledWith(
        expect.objectContaining({
          query: { lat: 37.5, lng: 127.0, radius_km: 3 },
        }),
      ),
    );
  });

  it("위치 거부 시 반경 비활성 + 안내 + 지역 유도(AC3, 막다른 화면 금지)", async () => {
    const user = userEvent.setup();
    mockGeolocation("denied");
    renderExplore();

    await user.click(screen.getByRole("button", { name: "목록" }));
    await user.click(await screen.findByRole("button", { name: "내 반경" }));

    // 안내 카피 + 반경 결과/컨트롤 미노출.
    expect(
      await screen.findByText("현재 위치를 못 받았어요. 동네를 골라서 찾아볼게요."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("radiogroup", { name: "반경 선택" }),
    ).not.toBeInTheDocument();
    expect(mockSearch).not.toHaveBeenCalled(); // 반경 조회 안 함(center 없음)

    // 지역 유도 버튼 → 지역 모드(콤보 등장).
    await user.click(
      screen.getByRole("button", { name: "지역으로 찾기" }),
    );
    expect(
      await screen.findByRole("combobox", { name: "시/군/구 선택" }),
    ).toBeInTheDocument();
  });

  it("검색방식 전환 후 양쪽 선택(지역·반경값)이 보존된다(AC2)", async () => {
    const user = userEvent.setup();
    mockGeolocation("granted", { lat: 37.5, lng: 127.0 });
    mockSearch.mockResolvedValue({ data: { items: [], next_cursor: null } } as never);
    renderExplore();

    await user.click(screen.getByRole("button", { name: "목록" }));

    // ① 지역: 강남구 선택.
    const sigungu = await screen.findByRole("combobox", {
      name: "시/군/구 선택",
    });
    await waitFor(() => expect(sigungu).not.toBeDisabled());
    await user.click(sigungu);
    await user.click(
      await screen.findByRole("option", { name: /서울특별시 강남구/ }),
    );

    // ② 반경으로 전환 후 5km 선택.
    await user.click(screen.getByRole("button", { name: "내 반경" }));
    await user.click(await screen.findByRole("radio", { name: "반경 5km" }));
    expect(screen.getByRole("radio", { name: "반경 5km" })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    // ③ 다시 지역 → 강남구 보존.
    await user.click(screen.getByRole("button", { name: "지역" }));
    const sigunguAgain = await screen.findByRole("combobox", {
      name: "시/군/구 선택",
    });
    await waitFor(() =>
      expect(sigunguAgain).toHaveTextContent("서울특별시 강남구"),
    );

    // ④ 다시 반경 → 5km 보존(전환 왕복 후에도 반경값 유지).
    await user.click(screen.getByRole("button", { name: "내 반경" }));
    expect(
      await screen.findByRole("radio", { name: "반경 5km" }),
    ).toHaveAttribute("aria-checked", "true");
  });
});

describe("ExploreView 지도 빈/에러 → 목록 우회 (Story 3.8 — AC1 통합)", () => {
  it("지도 빈 상태의 '반경으로 넓혀보기' 가 목록(반경)으로 전환한다", async () => {
    const user = userEvent.setup();
    mockGeolocation("granted", { lat: 37.5, lng: 127.0 });
    installFakeKakao(); // 지도 ready → 빈 상태(rooms=[]) 액션 버튼 노출

    renderExplore();

    await user.click(
      await screen.findByRole("button", { name: "반경으로 넓혀보기" }),
    );

    // 목록 + 반경 모드로 전환 → 반경 컨트롤(radiogroup) 등장.
    expect(
      await screen.findByRole("radiogroup", { name: "반경 선택" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "스터디룸 찾기 지도" }),
    ).not.toBeInTheDocument();
  });

  it("지도 에러의 '목록으로 보기' 가 목록(지역)으로 전환한다", async () => {
    const user = userEvent.setup();
    mockGeolocation("granted", { lat: 37.5, lng: 127.0 });
    mockLoad.mockRejectedValue(new Error("SDK 로드 실패")); // 지도 에러 → 에러 오버레이

    renderExplore();

    await user.click(
      await screen.findByRole("button", { name: "목록으로 보기" }),
    );

    // 목록 + 지역 모드로 전환 → 콤보 등장.
    expect(
      await screen.findByRole("combobox", { name: "시/군/구 선택" }),
    ).toBeInTheDocument();
  });
});
