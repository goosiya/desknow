// 예약 패널 통합 테스트 (Story 4.3 — AC2·AC3·AC4). roomsGetRoomSlots SDK 를 모킹해 날짜 선택·
// 슬롯 상태 표시·빈 날 제안·로딩/실패 분기·슬롯 표시 전용(4.4 경계)을 검증한다.
//
// kstToday() 결정성을 위해 Date 만 페이크한다(setTimeout 은 실타이머 유지 → waitFor 동작).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { reservationsCreateReservation, roomsGetRoomSlots } from "@/lib/api-client";
import { ReservationPanel } from "./ReservationPanel";

vi.mock("@/lib/api-client", () => ({
  roomsGetRoomSlots: vi.fn(),
  reservationsCreateReservation: vi.fn(),
}));

// 공유 SDK 로더 모킹 — 성공 배너 공유 버튼 렌더 시 실제 `<script>` 주입 금지(5.4).
vi.mock("@/lib/kakao-share", () => ({ shareReservation: vi.fn() }));

const mockSlots = vi.mocked(roomsGetRoomSlots);
const mockCreate = vi.mocked(reservationsCreateReservation);

// 슬롯 상태 혼합(09:00 past · 14:00 available · 15:00 reserved) — KST 벽시계 표시 검증.
const MIXED_SLOTS = {
  date: "2026-06-15",
  slots: [
    { slot_start: "2026-06-15T00:00:00Z", status: "past" as const },
    { slot_start: "2026-06-15T05:00:00Z", status: "available" as const },
    { slot_start: "2026-06-15T06:00:00Z", status: "reserved" as const },
  ],
  next_available_date: null,
};

// 연속 available 3칸(14·15·16 KST) — 선택 요약(범위·시간·금액) 검증용.
const CONSECUTIVE_SLOTS = {
  date: "2026-06-15",
  slots: [
    { slot_start: "2026-06-15T05:00:00Z", status: "available" as const }, // 14:00
    { slot_start: "2026-06-15T06:00:00Z", status: "available" as const }, // 15:00
    { slot_start: "2026-06-15T07:00:00Z", status: "available" as const }, // 16:00
  ],
  next_available_date: null,
};

function resolveSlots(data: unknown) {
  mockSlots.mockResolvedValue({ data } as never);
}

function renderPanel(roomId = "room-1", pricePerHour = 8000, roomName = "강남 스터디라운지") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactNode = (
    <ReservationPanel roomId={roomId} pricePerHour={pricePerHour} roomName={roomName} />
  );
  // client 를 노출해 테스트가 캐시를 직접 갱신(setQueryData)할 수 있게 한다(stale 재조회 모사 — 4.9).
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) };
}

function setOnLine(value: boolean): void {
  Object.defineProperty(navigator, "onLine", { configurable: true, value });
}

