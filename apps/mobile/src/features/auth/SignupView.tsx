import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { router, useLocalSearchParams, type Href } from 'expo-router';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

import { AuthForm } from './AuthForm';
import {
  PASSWORD_POLICY_HINT,
  registerErrorCopy,
  validateSignupCredentials,
} from './authCopy';
import { setPendingSignup } from './pendingSignup';
import { useRegister, type SignupRole } from './useAuth';

// 회원가입 화면 컨테이너 — 웹 SignupView RN 포팅 (Story 9.1 — AC2·§범위 2). 역할 토글(예약자/제공자)로
// 선택해 가입한다. booker는 register→자동 로그인→토큰 저장 후 next(또는 홈)로. provider는 1차 검증
// 통과 시 pendingSignup 보관 + 룸등록 라우트(9.3 스텁)로 이동(register 미호출 — 룸 없는 떠도는 계정 방지).

function safeNext(next: string | undefined): Href {
  if (next && next.startsWith('/') && !next.startsWith('//')) return next as Href;
  return '/';
}

/** 역할 선택 세그먼트 한 버튼(상단 토글). */
function RoleButton({
  active,
  label,
  desc,
  onPress,
}: {
  active: boolean;
  label: string;
  desc: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityState={{ selected: active }}
      style={[styles.roleButton, active ? styles.roleActive : styles.roleInactive]}
    >
      <ThemedText type="label" themeColor={active ? 'text' : 'textSecondary'}>
        {label}
      </ThemedText>
      <ThemedText type="caption" themeColor={active ? 'text' : 'textSecondary'}>
        {desc}
      </ThemedText>
    </Pressable>
  );
}

export function SignupView() {
  const params = useLocalSearchParams<{ next?: string }>();
  const register = useRegister();
  const [role, setRole] = useState<SignupRole>('booker');
  // provider 클라 1차 검증 실패 카피(가입을 미루기 전에 거른 이메일/비번 오류).
  const [localError, setLocalError] = useState<string | null>(null);
  const isProvider = role === 'provider';

  // 역할 전환 시 직전 시도의 에러를 정리한다(예: booker 가입 실패 후 provider 로 바꾸면 stale 한
  // register 에러 카피가 남는 것 방지 — code-review 회수).
  function selectRole(next: SignupRole) {
    setRole(next);
    setLocalError(null);
    register.reset();
  }

  return (
    <AuthForm
      title="회원가입"
      // provider는 이 단계에서 가입하지 않는다 — 버튼이 곧 "스터디룸 등록 화면으로" 이동을 뜻한다.
      submitLabel={isProvider ? '스터디룸 정보 등록' : '가입하고 시작하기'}
      pending={register.isPending}
      errorMessage={
        localError ?? (register.error ? registerErrorCopy(register.error.failure) : null)
      }
      passwordAutoComplete="new-password"
      passwordHint={PASSWORD_POLICY_HINT}
      topSlot={
        <View style={styles.roleSlot}>
          <ThemedText type="label" themeColor="text">
            가입 유형
          </ThemedText>
          <View
            accessibilityRole="radiogroup"
            accessibilityLabel="가입 유형 선택"
            style={styles.roleRow}
          >
            <RoleButton
              active={role === 'booker'}
              label="예약자"
              desc="스터디룸을 찾고 예약"
              onPress={() => selectRole('booker')}
            />
            <RoleButton
              active={role === 'provider'}
              label="제공자"
              desc="내 스터디룸을 등록"
              onPress={() => selectRole('provider')}
            />
          </View>
          {isProvider ? (
            <ThemedText type="caption" themeColor="destructive">
              스터디룸 정보를 등록해야 가입이 완료돼요. 등록 전에 나가면 가입되지 않아요.
            </ThemedText>
          ) : null}
        </View>
      }
      onSubmit={(credentials) => {
        setLocalError(null);
        if (isProvider) {
          // 가입은 룸 등록 시점으로 미루되, 빈값·형식·정책은 넘어가기 전에 1차 검증한다.
          const invalid = validateSignupCredentials(credentials);
          if (invalid) {
            setLocalError(invalid);
            return;
          }
          // 이메일/비번을 들고 룸 등록 화면(9.3 스텁)으로. 실제 가입은 거기서 등록과 함께.
          setPendingSignup(credentials);
          router.push('/provider/room' as Href);
          return;
        }
        register.mutate(
          { ...credentials, role },
          { onSuccess: () => router.replace(safeNext(params.next)) },
        );
      }}
      footer={
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <ThemedText type="bodySm" themeColor="textSecondary">
            이미 계정이 있으신가요?{' '}
          </ThemedText>
          <Pressable
            onPress={() =>
              router.push(
                (params.next
                  ? `/login?next=${encodeURIComponent(params.next)}`
                  : '/login') as Href,
              )
            }
            accessibilityRole="link"
            accessibilityLabel="로그인"
          >
            <ThemedText type="label" themeColor="primary">
              로그인
            </ThemedText>
          </Pressable>
        </View>
      }
    />
  );
}

const styles = StyleSheet.create({
  roleSlot: { gap: Spacing[2] },
  roleRow: { flexDirection: 'row', gap: Spacing[2] },
  roleButton: {
    flex: 1,
    gap: 2,
    alignItems: 'center',
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[3],
    borderRadius: Radius.md,
    borderWidth: 1,
  },
  roleActive: { borderColor: Colors.light.primary, backgroundColor: Colors.light.secondary },
  roleInactive: { borderColor: Colors.light.border, backgroundColor: Colors.light.card },
});
