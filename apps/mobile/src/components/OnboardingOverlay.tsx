import { useEffect, useRef, useState } from 'react';
import {
  FlatList,
  Modal,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useReducedMotion } from 'react-native-reanimated';
import { elevation } from '@desknow/ui';

import { ThemedText } from '@/components/themed-text';
import { Colors, Radius, Spacing } from '@/constants/theme';
import { useOnboarding } from '@/lib/useOnboarding';

// 첫 방문 온보딩 오버레이 (Story 3.9 → 9.4 — AC2·ONB). 진입 화면(찾기 탭) 위에 뜨는 RN 모달.
//
// 9.4: 웹 OnboardingOverlay(SLIDES[4] 스와이프 캐러셀)와 동등하게 **4슬라이드 캐러셀**로 재구현한다
// (과거 모바일은 단일 카드 1장이라 ②③④·캐러셀·"다시 보지 않기" 누락 — audit ONB-1·2·3 S1).
// 점 인디케이터·이전/다음·우상단 X·자동 넘김(4500ms·직접 조작 시 중단)·reduced-motion 게이팅을
// RN(FlatList paging)으로 동등 구현한다. 닫기 정책(웹=정본): **"다시 보지 않기"만 영속(dismiss)**,
// "시작하기"·X·바깥 탭·Android 백 = 비영속 close(다음 방문 재노출). 막다른 화면 금지 — 닫으면 이미
// 렌더된 찾기 화면이 드러난다. 아이콘은 모바일에 아이콘 라이브러리가 없어(신규 의존성 0) 개념 대응
// 이모지를 secondary 배지에 둔다(웹 lucide 라인 아이콘의 모바일 등가).
const c = Colors.light;
const AUTO_ADVANCE_MS = 4500;

type Slide = { icon: string; title: string; body: string; note?: string };

// 웹 SLIDES(apps/web/.../OnboardingOverlay.tsx:46-68) 문구 기준. 아이콘만 이모지 대응
// (Sparkles→✨·Compass→🧭·CalendarCheck→📅·MessageCircle→💬). 단 슬라이드2 note는 모바일만 '앱이나'로
// 분기한다(웹='브라우저나' 유지 — KTH 지시로 모바일 앱만 수정, 2026-06-20). 재-동기화 금지.
const SLIDES: Slide[] = [
  {
    icon: '✨',
    title: 'DeskNow에 오신 걸 환영해요',
    body: '내 주변에서 지금 비어 있는 스터디룸을 찾아 바로 예약하는 가장 빠른 방법이에요. 잠깐 둘러볼까요?',
  },
  {
    icon: '🧭',
    title: '지도와 목록으로 찾기',
    body: '지도 핀과 목록에서 지금 이용할 수 있는 스터디룸을 한눈에 볼 수 있어요. 지역이나 반경으로 원하는 동네만 좁혀보세요.',
    // 모바일 앱은 '앱이나'(웹은 '브라우저나' — 위 주석의 의도된 분기).
    note: '앱이나 휴대폰의 위치 정보가 꺼져 있으면 반경 검색은 이용할 수 없어요. 위치 권한을 켜주세요.',
  },
  {
    icon: '📅',
    title: '원하는 시간에 바로 예약',
    body: '스터디룸 상세에서 날짜와 시간을 고르고 ‘예약하기’를 누르면 끝이에요. 연속된 시간도 한 번에 선택할 수 있어요.',
  },
  {
    icon: '💬',
    title: '궁금하면 룸메이트 챗봇',
    body: '오른쪽 아래 챗봇에게 “강남에 지금 빈 방 있어?”처럼 물어보면 자리를 찾아 예약까지 도와드려요. 예약현황·즐겨찾기로 관리도 간편해요.',
  },
];

