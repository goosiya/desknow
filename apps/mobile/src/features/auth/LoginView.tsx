import { Pressable, View } from 'react-native';
import { router, useLocalSearchParams, type Href } from 'expo-router';

import { ThemedText } from '@/components/themed-text';

import { AuthForm } from './AuthForm';
import { loginErrorCopy } from './authCopy';
import { useLogin } from './useAuth';

// 로그인 화면 컨테이너 — 웹 LoginView RN 포팅 (Story 9.1 — AC2). AuthForm을 useLogin·라우팅에 배선.
// 성공 시 useLogin이 토큰 저장 + ["auth","me"] invalidate → next(또는 홈)로 이동. 에러는 loginErrorCopy로
// 분기해 인라인 표시(막다른 화면 금지).

/** next 안전 검증 — 오픈 리다이렉트 방지(앱 내부 경로만 허용). */
function safeNext(next: string | undefined): Href {
  if (next && next.startsWith('/') && !next.startsWith('//')) return next as Href;
  return '/';
}

export function LoginView() {
  const params = useLocalSearchParams<{ next?: string; expired?: string }>();
  const login = useLogin();
  const expired = params.expired === '1';

  return (
    <AuthForm
      title="로그인"
      submitLabel="로그인"
      pending={login.isPending}
      errorMessage={login.error ? loginErrorCopy(login.error.failure) : null}
      notice={expired ? '로그인 시간이 만료됐어요. 다시 로그인해 주세요.' : null}
      passwordAutoComplete="current-password"
      onSubmit={(credentials) => {
        login.mutate(credentials, {
          onSuccess: () => router.replace(safeNext(params.next)),
        });
      }}
      footer={
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <ThemedText type="bodySm" themeColor="textSecondary">
            아직 계정이 없으신가요?{' '}
          </ThemedText>
          <Pressable
            onPress={() =>
              router.push(
                (params.next
                  ? `/signup?next=${encodeURIComponent(params.next)}`
                  : '/signup') as Href,
              )
            }
            accessibilityRole="link"
            accessibilityLabel="회원가입"
          >
            <ThemedText type="label" themeColor="primary">
              회원가입
            </ThemedText>
          </Pressable>
        </View>
      }
    />
  );
}
