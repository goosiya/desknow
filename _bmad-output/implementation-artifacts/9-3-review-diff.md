# Story 9.3 — Review Diff (NO_VCS: full content of all created/modified files)

All paths relative to `apps/mobile/src/`. New files = entire content is added. Modified files: app-tabs.tsx, app-tabs.web.tsx, ChatbotFabSlot.tsx (full current content shown). Deleted: app/provider/room.tsx (9.1 stub, replaced by (tabs)/provider/room.tsx).


=========================================================================
FILE: apps/mobile/src/features/provider/format.ts
=========================================================================
```tsx
// provider 화면 포맷터 — 웹 ProviderReservations/ProviderReviews 추출 복사 (Story 9.3 — AC1·AC3).
//
// 프레임워크 무관 순수 함수(Intl 기반·RN 호환). 웹은 컴포넌트 모듈 내부에 두었던 것을 RN 미러에서
// 재사용하기 위해 feature-local 모듈로 추출했다(중복 인라인 금지). 와이어 시각은 UTC, 표시는 KST.

/** slot_starts(시간당 UTC 시작들) → KST "M월 D일 HH:MM–HH:MM"(첫 시작~마지막 시작+1h). */
export function formatSlots(slotStarts: string[]): string {
  if (slotStarts.length === 0) return "";
  const sorted = [...slotStarts].sort();
  const start = new Date(sorted[0]);
  const lastStart = new Date(sorted[sorted.length - 1]);
  const end = new Date(lastStart.getTime() + 60 * 60 * 1000); // 마지막 슬롯 끝 = 시작+1h
  const date = new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    timeZone: "Asia/Seoul",
  }).format(start);
  const hhmm = (d: Date) =>
    new Intl.DateTimeFormat("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Seoul",
    }).format(d);
  return `${date} ${hhmm(start)}–${hhmm(end)}`;
}

/** KST 날짜(YYYY년 M월 D일). 손상 입력은 빈 문자열(예외/NaN 노출 금지 — ReviewSection 동형). */
export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "Asia/Seoul",
  }).format(date);
}
```

=========================================================================
FILE: apps/mobile/src/features/provider/roomFields.ts
=========================================================================
```tsx
// 룸폼 순수 상수·변환 — 웹 RoomForm.tsx 추출 복사 (Story 9.3 — AC4). 프레임워크 무관(검증 순서는
// RoomForm.tsx 컴포넌트가 동일 순서로 적용). business_hours.weekday 규약 = 월0~일6(서버 동형).

import type { ProviderRoomDetail } from "@/lib/api-client";

/** 요일 라벨 — index = date.weekday()(월=0 … 일=6). 서버 business_hours.weekday 규약과 동일. */
export const WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"] as const;

/** 부대시설 코드(룸폼 토글 — roomSummary.AMENITY_LABELS로 라벨 매핑). */
export const AMENITY_CODES = [
  "wifi",
  "whiteboard",
  "parking",
  "projector_tv",
  "coffee",
  "etc",
] as const;

/** 룸 형태(roomSummary.ROOM_TYPE_LABELS로 라벨 매핑). */
export const ROOM_TYPES = ["open", "private"] as const;

/** 영업시간 입력 한 요일 — on(영업)/open/close("HH:MM"). 제출 시 on인 요일만 페이로드로 변환. */
export type DayHours = { on: boolean; open: string; close: string };

/** "09:00:00" → "09:00"(시간 입력 표시용). */
export function toHHMM(t: string): string {
  return t.slice(0, 5);
}

/** 초기 영업시간 — 보유 룸의 business_hours(영업일만 존재)를 7요일 행으로 펼친다. 없으면 매일 09–22. */
export function initialHours(room: ProviderRoomDetail | null): DayHours[] {
  return WEEKDAYS.map((_, weekday) => {
    const found = room?.business_hours.find((h) => h.weekday === weekday);
    if (found) {
      return { on: true, open: toHHMM(found.open_time), close: toHHMM(found.close_time) };
    }
    // 신규는 매일 09–22 기본, 수정인데 그 요일이 없으면 휴무로.
    return { on: room === null, open: "09:00", close: "22:00" };
  });
}
```

=========================================================================
FILE: apps/mobile/src/features/provider/useProviderReservations.ts
=========================================================================
```tsx
// provider 예약자 현황 + 예약 거부 훅 — 웹 useProviderReservations.ts 미러 (Story 9.3 — AC1·AC2).
//
// 백엔드 호출은 생성 SDK 경유만(1.9 가드). 거부는 백엔드가 슬롯 재활성 + 예약자 통지를 동일
// 트랜잭션 원자 처리한다([[langgraph-failed-turn-input-rollback]]와 무관 — 6.2 거절 원자성).
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import {
  reservationsListProviderReservations,
  reservationsRejectReservation,
} from "@/lib/api-client";
import {
  INITIAL_CURSOR,
  flattenPages,
  getNextCursorParam,
} from "@/lib/pagination";

export const PROVIDER_RESERVATIONS_QUERY_KEY = ["provider", "reservations"];

/**
 * 내 스터디룸의 확정 예약 목록(예약자는 익명 라벨 — [[anonymous-booker-label-no-display-name]]).
 *
 * 커서 페이징(`useInfiniteQuery`) — `select` 평탄화로 `data`는 `ProviderReservationItem[]`.
 * FlatList `onEndReached`는 `fetchNextPage`·`hasNextPage`로 구동(웹 sentinel의 RN 등가).
 */
export function useProviderReservations() {
  return useInfiniteQuery({
    queryKey: PROVIDER_RESERVATIONS_QUERY_KEY,
    initialPageParam: INITIAL_CURSOR,
    queryFn: async ({ pageParam }) => {
      const { data } = await reservationsListProviderReservations({
        query: { cursor: pageParam ?? undefined },
        throwOnError: true,
      });
      return data ?? { items: [], next_cursor: null };
    },
    getNextPageParam: getNextCursorParam,
    select: flattenPages,
  });
}

/** 예약 거부 — 성공 시 목록 무효화(슬롯 재활성·예약자 통지는 백엔드가 처리). 옵티미스틱 없음. */
export function useRejectReservation() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: async (reservationId: string) => {
      const { response } = await reservationsRejectReservation({
        path: { reservation_id: reservationId },
      });
      if (!response?.ok) throw new Error("예약 거부에 실패했어요.");
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: PROVIDER_RESERVATIONS_QUERY_KEY,
      });
    },
  });
}
```

=========================================================================
FILE: apps/mobile/src/features/provider/useProviderRoom.ts
=========================================================================
```tsx
// provider 스터디룸 등록/수정 훅 — 웹 useProviderRoom.ts 미러 (Story 9.3 — AC4).
//
// 백엔드 호출은 생성 SDK 경유만(직접 fetch 금지 — 1.9 가드). 본인 룸 조회는 404를 "아직 등록
// 안 함"(생성 모드)으로 정규화하고, 저장은 보유 여부에 따라 생성(POST)/수정(PATCH)을 가른다.
// 에러 분류(SaveRoomFailure·classifySaveError·saveRoomErrorCopy)는 프레임워크 무관 — 웹 그대로 복사.
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
 * 페이로드는 RoomCreateRequest 형상을 공유한다(수정도 같은 필드 전체 전송 — 단순화). 옵티미스틱 없음.
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
```

=========================================================================
FILE: apps/mobile/src/features/provider/useProviderReviews.ts
=========================================================================
```tsx
// provider 후기 보기 + 답글 훅 — 웹 useProviderReviews.ts 미러 (Story 9.3 — AC3).
//
// 후기는 룸 단위라 내 룸(useMyRoom)의 room_id로 조회한다. 답글은 reviewsCreateReply. 백엔드 호출은
// 생성 SDK 경유만(1.9 가드). 후기 키는 룸 상세(useRoomReviews)와 **동일**(roomReviewsKey)이라
// 캐시를 공유한다 — 답글 작성 후 양쪽(상세·provider)이 정확 invalidate된다.
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import { reviewsCreateReply, reviewsListRoomReviews } from "@/lib/api-client";
import { roomReviewsKey } from "@/features/detail/useRoomReviews";
import {
  INITIAL_CURSOR,
  flattenPages,
  getNextCursorParam,
} from "@/lib/pagination";

import { useMyRoom } from "./useProviderRoom";

/**
 * 내 룸 후기 목록(내 룸이 없으면 비활성). 내 room_id도 함께 노출(답글 무효화 키용).
 *
 * 커서 페이징(`useInfiniteQuery`) — `select` 평탄화로 `reviews`는 평탄 배열. 룸 상세 후기
 * (useRoomReviews)와 같은 키(roomReviewsKey)·엔드포인트라 캐시를 공유한다.
 */
export function useProviderReviews() {
  const myRoom = useMyRoom();
  const roomId = myRoom.data?.room_id ?? "";
  const reviews = useInfiniteQuery({
    queryKey: roomReviewsKey(roomId),
    enabled: roomId !== "",
    initialPageParam: INITIAL_CURSOR,
    queryFn: async ({ pageParam }) => {
      const { data } = await reviewsListRoomReviews({
        path: { room_id: roomId },
        query: { cursor: pageParam ?? undefined },
        throwOnError: true,
      });
      return data ?? { items: [], next_cursor: null };
    },
    getNextPageParam: getNextCursorParam,
    select: flattenPages,
  });
  return {
    roomId,
    hasRoom: myRoom.isSuccess && myRoom.data !== null,
    isLoading: myRoom.isLoading || reviews.isLoading,
    isError: myRoom.isError || reviews.isError,
    reviews: reviews.data ?? [],
    fetchNextPage: reviews.fetchNextPage,
    hasNextPage: reviews.hasNextPage,
    isFetchingNextPage: reviews.isFetchingNextPage,
  };
}

/** 후기 답글 작성 — 성공 시 해당 룸 후기 목록 무효화(답글이 붙은 채 갱신). 옵티미스틱 없음. */
export function useReplyToReview(roomId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, Error, { reviewId: string; text: string }>({
    mutationFn: async ({ reviewId, text }) => {
      const { response } = await reviewsCreateReply({
        path: { review_id: reviewId },
        body: { text },
      });
      if (!response?.ok) throw new Error("답글 작성에 실패했어요.");
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: roomReviewsKey(roomId) });
    },
  });
}
```