beforeEach(() => {
  vi.clearAllMocks();
  setOnLine(true);
  // 2026-06-15 03:00 UTC = KST 12:00(월) → kstToday()="2026-06-15".
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-06-15T03:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ReservationPanel 슬롯 상태 표시 (AC2)", () => {
  it("선택한 날의 슬롯을 KST 벽시계로 상태별 표시한다 — available/past/reserved", async () => {
    resolveSlots(MIXED_SLOTS);
    const { container } = renderPanel();

    // available 슬롯(14:00) — sr-only 없는 단순 텍스트라 getByText 로 잡힌다.
    expect(await screen.findByText("14:00")).toBeInTheDocument();
    // past(09:00)·reserved(15:00)는 비활성(취소선 + sr-only 텍스트 — 색 단독 금지).
    const past = container.querySelector('[data-status="past"]');
    expect(past).toHaveAttribute("aria-disabled", "true");
    expect(past?.textContent).toContain("지난 시간");
    expect(past?.className).toContain("line-through");
    const reserved = container.querySelector('[data-status="reserved"]');
    expect(reserved?.textContent).toContain("예약됨");
  });

  it("available 슬롯은 선택 가능한 <button>(4.4) · past/reserved 는 표시 전용 <span> 유지", async () => {
    resolveSlots(MIXED_SLOTS);
    const { container } = renderPanel();

    await screen.findByText("14:00");
    // available 슬롯은 4.4 에서 <button> 으로 승격(탭/드래그/키보드 선택).
    expect(screen.getByRole("button", { name: "14:00" })).toBeInTheDocument();
    // past/reserved 는 표시 전용 <span> 보존(선택/포커스 불가).
    expect(container.querySelector('[data-status="past"]')?.tagName).toBe("SPAN");
    expect(container.querySelector('[data-status="reserved"]')?.tagName).toBe("SPAN");
  });

  it("날짜를 바꾸면 그 날짜로 슬롯을 다시 조회한다(신선 — 날짜별 키)", async () => {
    resolveSlots(MIXED_SLOTS);
    renderPanel();
    await screen.findByText("14:00");

    // 6월 17일 달력 셀 선택 → 그 날짜 query 로 재조회.
    fireEvent.click(screen.getByRole("gridcell", { name: "2026년 6월 17일" }));
    await waitFor(() =>
      expect(mockSlots).toHaveBeenCalledWith(
        expect.objectContaining({ query: { date: "2026-06-17" } }),
      ),
    );
  });
});

