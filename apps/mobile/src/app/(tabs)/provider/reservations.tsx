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
      <SafeAreaView edges={["left", "right"]} style={styles.safeArea}>
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