=========================================================================
FILE: apps/mobile/src/features/provider/ProviderReservations.tsx
=========================================================================
```tsx
import { useState } from "react";
import { FlatList, Pressable, StyleSheet, View } from "react-native";

import { NetworkNotice } from "@/components/NetworkNotice";
import { ThemedText } from "@/components/themed-text";
import { Colors, Radius, Spacing } from "@/constants/theme";
import { useOnlineStatus } from "@/lib/useOnlineStatus";
import { InfoCard, RetryCard } from "@/features/list/ListStates";
import type { ProviderReservationItem } from "@/lib/api-client";

import { formatSlots } from "./format";
import {
  useProviderReservations,
  useRejectReservation,
} from "./useProviderReservations";

// provider 예약자 현황 — 웹 ProviderReservations.tsx RN 포팅 (Story 9.3 — AC1·AC2). 내 스터디룸의
// 확정 예약을 보고, 예외 예약을 2단 확인으로 거부한다(거부 시 해당 시간 재활성·예약자 통지는 백엔드
// 원자 처리). 예약자는 익명 라벨로만 보인다([[anonymous-booker-label-no-display-name]]). 인증/콜드
// 단절은 ProviderGuard가 막고, 이 화면은 데이터 5상태(로딩/에러/빈/단절/목록)를 일관 처리한다.

/** 상태 배지(확정/거부됨/취소됨) — 색+텍스트 동반(색 단독 금지). */
function StatusBadge({ status }: { status: string }) {
  const isConfirmed = status === "confirmed";
  const label = isConfirmed ? "확정" : status === "rejected" ? "거부됨" : "취소됨";
  return (
    <View style={[styles.badge, isConfirmed ? styles.badgeConfirmed : styles.badgeMuted]}>
      <ThemedText
        type="caption"
        themeColor={isConfirmed ? "secondaryForeground" : "textSecondary"}
        style={styles.bold}
      >
        {label}
      </ThemedText>
    </View>
  );
}

/** 예약 행 — 익명 라벨·상태 배지·시간범위 + 확정 행만 2단 확인 거부. */
function ReservationRow({ item }: { item: ProviderReservationItem }) {
  const reject = useRejectReservation();
  const [confirming, setConfirming] = useState(false);
  const isConfirmed = item.status === "confirmed";

  return (
    <View style={styles.card}>
      <View style={styles.rowBetween}>
        <View style={styles.rowInfo}>
          <ThemedText type="label" themeColor="cardForeground">
            {item.room_name}
          </ThemedText>
          <ThemedText type="bodySm" themeColor="textSecondary">
            {formatSlots(item.slot_starts)}
          </ThemedText>
          <ThemedText type="caption" themeColor="textSecondary">
            예약자 {item.booker_label}
          </ThemedText>
        </View>
        <StatusBadge status={item.status} />
      </View>

      {isConfirmed ? (
        confirming ? (
          <View style={styles.confirmBox}>
            <ThemedText type="bodySm" themeColor="textSecondary">
              이 예약을 거부하면 해당 시간이 다시 열리고 예약자에게 통지돼요. 거부할까요?
            </ThemedText>
            <View style={styles.actionRow}>
              <Pressable
                onPress={() =>
                  reject.mutate(item.id, { onSuccess: () => setConfirming(false) })
                }
                disabled={reject.isPending}
                accessibilityRole="button"
                style={[styles.destructiveButton, reject.isPending && styles.disabled]}
              >
                <ThemedText type="label" themeColor="primaryForeground">
                  {reject.isPending ? "처리 중…" : "거부"}
                </ThemedText>
              </Pressable>
              <Pressable
                onPress={() => setConfirming(false)}
                disabled={reject.isPending}
                accessibilityRole="button"
                style={[styles.outlineButton, reject.isPending && styles.disabled]}
              >
                <ThemedText type="label" themeColor="cardForeground">
                  취소
                </ThemedText>
              </Pressable>
            </View>
          </View>
        ) : (
          <Pressable
            onPress={() => setConfirming(true)}
            accessibilityRole="button"
            style={styles.outlineButtonSelf}
          >
            <ThemedText type="label" themeColor="cardForeground">
              예약 거부
            </ThemedText>
          </Pressable>
        )
      ) : null}

      {reject.isError ? (
        <ThemedText type="bodySm" themeColor="destructive">
          거부에 실패했어요. 잠시 후 다시 시도해 주세요.
        </ThemedText>
      ) : null}
    </View>
  );
}

/** 화면 헤더(제목 + 설명) — 목록 위 고정. */
function Header() {
  return (
    <View style={styles.header}>
      <ThemedText type="h2" themeColor="text">
        예약자 현황
      </ThemedText>
      <ThemedText type="bodySm" themeColor="textSecondary">
        내 스터디룸의 확정 예약이에요. 예외 상황이면 예약을 거부할 수 있어요(해당 시간이 다시 열려요).
      </ThemedText>
    </View>
  );
}

export function ProviderReservations() {
  const {
    data,
    isLoading,
    isError,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useProviderReservations();
  const isOnline = useOnlineStatus();

  // 네트워크 단절(로그인됨) — 캐시된 목록이 있으면 배너 + 행, 없으면 배너만(에러보다 우선).
  if (!isOnline && (!data || data.length === 0)) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <NetworkNotice />
      </View>
    );
  }

  if (isLoading) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <ThemedText type="bodySm" themeColor="textSecondary">
          불러오는 중…
        </ThemedText>
      </View>
    );
  }

  if (isError) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <RetryCard
          title="예약을 불러오지 못했어요. 잠시 후 다시 시도해 주세요."
          onRetry={() => refetch()}
        />
      </View>
    );
  }

  if (!data || data.length === 0) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <InfoCard text="아직 들어온 예약이 없어요." />
      </View>
    );
  }

  return (
    <FlatList
      data={data}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => <ReservationRow item={item} />}
      ListHeaderComponent={
        <View>
          <Header />
          {!isOnline ? <NetworkNotice style={styles.notice} /> : null}
        </View>
      }
      contentContainerStyle={styles.listContent}
      onEndReachedThreshold={0.5}
      onEndReached={() => {
        if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
      }}
      ListFooterComponent={
        isFetchingNextPage ? (
          <ThemedText type="bodySm" themeColor="textSecondary" style={styles.footer}>
            불러오는 중…
          </ThemedText>
        ) : null
      }
    />
  );
}

const styles = StyleSheet.create({
  stateWrap: { gap: Spacing[3] },
  header: { gap: Spacing[1] },
  listContent: { gap: Spacing[2], paddingBottom: Spacing[6] },
  notice: { marginTop: Spacing[2] },
  footer: { textAlign: "center", paddingVertical: Spacing[3] },
  card: {
    gap: Spacing[2],
    padding: Spacing[4],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  rowBetween: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: Spacing[3],
  },
  rowInfo: { flex: 1, gap: 2 },
  bold: { fontWeight: "600" },
  badge: {
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[1],
    borderRadius: Radius.full,
  },
  badgeConfirmed: { backgroundColor: Colors.light.secondary },
  badgeMuted: { backgroundColor: Colors.light.backgroundElement },
  confirmBox: {
    gap: Spacing[2],
    padding: Spacing[3],
    borderRadius: Radius.md,
    backgroundColor: Colors.light.backgroundElement,
  },
  actionRow: { flexDirection: "row", gap: Spacing[2] },
  destructiveButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    backgroundColor: Colors.light.destructive,
  },
  outlineButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  outlineButtonSelf: {
    minHeight: 44,
    alignSelf: "flex-start",
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  disabled: { opacity: 0.5 },
});
```

=========================================================================
FILE: apps/mobile/src/features/provider/ProviderReviews.tsx
=========================================================================
```tsx
import { useState } from "react";
import { FlatList, Pressable, StyleSheet, TextInput, View } from "react-native";

import { NetworkNotice } from "@/components/NetworkNotice";
import { ThemedText } from "@/components/themed-text";
import { Colors, Radius, Spacing } from "@/constants/theme";
import { useOnlineStatus } from "@/lib/useOnlineStatus";
import { InfoCard } from "@/features/list/ListStates";
import { StarRating } from "@/features/detail/StarRating";
import type { ReviewListItem } from "@/lib/api-client";

import { formatDate } from "./format";
import { useProviderReviews, useReplyToReview } from "./useProviderReviews";

// provider 후기 보기 + 답글 — 웹 ProviderReviews.tsx RN 포팅 (Story 9.3 — AC3). 내 스터디룸 후기를
// 보고 답글을 단다. 답글이 이미 있으면 "사장님 답글" read-only(9.2 ReviewSection 답글 렌더와 일관),
// 없으면 작성 폼. 후기 키는 룸 상세와 공유(roomReviewsKey) — 작성 후 양쪽 갱신. 별점은 9.2 StarRating.

/** 답글 작성 폼 — RN TextInput multiline(웹 textarea 대체)·최대 500자. */
function ReviewReplyForm({ reviewId, roomId }: { reviewId: string; roomId: string }) {
  const reply = useReplyToReview(roomId);
  const [text, setText] = useState("");
  const canSubmit = !reply.isPending && text.trim().length > 0;

  return (
    <View style={styles.form}>
      <TextInput
        value={text}
        onChangeText={setText}
        multiline
        maxLength={500}
        placeholder="답글을 남겨보세요(최대 500자)"
        placeholderTextColor={Colors.light.textSecondary}
        accessibilityLabel="답글 입력"
        style={styles.input}
      />
      <View style={styles.formActions}>
        <Pressable
          onPress={() => reply.mutate({ reviewId, text: text.trim() })}
          disabled={!canSubmit}
          accessibilityRole="button"
          style={[styles.primaryButton, !canSubmit && styles.disabled]}
        >
          <ThemedText type="label" themeColor="primaryForeground">
            {reply.isPending ? "등록 중…" : "답글 등록"}
          </ThemedText>
        </Pressable>
        {reply.isError ? (
          <ThemedText type="bodySm" themeColor="destructive">
            등록에 실패했어요.
          </ThemedText>
        ) : null}
      </View>
    </View>
  );
}

/** 후기 한 건 — 별점 + 작성일 + 텍스트 + (있으면) 사장님 답글 read-only / (없으면) 작성 폼. */
function ReviewCard({ review, roomId }: { review: ReviewListItem; roomId: string }) {
  return (
    <View style={styles.card}>
      <View style={styles.rowBetween}>
        <StarRating rating={review.rating} />
        <ThemedText type="caption" themeColor="textSecondary">
          {formatDate(review.created_at)}
        </ThemedText>
      </View>
      <ThemedText type="bodySm" themeColor="cardForeground">
        {review.text}
      </ThemedText>

      {review.reply ? (
        // 이미 답글 있음 — read-only(9.2 ReviewSection 답글 렌더와 일관).
        <View style={styles.reply}>
          <ThemedText type="caption" themeColor="text" style={styles.bold}>
            사장님 답글
          </ThemedText>
          <ThemedText type="bodySm" themeColor="cardForeground">
            {review.reply.text}
          </ThemedText>
        </View>
      ) : (
        <ReviewReplyForm reviewId={review.id} roomId={roomId} />
      )}
    </View>
  );
}

/** 화면 헤더(제목 + 설명). */
function Header() {
  return (
    <View style={styles.header}>
      <ThemedText type="h2" themeColor="text">
        후기
      </ThemedText>
      <ThemedText type="bodySm" themeColor="textSecondary">
        내 스터디룸에 달린 후기를 보고 답글을 남길 수 있어요.
      </ThemedText>
    </View>
  );
}

export function ProviderReviews() {
  const {
    roomId,
    hasRoom,
    isLoading,
    isError,
    reviews,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useProviderReviews();
  const isOnline = useOnlineStatus();

  if (!isOnline && reviews.length === 0) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <NetworkNotice />
      </View>
    );
  }

  if (isLoading) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <ThemedText type="bodySm" themeColor="textSecondary">
          불러오는 중…
        </ThemedText>
      </View>
    );
  }

  if (isError) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <ThemedText type="bodySm" themeColor="destructive">
          후기를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.
        </ThemedText>
      </View>
    );
  }

  if (!hasRoom) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <InfoCard text="먼저 스터디룸을 등록하면 후기를 받을 수 있어요." />
      </View>
    );
  }

  if (reviews.length === 0) {
    return (
      <View style={styles.stateWrap}>
        <Header />
        <InfoCard text="아직 후기가 없어요." />
      </View>
    );
  }

  return (
    <FlatList
      data={reviews}
      keyExtractor={(r) => r.id}
      renderItem={({ item }) => <ReviewCard review={item} roomId={roomId} />}
      ListHeaderComponent={
        <View>
          <Header />
          {!isOnline ? <NetworkNotice style={styles.notice} /> : null}
        </View>
      }
      contentContainerStyle={styles.listContent}
      keyboardShouldPersistTaps="handled"
      onEndReachedThreshold={0.5}
      onEndReached={() => {
        if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
      }}
      ListFooterComponent={
        isFetchingNextPage ? (
          <ThemedText type="bodySm" themeColor="textSecondary" style={styles.footer}>
            불러오는 중…
          </ThemedText>
        ) : null
      }
    />
  );
}

const styles = StyleSheet.create({
  stateWrap: { gap: Spacing[3] },
  header: { gap: Spacing[1] },
  listContent: { gap: Spacing[2], paddingBottom: Spacing[6] },
  notice: { marginTop: Spacing[2] },
  footer: { textAlign: "center", paddingVertical: Spacing[3] },
  card: {
    gap: Spacing[3],
    padding: Spacing[4],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  rowBetween: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: Spacing[2],
  },
  bold: { fontWeight: "600" },
  reply: {
    gap: Spacing[1],
    marginLeft: Spacing[3],
    paddingVertical: Spacing[2],
    paddingLeft: Spacing[3],
    paddingRight: Spacing[2],
    borderLeftWidth: 2,
    borderLeftColor: Colors.light.primary,
    borderRadius: Radius.md,
    backgroundColor: Colors.light.backgroundElement,
  },
  form: { gap: Spacing[2] },
  input: {
    minHeight: 64,
    borderWidth: 1,
    borderColor: Colors.light.border,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
    fontSize: 14,
    lineHeight: 22,
    color: Colors.light.cardForeground,
    backgroundColor: Colors.light.background,
    textAlignVertical: "top",
  },
  formActions: { flexDirection: "row", alignItems: "center", gap: Spacing[2] },
  primaryButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  disabled: { opacity: 0.5 },
});
```

