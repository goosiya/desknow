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
