import { useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

// 인증 폼(로그인·회원가입 공용 셸) — 웹 AuthForm RN 포팅 (Story 9.1 — AC2). 이메일/비밀번호 입력 +
// 제출 + 로딩/에러 표시 + 상호 이동 링크. 막다른 화면 금지: 에러는 인라인으로 띄우고 재제출 가능
// (폼 유지). 카피는 친근한 해요체. 토큰만 사용(하드코딩 색/픽셀 0). 탭 타겟 ≥44px.
export type AuthFormProps = {
  title: string;
  submitLabel: string;
  onSubmit: (credentials: { email: string; password: string }) => void;
  pending: boolean;
  errorMessage?: string | null;
  /** 정보성 안내(예: 세션 만료) — 에러와 구분된 중립 톤, 폼 위에 표시. */
  notice?: string | null;
  /** 비밀번호 필드 보조 안내(가입=정책 안내 등). */
  passwordHint?: string;
  /** 이메일 입력 위 추가 영역(가입=역할 선택 등). */
  topSlot?: ReactNode;
  /** 하단 상호 이동 링크 영역. */
  footer: ReactNode;
  emailAutoComplete?: 'email';
  passwordAutoComplete?: 'current-password' | 'new-password';
};

function Field({
  label,
  value,
  onChange,
  ...input
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
} & Omit<React.ComponentProps<typeof TextInput>, 'value' | 'onChange' | 'onChangeText'>) {
  return (
    <View style={styles.field}>
      {/* 필드 라벨 색 = primary(주황) — 웹 AuthForm 미러(9.4 LOGIN-2, 기존 진한 회색에서 정정). */}
      <ThemedText type="label" themeColor="primary">
        {label}
      </ThemedText>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholderTextColor={Colors.light.textSecondary}
        style={styles.input}
        {...input}
      />
    </View>
  );
}

export function AuthForm({
  title,
  submitLabel,
  onSubmit,
  pending,
  errorMessage,
  notice,
  passwordHint,
  topSlot,
  footer,
  emailAutoComplete = 'email',
  passwordAutoComplete = 'current-password',
}: AuthFormProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  function handleSubmit() {
    if (pending) return;
    onSubmit({ email: email.trim(), password });
  }

  return (
    <View style={styles.form}>
      <ThemedText type="h1">{title}</ThemedText>

      {/* 정보성 안내(중립 톤 — 에러와 구분). */}
      {notice ? (
        <View style={styles.notice} accessibilityLiveRegion="polite">
          <ThemedText type="bodySm" themeColor="textSecondary">
            {notice}
          </ThemedText>
        </View>
      ) : null}

      {topSlot}

      <Field
        label="이메일"
        value={email}
        onChange={setEmail}
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete={emailAutoComplete}
        inputMode="email"
        textContentType="emailAddress"
      />
      <Field
        label="비밀번호"
        value={password}
        onChange={setPassword}
        secureTextEntry
        autoCapitalize="none"
        autoComplete={passwordAutoComplete}
        textContentType={passwordAutoComplete === 'new-password' ? 'newPassword' : 'password'}
      />
      {passwordHint ? (
        <ThemedText type="caption" themeColor="textSecondary">
          {passwordHint}
        </ThemedText>
      ) : null}

      {/* 인라인 에러 — alert로 공지(막다른 화면 금지: 폼 유지·재제출 가능). */}
      {errorMessage ? (
        <View style={styles.error} accessibilityRole="alert">
          <ThemedText type="bodySm" themeColor="destructive">
            {errorMessage}
          </ThemedText>
        </View>
      ) : null}

      <Pressable
        onPress={handleSubmit}
        disabled={pending}
        accessibilityRole="button"
        accessibilityState={{ disabled: pending }}
        style={[styles.submit, pending && styles.submitDisabled]}
      >
        <ThemedText type="label" themeColor="primaryForeground">
          {pending ? '처리 중…' : submitLabel}
        </ThemedText>
      </Pressable>

      <View style={styles.footer}>{footer}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  form: { gap: Spacing[4] },
  field: { gap: Spacing[2] },
  input: {
    minHeight: 48,
    paddingHorizontal: Spacing[3],
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
    color: Colors.light.text,
    fontSize: 16,
  },
  notice: {
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.backgroundElement,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
  },
  error: {
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.destructive,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
  },
  submit: {
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  submitDisabled: { opacity: 0.6 },
  footer: { alignItems: 'center' },
});
