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
            {item.booker_label}
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
