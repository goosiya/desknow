import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  authMe,
  notificationsDismissNotification,
  notificationsDismissReminder,
  notificationsListNotifications,
} from "@/lib/api-client";
import { InAppBannerSlot } from "@/components/shell/InAppBannerSlot";

import { bannerMessage, NotificationBanner } from "./NotificationBanner";

// NotificationBanner / InAppBannerSlot 테스트 (Story 5.1·5.2 — AC3·AC4).
// 통지 렌더·닫기→소멸(type별 분기)·미로그인 빈 렌더·aria·카피 파생·key 충돌 없음.
vi.mock("@/lib/api-client", () => ({
  authMe: vi.fn(),
  notificationsListNotifications: vi.fn(() => Promise.resolve({ data: [] })),
  notificationsDismissNotification: vi.fn(() => Promise.resolve({ data: undefined })),
  notificationsDismissReminder: vi.fn(() => Promise.resolve({ data: undefined })),
}));

const mockAuthMe = vi.mocked(authMe);
const mockList = vi.mocked(notificationsListNotifications);
const mockDismiss = vi.mocked(notificationsDismissNotification);
const mockDismissReminder = vi.mocked(notificationsDismissReminder);

function loggedIn() {
  mockAuthMe.mockResolvedValue({
    data: { id: "u1", role: "booker" },
    response: new Response(null, { status: 200 }),
  } as never);
}
function loggedOut() {
  mockAuthMe.mockResolvedValue({
    data: undefined,
    response: new Response(null, { status: 401 }),
  } as never);
}

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  loggedOut();
  mockList.mockResolvedValue({ data: [] } as never);
  mockDismiss.mockResolvedValue({ data: undefined } as never);
  mockDismissReminder.mockResolvedValue({ data: undefined } as never);
});

// ── bannerMessage generic 카피 파생 (AC4 — render-time) ──────────────────────────
describe("bannerMessage generic 카피", () => {
  it("status_change+rejected → 거절 카피(room_name 접두)", () => {
    expect(
      bannerMessage({
        id: "n1",
        type: "status_change",
        reservation_id: "r1",
        reason: "rejected",
        room_name: "스터디카페A",
        slot_start: null,
        created_at: "2026-06-17T00:00:00Z",
      }),
    ).toBe("스터디카페A 예약이 거절됐어요.");
  });

  it("status_change+cancelled → 취소 카피", () => {
    expect(
      bannerMessage({
        id: "n2",
        type: "status_change",
        reservation_id: "r2",
        reason: "cancelled",
        room_name: "스터디카페B",
        slot_start: null,
        created_at: "2026-06-17T00:00:00Z",
      }),
    ).toBe("스터디카페B 예약이 취소됐어요.");
  });

  it("reservation_reminder + slot_start 없음 → generic 도래 카피(폴백)", () => {
    expect(
      bannerMessage({
        id: null,
        type: "reservation_reminder",
        reservation_id: "r3",
        reason: null,
        room_name: "스터디카페C",
        slot_start: null,
        created_at: null,
      }),
    ).toBe("스터디카페C 예약이 곧 다가와요.");
  });

  it("reservation_reminder + slot_start → KST 절대 날짜·시각 포함 카피", () => {
    expect(
      bannerMessage({
        id: null,
        type: "reservation_reminder",
        reservation_id: "r3",
        reason: null,
        room_name: "스터디카페C",
        slot_start: "2026-06-17T05:00:00Z", // KST 14:00, 6월 17일
        created_at: null,
      }),
    ).toBe("스터디카페C 예약이 곧 다가와요. 6월 17일 14:00에 만나요.");
  });

  it("room_name 누락 → 접두 없이 폴백(막다른 화면 금지)", () => {
    expect(
      bannerMessage({
        id: "n4",
        type: "status_change",
        reservation_id: "r4",
        reason: "cancelled",
        room_name: null,
        slot_start: null,
        created_at: "2026-06-17T00:00:00Z",
      }),
    ).toBe("예약이 취소됐어요.");
  });

  it("status_change + 미지 reason → 상태 변경 폴백", () => {
    expect(
      bannerMessage({
        id: "n5",
        type: "status_change",
        reservation_id: "r5",
        reason: "something_new",
        room_name: "스터디카페A",
        slot_start: null,
        created_at: "2026-06-17T00:00:00Z",
      }),
    ).toBe("스터디카페A 예약 상태가 변경됐어요.");
  });
});

