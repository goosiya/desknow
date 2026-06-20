import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { roomsListRegions } from "@/lib/api-client";
import { RegionCombos } from "./RegionCombos";

// RegionCombos 테스트 (Story 3.4 — AC1·AC5). roomsListRegions SDK 를 모킹하고, 선택 상태를 든
// stateful 하니스로 controlled 콤보를 구동한다. 시군구 선택 → 동 콤보 갱신(캐스케이드)을 검증한다.
// Radix Select 의 jsdom 상호작용은 vitest.setup 의 pointer/ResizeObserver 폴리필로 가능.
vi.mock("@/lib/api-client", () => ({ roomsListRegions: vi.fn() }));

const mockRegions = vi.mocked(roomsListRegions);

const GROUPS = [
  {
    code: "1168000000",
    name: "서울특별시 강남구",
    room_count: 2,
    dongs: [
      { code: "1168010100", name: "역삼동", room_count: 1 },
      { code: "1168010300", name: "개포동", room_count: 1 },
    ],
  },
  {
    code: "1111000000",
    name: "서울특별시 종로구",
    room_count: 1,
    dongs: [{ code: "1111010100", name: "청운동", room_count: 1 }],
  },
];

/** 선택 상태를 든 하니스 — RegionCombos 는 controlled 라 부모가 상태를 갱신해야 실제 동작한다. */
function Harness() {
  const [sigungu, setSigungu] = useState<string | undefined>();
  const [dong, setDong] = useState<string | undefined>();
  return (
    <RegionCombos
      sigunguCode={sigungu}
      dongCode={dong}
      onSigunguChange={setSigungu}
      onDongChange={setDong}
    />
  );
}

function renderCombos() {
  mockRegions.mockResolvedValue({ data: GROUPS } as never);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RegionCombos (AC1·AC5)", () => {
  it("두 콤보가 접근 이름을 가진다(NFR-5)", async () => {
    renderCombos();
    expect(
      await screen.findByRole("combobox", { name: "시/군/구 선택" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "동/읍/면 선택" }),
    ).toBeInTheDocument();
  });

  it("시군구 선택 → 동 콤보가 그 시군구의 동으로 갱신된다(캐스케이드)", async () => {
    const user = userEvent.setup();
    renderCombos();

    // 데이터 로드 후 시군구 콤보 활성화 대기.
    const sigungu = await screen.findByRole("combobox", { name: "시/군/구 선택" });
    await waitFor(() => expect(sigungu).not.toBeDisabled());

    // 시군구 열고 "강남구" 선택.
    await user.click(sigungu);
    await user.click(
      await screen.findByRole("option", { name: /서울특별시 강남구/ }),
    );

    // 동 콤보를 열면 강남구의 동(역삼동·개포동)이 보인다(종로구 청운동은 없음).
    const dong = screen.getByRole("combobox", { name: "동/읍/면 선택" });
    await waitFor(() => expect(dong).not.toBeDisabled());
    await user.click(dong);

    expect(
      await screen.findByRole("option", { name: /역삼동/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /개포동/ })).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: /청운동/ }),
    ).not.toBeInTheDocument();
  });
});
