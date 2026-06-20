import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RadiusControl } from "./RadiusControl";

// RadiusControl 테스트 (Story 3.5 — AC1·범위 결정 #6). 프리셋 세그먼트의 접근 이름·선택 상태·
// onChange 를 검증한다(연속 슬라이더 비채택 — 신규 의존성 0).

describe("RadiusControl (AC1)", () => {
  it("프리셋 옵션이 접근 이름을 가진 radio 로 노출된다(NFR-5)", () => {
    render(<RadiusControl radiusKm={3} onChange={vi.fn()} />);
    expect(
      screen.getByRole("radiogroup", { name: "반경 선택" }),
    ).toBeInTheDocument();
    // 프리셋 1·2·3·5·10km 모두 접근 이름을 가진 radio.
    for (const km of [1, 2, 3, 5, 10]) {
      expect(
        screen.getByRole("radio", { name: `반경 ${km}km` }),
      ).toBeInTheDocument();
    }
  });

  it("현재 반경값이 aria-checked 로 표시된다(기본 3km)", () => {
    render(<RadiusControl radiusKm={3} onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "반경 3km" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("radio", { name: "반경 1km" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

  it("프리셋 선택 시 onChange 가 그 km 로 호출된다", async () => {
    const onChange = vi.fn();
    render(<RadiusControl radiusKm={3} onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "반경 5km" }));
    expect(onChange).toHaveBeenCalledWith(5);
  });
});
