// 공유 텍스트 빌더 단위 테스트 (Story 5.4 — AC1·AC6). 순수 함수라 fake timer 불요 — 고정 ISO
// ...Z 주입 + Asia/Seoul 포맷터로 로컬 타임존 무관하게 결정적이다.
import { describe, expect, it } from "vitest";

import { buildReservationShareText } from "./share";

describe("buildReservationShareText (Story 5.4 — AC1)", () => {
  it("단일 슬롯 — 룸 이름 + KST 날짜 + 1시간 범위 + 브랜드 안내", () => {
    // 2026-06-20T05:00:00Z = KST 14:00 (6월 20일). 끝 = +1h = 15:00.
    const text = buildReservationShareText("강남 스터디라운지", ["2026-06-20T05:00:00Z"]);
    expect(text).toBe("강남 스터디라운지\n6월 20일 14:00–15:00\n데스크나우에서 예약했어요.");
  });

  it("연속 다중 슬롯 — 첫 슬롯 시작 ~ 마지막 슬롯 +1h 범위", () => {
    const text = buildReservationShareText("강남 스터디라운지", [
      "2026-06-20T05:00:00Z", // 14:00
      "2026-06-20T06:00:00Z", // 15:00
      "2026-06-20T07:00:00Z", // 16:00 → 끝 17:00
    ]);
    expect(text).toBe("강남 스터디라운지\n6월 20일 14:00–17:00\n데스크나우에서 예약했어요.");
  });

  it("KST 날짜 경계 — UTC 오후가 KST 다음날로 넘어간다(절대 표기)", () => {
    // 2026-06-20T15:00:00Z = KST 2026-06-21 00:00 → "6월 21일 00:00".
    const text = buildReservationShareText("심야룸", ["2026-06-20T15:00:00Z"]);
    expect(text).toBe("심야룸\n6월 21일 00:00–01:00\n데스크나우에서 예약했어요.");
  });

  it("룸 이름 누락(공백) → '예약' 폴백", () => {
    const text = buildReservationShareText("   ", ["2026-06-20T05:00:00Z"]);
    expect(text).toBe("예약\n6월 20일 14:00–15:00\n데스크나우에서 예약했어요.");
  });

  it("slot_starts 0건(레거시 방어) → 일시 줄 생략, 이름 + 안내만(막다른 화면 금지)", () => {
    const text = buildReservationShareText("강남룸", []);
    expect(text).toBe("강남룸\n데스크나우에서 예약했어요.");
  });
});
