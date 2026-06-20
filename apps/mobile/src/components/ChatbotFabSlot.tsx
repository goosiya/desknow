import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { elevation } from '@desknow/ui';

import { Colors, Radius } from '@/constants/theme';
import { ChatbotPanel } from '@/features/chatbot/ChatbotPanel';
import { useDeviceId } from '@/features/chatbot/deviceId';
import { useChatbot } from '@/features/chatbot/useChatbot';

const c = Colors.light;

// FAB을 하단 탭바 위로 띄우는 간격(안전영역 하단 인셋에 더한다). 네이티브 탭바(NativeTabs ~56–80dp) +
// 여백. 플랫 96만 쓰면 제스처바 인셋이 빠져 탭바와 겹쳤다(실기기 확인 2026-06-20).
const FAB_BOTTOM_GAP = 96;

// 챗봇 FAB 아이콘 (9.4 — AC1④·SYS-3·KTH #3). 웹은 lucide `MessageCircle`(흰 윤곽 말풍선)이고 모바일엔
// 아이콘 라이브러리·react-native-svg가 없으며 9.4는 신규 의존성 0이 제약이라, 순수 RN View로 웹과 동일한
// **윤곽 말풍선**을 그린다(채움 아님 — KTH가 웹 기준으로 윤곽 선호). primaryForeground(흰) 테두리 둥근
// 사각형 본체 + 좌하단 꼬리(테두리 2변 + FAB 색 사각형으로 본체 하단선을 가려 꼬리만 돌출). 꼬리가 있어
// 단순 링/도넛으로 안 보인다.
function ChatBubbleIcon() {
  return (
    <View style={styles.bubbleWrap}>
      <View style={styles.bubble} />
      <View style={styles.tail} />
    </View>
  );
}

// 플로팅 챗봇 "룸메이트" FAB + 대화 패널 (Story 1.6 스텁 → 9.3 실동작 — AC6). 웹 ChatbotFabSlot 미러.
// _layout.tsx 루트 직속에 영속 마운트되므로(Stack 형제) 패널 오픈 상태·대화 맥락이 탭 네비게이션을
// 가로질러 보존된다(AC6). 로그아웃 전이 시 useChatbot이 캐시 제거 + 서버 thread 폐기 + 패널을 닫는다
// (onSessionEnd, AC6). deviceId(AsyncStorage)로 세션·대화를 유지한다. 스타일·위치·a11y는 스텁 보존.
export function ChatbotFabSlot() {
  const [open, setOpen] = useState(false);
  const insets = useSafeAreaInsets();
  const deviceId = useDeviceId();
  // 로그아웃 전이 시 패널을 닫는다(useChatbot이 캐시 제거 + 서버 thread 폐기 동반).
  const chatbot = useChatbot({ deviceId, onSessionEnd: () => setOpen(false) });

  return (
    <>
      {/* 패널이 열리면 FAB 숨김(KTH #4 — 열린 시트 위로 FAB가 떠 보이던 문제). 닫히면 다시 노출. */}
      {!open ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="룸메이트 챗봇 열기"
          hitSlop={8}
          onPress={() => setOpen(true)}
          // 하단 탭바 + 안전영역 인셋 위로 띄운다(겹침 방지 — bottom을 인셋 기반으로 동적 산출).
          style={({ pressed }) => [
            styles.fab,
            { bottom: insets.bottom + FAB_BOTTOM_GAP },
            pressed && styles.pressed,
          ]}
        >
          <ChatBubbleIcon />
        </Pressable>
      ) : null}
      <ChatbotPanel chatbot={chatbot} open={open} onClose={() => setOpen(false)} />
    </>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: 'absolute',
    right: 16,
    // bottom은 안전영역 인셋 기반으로 인라인 산출(FAB_BOTTOM_GAP) — 탭바 겹침 방지.
    width: 56,
    height: 56,
    minWidth: 44,
    minHeight: 44,
    borderRadius: Radius.full,
    backgroundColor: c.primary,
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: elevation.fab,
    zIndex: 100,
  },
  pressed: { opacity: 0.85 },
  // 말풍선 — 주황 FAB 위 흰 윤곽 말풍선(웹 lucide MessageCircle 등가).
  bubbleWrap: { width: 28, height: 26, alignItems: 'center', justifyContent: 'flex-start' },
  bubble: {
    width: 26,
    height: 20,
    borderWidth: 2.5,
    borderColor: c.primaryForeground,
    borderRadius: 9,
    backgroundColor: 'transparent',
  },
  // 좌하단 꼬리 — 좌·하 테두리(흰)만 있는 회전 사각형. 채움은 FAB 색(primary)이라 본체 하단선을 가려
  // 꼬리 2획만 돌출한다(CSS 말풍선 꼬리 트릭의 RN 등가).
  tail: {
    position: 'absolute',
    bottom: 1,
    left: 6,
    width: 9,
    height: 9,
    borderLeftWidth: 2.5,
    borderBottomWidth: 2.5,
    borderColor: c.primaryForeground,
    backgroundColor: c.primary,
    transform: [{ rotate: '45deg' }],
  },
});