=========================================================================
FILE: apps/mobile/src/features/provider/RoomForm.tsx
=========================================================================
```tsx
import { useState } from "react";
import { Platform, Pressable, StyleSheet, TextInput, View } from "react-native";
import { router, type Href } from "expo-router";

import { ThemedText } from "@/components/themed-text";
import { ComboSelect, type ComboOption } from "@/components/ComboSelect";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Colors, Radius, Spacing } from "@/constants/theme";
import { AMENITY_LABELS, ROOM_TYPE_LABELS } from "@/features/map/roomSummary";
import { RoomLocationMap } from "@/features/detail/RoomLocationMap";
import { registerErrorCopy } from "@/features/auth/authCopy";
import {
  clearPendingSignup,
  getPendingSignup,
  type PendingSignup,
} from "@/features/auth/pendingSignup";
import { useRegister } from "@/features/auth/useAuth";
import type {
  GeocodeResult,
  ProviderRoomDetail,
  RoomCreateRequest,
} from "@/lib/api-client";

import { GeocoderWebView } from "./GeocoderWebView";
import {
  AMENITY_CODES,
  ROOM_TYPES,
  WEEKDAYS,
  initialHours,
  type DayHours,
} from "./roomFields";
import {
  saveRoomErrorCopy,
  useGeocode,
  useMyRoom,
  useSaveRoom,
} from "./useProviderRoom";

// 스터디룸 등록/수정 폼 — 웹 RoomForm.tsx RN 포팅 (Story 9.3 — AC4·§범위 2). 이름·주소검색(지오코딩)·
// 수용·시간당 금액·룸형태·부대시설·영업시간을 입력해 저장한다. 보유 룸이 있으면 prefill(수정), 없으면
// 생성. 가입 전(pendingSignup)이면 저장이 회원가입→룸 생성을 원자 처리한다(떠도는 계정 방지). 백엔드
// 호출은 생성 SDK 경유 훅(useProviderRoom)만. 지오코딩은 로그인=백엔드 geocode / 가입 전=WebView 카카오.

// 영업시간 선택지 — 30분 단위 "HH:MM"(RN엔 <input type=time>이 없어 ComboSelect로 대체·무효입력 방지·
// 분 정밀·Expo Web 호환). 그리드 밖 값(예: 보유 룸 09:15)은 선택지에 없어도 저장값은 보존된다.
const TIME_OPTIONS: ComboOption[] = Array.from({ length: 48 }, (_, i) => {
  const hh = String(Math.floor(i / 2)).padStart(2, "0");
  const mm = i % 2 === 0 ? "00" : "30";
  const v = `${hh}:${mm}`;
  return { value: v, label: v };
});

const ROOM_TYPE_OPTIONS = ROOM_TYPES.map((t) => ({
  value: t,
  label: ROOM_TYPE_LABELS[t],
}));

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <ThemedText type="label" themeColor="text">
      {children}
    </ThemedText>
  );
}

function RoomFormInner({
  initial,
  pendingSignup,
}: {
  initial: ProviderRoomDetail | null;
  pendingSignup: PendingSignup | null;
}) {
  const geocode = useGeocode();
  const save = useSaveRoom(initial?.room_id ?? null);
  const register = useRegister();

  const [name, setName] = useState(initial?.name ?? "");
  // 신규 등록은 빈 값 + placeholder(기본값 미리 넣지 않음 — KTH 2026-06-19). 수정은 기존값 prefill.
  const [capacity, setCapacity] = useState(initial ? String(initial.capacity) : "");
  const [price, setPrice] = useState(initial ? String(initial.price_per_hour) : "");
  const [roomType, setRoomType] = useState<string>(initial?.room_type ?? "open");
  const [amenities, setAmenities] = useState<Set<string>>(
    new Set(initial?.amenities ?? ["wifi"]),
  );
  const [hours, setHours] = useState<DayHours[]>(() => initialHours(initial));

  // 주소(지오코딩으로 확정) — 좌표·지역은 직접 못 넣고 검색 결과 선택으로만 채운다.
  const [query, setQuery] = useState(initial?.address ?? "");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [noUsable, setNoUsable] = useState(false); // 결과는 있으나 등록불가(b_code 없음)
  const [noResults, setNoResults] = useState(false); // 0건(못 찾음)
  const [picked, setPicked] = useState<GeocodeResult | null>(
    initial
      ? {
          address: initial.address ?? "",
          lat: initial.lat,
          lng: initial.lng,
          admin_dong_code: initial.admin_dong_code,
        }
      : null,
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);
  // 가입 전 WebView 지오코더 검색 트리거(nonce 증가 = 검색 실행).
  const [geocodeNonce, setGeocodeNonce] = useState(0);

  function toggleAmenity(code: string) {
    setAmenities((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  function setDay(i: number, patch: Partial<DayHours>) {
    setHours((prev) => prev.map((d, idx) => (idx === i ? { ...d, ...patch } : d)));
  }

  /** 지오코딩 결과(로그인 백엔드/가입 전 WebView 공통)를 usable 필터·상태에 반영한다(웹 runGeocode 동형). */
  function applyGeocodeResults(all: GeocodeResult[]) {
    // 등록엔 지역 코드가 필수 — 도로명만(b_code 없는) 결과는 거른다. 0건과 "결과 있으나 등록불가"를 구분.
    const usable = all.filter((r) => r.admin_dong_code);
    setResults(usable);
    setNoResults(all.length === 0);
    setNoUsable(all.length > 0 && usable.length === 0);
    if (usable.length === 0) setPicked(null);
  }

  async function runGeocode() {
    if (!query.trim() || searching) return;
    // 새 검색마다 이전 결과·안내를 비운다(옛 후보 잔존 방지).
    setResults([]);
    setNoUsable(false);
    setNoResults(false);
    setSearchFailed(false);
    setSearching(true);
    if (pendingSignup) {
      // 가입 전: 미인증이라 백엔드 geocode 불가 → WebView 카카오 Geocoder(nonce 트리거·결과는 콜백).
      // Expo Web은 react-native-webview 미지원 → 즉시 graceful degrade(검증 불가 인지·맵 동형).
      if (Platform.OS === "web") {
        setSearching(false);
        setSearchFailed(true);
        return;
      }
      setGeocodeNonce((n) => n + 1); // onResults/onError가 setSearching(false) 마무리
      return;
    }
    // 로그인 provider: 백엔드 geocode(provider 전용·Expo Web 동작).
    try {
      const all = await geocode.mutateAsync(query.trim());
      applyGeocodeResults(all);
    } catch {
      setSearchFailed(true);
    } finally {
      setSearching(false);
    }
  }

  function selectResult(r: GeocodeResult) {
    setPicked(r);
    setQuery(r.address);
    setResults([]);
    setNoUsable(false);
    setNoResults(false);
  }

  function submit() {
    setFormError(null);
    if (!name.trim()) {
      setFormError("스터디룸 이름을 입력해 주세요.");
      return;
    }
    if (!picked) {
      setFormError("주소를 검색해 선택해 주세요.");
      return;
    }
    const capacityNum = Number(capacity);
    if (!capacity.trim() || !Number.isInteger(capacityNum) || capacityNum < 1) {
      setFormError("수용 인원을 1명 이상 입력해 주세요.");
      return;
    }
    const priceNum = Number(price);
    if (!price.trim() || !Number.isInteger(priceNum) || priceNum < 0) {
      setFormError("시간당 금액을 0원 이상 정수로 입력해 주세요.");
      return;
    }
    if (!roomType) {
      setFormError("룸 형태를 선택해 주세요.");
      return;
    }
    const businessHours = hours
      .map((d, weekday) => ({ d, weekday }))
      .filter(({ d }) => d.on)
      .map(({ d, weekday }) => ({
        weekday,
        open_time: `${d.open}:00`,
        close_time: `${d.close}:00`,
      }));
    if (businessHours.length === 0) {
      setFormError("영업하는 요일을 하나 이상 선택해 주세요.");
      return;
    }
    if (businessHours.some((b) => b.close_time <= b.open_time)) {
      setFormError("영업 종료 시각은 시작 시각보다 늦어야 해요.");
      return;
    }
    const payload: RoomCreateRequest = {
      name: name.trim(),
      price_per_hour: Number(price),
      capacity: Number(capacity),
      room_type: roomType as RoomCreateRequest["room_type"],
      amenities: [...amenities] as RoomCreateRequest["amenities"],
      lat: picked.lat,
      lng: picked.lng,
      admin_dong_code: picked.admin_dong_code,
      address: picked.address,
      business_hours: businessHours,
    };
    const goProvider = () => router.replace("/provider/reservations" as Href);
    if (pendingSignup) {
      // 가입 대기: 회원가입(→자동 로그인) 성공 후에만 룸을 생성(원자 처리). 가입 실패면 룸 미생성.
      register.mutate(
        { email: pendingSignup.email, password: pendingSignup.password, role: "provider" },
        {
          onSuccess: () => {
            save.mutate(payload, {
              onSuccess: () => {
                clearPendingSignup();
                goProvider();
              },
            });
          },
        },
      );
      return;
    }
    save.mutate(payload, { onSuccess: goProvider });
  }

  const submitting = save.isPending || register.isPending;
  const submitLabel = submitting
    ? "처리 중…"
    : pendingSignup
      ? "가입하고 등록하기"
      : initial
        ? "수정 저장"
        : "등록하기";
  const errorCopy = formError
    ? formError
    : save.error
      ? saveRoomErrorCopy(save.error.failure)
      : register.error
        ? registerErrorCopy(register.error.failure)
        : null;

  return (
    <View style={styles.wrap}>
      {/* 가입 전 WebView 지오코더(보이지 않음) — 네이티브에서만 실동작(웹 degrade). */}
      {pendingSignup ? (
        <GeocoderWebView
          query={query.trim()}
          nonce={geocodeNonce}
          onResults={(all) => {
            applyGeocodeResults(all);
            setSearching(false);
          }}
          onError={() => {
            setSearchFailed(true);
            setSearching(false);
          }}
        />
      ) : null}

      <View style={styles.header}>
        <ThemedText type="h2" themeColor="text">
          {initial ? "스터디룸 수정" : "스터디룸 등록"}
        </ThemedText>
        <ThemedText type="bodySm" themeColor="textSecondary">
          MVP에서는 제공자당 한 개의 스터디룸을 등록할 수 있어요.
        </ThemedText>
        {pendingSignup ? (
          <ThemedText type="caption" themeColor="destructive" style={styles.bold}>
            이 정보를 등록하면 회원가입이 함께 완료돼요.
          </ThemedText>
        ) : null}
      </View>

      {/* 이름 */}
      <View style={styles.field}>
        <FieldLabel>스터디룸 이름</FieldLabel>
        <TextInput
          value={name}
          onChangeText={setName}
          placeholder="예: 미사 스터디카페 A룸"
          placeholderTextColor={Colors.light.textSecondary}
          style={styles.input}
        />
      </View>

      {/* 주소 검색 */}
      <View style={styles.field}>
        <View style={styles.labelRow}>
          <FieldLabel>주소</FieldLabel>
          <ThemedText type="caption" themeColor="destructive" style={styles.bold}>
            정확하지 않으면 지도에 안 보여요
          </ThemedText>
        </View>
        <View style={styles.searchRow}>
          <TextInput
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => void runGeocode()}
            placeholder="도로명·지번 주소 검색"
            placeholderTextColor={Colors.light.textSecondary}
            style={[styles.input, styles.searchInput]}
          />
          <Pressable
            onPress={() => void runGeocode()}
            disabled={searching}
            accessibilityRole="button"
            accessibilityLabel="주소 검색"
            style={[styles.outlineButton, searching && styles.disabled]}
          >
            <ThemedText type="label" themeColor="cardForeground">
              {searching ? "검색 중" : "검색"}
            </ThemedText>
          </Pressable>
        </View>

        {/* 선택된 주소 + 위치 미니 지도(9.2 RoomLocationMap 재사용 — Expo Web degrade). */}
        {picked ? (
          <View style={styles.field}>
            <ThemedText type="bodySm" themeColor="text">
              📍 {picked.address}
            </ThemedText>
            <RoomLocationMap lat={picked.lat} lng={picked.lng} name={picked.address} />
          </View>
        ) : null}

        {/* 검색 결과 후보 — "선택"하라고 명시. */}
        {results.length > 0 ? (
          <View style={styles.resultsBox}>
            <ThemedText type="bodySm" themeColor="textSecondary">
              검색된 주소예요. 아래에서 정확한 주소를 선택해 주세요.
            </ThemedText>
            {results.map((r) => (
              <Pressable
                key={`${r.lat},${r.lng},${r.address}`}
                onPress={() => selectResult(r)}
                accessibilityRole="button"
                style={styles.resultItem}
              >
                <ThemedText type="bodySm" themeColor="cardForeground">
                  📍 {r.address}
                </ThemedText>
              </Pressable>
            ))}
          </View>
        ) : null}

        {noResults ? (
          <ThemedText type="bodySm" themeColor="textSecondary">
            검색 결과가 없어요. 지번 또는 도로명 주소(번지 포함)로 다시 검색해 주세요.
          </ThemedText>
        ) : null}
        {noUsable ? (
          <ThemedText type="bodySm" themeColor="textSecondary">
            번지까지 포함한 구체적인 주소로 검색해 주세요(도로명만으로는 등록할 수 없어요).
          </ThemedText>
        ) : null}
        {searchFailed ? (
          <ThemedText type="bodySm" themeColor="destructive">
            주소 검색에 실패했어요. 다시 시도해 주세요.
          </ThemedText>
        ) : null}
      </View>

      {/* 수용 인원 · 시간당 금액 */}
      <View style={styles.twoCol}>
        <View style={[styles.field, styles.flex1]}>
          <FieldLabel>수용 인원</FieldLabel>
          <TextInput
            value={capacity}
            onChangeText={setCapacity}
            keyboardType="number-pad"
            placeholder="예: 4"
            placeholderTextColor={Colors.light.textSecondary}
            style={styles.input}
          />
        </View>
        <View style={[styles.field, styles.flex1]}>
          <FieldLabel>시간당 금액(원)</FieldLabel>
          <TextInput
            value={price}
            onChangeText={setPrice}
            keyboardType="number-pad"
            placeholder="예: 10000"
            placeholderTextColor={Colors.light.textSecondary}
            style={styles.input}
          />
        </View>
      </View>

      {/* 룸 형태 */}
      <View style={styles.field}>
        <FieldLabel>룸 형태</FieldLabel>
        <SegmentedControl
          accessibilityLabel="룸 형태 선택"
          variant="radio"
          value={roomType}
          onChange={setRoomType}
          options={ROOM_TYPE_OPTIONS}
        />
      </View>

      {/* 부대시설 */}
      <View style={styles.field}>
        <FieldLabel>부대시설</FieldLabel>
        <View style={styles.chipRow}>
          {AMENITY_CODES.map((code) => {
            const active = amenities.has(code);
            return (
              <Pressable
                key={code}
                onPress={() => toggleAmenity(code)}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: active }}
                accessibilityLabel={AMENITY_LABELS[code]}
                style={[styles.chip, active ? styles.chipActive : styles.chipInactive]}
              >
                <ThemedText type="bodySm" themeColor={active ? "text" : "textSecondary"}>
                  {AMENITY_LABELS[code]}
                </ThemedText>
              </Pressable>
            );
          })}
        </View>
      </View>

      {/* 영업시간 */}
      <View style={styles.field}>
        <FieldLabel>영업시간</FieldLabel>
        <View style={styles.hoursList}>
          {hours.map((d, i) => (
            <View key={WEEKDAYS[i]} style={styles.hourRow}>
              <Pressable
                onPress={() => setDay(i, { on: !d.on })}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: d.on }}
                accessibilityLabel={`${WEEKDAYS[i]}요일 영업`}
                style={styles.dayToggle}
              >
                <View style={[styles.checkbox, d.on && styles.checkboxOn]}>
                  {d.on ? (
                    <ThemedText type="caption" themeColor="primaryForeground">
                      ✓
                    </ThemedText>
                  ) : null}
                </View>
                <ThemedText type="bodySm" themeColor="text">
                  {WEEKDAYS[i]}
                </ThemedText>
              </Pressable>
              {d.on ? (
                <View style={styles.timeRow}>
                  <ComboSelect
                    accessibilityLabel={`${WEEKDAYS[i]}요일 영업 시작 시각`}
                    placeholder="시작"
                    value={d.open}
                    options={TIME_OPTIONS}
                    onChange={(v) => setDay(i, { open: v })}
                  />
                  <ThemedText type="bodySm" themeColor="textSecondary">
                    –
                  </ThemedText>
                  <ComboSelect
                    accessibilityLabel={`${WEEKDAYS[i]}요일 영업 종료 시각`}
                    placeholder="종료"
                    value={d.close}
                    options={TIME_OPTIONS}
                    onChange={(v) => setDay(i, { close: v })}
                  />
                </View>
              ) : (
                <ThemedText type="bodySm" themeColor="textSecondary">
                  휴무
                </ThemedText>
              )}
            </View>
          ))}
        </View>
      </View>

      {errorCopy ? (
        <View accessibilityRole="alert" style={styles.errorBox}>
          <ThemedText type="bodySm" themeColor="destructive">
            {errorCopy}
          </ThemedText>
        </View>
      ) : null}

      <Pressable
        onPress={submit}
        disabled={submitting}
        accessibilityRole="button"
        style={[styles.submitButton, submitting && styles.disabled]}
      >
        <ThemedText type="label" themeColor="primaryForeground">
          {submitLabel}
        </ThemedText>
      </Pressable>
    </View>
  );
}

/** 로그인된 provider — 내 룸 로드 후 prefill로 렌더(생성/수정 분기). 로드 전엔 안내. */
function ExistingRoomForm() {
  const { data, isLoading, isError } = useMyRoom();
  if (isLoading) {
    return (
      <ThemedText type="bodySm" themeColor="textSecondary">
        불러오는 중…
      </ThemedText>
    );
  }
  if (isError) {
    return (
      <ThemedText type="bodySm" themeColor="destructive">
        내 스터디룸 정보를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.
      </ThemedText>
    );
  }
  return <RoomFormInner initial={data ?? null} pendingSignup={null} />;
}

/** 가입 대기(provider 신규) vs 로그인된 provider 분기 — mount 1회 캡처(ProviderGuard와 동일 패턴). */
export function RoomForm() {
  const [pending] = useState(() => getPendingSignup());
  if (pending) {
    return <RoomFormInner initial={null} pendingSignup={pending} />;
  }
  return <ExistingRoomForm />;
}

const styles = StyleSheet.create({
  wrap: { gap: Spacing[5] },
  header: { gap: Spacing[1] },
  bold: { fontWeight: "600" },
  field: { gap: Spacing[2] },
  flex1: { flex: 1 },
  labelRow: { flexDirection: "row", flexWrap: "wrap", alignItems: "baseline", gap: Spacing[2] },
  input: {
    minHeight: 44,
    borderWidth: 1,
    borderColor: Colors.light.border,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing[3],
    fontSize: 14,
    color: Colors.light.text,
    backgroundColor: Colors.light.background,
  },
  searchRow: { flexDirection: "row", gap: Spacing[2] },
  searchInput: { flex: 1 },
  outlineButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  resultsBox: {
    gap: Spacing[1],
    borderWidth: 1,
    borderColor: Colors.light.border,
    borderRadius: Radius.md,
    padding: Spacing[3],
    backgroundColor: Colors.light.card,
  },
  resultItem: {
    minHeight: 44,
    justifyContent: "center",
    paddingVertical: Spacing[2],
  },
  twoCol: { flexDirection: "row", gap: Spacing[3] },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: Spacing[2] },
  chip: {
    minHeight: 36,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
    borderRadius: Radius.full,
    borderWidth: 1,
    justifyContent: "center",
  },
  chipActive: { borderColor: Colors.light.primary, backgroundColor: Colors.light.secondary },
  chipInactive: { borderColor: Colors.light.border, backgroundColor: Colors.light.background },
  hoursList: { gap: Spacing[2] },
  hourRow: { flexDirection: "row", alignItems: "center", gap: Spacing[3] },
  dayToggle: {
    width: 64,
    flexDirection: "row",
    alignItems: "center",
    gap: Spacing[2],
    minHeight: 44,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.light.border,
    alignItems: "center",
    justifyContent: "center",
  },
  checkboxOn: { backgroundColor: Colors.light.primary, borderColor: Colors.light.primary },
  timeRow: { flexDirection: "row", alignItems: "center", gap: Spacing[2] },
  errorBox: {
    borderWidth: 1,
    borderColor: Colors.light.destructive,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
    backgroundColor: Colors.light.background,
  },
  submitButton: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  disabled: { opacity: 0.5 },
});
```

