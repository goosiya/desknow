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
      <SafeAreaView edges={["left", "right"]} style={styles.safeArea}>
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