describe("ReservationPanel 빈 날 안내 + 다음 빈 날짜 제안 (AC3)", () => {
  it("available 0개면 '다 찼어요' + 다음 빈 날짜 제안 버튼을 보이고, 누르면 그 날로 이동한다", async () => {
    resolveSlots({ date: "2026-06-15", slots: [], next_available_date: "2026-06-18" });
    renderPanel();

    expect(
      await screen.findByText("이 날은 다 찼어요. 다른 날을 골라보세요."),
    ).toBeInTheDocument();
    const suggestion = screen.getByRole("button", { name: "6월 18일은 자리가 있어요" });
    fireEvent.click(suggestion);

    // 제안 클릭 → 6/18 로 달력 선택 이동 + 그 날짜 재조회.
    await waitFor(() =>
      expect(mockSlots).toHaveBeenCalledWith(
        expect.objectContaining({ query: { date: "2026-06-18" } }),
      ),
    );
    expect(screen.getByRole("gridcell", { name: "2026년 6월 18일" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("next_available_date 가 null 이면 안내만 — 제안 버튼 없음(막다른 화면 금지)", async () => {
    resolveSlots({ date: "2026-06-15", slots: [], next_available_date: null });
    renderPanel();

    expect(
      await screen.findByText("이 날은 다 찼어요. 다른 날을 골라보세요."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /자리가 있어요/ })).not.toBeInTheDocument();
  });
});

describe("ReservationPanel 선택 요약 (AC3 — 범위·날짜·시간·금액)", () => {
  it("슬롯을 선택하면 하단에 '범위 · 날짜 · 시간 · 금액' 요약 + SR 구간 피드백을 보인다", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    renderPanel("room-1", 8000);

    // 선택 전: "시간을 선택해 주세요" 안내(막다른 화면 금지).
    expect(await screen.findByText("시간을 선택해 주세요.")).toBeInTheDocument();

    // 14:00 탭 → 16:00 탭으로 14·15·16 연속 선택(3시간).
    fireEvent.click(screen.getByRole("button", { name: "14:00" }));
    fireEvent.click(screen.getByRole("button", { name: "16:00" }));

    // 요약: "14:00–17:00 · 6월 15일 · 3시간 · 24,000원"(끝=마지막 슬롯+1h · 3시간 × 8000).
    expect(
      screen.getByText("14:00–17:00 · 6월 15일 · 3시간 · 24,000원"),
    ).toBeInTheDocument();
    // SR 구간 피드백.
    expect(screen.getByText("14시부터 17시까지 선택됨")).toBeInTheDocument();
    expect(screen.queryByText("시간을 선택해 주세요.")).not.toBeInTheDocument();
  });

  it("금액은 pricePerHour 에 따른다(단일 슬롯 1시간)", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    renderPanel("room-1", 12000);

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    expect(
      screen.getByText("14:00–15:00 · 6월 15일 · 1시간 · 12,000원"),
    ).toBeInTheDocument();
  });

  it("날짜를 바꾸면 선택이 초기화된다(요약 사라짐 — AC3)", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    expect(screen.getByText(/24,000원|8,000원/)).toBeInTheDocument(); // 선택 요약 표시됨

    // 6월 17일로 날짜 변경 → selection 리셋 → 요약 사라지고 안내로 복귀.
    fireEvent.click(screen.getByRole("gridcell", { name: "2026년 6월 17일" }));
    expect(await screen.findByText("시간을 선택해 주세요.")).toBeInTheDocument();
  });

});

describe("ReservationPanel 즉시 예약 확정 (Story 4.5 — AC4·AC5)", () => {
  it("선택이 있을 때만 '예약하기' CTA 가 등장한다(선택 없으면 부재 — dead 버튼 금지)", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    renderPanel();

    // 선택 전: CTA 없음(4.4 회귀를 4.5 등장으로 교체).
    await screen.findByText("시간을 선택해 주세요.");
    expect(screen.queryByRole("button", { name: "예약하기" })).not.toBeInTheDocument();

    // 14:00 선택 → '예약하기' 등장.
    fireEvent.click(screen.getByRole("button", { name: "14:00" }));
    expect(screen.getByRole("button", { name: "예약하기" })).toBeInTheDocument();
  });

  it("'예약하기' 클릭 → slot_starts 본문(서버 UTC)으로 예약을 제출한다", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    mockCreate.mockResolvedValue({ data: { id: "r1" } } as never);
    renderPanel("room-1", 8000);

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    fireEvent.click(screen.getByRole("button", { name: "예약하기" }));

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({
          path: { room_id: "room-1" },
          body: { slot_starts: ["2026-06-15T05:00:00Z"] },
        }),
      ),
    );
  });

  it("성공 → '예약이 완료됐어요!' 인라인 배너 + selection 초기화(요약 사라짐)", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    mockCreate.mockResolvedValue({ data: { id: "r1" } } as never);
    renderPanel("room-1", 8000);

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    fireEvent.click(screen.getByRole("button", { name: "예약하기" }));

    // 성공 배너 표시.
    expect(await screen.findByText("예약이 완료됐어요!")).toBeInTheDocument();
    // selection 초기화 → 선택 요약·CTA 사라짐.
    expect(screen.queryByText(/8,000원/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "예약하기" })).not.toBeInTheDocument();
  });

  it("성공 배너에 카카오 공유 버튼이 노출된다(UJ-1 climax — 5.4 AC3)", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    // 응답에 slot_starts 동반 — 공유 텍스트 합성용(추가 조회 0).
    mockCreate.mockResolvedValue({
      data: { id: "r1", slot_starts: ["2026-06-15T05:00:00Z"] },
    } as never);
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    fireEvent.click(screen.getByRole("button", { name: "예약하기" }));

    await screen.findByText("예약이 완료됐어요!");
    expect(
      screen.getByRole("button", { name: "카카오톡으로 공유" }),
    ).toBeInTheDocument();
  });

  it("generic 실패(detail.code 없음) → generic 안내 + selection 유지 + '다시 시도'(무회귀)", async () => {
    // detail.code 가 없는 실패(404·5xx·일반)는 SLOT_CONFLICT 가 아니므로 4.5 generic 경로 그대로.
    resolveSlots(CONSECUTIVE_SLOTS);
    mockCreate.mockRejectedValue(new Error("boom"));
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    fireEvent.click(screen.getByRole("button", { name: "예약하기" }));

    // generic 카피 + selection 유지(요약 그대로) + '다시 시도' 버튼.
    expect(
      await screen.findByText("예약을 완료하지 못했어요. 다시 시도해 주세요."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
    // SLOT_CONFLICT 특화 카피는 generic 실패엔 표시되지 않는다(분기 무회귀).
    expect(screen.queryByText(/먼저 잡았어요/)).not.toBeInTheDocument();
    // selection 유지 → 요약 그대로(초기화되지 않음).
    expect(screen.getByText(/8,000원/)).toBeInTheDocument();

    // '다시 시도' → 재제출(재호출).
    mockCreate.mockResolvedValue({ data: { id: "r1" } } as never);
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(await screen.findByText("예약이 완료됐어요!")).toBeInTheDocument();
  });

  // ── Story 4.6 — SLOT_CONFLICT(409) 특화 UX (AC3·AC4) ──
  it("SLOT_CONFLICT → '먼저 잡았어요' 특화 카피 + selection 초기화(요약·CTA 사라짐, 막다른 화면 금지)", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    // SDK 는 throwOnError 시 파싱된 본문 {detail:{code,message}} 를 throw(client-fetch 실측).
    mockCreate.mockRejectedValue({
      detail: { code: "SLOT_CONFLICT", message: "선택한 시간 중 이미 예약된 슬롯이 있습니다." },
    });
    renderPanel("room-1", 8000);

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    fireEvent.click(screen.getByRole("button", { name: "예약하기" }));

    // 특화 카피(고정 한국어 — 에러코드 노출 금지) 표시.
    expect(
      await screen.findByText(
        "앗, 방금 다른 분이 먼저 잡았어요. 가까운 빈 시간을 다시 보여드릴게요.",
      ),
    ).toBeInTheDocument();
    // selection 초기화 → 요약·CTA 사라짐(generic 카피도 미표시 — 분기).
    expect(screen.queryByText(/8,000원/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /예약하기|다시 시도/ })).not.toBeInTheDocument();
    expect(
      screen.queryByText("예약을 완료하지 못했어요. 다시 시도해 주세요."),
    ).not.toBeInTheDocument();
    // 막다른 화면 금지 — 새로고침된 그리드에서 재선택 가능(슬롯 버튼 인터랙티브 유지).
    expect(screen.getByRole("button", { name: "14:00" })).toBeInTheDocument();
  });

  it("SLOT_CONFLICT 후 그리드에서 재선택 → '예약하기' 재등장(막다른 화면 부재)", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    mockCreate.mockRejectedValue({
      detail: { code: "SLOT_CONFLICT", message: "선택한 시간 중 이미 예약된 슬롯이 있습니다." },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    fireEvent.click(screen.getByRole("button", { name: "예약하기" }));
    await screen.findByText(
      "앗, 방금 다른 분이 먼저 잡았어요. 가까운 빈 시간을 다시 보여드릴게요.",
    );

    // 새로고침된 그리드에서 다시 선택 → CTA 재등장(특화 카피는 새 선택 시 reset 으로 사라짐).
    fireEvent.click(screen.getByRole("button", { name: "15:00" }));
    expect(screen.getByRole("button", { name: "예약하기" })).toBeInTheDocument();
    expect(screen.queryByText(/먼저 잡았어요/)).not.toBeInTheDocument();
  });

  it("단절 중 SLOT_CONFLICT 도 특화 카피 대신 NetworkNotice 우선(단절≠충돌 — AC4)", async () => {
    setOnLine(false);
    resolveSlots(CONSECUTIVE_SLOTS);
    mockCreate.mockRejectedValue({
      detail: { code: "SLOT_CONFLICT", message: "x" },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    fireEvent.click(screen.getByRole("button", { name: "예약하기" }));

    expect(
      await screen.findByText("네트워크 연결이 끊겼어요. 연결되면 다시 보여드릴게요."),
    ).toBeInTheDocument();
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    // 단절 게이팅(showSubmitError = isOnline && isError)으로 특화 카피 미표시.
    expect(screen.queryByText(/먼저 잡았어요/)).not.toBeInTheDocument();
  });

  it("네트워크 단절 중 제출 실패는 generic 에러로 오인하지 않는다(NetworkNotice 일원화 — AC5)", async () => {
    setOnLine(false);
    resolveSlots(CONSECUTIVE_SLOTS);
    mockCreate.mockRejectedValue(new Error("offline"));
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    fireEvent.click(screen.getByRole("button", { name: "예약하기" }));

    // 단절 배너는 표시 + 제출 generic 에러는 오인 표시하지 않는다(showSubmitError = isOnline && isError).
    expect(
      await screen.findByText("네트워크 연결이 끊겼어요. 연결되면 다시 보여드릴게요."),
    ).toBeInTheDocument();
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(
      screen.queryByText("예약을 완료하지 못했어요. 다시 시도해 주세요."),
    ).not.toBeInTheDocument();
  });

  it("제출 중에는 버튼이 '예약 중…' + disabled(이중 제출 방지)", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    mockCreate.mockReturnValue(new Promise(() => {}) as never); // 영원히 pending
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    fireEvent.click(screen.getByRole("button", { name: "예약하기" }));

    const pending = await screen.findByRole("button", { name: "예약 중…" });
    expect(pending).toBeDisabled();
  });
});

