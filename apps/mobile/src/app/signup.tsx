import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AuthBottomNav } from '@/components/AuthBottomNav';
import { ThemedView } from '@/components/themed-view';
import { SignupView } from '@/features/auth/SignupView';
import { MaxContentWidth, Spacing } from '@/constants/theme';

// 회원가입 라우트 (Story 9.1 → 9.4 셸 정렬 — AC2). 탭 위로 push되는 Stack 화면. 9.4: login과 동형 —
// 글로벌 헤더(_layout) + 하단탭(AuthBottomNav·웹 AppBottomNav 미러·역할 인지) 노출(웹=정본)이라 edges에서 top/bottom 제거,
// 콘텐츠 상단 정렬(웹 SIGNUP-2). 키보드 회피 + 스크롤 유지.
export default function SignupScreen() {
  return (
    <ThemedView style={styles.container}>
      <SafeAreaView edges={['left', 'right']} style={styles.safeArea}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.flex}
        >
          <ScrollView
            contentContainerStyle={styles.scroll}
            keyboardShouldPersistTaps="handled"
          >
            <SignupView />
          </ScrollView>
        </KeyboardAvoidingView>
        <AuthBottomNav />
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  safeArea: { flex: 1 },
  flex: { flex: 1 },
  scroll: {
    flexGrow: 1,
    // 상단 정렬 — 헤더 아래에서 시작(웹 SIGNUP-2 정본).
    justifyContent: 'flex-start',
    padding: Spacing[5],
    maxWidth: MaxContentWidth,
    width: '100%',
    alignSelf: 'center',
  },
});