=========================================================================
FILE: apps/mobile/src/features/provider/GeocoderWebView.tsx
=========================================================================
```tsx
import { useEffect, useRef, useState } from "react";
import { StyleSheet } from "react-native";
import { WebView, type WebViewMessageEvent } from "react-native-webview";

import type { GeocodeResult } from "@/lib/api-client";

// 가입 전(pendingSignup) 주소 검색용 카카오 Geocoder WebView — 웹 geocodeViaKakaoJs RN 대체
// (Story 9.3 — AC4·§범위 2). 가입 전 provider는 백엔드 /rooms/geocode(provider 전용)를 못 쓰므로,
// 9.1 WebView 카카오맵 패턴을 재사용해 `services` 라이브러리를 로드한 **보이지 않는** WebView에서
// `kakao.maps.services.Geocoder().addressSearch`를 돌리고 결과를 백엔드 GeocodeResult 형상으로
// 통일해 postMessage로 RN에 회신한다. WebView는 캔버스/지도가 아니라 지오코딩 브릿지만 담당한다.
//
// ⚠️ Expo Web=react-native-webview 미지원(맵 degrade와 동형) → 가입 전 지오코딩은 Playwright
//    검증 불가(AC9 인지 한계). 네이티브 dev-build에서만 실동작. origin 화이트리스트(baseUrl)는
//    9.1 MapWebView 상수 동형(deferred 회수 후보=env화 EXPO_PUBLIC_KAKAO_WEBVIEW_ORIGIN).

// 카카오 콘솔 등록 WebView origin(JS 키 화이트리스트) — 9.1 MapWebView/RoomLocationMap 동형.
const KAKAO_WEBVIEW_ORIGIN = "http://localhost:3000";

type GeocoderWebViewProps = {
  // 검색어. nonce가 바뀔 때마다 이 query로 addressSearch를 실행한다.
  query: string;
  // 검색 트리거 — RoomForm이 "검색" 누를 때 증가시킨다(0=미실행).
  nonce: number;
  // 검색 결과(GeocodeResult 형상으로 통일됨) — RoomForm이 usable 필터·선택 처리.
  onResults: (results: GeocodeResult[]) => void;
  // SDK 로드/검색 실패 — RoomForm이 graceful 안내("주소 검색에 실패했어요…").
  onError: () => void;
};

/** services 라이브러리 로드 카카오 SDK HTML — window.__search(query)로 addressSearch 실행·결과 회신. */
function buildGeocoderHtml(jsKey: string): string {
  return `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<script src="//dapi.kakao.com/v2/maps/sdk.js?appkey=${jsKey}&autoload=false&libraries=services"></script>
</head>
<body>
<script>
  function post(msg) {
    if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(msg));
  }
  function init() {
    if (!window.kakao || !window.kakao.maps) { post({ type: 'error', message: 'sdk-unavailable' }); return; }
    try {
      kakao.maps.load(function () {
        var geocoder = new kakao.maps.services.Geocoder();
        window.__search = function (query) {
          try {
            geocoder.addressSearch(query, function (data, status) {
              if (status === 'ZERO_RESULT') { post({ type: 'results', results: [] }); return; }
              if (status !== 'OK' || !Array.isArray(data)) { post({ type: 'error', message: 'search-failed' }); return; }
              var out = data.map(function (d) {
                var bcode = (d.address && d.address.b_code) || (d.road_address && d.road_address.b_code) || '';
                return { address: d.address_name, lat: Number(d.y), lng: Number(d.x), admin_dong_code: bcode };
              });
              post({ type: 'results', results: out });
            });
          } catch (e) {
            post({ type: 'error', message: 'search-threw' });
          }
        };
        post({ type: 'ready' });
      });
    } catch (e) {
      post({ type: 'error', message: 'init-failed' });
    }
  }
  init();
</script>
</body>
</html>`;
}

export function GeocoderWebView({ query, nonce, onResults, onError }: GeocoderWebViewProps) {
  const jsKey = process.env.EXPO_PUBLIC_KAKAO_JS_KEY;
  const webRef = useRef<WebView>(null);
  const [ready, setReady] = useState(false);
  // ready 전에 들어온 검색을 보류했다가 ready 직후 1회 실행한다(SDK 로드 레이스).
  const pendingNonce = useRef(0);

  // 키 부재 → 즉시 graceful 실패(웹 키 부재 degrade 동형).
  useEffect(() => {
    if (!jsKey) onError();
  }, [jsKey, onError]);

  // nonce 변화 → 검색 실행(ready면 즉시, 아니면 보류 후 ready에서 flush).
  useEffect(() => {
    if (nonce === 0) return;
    if (ready) {
      webRef.current?.injectJavaScript(
        `window.__search(${JSON.stringify(query)}); true;`,
      );
    } else {
      pendingNonce.current = nonce;
    }
  }, [nonce, ready, query]);

  const handleMessage = (e: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(e.nativeEvent.data) as {
        type: string;
        results?: GeocodeResult[];
      };
      if (msg.type === "ready") {
        setReady(true);
        // ready 전 보류된 검색이 있으면 1회 실행.
        if (pendingNonce.current !== 0) {
          webRef.current?.injectJavaScript(
            `window.__search(${JSON.stringify(query)}); true;`,
          );
          pendingNonce.current = 0;
        }
      } else if (msg.type === "results") {
        onResults(msg.results ?? []);
      } else if (msg.type === "error") {
        onError();
      }
    } catch {
      // 브릿지 메시지가 아닌 잡음 — 무시.
    }
  };

  if (!jsKey) return null;

  return (
    <WebView
      ref={webRef}
      originWhitelist={["*"]}
      source={{ html: buildGeocoderHtml(jsKey), baseUrl: KAKAO_WEBVIEW_ORIGIN }}
      onMessage={handleMessage}
      onError={onError}
      onHttpError={onError}
      javaScriptEnabled
      domStorageEnabled
      // 보이지 않는 브릿지 — 화면에 지도/캔버스를 그리지 않는다(지오코딩 전용).
      style={styles.hidden}
      pointerEvents="none"
    />
  );
}

const styles = StyleSheet.create({
  hidden: { position: "absolute", width: 0, height: 0, opacity: 0 },
});
```