describe("ReservationPanel stale 선택 무효화 (Story 4.9 — AC5·의무회수 L214·L224)", () => {
  const SLOT_KEY = ["room", "room-1", "slots", "2026-06-15"];

  it("선택 후 그 슬롯이 reserved 로 바뀌면 선택이 비워지고 안내 표시(요약·CTA 사라짐·강조 해제)", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    const { client } = renderPanel("room-1", 8000);

    // 14·15 연속 선택 → 요약·CTA 표시.
    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    fireEvent.click(screen.getByRole("button", { name: "15:00" }));
    expect(screen.getByText(/16,000원/)).toBeInTheDocument(); // 2시간 × 8000
    expect(screen.getByRole("button", { name: "예약하기" })).toBeInTheDocument();
    // 선택 강조(aria-pressed) 확인.
    expect(screen.getByRole("button", { name: "14:00" })).toHaveAttribute("aria-pressed", "true");

    // 백그라운드 재조회 모사 — 15:00 이 방금 reserved 로 바뀜(인덱스 안 밀림·내용만 stale).
    act(() => {
      client.setQueryData(SLOT_KEY, {
        date: "2026-06-15",
        slots: [
          { slot_start: "2026-06-15T05:00:00Z", status: "available" }, // 14:00
          { slot_start: "2026-06-15T06:00:00Z", status: "reserved" }, // 15:00 ← 점유됨
          { slot_start: "2026-06-15T07:00:00Z", status: "available" }, // 16:00
        ],
        next_available_date: null,
      });
    });

    // 선택 무효화 안내 표시 + 요약·CTA 사라짐(막다른 화면 금지 — 재선택 유도).
    expect(
      await screen.findByText("선택한 시간 중 일부가 방금 예약됐어요. 다시 선택해 주세요."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/16,000원/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "예약하기" })).not.toBeInTheDocument();
    // SlotGrid 에 stale 강조 미전달(safeSelection=null) — 14:00 더는 선택 강조 아님.
    expect(screen.getByRole("button", { name: "14:00" })).toHaveAttribute("aria-pressed", "false");
  });

  it("무효화 후 재선택하면 안내 사라지고 '예약하기' 재등장(막다른 화면 부재)", async () => {
    resolveSlots(CONSECUTIVE_SLOTS);
    const { client } = renderPanel("room-1", 8000);

    fireEvent.click(await screen.findByRole("button", { name: "14:00" }));
    act(() => {
      client.setQueryData(SLOT_KEY, {
        date: "2026-06-15",
        slots: [
          { slot_start: "2026-06-15T05:00:00Z", status: "reserved" }, // 14:00 점유됨
          { slot_start: "2026-06-15T06:00:00Z", status: "available" }, // 15:00
          { slot_start: "2026-06-15T07:00:00Z", status: "available" }, // 16:00
        ],
        next_available_date: null,
      });
    });
    await screen.findByText("선택한 시간 중 일부가 방금 예약됐어요. 다시 선택해 주세요.");

    // 여전히 가용한 15:00 재선택 → 안내 사라지고 CTA 재등장.
    fireEvent.click(screen.getByRole("button", { name: "15:00" }));
    expect(screen.getByRole("button", { name: "예약하기" })).toBeInTheDocument();
    expect(
      screen.queryByText("선택한 시간 중 일부가 방금 예약됐어요. 다시 선택해 주세요."),
    ).not.toBeInTheDocument();
  });
});

