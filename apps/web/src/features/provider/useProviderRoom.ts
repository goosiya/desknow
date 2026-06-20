// provider 스터디룸 등록/수정 훅 (idea.md L36 — provider 웹 표면 구축).
//
// 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드). 본인 룸 조회는 404를 "아직 등록
// 안 함"(생성 모드)으로 정규화하고, 저장은 보유 여부에 따라 생성(POST)/수정(PATCH)을 가른다.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  roomsCreateRoom,
  roomsGeocodeAddress,
  roomsGetMyRoom,
  roomsUpdateRoom,
  type GeocodeResult,
  type ProviderRoomDetail,
  type RoomCreateRequest,
} from "@/lib/api-client";

/** 내 룸 쿼리 키 — 저장 성공 시 무효화 대상. */
export const MY_ROOM_QUERY_KEY = ["rooms", "mine"];

/**
 * 내 스터디룸 조회. 404(ROOM_NOT_FOUND=미등록)는 에러가 아니라 `null`로 정규화한다 →
 * 폼이 생성/수정 모드를 가른다. 그 외 비-2xx는 isError.
 */
export function useMyRoom() {
  return useQuery<ProviderRoomDetail | null>({
    queryKey: MY_ROOM_QUERY_KEY,
    queryFn: async () => {
      const { data, response } = await roomsGetMyRoom();
      if (response?.status === 404) return null; // 미등록 → 생성 모드
      if (!response?.ok) throw new Error("내 스터디룸을 불러오지 못했어요.");
      return (data ?? null) as ProviderRoomDetail | null;
    },
  });
}

/** 스터디룸 저장 실패 분류 — 화면이 카피를 분기하기 위한 판별 결과(useAuth.AuthFailure 미러). */
export type SaveRoomFailure =
  | { kind: "room_limit" } // 409 — 제공자당 1개 초과(ROOM_LIMIT_REACHED)
  | { kind: "validation"; message: string } // 422 — 검증 실패(서버 message)
  | { kind: "network" } // 네트워크 단절(fetch reject)
  | { kind: "unknown"; status?: number }; // 그 외(5xx 등)

/** SaveRoomFailure 를 mutation 오류로 던지기 위한 래퍼 — error.failure 로 꺼내 카피 분기한다. */
export class SaveRoomError extends Error {
  failure: SaveRoomFailure;
  constructor(failure: SaveRoomFailure) {
    super(failure.kind);
    this.name = "SaveRoomError";
    this.failure = failure;
  }
}

/** SDK 결과(status·error body)를 SaveRoomFailure 로 정규화한다(classifyHttpError 미러). */
function classifySaveError(
  status: number | undefined,
  errorBody: unknown,
): SaveRoomFailure {
  if (status === 409) return { kind: "room_limit" };
  if (status === 422) {
    // 422 본문 형상: { detail: { code, message } } — 서버 message 노출(없으면 빈 문자열).
    const message =
      (errorBody as { detail?: { message?: string } } | undefined)?.detail
        ?.message ?? "";
    return { kind: "validation", message };
  }
  return { kind: "unknown", status };
}

/** 네트워크 reject(SDK가 응답을 못 받음) → network 로 정규화(toAuthError 미러). */
function toSaveRoomError(err: unknown): SaveRoomError {
  if (err instanceof SaveRoomError) return err;
  return new SaveRoomError({ kind: "network" });
}

/** 저장 실패 → 사용자 카피. 409=이미 1룸 보유(수정 유도), 그 외=재시도(막다른 화면 금지). */
export function saveRoomErrorCopy(failure: SaveRoomFailure): string {
  switch (failure.kind) {
    case "room_limit":
      return "이미 등록한 스터디룸이 있어요. 새로고침하면 기존 스터디룸을 수정할 수 있어요.";
    case "validation":
      return failure.message || "입력값을 확인하고 다시 시도해 주세요.";
    case "network":
      return "네트워크 연결이 끊겼어요. 연결되면 다시 시도해 주세요.";
    default:
      return "저장에 실패했어요. 입력값을 확인하고 다시 시도해 주세요.";
  }
}

/** 주소 검색(지오코딩) — provider가 주소를 입력해 좌표·지역 후보를 받는다(roomsGeocodeAddress). */
export function useGeocode() {
  return useMutation<GeocodeResult[], Error, string>({
    mutationFn: async (query: string) => {
      const { data } = await roomsGeocodeAddress({
        query: { query },
        throwOnError: true,
      });
      return (data ?? []) as GeocodeResult[];
    },
  });
}

/**
 * 스터디룸 저장 — 보유 룸이 있으면 PATCH(수정), 없으면 POST(생성). 성공 시 내 룸 쿼리 무효화.
 * 페이로드는 RoomCreateRequest 형상을 공유한다(수정도 같은 필드 전체 전송 — 단순화).
 */
export function useSaveRoom(existingRoomId: string | null) {
  const queryClient = useQueryClient();
  return useMutation<void, SaveRoomError, RoomCreateRequest>({
    mutationFn: async (payload) => {
      try {
        if (existingRoomId) {
          const { error, response } = await roomsUpdateRoom({
            path: { room_id: existingRoomId },
            body: payload,
          });
          if (!response?.ok) {
            throw new SaveRoomError(classifySaveError(response?.status, error));
          }
        } else {
          const { error, response } = await roomsCreateRoom({ body: payload });
          if (!response?.ok) {
            // 등록 경로의 409=ROOM_LIMIT_REACHED(이미 1룸 보유). 그 외는 classify 가 분기.
            throw new SaveRoomError(classifySaveError(response?.status, error));
          }
        }
      } catch (err) {
        // SDK 미응답(네트워크 reject)은 toSaveRoomError 가 network 로 정규화한다.
        throw toSaveRoomError(err);
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MY_ROOM_QUERY_KEY });
    },
  });
}