=========================================================================
FILE: apps/mobile/src/features/provider/ProviderGuard.tsx
=========================================================================
```tsx
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { router, usePathname, type Href } from "expo-router";

import { NetworkNotice } from "@/components/NetworkNotice";
import { ThemedText } from "@/components/themed-text";
import { Colors, Radius, Spacing } from "@/constants/theme";
import { getPendingSignup } from "@/features/auth/pendingSignup";
import { useSession } from "@/features/auth/useSession";
import { useOnlineStatus } from "@/lib/useOnlineStatus";

// provider 역할 가드 — 웹 ProviderGuard.tsx RN 포팅 (Story 9.3 — AC5). booker/미로그인이 /provider/*
// 진입 시 친절한 전환으로 막는다: 미로그인 → /login?next=(복귀 경로 보존), booker/admin → 홈(/).
// ★ pendingSignup(provider 신규 가입 중)은 아직 미로그인이지만 통과시킨다 — 가입+룸 생성을 룸 폼에서
//   원자 처리하는 흐름이라([[provider-signup-deferred-and-geocode]]) 여기서 막으면 가입이 불가능해진다.
//   RoomForm과 동일하게 mount 1회 캡처한다. 세션 매트릭스(로딩→스켈레톤·판별실패→재시도·단절→배너)는
//   ReservationList/FavoriteList 선례를 미러한다(로그아웃 오인 금지).

/** 리다이렉트 대기/세션 판별 중 자리 — 화면 깜빡임 방지(셸 톤 스켈레톤). */
function GuardSkeleton() {
  return (
    <View style={styles.skeletonWrap} accessibilityLabel="불러오는 중">
      <View style={styles.skeletonTitle} />
      <View style={styles.skeletonCard} />
      <View style={styles.skeletonCard} />
    </View>
  );
}

export function ProviderGuard({ children }: { children: React.ReactNode }) {
  // 가입 보류(provider 신규)는 mount 1회 캡처 — 있으면 미로그인이라도 통과(RoomForm 동일 패턴).
  const [pending] = useState(() => getPendingSignup());
  const {
    data: session,
    isLoading: sessionLoading,
    isError: sessionError,
    refetch: refetchSession,
  } = useSession();
  const isOnline = useOnlineStatus();
  const pathname = usePathname();

  // 리다이렉트 판정 — 온라인+세션 확정 상태에서만 보낸다. session===null=미로그인, role!=="provider"=booker/admin.
  const settled = !pending && !sessionLoading && !sessionError && isOnline;
  const isLoggedOut = settled && session === null;
  const isWrongRole = settled && !!session && session.role !== "provider";

  // 렌더 중 부작용 금지 → effect에서 리다이렉트. 미로그인은 ?next=로 복귀 경로 보존, 잘못된 역할은 홈.
  useEffect(() => {
    if (isLoggedOut) {
      router.replace(
        `/login?next=${encodeURIComponent(pathname ?? "/provider/reservations")}` as Href,
      );
    } else if (isWrongRole) {
      router.replace("/" as Href);
    }
  }, [isLoggedOut, isWrongRole, pathname]);

  // 가입 보류(provider 신규) — 미로그인이라도 룸 폼 통과.
  if (pending) return <>{children}</>;

  // 세션 판별 중 — 스켈레톤(미로그인/콘텐츠 깜빡임 방지).
  if (sessionLoading) return <GuardSkeleton />;

  // 세션 판별 실패(네트워크/5xx) — 로그아웃이 아니라 오류·재시도(로그아웃 오인 금지).
  if (sessionError) {
    return (
      <View style={styles.errorWrap}>
        <ThemedText type="body" themeColor="cardForeground" style={styles.center}>
          로그인 상태를 확인하지 못했어요.
        </ThemedText>
        <Pressable
          onPress={() => refetchSession()}
          accessibilityRole="button"
          style={styles.primaryButton}
        >
          <ThemedText type="label" themeColor="primaryForeground">
            다시 시도
          </ThemedText>
        </Pressable>
      </View>
    );
  }

  // 세션 미확정(단절 콜드 진입) — 로그인 사용자 오인 방지로 단절 배너.
  if (!isOnline && session === undefined) {
    return (
      <View style={styles.bannerWrap}>
        <NetworkNotice />
      </View>
    );
  }

  // 미로그인·잘못된 역할 — effect가 리다이렉트하는 동안 잠깐 스켈레톤(깜빡임 최소화).
  if (isLoggedOut || isWrongRole) return <GuardSkeleton />;

  // provider(또는 단절 중 캐시된 provider 세션) — 통과.
  return <>{children}</>;
}

const styles = StyleSheet.create({
  skeletonWrap: { gap: Spacing[4], paddingVertical: Spacing[6] },
  skeletonTitle: {
    height: 32,
    width: 160,
    borderRadius: Radius.md,
    backgroundColor: Colors.light.backgroundElement,
  },
  skeletonCard: {
    height: 96,
    borderRadius: Radius.lg,
    backgroundColor: Colors.light.backgroundElement,
  },
  errorWrap: {
    gap: Spacing[3],
    alignItems: "center",
    padding: Spacing[6],
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  center: { textAlign: "center" },
  primaryButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  bannerWrap: { paddingVertical: Spacing[6] },
});
```

=========================================================================
FILE: apps/mobile/src/features/chatbot/deviceId.ts
=========================================================================
```tsx
// 디바이스 식별자 — 웹 deviceId.ts RN 포팅 (Story 9.3 — AC6).
//
// thread_id = `${user_id}:${device_id}`(서버 도출)의 device 부분을 클라가 책임진다. 웹은
// localStorage였지만 모바일은 **AsyncStorage**(온보딩과 동형·키 `desknow.deviceId`)에 1회
// 생성·영속하며 **로그아웃에도 회전하지 않는다**(디바이스 식별자 — 세션이 아니라 기기 단위).
//
// ⚠️ RN(Hermes)엔 `crypto.randomUUID`가 없으므로 **Math.random v4 폴백**(웹의 비-secure-context
//    폴백 복사). device_id는 보안 토큰이 아니라 불투명 식별자라 충분하다. 와이어는 snake_case
//    `device_id`(camelCase 변환 금지).
import { useEffect, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";

/** AsyncStorage 키 — 디바이스 식별자 단일 출처. */
const DEVICE_ID_KEY = "desknow.deviceId";

/** 클라 1회 확정한 device_id 캐시 — 동기 초기값(같은 참조)·생성 write 1회화. */
let cachedDeviceId: string | null = null;

/** RFC4122 v4 UUID — Math.random 폴백(crypto 부재 RN). device_id는 비민감이라 충분(웹 폴백 복사). */
function generateUuid(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * AsyncStorage에서 device_id를 읽고, 없으면 생성·저장해 반환한다. 캐시 적중 시 write 없이
 * 동일 참조 반환. 저장 실패(프라이빗 모드 등)는 graceful(메모리 캐시로 세션 내 일관 — 다음 진입 재생성).
 */
export async function getOrCreateDeviceId(): Promise<string> {
  if (cachedDeviceId !== null) return cachedDeviceId;
  let id: string | null = null;
  try {
    id = await AsyncStorage.getItem(DEVICE_ID_KEY);
  } catch {
    id = null;
  }
  if (!id) {
    id = generateUuid();
    try {
      await AsyncStorage.setItem(DEVICE_ID_KEY, id);
    } catch {
      // 저장 실패 — 메모리 캐시로 세션 내 일관 유지(다음 앱 진입 시 재생성 감수).
    }
  }
  cachedDeviceId = id;
  return id;
}

/**
 * device_id를 제공하는 클라 훅. AsyncStorage가 비동기라 `useSyncExternalStore`(웹) 대신
 * `useState`+effect로 단순화한다. 해소 전엔 빈 문자열(`""`)을 반환하고, 소비처(useChatbot)는
 * `""` 동안 쿼리/스트림을 비활성화한다(빈 device_id로 서버 422 회피).
 */
export function useDeviceId(): string {
  // 초기값이 캐시 적중 시 곧 값이다(동기 setState 불요). 캐시 미스일 때만 effect에서 비동기 해소.
  const [deviceId, setDeviceId] = useState<string>(cachedDeviceId ?? "");
  useEffect(() => {
    if (cachedDeviceId !== null) return; // 이미 확정 — 초기 state로 충분
    let active = true;
    void getOrCreateDeviceId().then((id) => {
      if (active) setDeviceId(id);
    });
    return () => {
      active = false;
    };
  }, []);
  return deviceId;
}
```

=========================================================================
FILE: apps/mobile/src/features/chatbot/streamMessage.ts
=========================================================================
```tsx
// 챗봇 응답 SSE 스트리밍 클라이언트 — 웹 streamMessage.ts RN 대체 (Story 9.3 — AC7·§범위 3).
//
// 웹은 레포 유일의 raw fetch+ReadableStream+`credentials:"include"`(쿠키)였다. RN(Hermes)은 스트리밍
// ReadableStream이 불안정하므로 **react-native-sse `EventSource`**(POST+body+Bearer 헤더 지원)로
// 대체한다. `EventSource`는 별도 import라 eslint 직접-fetch 가드에 안 걸린다(allowlist 불요·내부 XHR).
//
// 인증=쿠키→**Bearer**(`getAccessToken` 헤더)·`credentials:"include"` 절대 금지(RN 무존재). 401은
// SDK 인터셉터가 SSE 경로를 안 타므로 **수동 재시도**: 9.1 `refreshSession()`(단일-flight) 1회 →
// 새 토큰으로 재연결(무한루프 가드). `StreamEvent` 타입·done/error/delta 의미부여는 웹 verbatim(파서는
// react-native-sse가 프레임을 분해해 주므로 data JSON 파싱만 한다).
import EventSource from "react-native-sse";

import { refreshSession } from "@/lib/api-client";
import { clearTokens, getAccessToken } from "@/lib/session-store";

/** 스트림 소비자에게 전달되는 이벤트(델타 누적·종료·강등) — 웹과 동일. */
export type StreamEvent =
  | { type: "delta"; text: string }
  | { type: "done" }
  | { type: "error"; code: string; message: string };

/** 스트림 시작 전/중 실패(401·네트워크 등) 강등 이벤트 — 웹과 동일. */
const STREAM_FAILED: StreamEvent = {
  type: "error",
  code: "STREAM_FAILED",
  message: "스트림을 시작할 수 없습니다.",
};

// baseUrl = 백엔드 origin만(api-client.ts와 동일 출처·드리프트 방지). SSE는 SDK가 소비 못 하므로
// EventSource로 직접 URL을 짠다(경로 /api/v1/...는 여기서만 명시).
const API_BASE = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** message 프레임(`data:{"delta":"..."}`)을 delta 이벤트로 — 웹 parseFrame의 message 분기. */
function parseDeltaFrame(data: string | null): StreamEvent | null {
  if (!data) return null;
  try {
    const parsed = JSON.parse(data) as { delta?: string };
    return { type: "delta", text: parsed.delta ?? "" };
  } catch {
    return null; // 깨진 델타 프레임은 조용히 건너뛴다(스트림 계속) — 웹 동형
  }
}

/** 인밴드 `event: error` 프레임(`data:{"code","message"}`)을 error 이벤트로 — 웹 parseFrame의 error 분기. */
function parseErrorFrame(data: string | null): StreamEvent {
  try {
    const parsed = JSON.parse(data ?? "") as { code?: string; message?: string };
    return { type: "error", code: parsed.code ?? "UNKNOWN", message: parsed.message ?? "" };
  } catch {
    return { type: "error", code: "PARSE_ERROR", message: "" };
  }
}

/**
 * `POST /api/v1/chatbot/stream`에 메시지를 보내고 SSE 토큰 스트림을 이벤트로 yield한다(웹과 동일
 * AsyncIterable 인터페이스 — useChatbot의 `for await` 루프 그대로 재사용).
 *
 * react-native-sse(XHR 기반·web에선 XHR 폴백으로 동작)로 연결한다. **`pollingInterval: 0`**으로
 * 종료 후 자동 재연결(중복 POST)을 막는다(라이브러리 기본 5초 재연결 함정). 401 전송 오류 시
 * `refreshSession()` 후 **1회만** 재연결한다(무한루프 가드). 인밴드 `event: error`(LLM 실패)는
 * `.data`로, 전송 오류는 `.xhrStatus`로 구분한다.
 */
export async function* streamMessage({
  message,
  deviceId,
  signal,
}: {
  message: string;
  deviceId: string;
  /** 진행 중 스트림 취소(언마운트/로그아웃 — 소비처가 AbortController로 주입). */
  signal?: AbortSignal;
}): AsyncIterable<StreamEvent> {
  // 이벤트 → 비동기 이터러블 브릿지(큐 + 단일 대기 resolver).
  const queue: StreamEvent[] = [];
  let resolveNext: (() => void) | null = null;
  let finished = false;
  let source: EventSource<"done"> | null = null;
  let retriedAuth = false;

  const push = (ev: StreamEvent) => {
    queue.push(ev);
    resolveNext?.();
    resolveNext = null;
  };
  const finish = () => {
    finished = true;
    resolveNext?.();
    resolveNext = null;
  };

  const connect = (token: string | null): EventSource<"done"> => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const es = new EventSource<"done">(`${API_BASE}/api/v1/chatbot/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({ message, device_id: deviceId }),
      // ⚠️ 단발 스트림 — 종료 후 자동 재연결(중복 POST)을 끈다(기본 5000ms 함정).
      pollingInterval: 0,
    });

    // 기본 message 이벤트 = 토큰 델타.
    es.addEventListener("message", (e) => {
      const ev = parseDeltaFrame(e.data);
      if (ev) push(ev);
    });

    // 명시 종료(event: done) — addEventListener 등록 시에만 디스패치된다(라이브러리 동작).
    es.addEventListener("done", () => {
      push({ type: "done" });
      finish();
      es.close();
    });

    // 'error' 리스너는 두 종류를 받는다: ① 인밴드 SSE error(`.data` 보유=LLM 실패) ② 전송 오류
    // (`.xhrStatus` 보유=401/네트워크/타임아웃). data 유무로 구분한다.
    es.addEventListener("error", (e) => {
      const ev = e as { type: string; data?: string | null; xhrStatus?: number };
      if (typeof ev.data === "string" && ev.data.length > 0) {
        // 인밴드 LLM 실패 → graceful error로 전달(막다른 화면 금지).
        push(parseErrorFrame(ev.data));
        finish();
        es.close();
        return;
      }
      // 전송 오류. 401이면 refresh 회전 후 1회만 재연결(무한루프 가드).
      if (ev.xhrStatus === 401 && !retriedAuth) {
        retriedAuth = true;
        es.close();
        void (async () => {
          const ok = await refreshSession();
          if (ok) {
            const newToken = await getAccessToken();
            source = connect(newToken); // 새 토큰으로 1회 재연결
          } else {
            // refresh까지 실패(만료/회전/로그아웃) → 토큰 정리(다음 authMe가 401→세션 null 전이).
            await clearTokens();
            push(STREAM_FAILED);
            finish();
          }
        })();
        return;
      }
      push(STREAM_FAILED); // 시작 불가/네트워크 단절/타임아웃 — 강등
      finish();
      es.close();
    });

    return es;
  };

  // 시작 시 이미 abort면 즉시 종료(빈 스트림).
  if (signal?.aborted) return;
  const onAbort = () => {
    source?.close();
    finish();
  };
  signal?.addEventListener("abort", onAbort);

  try {
    const token = await getAccessToken();
    source = connect(token);
    while (true) {
      if (queue.length > 0) {
        yield queue.shift()!;
        continue;
      }
      if (finished) break;
      await new Promise<void>((resolve) => {
        resolveNext = resolve;
      });
    }
  } finally {
    // 조기 종료(소비처 break)·abort·정상 종료 모두 연결 정리(reader/연결 누수 방지 — 웹 reader.cancel 등가).
    signal?.removeEventListener("abort", onAbort);
    source?.close();
  }
}
```

=========================================================================
FILE: apps/mobile/src/features/chatbot/useChatbot.ts
=========================================================================
```tsx
// 챗봇 대화 상태 훅 — 웹 useChatbot.ts RN 포팅 (Story 9.3 — AC6·AC7).
//
// - transcript 쿼리(`["chatbot","messages",deviceId]`): QueryClient(_layout 레벨)가 탭 네비게이션을
//   가로질러 캐시를 보존(AC6)하고, 패널 오픈/마운트 시 `GET /chatbot/messages`로 서버 checkpointer
//   상태를 재수화한다(GET/DELETE는 SDK 경유·Bearer는 인터셉터). `refetchOnMount:false`로 스트리밍
//   옵티미스틱 캐시를 재수화가 덮지 않게 한다(전역 기본 refetchOnMount:'always'를 챗봇에선 끈다).
// - send(스트리밍): 사용자 메시지를 옵티미스틱 append 후 `streamMessage`(react-native-sse)로 토큰
//   소비. 첫 델타 전엔 타이핑 인디케이터(isSending), 정상 종료(done)면 최종화, 실패면 부분 어시스턴트
//   제거 + 사용자 버블 유지(재전송용) + isError. BE가 실패 turn 입력을 서버 thread에서 롤백하므로
//   ([[langgraph-failed-turn-input-rollback]]) 클라는 부분 어시스턴트만 정리한다.
// - 로그아웃/미인증 초기화(AC6): useSession data가 로그인→null 전이하면 transcript 캐시 제거 + 패널
//   닫기(onSessionEnd) + `DELETE /chatbot/session` best-effort. device_id는 유지(thread만 초기화).
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  chatbotGetTranscript,
  chatbotResetSession,
  type ChatMessage,
} from "@/lib/api-client";
import { useSession } from "@/features/auth/useSession";