describe("ReservationPanel 만석일 경로 (Story 4.9 — AC2·회수 L221)", () => {
  it("차감으로 모든 슬롯이 reserved(available 0)면 '다 찼어요' + 다음 빈 날 제안이 트리거된다", async () => {
    // 4.9 차감 후 한 날이 전부 예약되면 availableCount===0 → isEmptyDay 경로가 **실제 트리거**된다
    // (L221 deferred = "4.9 차감 미배선이라 트리거 불가" 회수). slots 가 비어있지 않아도(reserved 표시)
    // available 0 이면 같은 안내·제안이 떠야 한다.
    resolveSlots({
      date: "2026-06-15",
      slots: [
        { slot_start: "2026-06-15T05:00:00Z", status: "reserved" as const },
        { slot_start: "2026-06-15T06:00:00Z", status: "reserved" as const },
      ],
      next_available_date: "2026-06-18",
    });
    renderPanel();

    expect(
      await screen.findByText("이 날은 다 찼어요. 다른 날을 골라보세요."),
    ).toBeInTheDocument();
    // 다음 빈 날 제안(차감으로 만석 날을 건너뛴 백엔드 next_available_date)도 함께 트리거.
    expect(
      screen.getByRole("button", { name: "6월 18일은 자리가 있어요" }),
    ).toBeInTheDocument();
  });
});

