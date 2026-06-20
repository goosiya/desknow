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
      <SafeAreaView edges={["left", "right"]} style={styles.safeArea}>
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