import { streamMessage } from "./streamMessage";

/** 챗봇 transcript 캐시 키 프리픽스(최상위 독립 — ["rooms"]/광역 무효화 금지). */
const CHATBOT_KEY = ["chatbot"] as const;

/** deviceId별 transcript 정확 키. */
function transcriptKey(deviceId: string) {
  return [...CHATBOT_KEY, "messages", deviceId] as const;
}

export type UseChatbotResult = {
  /** 표시 transcript(서버 재수화 + 옵티미스틱 + 스트리밍 누적). */
  messages: ChatMessage[];
  /** 새 메시지 전송(옵티미스틱 append → SSE 스트리밍 소비). deviceId 미준비 시 no-op. */
  send: (text: string) => void;
  /** 마지막 실패 메시지 재전송(사용자 버블 재append 없이 스트림만 재시도). */
  retry: () => void;
  /** 첫 델타 대기 중(타이핑 인디케이터 — 전송~첫 토큰 사이). */
  isSending: boolean;
  /** 스트림 진행 중(전송~종료/에러 전체 — 입력 비활성으로 동시 전송 차단). */
  isStreaming: boolean;
  /** 마지막 전송 실패(에러 카피 + 재전송 노출). */
  isError: boolean;
  /** device_id 준비 완료(빈 동안 입력 비활성). */
  isReady: boolean;
  /** 로그인 여부(미로그인이면 패널이 로그인 안내로 분기 — 백엔드 /chatbot/stream 인증 필수). */
  isAuthed: boolean;
};

export function useChatbot({
  deviceId,
  onSessionEnd,
}: {
  deviceId: string;
  onSessionEnd?: () => void;
}): UseChatbotResult {
  const queryClient = useQueryClient();
  const { data: user } = useSession();
  const key = transcriptKey(deviceId);
  const isReady = deviceId !== "";
  // 백엔드 /chatbot/stream은 인증 필수 — 미로그인 전송은 401로 떨어져 카피로 위장된다(원인 추적 불가).
  // 따라서 미로그인이면 패널이 입력 대신 로그인 안내로 분기한다.
  const isAuthed = user != null;
  // 마지막 "실패한" 전송 텍스트(인터리빙 안전 — A 실패→B 전송 시 retry가 A 대상).
  const lastFailedText = useRef<string | null>(null);
  // 진행 중 스트림 취소 핸들 — 언마운트/로그아웃 시 abort(reader·연결 정리·제거된 캐시 부활 방지).
  const abortRef = useRef<AbortController | null>(null);
  // 동기 재진입 가드 — setIsStreaming 반영 전 좁은 창의 동시 스트림을 ref로 차단.
  const streamingRef = useRef(false);

  // 서버 transcript 재수화(AC6). deviceId 준비 전엔 비활성. 미로그인이면 401 → 빈 대화 유지.
  const transcriptQuery = useQuery({
    queryKey: key,
    enabled: isReady && !!user,
    // 스트리밍 옵티미스틱 캐시를 재수화가 덮지 않게 한다(전역 refetchOnMount:'always'를 끈다).
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    queryFn: async (): Promise<ChatMessage[]> => {
      const { data } = await chatbotGetTranscript({
        query: { device_id: deviceId },
        throwOnError: true,
      });
      return data?.messages ?? [];
    },
  });

  // 스트리밍 상태(타이핑 인디케이터·입력 비활성·에러 카피). useMutation 대신 직접 관리(SSE는 단일 응답
  // 모델에 안 맞고 "첫 델타 전/스트림 전체" 두 시점이 필요).
  const [isSending, setIsSending] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isError, setIsError] = useState(false);

  /** 마지막 어시스턴트 버블 content에 델타를 누적한다(점진 렌더). 마지막이 assistant일 때만. */
  const appendDelta = (text: string) => {
    queryClient.setQueryData<ChatMessage[]>(key, (old) => {
      if (!old || old.length === 0) return old;
      const last = old[old.length - 1];
      if (last.role !== "assistant") return old;
      return [...old.slice(0, -1), { ...last, content: last.content + text }];
    });
  };

  /** 마지막 어시스턴트 버블(부분 수신)을 제거한다(에러 강등 시 — 사용자 버블은 유지). */
  const dropPartialAssistant = () => {
    queryClient.setQueryData<ChatMessage[]>(key, (old) => {
      if (!old || old.length === 0) return old;
      const last = old[old.length - 1];
      if (last.role !== "assistant") return old;
      return old.slice(0, -1);
    });
  };

  /** 전송/재전송 공통 스트리밍 루프. 옵티미스틱 사용자 버블 → SSE 델타 누적 → 종료/에러 처리. */
  const runStream = async (text: string, isRetry: boolean) => {
    // 동기 재진입 가드 — setIsStreaming 반영 전 좁은 창의 동시 스트림을 ref로 차단.
    if (streamingRef.current) return;
    streamingRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;

    if (!isRetry) {
      // 정확 키만 — cancel 후 즉시 사용자 버블 append(≤100ms 반영). 광역 무효화 금지.
      await queryClient.cancelQueries({ queryKey: key });
      queryClient.setQueryData<ChatMessage[]>(key, (old) => [
        ...(old ?? []),
        { role: "user", content: text },
      ]);
    }
    setIsError(false);
    setIsSending(true); // 첫 델타 전 — 타이핑 인디케이터
    setIsStreaming(true);

    let assistantStarted = false;
    let errored = false;
    let receivedDone = false; // 명시 종료(event: done) 수신 여부 — 없이 끝나면 절단으로 간주.
    try {
      for await (const ev of streamMessage({
        message: text,
        deviceId,
        signal: controller.signal,
      })) {
        if (ev.type === "delta") {
          if (!assistantStarted) {
            assistantStarted = true;
            setIsSending(false); // 첫 델타 도착 → 인디케이터 해제(스트리밍 텍스트로 전환)
            queryClient.setQueryData<ChatMessage[]>(key, (old) => [
              ...(old ?? []),
              { role: "assistant", content: ev.text },
            ]);
          } else {
            appendDelta(ev.text);
          }
        } else if (ev.type === "done") {
          receivedDone = true; // 정상 종료 신호(절단/무응답 구분용)
        } else if (ev.type === "error") {
          errored = true; // 인밴드 LLM 실패 — 강등 처리(아래)
          break;
        }
      }
    } catch {
      errored = true; // 네트워크 단절 등 예기치 못한 실패
    }

    // abort(언마운트/로그아웃): 캐시·에러 상태는 건드리지 않고 진행 플래그만 해제한다.
    if (controller.signal.aborted) {
      setIsSending(false);
      setIsStreaming(false);
      streamingRef.current = false;
      abortRef.current = null;
      return;
    }

    // 명시 done 없이 종료(절단)했거나 봇 출력 0개(빈 응답)면 graceful error로 강등한다(절단을 완성본으로
    // 오인하거나 무응답 막다른 화면이 남는 것을 막는다 — AC7).
    if (!errored && (!receivedDone || !assistantStarted)) {
      errored = true;
    }

    if (errored) {
      if (assistantStarted) dropPartialAssistant(); // 부분 어시스턴트 정리(사용자 버블 유지)
      lastFailedText.current = text; // 현재 에러 UI와 일치하는 실패 텍스트(retry 대상)
      setIsError(true);
    } else {
      lastFailedText.current = null; // 성공 → 보류 중 실패 텍스트 클리어
    }
    setIsSending(false);
    setIsStreaming(false);
    streamingRef.current = false;
    abortRef.current = null;
  };

  /** 새 메시지 전송. deviceId 미준비/미인증/스트림 진행 중이면 무시. */
  const send = (text: string) => {
    const trimmed = text.trim();
    if (!isReady || !isAuthed || streamingRef.current || trimmed === "") return;
    void runStream(trimmed, false);
  };

  /** 마지막 실패 메시지 재전송(실패 텍스트 ref 재사용 — 인터리빙 안전). */
  const retry = () => {
    const text = lastFailedText.current;
    if (!isReady || streamingRef.current || !text) return;
    void runStream(text, true);
  };

  // 언마운트 시 진행 중 스트림 취소(reader·연결 정리, 닫힌 패널에 대한 유령 setState 방지).
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // ── 로그아웃/미인증 초기화(AC6) — 로그인→null 전이에서만 발화 ──
  const wasAuthenticated = useRef(false);
  useEffect(() => {
    if (user) {
      wasAuthenticated.current = true;
      return;
    }
    if (user === null && wasAuthenticated.current) {
      wasAuthenticated.current = false;
      abortRef.current?.abort(); // 진행 중 스트림 취소 — 뒤늦은 델타가 제거할 캐시를 부활시키지 못하게
      queryClient.removeQueries({ queryKey: CHATBOT_KEY }); // transcript 캐시 제거
      onSessionEnd?.(); // 패널 닫기
      if (deviceId !== "") {
        // 서버 thread 폐기(best-effort — 401/네트워크 실패 무시). device_id는 유지.
        chatbotResetSession({
          query: { device_id: deviceId },
          throwOnError: false,
        }).catch(() => {});
      }
    }
  }, [user, deviceId, queryClient, onSessionEnd]);

  return {
    messages: transcriptQuery.data ?? [],
    send,
    retry,
    isSending,
    isStreaming,
    isError,
    isReady,
    isAuthed,
  };
}
```

=========================================================================
FILE: apps/mobile/src/features/chatbot/ChatbotPanel.tsx
=========================================================================
```tsx
import { useCallback, useEffect, useRef, type ReactNode } from "react";
import {
  AccessibilityInfo,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from "react-native";
import { router, type Href } from "expo-router";
import BottomSheet, {
  BottomSheetBackdrop,
  BottomSheetScrollView,
  BottomSheetView,
  type BottomSheetBackdropProps,
} from "@gorhom/bottom-sheet";

import { ThemedText } from "@/components/themed-text";
import { Colors, Radius, Spacing } from "@/constants/theme";

import type { UseChatbotResult } from "./useChatbot";

// 챗봇 "룸메이트" 대화 패널 — 웹 ChatbotPanel(vaul) RN 포팅 (Story 9.3 — AC6·AC8). @gorhom/bottom-sheet
// (9.1 RoomSheet 동형·~80% 스냅)로 드래그-닫기 + controlled open/close. 메시지 목록(BottomSheetScrollView
// 자동 하단 스크롤) + 입력 + 전송. 첫 진입 인사·제안 칩, 스트리밍 타이핑 인디케이터, 전송 실패 재전송,
// 미로그인 안내(입력 대신 로그인 유도 — 401 위장 차단)를 RN으로 그린다. 어시스턴트 본문의 마크다운
// 내부 링크만 화이트리스트로 라우팅(오픈리다이렉트/XSS 방지). 카피·정규식은 웹 verbatim 복사.

// 첫 진입 제안 칩 — 탭=전송. (웹 verbatim)
const SUGGESTION_CHIPS = ["환불 규정?", "강남 오후 3시 빈 방"] as const;

// 모델 실패 카피(고정). 네트워크 단절 카피는 별도 표준이나, 본 패널의 일반 전송 실패는 업스트림(LLM)
// 막힘이 주 경로라 아래 카피를 쓴다([[terminology-network-disconnect-not-offline]]). (웹 verbatim)
const ERROR_COPY = "잠깐 답이 막혔어요. 다시 물어봐 주실래요?";

// ── 내부 링크 화이트리스트(웹 verbatim 복사 — Story 7.6 AC6) ──────────────────────────────
// href 완전 일치: 룸 상세 `/rooms/{uuid}` · 홈 `/` · 탐색 딥링크 `/?view=list&sigungu=&dong=`만 허용.
// 모두 same-origin 상대경로라 오픈리다이렉트 위험 없음. 그 밖 임의 URL/스킴은 링크화하지 않는다.
const INTERNAL_HREF_RE =
  /^(?:\/rooms\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\/(?:\?view=list(?:&(?:sigungu|dong)=\d{1,10})*)?)$/;

// LLM이 룸 안내에 쓰는 마크다운 링크 `[라벨](/경로)` — URL을 숨기고 라벨만 링크로 렌더.
const MD_LINK_RE = /\[([^\]\n]+)\]\((\/[^)\s]*)\)/g;