describe("ReservationPanel 상태 분기 (AC4 — 부분 degrade)", () => {
  it("로딩 중에는 슬롯 스켈레톤을 보이고 달력은 즉시 표시한다", () => {
    mockSlots.mockReturnValue(new Promise(() => {}) as never); // 영원히 pending
    renderPanel();

    expect(screen.getByTestId("slots-skeleton")).toBeInTheDocument();
    expect(screen.getByText("날짜 선택")).toBeInTheDocument(); // 달력은 즉시
  });

  it("슬롯 조회 실패 시 '시간표를 못 불러왔어요' + 다시 시도(달력은 정상)", async () => {
    mockSlots.mockRejectedValue(new Error("boom"));
    renderPanel();

    expect(await screen.findByText("시간표를 못 불러왔어요.")).toBeInTheDocument();
    expect(screen.getByText("날짜 선택")).toBeInTheDocument(); // 부분 degrade — 달력 정상
    // 다시 시도 → refetch(재호출).
    mockSlots.mockResolvedValue({ data: MIXED_SLOTS } as never);
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(await screen.findByText("14:00")).toBeInTheDocument();
  });

  it("네트워크 단절이면 NetworkNotice 를 보이고 슬롯 에러로 오인하지 않는다", async () => {
    setOnLine(false);
    mockSlots.mockRejectedValue(new Error("offline"));
    renderPanel();

    // 단절 배너(공유 카피) 표시 + '시간표를 못 불러왔어요'(에러 오인) 미표시.
    expect(
      await screen.findByText("네트워크 연결이 끊겼어요. 연결되면 다시 보여드릴게요."),
    ).toBeInTheDocument();
    expect(screen.queryByText("시간표를 못 불러왔어요.")).not.toBeInTheDocument();
  });
});
