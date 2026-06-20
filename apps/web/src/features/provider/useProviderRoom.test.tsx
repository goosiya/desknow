// useSaveRoom 에러 분류 + 카피 테스트 (인계 3 — 1룸 초과 409 안내). 409=room_limit / 422=validation /
// 미응답=network 로 분류되고, saveRoomErrorCopy 가 사용자 카피로 매핑됨을 검증한다.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { roomsCreateRoom, roomsUpdateRoom } from "@/lib/api-client";
import { saveRoomErrorCopy, useSaveRoom } from "./useProviderRoom";

vi.mock("@/lib/api-client", () => ({
  roomsCreateRoom: vi.fn(),
  roomsUpdateRoom: vi.fn(),
}));

const mockCreate = vi.mocked(roomsCreateRoom);
const mockUpdate = vi.mocked(roomsUpdateRoom);

const PAYLOAD = {
  name: "테스트룸",
  price_per_hour: 10000,
  capacity: 4,
  room_type: "open",
  amenities: ["wifi"],
  lat: 37.5,
  lng: 127.1,
  admin_dong_code: "4145011000",
  address: "경기 하남시 미사강변대로 100",
  business_hours: [{ weekday: 0, open_time: "09:00:00", close_time: "22:00:00" }],
} as never;

function setup(existingRoomId: string | null = null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useSaveRoom(existingRoomId), { wrapper });
  return { result };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useSaveRoom 에러 분류 (인계 3)", () => {
  it("등록 409 → failure.kind='room_limit'", async () => {
    mockCreate.mockResolvedValue({
      data: undefined,
      error: { detail: { code: "ROOM_LIMIT_REACHED" } },
      response: new Response(null, { status: 409 }),
    } as never);
    const { result } = setup(null);

    act(() => result.current.mutate(PAYLOAD));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.failure).toEqual({ kind: "room_limit" });
  });

  it("수정 422 → failure.kind='validation' + 서버 message 보존", async () => {
    mockUpdate.mockResolvedValue({
      data: undefined,
      error: { detail: { code: "VALIDATION", message: "영업 종료가 시작보다 빨라요." } },
      response: new Response(null, { status: 422 }),
    } as never);
    const { result } = setup("room-1");

    act(() => result.current.mutate(PAYLOAD));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.failure).toEqual({
      kind: "validation",
      message: "영업 종료가 시작보다 빨라요.",
    });
  });

  it("SDK 미응답(네트워크 reject) → failure.kind='network'", async () => {
    mockCreate.mockRejectedValue(new TypeError("Failed to fetch"));
    const { result } = setup(null);

    act(() => result.current.mutate(PAYLOAD));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.failure).toEqual({ kind: "network" });
  });
});

describe("saveRoomErrorCopy", () => {
  it("room_limit → 1룸 보유 안내(수정 유도)", () => {
    expect(saveRoomErrorCopy({ kind: "room_limit" })).toContain(
      "이미 등록한 스터디룸이 있어요",
    );
  });
  it("validation → 서버 message 우선, 없으면 폴백", () => {
    expect(saveRoomErrorCopy({ kind: "validation", message: "오류 X" })).toBe(
      "오류 X",
    );
    expect(saveRoomErrorCopy({ kind: "validation", message: "" })).toContain(
      "입력값을 확인",
    );
  });
  it("network → 네트워크 단절 카피", () => {
    expect(saveRoomErrorCopy({ kind: "network" })).toContain(
      "네트워크 연결이 끊겼어요",
    );
  });
  it("unknown → 일반 재시도 카피", () => {
    expect(saveRoomErrorCopy({ kind: "unknown", status: 500 })).toContain(
      "저장에 실패했어요",
    );
  });
});