// ── bannerMessage 정밀 카피 + L6 손상 가드 (AC2·AC4 — 본 스토리 핵심) ──────────────────
describe("bannerMessage status_change 정밀 카피(5.3)", () => {
  it("status_change rejected + slot_start → 룸+KST 날짜+시각 포함 카피", () => {
    expect(
      bannerMessage({
        id: "n1",
        type: "status_change",
        reservation_id: "r1",
        reason: "rejected",
        room_name: "강남 스터디라운지",
        slot_start: "2026-06-17T05:00:00Z", // KST 14:00, 6월 17일
        created_at: "2026-06-17T00:00:00Z",
      }),
    ).toBe("강남 스터디라운지 6월 17일 14:00 예약이 거절됐어요.");
  });

  it("status_change cancelled + slot_start → 룸+KST 날짜+시각 취소 카피", () => {
    expect(
      bannerMessage({
        id: "n2",
        type: "status_change",
        reservation_id: "r2",
        reason: "cancelled",
        room_name: "강남 스터디라운지",
        slot_start: "2026-06-17T05:00:00Z",
        created_at: "2026-06-17T00:00:00Z",
      }),
    ).toBe("강남 스터디라운지 6월 17일 14:00 예약이 취소됐어요.");
  });

  it("status_change + 손상 slot_start → 크래시 없이 시각 없는 generic 폴백(L6 회수)", () => {
    expect(
      bannerMessage({
        id: "n3",
        type: "status_change",
        reservation_id: "r3",
        reason: "rejected",
        room_name: "스터디카페A",
        slot_start: "totally-not-iso", // 손상 — RangeError 유발 가능
        created_at: "2026-06-17T00:00:00Z",
      }),
    ).toBe("스터디카페A 예약이 거절됐어요.");
  });

  it("status_change + naive(무-Z) slot_start → 시각 없는 generic 폴백(host-tz 오시각 회피·코드리뷰 2026-06-17)", () => {
    // "2026-06-17T10:00:00"은 유효하나 tz 지정자가 없어 new Date가 host-local로 해석(NaN 아님).
    // NaN 가드만으론 통과해 host-tz 의존 오시각이 되므로 tz 지정자 부재도 손상으로 폴백한다.
    expect(
      bannerMessage({
        id: "n6",
        type: "status_change",
        reservation_id: "r6",
        reason: "rejected",
        room_name: "스터디카페A",
        slot_start: "2026-06-17T10:00:00", // 무-Z naive
        created_at: "2026-06-17T00:00:00Z",
      }),
    ).toBe("스터디카페A 예약이 거절됐어요.");
  });

  it("reservation_reminder + 손상 slot_start → 크래시 없이 generic 도래 폴백(L6 회수)", () => {
    expect(
      bannerMessage({
        id: null,
        type: "reservation_reminder",
        reservation_id: "r4",
        reason: null,
        room_name: "스터디카페C",
        slot_start: "not-a-date",
        created_at: null,
      }),
    ).toBe("스터디카페C 예약이 곧 다가와요.");
  });
});

// ── NotificationBanner 단건 (AC4·AC5) ────────────────────────────────────────────
describe("NotificationBanner 단건", () => {
  const notification = {
    id: "n1",
    type: "status_change",
    reservation_id: "r1",
    reason: "rejected" as string | null,
    room_name: "스터디카페A",
    slot_start: null,
    created_at: "2026-06-17T00:00:00Z",
  };

  const reminder = {
    id: null,
    type: "reservation_reminder",
    reservation_id: "r9",
    reason: null,
    room_name: "스터디카페Z",
    slot_start: "2026-06-17T05:00:00Z",
    created_at: null,
  };

  it("텍스트(아이콘+텍스트 3중 신호) + 닫기(aria-label)로 렌더한다", () => {
    // 배너 자체엔 role=status 를 두지 않는다(부모 슬롯 aria-live="polite" 가 출현 안내 —
    // 중첩 live region 회피, code review 2026-06-17). 표시는 텍스트로 단언한다.
    renderWithClient(<NotificationBanner notification={notification} />);
    expect(
      screen.getByText("스터디카페A 예약이 거절됐어요."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "알림 닫기" }),
    ).toBeInTheDocument();
  });

  it("status_change → 닫기 라벨 '확인' + 정확 id 로 dismiss 호출", async () => {
    renderWithClient(<NotificationBanner notification={notification} />);
    expect(screen.getByText("확인")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "알림 닫기" }));
    expect(mockDismiss).toHaveBeenCalledWith({
      path: { notification_id: "n1" },
      throwOnError: true,
    });
    expect(mockDismissReminder).not.toHaveBeenCalled(); // 독립 트리거 — reminder 미호출
  });

  it("reservation_reminder → 닫기 라벨 '다시 보지 않기' + reservation_id 로 reminder dismiss", async () => {
    renderWithClient(<NotificationBanner notification={reminder} />);
    // KST 절대 날짜·시각 카피.
    expect(
      screen.getByText("스터디카페Z 예약이 곧 다가와요. 6월 17일 14:00에 만나요."),
    ).toBeInTheDocument();
    expect(screen.getByText("다시 보지 않기")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "알림 닫기" }));
    expect(mockDismissReminder).toHaveBeenCalledWith({
      path: { reservation_id: "r9" },
      throwOnError: true,
    });
    expect(mockDismiss).not.toHaveBeenCalled(); // 독립 트리거 — status_change 미호출
  });
});

