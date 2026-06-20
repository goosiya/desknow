import { useState } from 'react';
import { FlatList, Modal, Pressable, StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';

// 모달 기반 드롭다운 — 웹 shadcn Select RN 대체 (Story 9.1). 신규 picker 의존성 없이 RN Modal +
// FlatList로 시군구/지역 콤보를 구현한다. 트리거를 누르면 옵션 목록 모달이 뜨고, 선택 시 닫힌다.
// a11y: 트리거 button + 접근 이름, 옵션 button + selected 상태.
export type ComboOption = { value: string; label: string };

type ComboSelectProps = {
  accessibilityLabel: string;
  placeholder: string;
  value: string | undefined;
  options: ComboOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
};

export function ComboSelect({
  accessibilityLabel,
  placeholder,
  value,
  options,
  onChange,
  disabled,
}: ComboSelectProps) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.value === value);

  return (
    <>
      <Pressable
        onPress={() => !disabled && setOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel}
        accessibilityState={{ disabled: !!disabled, expanded: open }}
        style={[styles.trigger, disabled && styles.triggerDisabled]}
      >
        <ThemedText
          type="bodySm"
          themeColor={selected ? 'cardForeground' : 'textSecondary'}
          numberOfLines={1}
        >
          {selected ? selected.label : placeholder}
        </ThemedText>
        <ThemedText type="bodySm" themeColor="textSecondary">
          ▾
        </ThemedText>
      </Pressable>

      <Modal
        visible={open}
        transparent
        animationType="fade"
        onRequestClose={() => setOpen(false)}
      >
        {/* 바깥 탭으로 닫힘(막다른 화면 금지). */}
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          {/* 카드 — 내부 탭이 바깥 닫힘으로 전파되지 않게 흡수. */}
          <Pressable
            style={styles.sheet}
            onPress={() => {}}
            accessibilityLabel={accessibilityLabel}
          >
            <ThemedText type="label" themeColor="textSecondary" style={styles.sheetTitle}>
              {accessibilityLabel}
            </ThemedText>
            <FlatList
              data={options}
              keyExtractor={(o) => o.value}
              style={styles.list}
              renderItem={({ item }) => {
                const active = item.value === value;
                return (
                  <Pressable
                    onPress={() => {
                      onChange(item.value);
                      setOpen(false);
                    }}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                    style={[styles.option, active && styles.optionActive]}
                  >
                    <ThemedText
                      type="body"
                      themeColor={active ? 'primary' : 'cardForeground'}
                    >
                      {item.label}
                    </ThemedText>
                  </Pressable>
                );
              }}
            />
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  trigger: {
    minHeight: 44,
    minWidth: 150,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing[2],
    paddingHorizontal: Spacing[3],
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  triggerDisabled: { opacity: 0.5 },
  backdrop: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(40, 32, 15, 0.2)',
  },
  sheet: {
    maxHeight: '70%',
    gap: Spacing[2],
    padding: Spacing[4],
    borderTopLeftRadius: Radius.xl,
    borderTopRightRadius: Radius.xl,
    backgroundColor: Colors.light.card,
  },
  sheetTitle: { paddingHorizontal: Spacing[2] },
  list: { flexGrow: 0 },
  option: {
    minHeight: 48,
    justifyContent: 'center',
    paddingHorizontal: Spacing[3],
    borderRadius: Radius.md,
  },
  optionActive: { backgroundColor: Colors.light.secondary },
});
