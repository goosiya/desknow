import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { loadKakaoMaps } from "@/lib/kakao-map";
import { RoomLocationMap } from "./RoomLocationMap";

// RoomLocationMap 단위 테스트 (Story 4.2 — AC3). loadKakaoMaps·카카오 SDK 를 모킹해 라이브 지도
// 없이 ① 중심 좌표 전달 ② 로드 중 스켈레톤 ③ 실패 시 자리 표시(전체 화면 막지 않음)를 단언한다.
// jsdom 은 실 타일을 렌더하지 못하므로 호출·좌표·상태 분기만 검증한다(3.2 선례).
vi.mock("@/lib/kakao-map", () => ({ loadKakaoMaps: vi.fn() }));

const mockLoad = vi.mocked(loadKakaoMaps);

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

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RoomLocationMap (AC3)", () => {
  it("로드 중에는 스켈레톤 자리를 보여준다", () => {
    mockLoad.mockReturnValue(new Promise(() => {}) as never); // 펜딩 유지
    render(<RoomLocationMap lat={37.5} lng={127.0} name="강남룸" />);
    expect(screen.getByTestId("location-map-skeleton")).toBeInTheDocument();
  });

  it("로드 성공 시 룸 좌표를 중심으로 지도를 만든다(단일 핀)", async () => {
    const { mapCenters } = installFakeKakao();
    render(<RoomLocationMap lat={37.5} lng={127.01} name="강남룸" />);

    await waitFor(() => expect(mockLoad).toHaveBeenCalled());
    await waitFor(() =>
      expect(mapCenters).toContainEqual({ lat: 37.5, lng: 127.01 }),
    );
    // 핀(단일) 접근성 라벨 — content 엘리먼트가 컨테이너에 붙는다.
    expect(await screen.findByLabelText("강남룸 위치")).toBeInTheDocument();
  });

  it("SDK 로드 실패 시 '지도를 못 불러왔어요' 자리로 degrade 한다(전체 막지 않음)", async () => {
    mockLoad.mockRejectedValue(new Error("SDK 로드 실패"));
    render(<RoomLocationMap lat={37.5} lng={127.0} />);

    expect(await screen.findByText("지도를 못 불러왔어요.")).toBeInTheDocument();
  });
});