// ── InAppBannerSlot 통합 (AC4·AC5) ───────────────────────────────────────────────
describe("InAppBannerSlot 통합", () => {
  it("로그인 + 미확인 통지 → 배너 렌더", async () => {
    loggedIn();
    mockList.mockResolvedValue({
      data: [
        {
          id: "n1",
          type: "status_change",
          reservation_id: "r1",
          reason: "cancelled",
          room_name: "스터디카페A",
          created_at: "2026-06-17T00:00:00Z",
        },
      ],
    } as never);
    renderWithClient(<InAppBannerSlot />);

    await waitFor(() =>
      expect(
        screen.getByText("스터디카페A 예약이 취소됐어요."),
      ).toBeInTheDocument(),
    );
  });

  it("미로그인 → 통지 미조회·빈 렌더(배너 없음)", async () => {
    loggedOut();
    const { container } = renderWithClient(<InAppBannerSlot />);

    // 슬롯 컨테이너는 존재하되(id 보존) 내부는 비어 empty:hidden 으로 숨는다.
    const slot = container.querySelector("#in-app-banner-slot");
    expect(slot).not.toBeNull();
    expect(slot?.children.length).toBe(0);
    // 미로그인이라 통지 조회 자체를 하지 않는다(enabled=false).
    expect(mockList).not.toHaveBeenCalled();
    // 배너(닫기 버튼)가 렌더되지 않음 — 배너엔 role=status 가 없으므로 버튼 부재로 단언.
    expect(
      screen.queryByRole("button", { name: "알림 닫기" }),
    ).not.toBeInTheDocument();
  });

  it("로그인 + 통지 0건 → 빈 렌더(슬롯 공간 차지 안 함)", async () => {
    loggedIn();
    mockList.mockResolvedValue({ data: [] } as never);
    const { container } = renderWithClient(<InAppBannerSlot />);

    await waitFor(() => expect(mockList).toHaveBeenCalled());
    const slot = container.querySelector("#in-app-banner-slot");
    expect(slot?.children.length).toBe(0);
  });

  it("리마인드(id=null)와 status_change가 같은 예약에 공존 → 둘 다 렌더(key 충돌 없음)", async () => {
    loggedIn();
    mockList.mockResolvedValue({
      data: [
        {
          id: null,
          type: "reservation_reminder",
          reservation_id: "r1", // 같은 예약 — key는 type:reservation_id 라 충돌 없음
          reason: null,
          room_name: "공존룸",
          slot_start: "2026-06-17T05:00:00Z",
          created_at: null,
        },
        {
          id: "n1",
          type: "status_change",
          reservation_id: "r1",
          reason: "cancelled",
          room_name: "공존룸",
          slot_start: null,
          created_at: "2026-06-17T00:00:00Z",
        },
      ],
    } as never);
    renderWithClient(<InAppBannerSlot />);

    await waitFor(() =>
      expect(
        screen.getByText("공존룸 예약이 취소됐어요."),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText("공존룸 예약이 곧 다가와요. 6월 17일 14:00에 만나요."),
    ).toBeInTheDocument();
    // 두 배너 = 닫기 버튼 2개(리마인드='다시 보지 않기'·status_change='확인').
    expect(screen.getAllByRole("button", { name: "알림 닫기" })).toHaveLength(2);
    expect(screen.getByText("다시 보지 않기")).toBeInTheDocument();
    expect(screen.getByText("확인")).toBeInTheDocument();
  });
});