export function OnboardingOverlay() {
  const { shouldShow, dismiss, close } = useOnboarding();
  const reduceMotion = useReducedMotion();

  const listRef = useRef<FlatList<Slide>>(null);
  const [current, setCurrent] = useState(0);
  // 사용자가 직접 조작(스와이프·점·버튼)하면 자동 넘김 중단(웹 동형 — 통제권을 가져가면 멈춘다).
  const [autoPlay, setAutoPlay] = useState(true);
  // 캐러셀 페이지 폭 — 카드 내부 실측(onLayout). 0이면 paging/scrollToIndex 보류.
  const [pageWidth, setPageWidth] = useState(0);

  const last = SLIDES.length - 1;
  const isLast = current === last;

  // 초기 state(current=0·autoPlay=true)가 최초(유일) 노출을 처리한다. shouldShow는 한 마운트에서
  // true→false(close/dismiss)로만 가고 재노출은 다음 앱 실행의 새 마운트라, 마운트 내 재설정 effect는
  // 불필요하다(react-hooks/set-state-in-effect 회피).

  function goTo(index: number, manual: boolean) {
    const next = Math.max(0, Math.min(index, last));
    if (manual) setAutoPlay(false);
    setCurrent(next);
    if (pageWidth > 0) {
      listRef.current?.scrollToIndex({ index: next, animated: !reduceMotion });
    }
  }

  // 자동 넘김 — 마지막 전까지 한 칸씩. 직접 조작/reduced-motion/닫힘/레이아웃 전엔 멈춘다(웹 동형).
  useEffect(() => {
    if (!shouldShow || !autoPlay || reduceMotion || pageWidth === 0 || current >= last) {
      return;
    }
    const id = setTimeout(() => goTo(current + 1, false), AUTO_ADVANCE_MS);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldShow, autoPlay, reduceMotion, pageWidth, current, last]);

  function onMomentumScrollEnd(e: NativeSyntheticEvent<NativeScrollEvent>) {
    if (pageWidth === 0) return;
    const idx = Math.round(e.nativeEvent.contentOffset.x / pageWidth);
    if (idx !== current) setCurrent(idx);
  }

  return (
    <Modal
      transparent
      visible={shouldShow}
      animationType={reduceMotion ? 'none' : 'fade'}
      // Android 하드웨어 백 = 비영속 close(9.4 — "다시 보지 않기"만 영속).
      onRequestClose={close}
    >
      {/* 딤 배경 — accessibilityViewIsModal로 스크린리더 형제 격리(모달 루트). */}
      <View style={styles.backdrop} accessibilityViewIsModal>
        {/* 바깥 탭 = 비영속 close. ⚠️ 카드를 '감싸지 않는' 절대 레이어로 둔다 — 과거엔 카드를 Pressable로
            감싸 그 내부 캐러셀의 가로 스와이프 제스처를 Pressable이 가로채 스와이프가 안 됐다(실기기
            2026-06-20). 백드롭을 형제로 분리하면 카드 내부 FlatList가 제스처를 정상 수신한다. */}
        <Pressable
          style={StyleSheet.absoluteFill}
          onPress={close}
          accessibilityRole="button"
          accessibilityLabel="닫기"
        />
        {/* 카드 — 평범한 View(Pressable 아님). 바깥 탭은 뒤 백드롭이 받고, 카드 영역 탭은 카드가 흡수. */}
        <View style={styles.card}>
          {/* 우상단 X — 비영속 close. */}
          <Pressable
            style={styles.closeButton}
            onPress={close}
            accessibilityRole="button"
            accessibilityLabel="닫기"
            hitSlop={8}
          >
            <Text style={styles.closeIcon}>✕</Text>
          </Pressable>

          {/* 슬라이드 캐러셀(가로 paging). 페이지 폭은 onLayout 실측. */}
          <View
            style={styles.carousel}
            onLayout={(e) => setPageWidth(e.nativeEvent.layout.width)}
          >
            {pageWidth > 0 ? (
              <FlatList
                ref={listRef}
                data={SLIDES}
                keyExtractor={(s) => s.title}
                horizontal
                pagingEnabled
                showsHorizontalScrollIndicator={false}
                onScrollBeginDrag={() => setAutoPlay(false)}
                onMomentumScrollEnd={onMomentumScrollEnd}
                getItemLayout={(_, index) => ({
                  length: pageWidth,
                  offset: pageWidth * index,
                  index,
                })}
                renderItem={({ item }) => (
                  <View
                    style={[styles.slide, { width: pageWidth }]}
                    accessible
                    accessibilityLabel={
                      item.note ? `${item.title}. ${item.body} ${item.note}` : `${item.title}. ${item.body}`
                    }
                  >
                    <View style={styles.iconBadge}>
                      <Text style={styles.icon}>{item.icon}</Text>
                    </View>
                    <ThemedText type="h2" style={styles.slideTitle}>
                      {item.title}
                    </ThemedText>
                    <ThemedText type="bodySm" themeColor="textSecondary" style={styles.slideBody}>
                      {item.body}
                    </ThemedText>
                    {item.note ? (
                      <ThemedText type="caption" themeColor="destructive" style={styles.slideNote}>
                        {item.note}
                      </ThemedText>
                    ) : null}
                  </View>
                )}
              />
            ) : null}
          </View>

          {/* 페이지 점(눌러 이동). */}
          <View style={styles.dots} accessibilityRole="tablist">
            {SLIDES.map((slide, i) => (
              <Pressable
                key={slide.title}
                accessibilityRole="tab"
                accessibilityState={{ selected: i === current }}
                accessibilityLabel={`${i + 1}번째 안내`}
                hitSlop={8}
                onPress={() => goTo(i, true)}
                style={[styles.dot, i === current ? styles.dotActive : styles.dotIdle]}
              />
            ))}
          </View>

          {/* 하단: 다시 보지 않기(영속 dismiss) / 이전·다음(마지막=시작하기, 비영속 close). */}
          <View style={styles.footer}>
            <Pressable onPress={dismiss} accessibilityRole="button" hitSlop={8} style={styles.skip}>
              <ThemedText type="bodySm" themeColor="textSecondary">
                다시 보지 않기
              </ThemedText>
            </Pressable>
            <View style={styles.footerActions}>
              {current > 0 ? (
                <Pressable
                  onPress={() => goTo(current - 1, true)}
                  accessibilityRole="button"
                  accessibilityLabel="이전"
                  style={styles.prevButton}
                >
                  <ThemedText type="label" themeColor="text">
                    이전
                  </ThemedText>
                </Pressable>
              ) : null}
              {isLast ? (
                <Pressable
                  onPress={close}
                  accessibilityRole="button"
                  accessibilityLabel="시작하기"
                  style={styles.nextButton}
                >
                  <ThemedText type="label" themeColor="primaryForeground">
                    시작하기
                  </ThemedText>
                </Pressable>
              ) : (
                <Pressable
                  onPress={() => goTo(current + 1, true)}
                  accessibilityRole="button"
                  accessibilityLabel="다음"
                  style={styles.nextButton}
                >
                  <ThemedText type="label" themeColor="primaryForeground">
                    다음
                  </ThemedText>
                </Pressable>
              )}
            </View>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing[5],
    backgroundColor: 'rgba(40, 32, 15, 0.3)',
  },
  card: {
    width: '100%',
    maxWidth: 400,
    gap: Spacing[5],
    padding: Spacing[6],
    borderRadius: Radius.xl,
    borderWidth: 1,
    borderColor: c.border,
    backgroundColor: c.card,
    boxShadow: elevation.dialog,
  },
  closeButton: {
    position: 'absolute',
    right: Spacing[3],
    top: Spacing[3],
    zIndex: 10,
    minWidth: 32,
    minHeight: 32,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
  },
  closeIcon: { fontSize: 18, color: c.textSecondary },
  carousel: { width: '100%' },
  slide: {
    alignItems: 'center',
    gap: Spacing[4],
    paddingHorizontal: Spacing[1],
  },
  iconBadge: {
    width: 64,
    height: 64,
    borderRadius: Radius.full,
    backgroundColor: c.secondary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  icon: { fontSize: 30 },
  slideTitle: { textAlign: 'center' },
  slideBody: { textAlign: 'center' },
  slideNote: { textAlign: 'center' },
  dots: { flexDirection: 'row', justifyContent: 'center', gap: Spacing[2] },
  dot: { width: 8, height: 8, borderRadius: Radius.full },
  dotActive: { backgroundColor: c.primary },
  dotIdle: { backgroundColor: c.border },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing[3],
  },
  footerActions: { flexDirection: 'row', alignItems: 'center', gap: Spacing[2] },
  skip: { minHeight: 44, justifyContent: 'center' },
  prevButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: c.border,
  },
  nextButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[5],
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Radius.md,
    backgroundColor: c.primary,
  },
});