// 마크다운 링크 밖 평문에 떠도는 bare 내부 경로(안전망). 경계는 유니코드 letter/number + `/`(u 플래그).
const BARE_PATH_RE =
  "(?<![\\p{L}\\p{N}/])(?:\\/rooms\\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\\/(?![\\p{L}\\p{N}/]))";

export function ChatbotPanel({
  chatbot,
  open,
  onClose,
}: {
  chatbot: UseChatbotResult;
  /** 드로어 오픈 여부 — 부모(FAB)가 controlled로 연다. */
  open: boolean;
  /** 닫힘(드래그/백드롭/내부 링크 탭/로그아웃) 시 부모에 알림. */
  onClose: () => void;
}) {
  const { messages, send, retry, isSending, isStreaming, isError, isReady, isAuthed } =
    chatbot;
  const isEmpty = messages.length === 0;

  const sheetRef = useRef<BottomSheet>(null);
  const scrollRef = useRef<{ scrollToEnd: (opts?: { animated?: boolean }) => void }>(null);
  const inputRef = useRef<TextInput>(null);

  // open 변화에 따라 시트를 펼치고/닫는다(controlled — FAB이 연다).
  useEffect(() => {
    if (open) sheetRef.current?.expand();
    else sheetRef.current?.close();
  }, [open]);

  // 새 메시지/스트리밍 토큰·오픈 시 대화 영역을 최신(하단)으로 자동 스크롤(웹 scrollTop=scrollHeight 등가).
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(t);
  }, [open, messages, isSending, isError]);

  // 타이핑 시작 시 스크린리더 공지(웹 sr-only aria-live 등가).
  useEffect(() => {
    if (isSending) AccessibilityInfo.announceForAccessibility("답변을 준비하고 있어요");
  }, [isSending]);

  const handleChange = useCallback(
    (index: number) => {
      if (index === -1 && open) onClose();
    },
    [open, onClose],
  );

  const renderBackdrop = useCallback(
    (props: BottomSheetBackdropProps) => (
      <BottomSheetBackdrop
        {...props}
        appearsOnIndex={0}
        disappearsOnIndex={-1}
        pressBehavior="close"
      />
    ),
    [],
  );

  /** 내부 링크 탭 → 라우팅 + 패널 닫기(웹 Drawer.Close 상속 등가). */
  const navigateInternal = useCallback(
    (href: string) => {
      onClose();
      router.push(href as Href);
    },
    [onClose],
  );

  return (
    <BottomSheet
      ref={sheetRef}
      index={-1}
      snapPoints={["80%"]}
      enableDynamicSizing={false}
      enablePanDownToClose
      keyboardBehavior="interactive"
      keyboardBlurBehavior="restore"
      onChange={handleChange}
      backdropComponent={renderBackdrop}
      backgroundStyle={styles.sheetBackground}
      handleIndicatorStyle={styles.handle}
    >
      <BottomSheetView style={styles.content}>
        {/* 헤더 — 제목 + 닫기 */}
        <View style={styles.header}>
          <ThemedText type="h3" themeColor="cardForeground">
            룸메이트
          </ThemedText>
          <Pressable
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel="챗봇 닫기"
            style={styles.close}
          >
            <ThemedText type="h3" themeColor="textSecondary">
              ✕
            </ThemedText>
          </Pressable>
        </View>

        {/* 메시지 영역 */}
        <BottomSheetScrollView
          ref={scrollRef as never}
          contentContainerStyle={styles.messages}
          accessibilityLiveRegion="polite"
          keyboardShouldPersistTaps="handled"
        >
          {!isAuthed ? (
            // 미로그인: 입력 대신 로그인 안내(401 위장 차단).
            <View style={styles.authGate}>
              <ThemedText type="bodySm" themeColor="textSecondary">
                로그인하면 룸메이트와 대화할 수 있어요.
              </ThemedText>
              <Pressable
                onPress={() => {
                  onClose();
                  router.push("/login?next=/" as Href);
                }}
                accessibilityRole="button"
                style={styles.primaryButton}
              >
                <ThemedText type="label" themeColor="primaryForeground">
                  로그인하기
                </ThemedText>
              </Pressable>
            </View>
          ) : isEmpty ? (
            // 첫 진입: 인사 + 제안 칩(탭=전송).
            <View style={styles.intro}>
              <ThemedText type="bodySm" themeColor="textSecondary">
                안녕하세요, 룸메이트예요. 무엇을 도와드릴까요?
              </ThemedText>
              <View style={styles.chips}>
                {SUGGESTION_CHIPS.map((chip) => (
                  <Pressable
                    key={chip}
                    onPress={() => send(chip)}
                    disabled={!isReady || isStreaming}
                    accessibilityRole="button"
                    style={[styles.chip, (!isReady || isStreaming) && styles.disabled]}
                  >
                    <ThemedText type="bodySm" themeColor="text">
                      {chip}
                    </ThemedText>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : (
            messages.map((m, i) => (
              <ChatBubble
                key={i}
                role={m.role}
                content={m.content}
                onNavigate={navigateInternal}
              />
            ))
          )}

          {/* 타이핑 인디케이터 — 전송~첫 토큰 사이만. */}
          {isSending ? (
            <View
              style={styles.typing}
              accessibilityLabel="답변을 준비하고 있어요"
              testID="chatbot-typing"
            >
              <ThemedText type="bodySm" themeColor="textSecondary">
                ···
              </ThemedText>
            </View>
          ) : null}

          {/* 전송 실패 — 에러 카피 + 재전송(스트림 종료 후에만). */}
          {isError && !isStreaming ? (
            <View style={styles.errorBox} accessibilityRole="alert">
              <ThemedText type="bodySm" themeColor="textSecondary">
                {ERROR_COPY}
              </ThemedText>
              <Pressable onPress={retry} accessibilityRole="button" style={styles.primaryButton}>
                <ThemedText type="label" themeColor="primaryForeground">
                  다시 보내기
                </ThemedText>
              </Pressable>
            </View>
          ) : null}
        </BottomSheetScrollView>

        {/* 입력 + 전송 */}
        <ChatInput
          inputRef={inputRef}
          disabled={!isReady || isStreaming || !isAuthed}
          isAuthed={isAuthed}
          onSend={send}
        />
      </BottomSheetView>
    </BottomSheet>
  );
}

/** 입력창 + 전송 버튼 — 비제어 입력(전송 후 초기화). */
function ChatInput({
  inputRef,
  disabled,
  isAuthed,
  onSend,
}: {
  inputRef: React.RefObject<TextInput | null>;
  disabled: boolean;
  isAuthed: boolean;
  onSend: (text: string) => void;
}) {
  const valueRef = useRef("");
  const submit = () => {
    const text = valueRef.current;
    if (text.trim() === "") return;
    onSend(text);
    valueRef.current = "";
    inputRef.current?.clear();
  };
  return (
    <View style={styles.inputRow}>
      <TextInput
        ref={inputRef}
        onChangeText={(t) => {
          valueRef.current = t;
        }}
        onSubmitEditing={submit}
        editable={!disabled}
        placeholder={isAuthed ? "메시지를 입력하세요" : "로그인 후 이용할 수 있어요"}
        placeholderTextColor={Colors.light.textSecondary}
        accessibilityLabel="메시지 입력"
        returnKeyType="send"
        style={[styles.input, disabled && styles.disabled]}
      />
      <Pressable
        onPress={submit}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityLabel="전송"
        style={[styles.sendButton, disabled && styles.disabled]}
      >
        <ThemedText type="label" themeColor="primaryForeground">
          전송
        </ThemedText>
      </Pressable>
    </View>
  );
}

/** 내부 경로 링크 1개 — 라벨 텍스트로 표시. 탭 시 라우팅 + 패널 닫기. */
function internalLink(
  href: string,
  label: string,
  key: string,
  onNavigate: (href: string) => void,
): ReactNode {
  return (
    <ThemedText
      key={key}
      type="bodySm"
      themeColor="primary"
      style={styles.link}
      onPress={() => onNavigate(href)}
    >
      {label}
    </ThemedText>
  );
}

/** 평문 조각에서 bare 내부 경로(라벨=경로)를 링크화한다(마크다운 링크 처리 후 안전망). */
function linkifyBarePaths(
  text: string,
  keyPrefix: string,
  onNavigate: (href: string) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = new RegExp(BARE_PATH_RE, "gu");
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const path = match[0];
    nodes.push(internalLink(path, path, `${keyPrefix}-${match.index}`, onNavigate));
    last = match.index + path.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/** 어시스턴트 content 렌더 분해: 마크다운 `[라벨](/경로)`는 라벨만 링크(내부 화이트리스트), bare 내부
 *  경로는 안전망 링크, 비-내부 URL은 링크하지 않는다(웹 renderAssistantContent 미러). */
function renderAssistantContent(
  content: string,
  onNavigate: (href: string) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = new RegExp(MD_LINK_RE.source, "g");
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = re.exec(content)) !== null) {
    if (match.index > last) {
      nodes.push(...linkifyBarePaths(content.slice(last, match.index), `seg${i}`, onNavigate));
    }
    const label = match[1];
    const href = match[2];
    if (INTERNAL_HREF_RE.test(href)) {
      nodes.push(internalLink(href, label, `md${i}`, onNavigate));
    } else {
      nodes.push(label); // 비-내부(잠재 악성 URL/스킴) → 라벨만 평문(링크 금지 — 신뢰 경계)
    }
    last = match.index + match[0].length;
    i += 1;
  }
  if (last < content.length) {
    nodes.push(...linkifyBarePaths(content.slice(last), "tail", onNavigate));
  }
  return nodes;
}

/** 대화 한 줄 버블 — user(우측 primary) / assistant(좌측 muted, 내부 경로 linkify). */
function ChatBubble({
  role,
  content,
  onNavigate,
}: {
  role: string;
  content: string;
  onNavigate: (href: string) => void;
}) {
  const isUser = role === "user";
  return (
    <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAssistant]}>
      <ThemedText type="bodySm" themeColor={isUser ? "primaryForeground" : "text"}>
        {isUser ? content : renderAssistantContent(content, onNavigate)}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  sheetBackground: {
    backgroundColor: Colors.light.card,
    borderTopLeftRadius: Radius.xl,
    borderTopRightRadius: Radius.xl,
  },
  handle: { backgroundColor: Colors.light.border, width: 48 },
  content: { flex: 1, paddingHorizontal: Spacing[5], paddingBottom: Spacing[4] },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingBottom: Spacing[2],
  },
  close: { minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" },
  messages: { gap: Spacing[3], paddingVertical: Spacing[2] },
  authGate: { gap: Spacing[3], alignItems: "flex-start" },
  intro: { gap: Spacing[3] },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: Spacing[2] },
  chip: {
    minHeight: 44,
    paddingHorizontal: Spacing[3],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.full,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.background,
  },
  bubble: {
    maxWidth: "85%",
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
    borderRadius: Radius.lg,
  },
  bubbleUser: { alignSelf: "flex-end", backgroundColor: Colors.light.primary },
  bubbleAssistant: { alignSelf: "flex-start", backgroundColor: Colors.light.backgroundElement },
  link: { textDecorationLine: "underline" },
  typing: {
    alignSelf: "flex-start",
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
    borderRadius: Radius.lg,
    backgroundColor: Colors.light.backgroundElement,
  },
  errorBox: { gap: Spacing[2], alignItems: "flex-start" },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: Spacing[2],
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: Colors.light.border,
    paddingTop: Spacing[3],
  },
  input: {
    flex: 1,
    minHeight: 44,
    borderWidth: 1,
    borderColor: Colors.light.border,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing[3],
    fontSize: 14,
    color: Colors.light.text,
    backgroundColor: Colors.light.background,
  },
  sendButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  primaryButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  disabled: { opacity: 0.5 },
});
```

=========================================================================
FILE: apps/mobile/src/app/(tabs)/provider/reservations.tsx
=========================================================================
```tsx
import { StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ThemedView } from "@/components/themed-view";
import { ProviderGuard } from "@/features/provider/ProviderGuard";
import { ProviderReservations } from "@/features/provider/ProviderReservations";
import { Spacing } from "@/constants/theme";

