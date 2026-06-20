import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AuthBottomNav } from '@/components/AuthBottomNav';
import { ThemedView } from '@/components/themed-view';
import { LoginView } from '@/features/auth/LoginView';
import { MaxContentWidth, Spacing } from '@/constants/theme';

// 로그인 라우트 (Story 9.1 → 9.4 셸 정렬 — AC2). 탭 위로 push되는 Stack 화면. 9.4: 웹은 인증화면도
// AppShell로 감싸 글로벌 헤더 + booker 하단탭을 보인다(웹=정본) → top은 글로벌 헤더(_layout)가, 하단
// 하단탭은 AuthBottomNav(웹 AppBottomNav 미러·역할 인지, code-review 2026-06-20)가 담당하므로 SafeAreaView
// edges에서 top/bottom을 뺀다. 폼은 헤더 바로 아래 상단 정렬(웹 LOGIN-1 — 기존 수직 중앙에서 정정).
// 키보드 회피 + 스크롤은 유지.
export default function LoginScreen() {
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
            <LoginView />
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
    // 상단 정렬 — 헤더 바로 아래에서 시작(웹 LOGIN-1 정본).
    justifyContent: 'flex-start',
    padding: Spacing[5],
    maxWidth: MaxContentWidth,
    width: '100%',
    alignSelf: 'center',
  },
});