// provider 예약자 현황 라우트 (Story 9.3 — AC1·AC2). (tabs) 그룹이라 URL은 /provider/reservations.
// 셸 크롬은 라우트가, 상태/거부 로직은 ProviderReservations가, 역할 가드는 ProviderGuard가 소유한다.
export default function ProviderReservationsScreen() {
  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={["top", "left", "right"]} style={styles.safeArea}>
        <ProviderGuard>
          <ProviderReservations />
        </ProviderGuard>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  safeArea: { flex: 1, padding: Spacing[4] },
});
```

=========================================================================
FILE: apps/mobile/src/app/(tabs)/provider/reviews.tsx
=========================================================================
```tsx
import { StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ThemedView } from "@/components/themed-view";
import { ProviderGuard } from "@/features/provider/ProviderGuard";
import { ProviderReviews } from "@/features/provider/ProviderReviews";
import { Spacing } from "@/constants/theme";

// provider 후기 라우트 (Story 9.3 — AC3). (tabs) 그룹이라 URL은 /provider/reviews.
// 목록/답글 작성은 ProviderReviews가, 역할 가드는 ProviderGuard가 소유한다.
export default function ProviderReviewsScreen() {
  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={["top", "left", "right"]} style={styles.safeArea}>
        <ProviderGuard>
          <ProviderReviews />
        </ProviderGuard>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  safeArea: { flex: 1, padding: Spacing[4] },
});
```

=========================================================================
FILE: apps/mobile/src/app/(tabs)/provider/room.tsx
=========================================================================
```tsx
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ThemedView } from "@/components/themed-view";
import { ProviderGuard } from "@/features/provider/ProviderGuard";
import { RoomForm } from "@/features/provider/RoomForm";
import { MaxContentWidth, Spacing } from "@/constants/theme";

// provider 스터디룸 등록/수정 라우트 (Story 9.3 — AC4). (tabs) 그룹이라 URL은 /provider/room
// (9.1 스텁 교체·SignupView가 가입 전 push하는 그 경로). 긴 폼이라 KeyboardAvoidingView + ScrollView로
// 감싸 작은 화면에서도 입력이 가려지지 않게 한다. 가입+룸 생성 원자 처리·지오코딩은 RoomForm이 소유.
export default function ProviderRoomScreen() {
  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={["top", "left", "right"]} style={styles.safeArea}>
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={styles.flex}
        >
          <ScrollView
            contentContainerStyle={styles.scroll}
            keyboardShouldPersistTaps="handled"
          >
            <ProviderGuard>
              <RoomForm />
            </ProviderGuard>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  safeArea: { flex: 1 },
  flex: { flex: 1 },
  scroll: {
    padding: Spacing[5],
    paddingBottom: Spacing[16],
    maxWidth: MaxContentWidth,
    width: "100%",
    alignSelf: "center",
  },
});
```

=========================================================================
FILE: apps/mobile/src/components/app-tabs.tsx
=========================================================================
```tsx
import { NativeTabs } from 'expo-router/unstable-native-tabs';

import { Colors } from '@/constants/theme';
import { useSession } from '@/features/auth/useSession';

// 역할조건부 1급 네비 (Story 1.6 AC4 → 9.3 AC5·§범위 4). 웹 AppNav의 PROVIDER_NAV↔BOOKER_NAV 스왑
// 미러: provider면 운영 메뉴(예약자 현황·후기·내 스터디룸), 그 외(로딩·미로그인·booker)는 예약자
// 메뉴(찾기·예약현황·즐겨찾기). 6개 라우트를 항상 선언하고 비활성 역할 탭만 `hidden`으로 숨긴다.
// 라이트 고정 토큰 색. 아이콘은 sf(iOS)+md(Android)로 에셋 없이 구성.
export default function AppTabs() {
  const c = Colors.light;
  const { data: session } = useSession();
  const isProvider = session?.role === 'provider';

  return (
    <NativeTabs
      backgroundColor={c.background}
      indicatorColor={c.backgroundElement}
      labelStyle={{ default: { color: c.textSecondary }, selected: { color: c.primary } }}
      iconColor={{ default: c.textSecondary, selected: c.primary }}
    >
      {/* 예약자(booker) 메뉴 — provider일 때 숨김. */}
      <NativeTabs.Trigger name="index" hidden={isProvider}>
        <NativeTabs.Trigger.Label>스터디룸 찾기</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="magnifyingglass" md="search" selectedColor={c.primary} />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="reservations" hidden={isProvider}>
        <NativeTabs.Trigger.Label>예약현황</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="calendar" md="calendar_month" selectedColor={c.primary} />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="favorites" hidden={isProvider}>
        <NativeTabs.Trigger.Label>즐겨찾기</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="heart" md="favorite" selectedColor={c.primary} />
      </NativeTabs.Trigger>

      {/* 제공자(provider) 메뉴 — provider일 때만 노출. */}
      <NativeTabs.Trigger name="provider/reservations" hidden={!isProvider}>
        <NativeTabs.Trigger.Label>예약자 현황</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="person.2" md="groups" selectedColor={c.primary} />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="provider/reviews" hidden={!isProvider}>
        <NativeTabs.Trigger.Label>후기</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="star" md="star" selectedColor={c.primary} />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="provider/room" hidden={!isProvider}>
        <NativeTabs.Trigger.Label>내 스터디룸</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="house" md="home" selectedColor={c.primary} />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
```

=========================================================================
FILE: apps/mobile/src/components/app-tabs.web.tsx
=========================================================================
```tsx
import {
  Tabs,
  TabList,
  TabTrigger,
  TabSlot,
  TabTriggerSlotProps,
  TabListProps,
} from 'expo-router/ui';
import type { Href } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from './themed-text';

import { Colors, MaxContentWidth, Spacing } from '@/constants/theme';
import { useSession } from '@/features/auth/useSession';

const c = Colors.light;

// 웹(react-native-web) 변형 — 역할조건부 1급 네비 (Story 1.6 AC4 → 9.3 AC5·§범위 4). 웹 AppNav의
// PROVIDER_NAV↔BOOKER_NAV 스왑 미러: provider면 운영 메뉴(예약자 현황·후기·내 스터디룸), 그 외(로딩·
// 미로그인·booker)는 예약자 메뉴(찾기·예약현황·즐겨찾기). **6개 라우트를 항상 등록**(TabTrigger가 곧
// 라우트 정의 — TabSlot이 어떤 역할에서도 렌더 가능·pendingSignup이 /provider/room으로 가도 navigable)
// 하고, 비활성 역할 버튼만 display:none으로 숨긴다(라우트 등록은 유지·바만 스왑).
export default function AppTabs() {
  const { data: session } = useSession();
  const isProvider = session?.role === 'provider';
  return (
    <Tabs>
      <TabSlot style={{ height: '100%' }} />
      <TabList asChild>
        <CustomTabList>
          <TabTrigger name="index" href="/" asChild>
            <TabButton hidden={isProvider}>스터디룸 찾기</TabButton>
          </TabTrigger>
          <TabTrigger name="reservations" href="/reservations" asChild>
            <TabButton hidden={isProvider}>예약현황</TabButton>
          </TabTrigger>
          <TabTrigger name="favorites" href="/favorites" asChild>
            <TabButton hidden={isProvider}>즐겨찾기</TabButton>
          </TabTrigger>
          <TabTrigger name="provider/reservations" href={"/provider/reservations" as Href} asChild>
            <TabButton hidden={!isProvider}>예약자 현황</TabButton>
          </TabTrigger>
          <TabTrigger name="provider/reviews" href={"/provider/reviews" as Href} asChild>
            <TabButton hidden={!isProvider}>후기</TabButton>
          </TabTrigger>
          <TabTrigger name="provider/room" href={"/provider/room" as Href} asChild>
            <TabButton hidden={!isProvider}>내 스터디룸</TabButton>
          </TabTrigger>
        </CustomTabList>
      </TabList>
    </Tabs>
  );
}

function TabButton({
  children,
  isFocused,
  hidden,
  ...props
}: TabTriggerSlotProps & { hidden?: boolean }) {
  return (
    <Pressable
      {...props}
      style={({ pressed }) => [styles.tabButton, hidden && styles.hidden, pressed && styles.pressed]}
    >
      {!hidden ? (
        <ThemedText type="label" themeColor={isFocused ? 'primary' : 'textSecondary'}>
          {children}
        </ThemedText>
      ) : null}
    </Pressable>
  );
}

function CustomTabList(props: TabListProps) {
  return (
    <View style={styles.barContainer}>
      <View style={styles.bar}>{props.children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  barContainer: {
    position: 'absolute',
    bottom: 0,
    width: '100%',
    alignItems: 'center',
    backgroundColor: c.background,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.border,
  },
  bar: {
    flexDirection: 'row',
    width: '100%',
    maxWidth: MaxContentWidth,
    justifyContent: 'space-around',
    paddingVertical: Spacing[2],
  },
  tabButton: {
    minHeight: 44,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing[2],
  },
  // 비활성 역할 버튼 — 라우트 등록은 유지하되 바에서 숨긴다(레이아웃 제외).
  hidden: { display: 'none' },
  pressed: {
    opacity: 0.7,
  },
});
```

=========================================================================
FILE: apps/mobile/src/components/ChatbotFabSlot.tsx
=========================================================================
```tsx
import { useState } from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import { elevation } from '@desknow/ui';

import { Colors, Radius } from '@/constants/theme';
import { ChatbotPanel } from '@/features/chatbot/ChatbotPanel';
import { useDeviceId } from '@/features/chatbot/deviceId';
import { useChatbot } from '@/features/chatbot/useChatbot';

const c = Colors.light;

// 플로팅 챗봇 "룸메이트" FAB + 대화 패널 (Story 1.6 스텁 → 9.3 실동작 — AC6). 웹 ChatbotFabSlot 미러.
// _layout.tsx 루트 직속에 영속 마운트되므로(Stack 형제) 패널 오픈 상태·대화 맥락이 탭 네비게이션을
// 가로질러 보존된다(AC6). 로그아웃 전이 시 useChatbot이 캐시 제거 + 서버 thread 폐기 + 패널을 닫는다
// (onSessionEnd, AC6). deviceId(AsyncStorage)로 세션·대화를 유지한다. 스타일·위치·a11y는 스텁 보존.
export function ChatbotFabSlot() {
  const [open, setOpen] = useState(false);
  const deviceId = useDeviceId();
  // 로그아웃 전이 시 패널을 닫는다(useChatbot이 캐시 제거 + 서버 thread 폐기 동반).
  const chatbot = useChatbot({ deviceId, onSessionEnd: () => setOpen(false) });

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="룸메이트 챗봇 열기"
        hitSlop={8}
        onPress={() => setOpen(true)}
        style={({ pressed }) => [styles.fab, pressed && styles.pressed]}
      >
        <Text style={styles.icon}>💬</Text>
      </Pressable>
      <ChatbotPanel chatbot={chatbot} open={open} onClose={() => setOpen(false)} />
    </>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: 'absolute',
    right: 16,
    // 하단 탭바 위로 띄운다.
    bottom: 96,
    width: 56,
    height: 56,
    minWidth: 44,
    minHeight: 44,
    borderRadius: Radius.full,
    backgroundColor: c.primary,
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: elevation.fab,
    zIndex: 100,
  },
  pressed: { opacity: 0.85 },
  icon: { fontSize: 24 },
});
```
