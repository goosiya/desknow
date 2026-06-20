import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  AccessibilityInfo,
  Keyboard,
  Pressable,
  StyleSheet,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { router, type Href } from "expo-router";
import BottomSheet, {
  BottomSheetBackdrop,
  BottomSheetScrollView,
  BottomSheetTextInput,
  BottomSheetView,
  type BottomSheetBackdropProps,
} from "@gorhom/bottom-sheet";

import { ThemedText } from "@/components/themed-text";
import { Colors, Radius, Spacing } from "@/constants/theme";

import type { UseChatbotResult } from "./useChatbot";

// 챗봇 "룸메이트" 대화 패널 — 웹 ChatbotPanel(vaul) RN 포팅 (Story 9.3 — AC6·AC8). @gorhom/bottom-sheet
// (9.1 RoomSheet 동형·~80% 스냅)로 드래그-닫기 + controlled open/close. 메시지 목록(BottomSheetScrollView
// 자동 하단 스크롤) + 입력 + 전송. 첫 진입 인사·제안 칩, 스트리밍 타이핑 인디케이터, 전송 실패 재전송,
// 미로그인 안내(입력 대신 로그인 유도 — 401 위장 차단)를 RN으로 그린다. 어시스턴트 본문의 마크다운
// 내부 링크만 화이트리스트로 라우팅(오픈리다이렉트/XSS 방지). 카피·정규식은 웹 verbatim 복사.

// 첫 진입 제안 칩 — 탭=전송. (웹 verbatim)
const SUGGESTION_CHIPS = ["환불 규정?", "강남 오후 3시 빈 방"] as const;

// 모델 실패 카피(고정). 네트워크 단절 카피는 별도 표준이나, 본 패널의 일반 전송 실패는 업스트림(LLM)
// 막힘이 주 경로라 아래 카피를 쓴다([[terminology-network-disconnect-not-offline]]). (웹 verbatim)
const ERROR_COPY = "잠깐 답이 막혔어요. 다시 물어봐 주실래요?";

// ── 내부 링크 화이트리스트(웹 verbatim 복사 — Story 7.6 AC6) ──────────────────────────────
// href 완전 일치: 룸 상세 `/rooms/{uuid}` · 홈 `/` · 탐색 딥링크 `/?view=list&sigungu=&dong=`만 허용.
// 모두 same-origin 상대경로라 오픈리다이렉트 위험 없음. 그 밖 임의 URL/스킴은 링크화하지 않는다.
const INTERNAL_HREF_RE =
  /^(?:\/rooms\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\/(?:\?view=list(?:&(?:sigungu|dong)=\d{1,10})*)?)$/;

// LLM이 룸 안내에 쓰는 마크다운 링크 `[라벨](href)` — href는 상대경로(/rooms/...)일 수도, LLM이 도메인을
// 붙인 절대 URL(https://.../rooms/...)일 수도 있다. 둘 다 매칭하고(아래 toInternalPath로 경로만 추출),
// 내부 경로면 라벨만 링크화, 아니면 라벨만 평문으로 — **어느 경우든 URL은 화면에 노출하지 않는다**(KTH #7).
const MD_LINK_RE = /\[([^\]\n]+)\]\(([^)\s]+)\)/g;

// 마크다운 링크 밖 평문에 떠도는 bare 내부 경로(안전망). 경계는 유니코드 letter/number + `/`(u 플래그).
const BARE_PATH_RE =
  "(?<![\\p{L}\\p{N}/])(?:\\/rooms\\/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\\/(?![\\p{L}\\p{N}/]))";

export function ChatbotPanel({
  chatbot,
  open,
  onClose,
}: {
  chatbot: UseChatbotResult;
  /** 드로어 오픈 여부 — 부모(FAB)가 controlled로 연다. */
  open: boolean;
  /** 닫힘(드래그/백드롭/내부 링크 탭/로그아웃) 시 부모에 알림. */
  onClose: () => void;
}) {
  const { messages, send, retry, isSending, isStreaming, isError, isReady, isAuthed } =
    chatbot;
  const isEmpty = messages.length === 0;

  // 시트 콘텐츠 고정 높이(9.4 CHAT-1·KTH #4) — @gorhom BottomSheetView 는 flex:1 만으론 스냅 높이를
  // 채우지 않고 콘텐츠 높이로 줄어, 메시지가 적으면 입력바가 위로 떠올랐다. 스냅(90%)에서 핸들을 뺀
  // 높이를 명시해 스크롤 영역(flex:1)이 채워지고 입력바가 하단에 고정되게 한다.
  const { height: windowHeight } = useWindowDimensions();
  // 안전영역 하단 인셋 = Android 소프트 내비키/제스처바 높이. 입력·전송 버튼이 소프트키와 겹치지 않게
  // 시트 하단 패딩에 이 값을 더한다(실기기 2026-06-20). 키보드 열림 시엔 keyboardBehavior가 추가로 들어올림.
  const insets = useSafeAreaInsets();
  const sheetContentHeight = Math.round(windowHeight * 0.9) - 28;

  // Android 15 edge-to-edge 키보드 회피 — @gorhom의 키보드 핸들링(interactive/adjustResize)이 OS에서
  // 무시돼 입력창이 키보드에 가린다. RN Keyboard 이벤트로 키보드 높이를 직접 받아 시트 하단 패딩으로 입력을
  // 키보드 위로 올린다(JS 전용·네이티브 재빌드 불필요).
  const [keyboardHeight, setKeyboardHeight] = useState(0);
  useEffect(() => {
    const onShow = Keyboard.addListener("keyboardDidShow", (e) => {
      setKeyboardHeight(e.endCoordinates?.height ?? 0);
    });
    const onHide = Keyboard.addListener("keyboardDidHide", () => {
      setKeyboardHeight(0);
    });
    return () => {
      onShow.remove();
      onHide.remove();
    };
  }, []);

  const sheetRef = useRef<BottomSheet>(null);
  const scrollRef = useRef<{ scrollToEnd: (opts?: { animated?: boolean }) => void }>(null);
  const inputRef = useRef<TextInput>(null);

  // open 변화에 따라 시트를 펼치고/닫는다(controlled — FAB이 연다).
  useEffect(() => {
    if (open) sheetRef.current?.expand();
    else sheetRef.current?.close();
  }, [open]);

  // 새 메시지/스트리밍 토큰·오픈 시, 그리고 **키보드 표시/숨김 시**(keyboardHeight 변화) 대화 영역을 최신
  // (하단)으로 자동 스크롤한다(웹 scrollTop=scrollHeight 등가). 키보드가 뜨면 스크롤 영역이 줄어드는데 같이
  // 하단 정렬해 최신 메시지가 입력창 바로 위에 보이게 한다(실기기 2026-06-20).
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(t);
  }, [open, messages, isSending, isError, keyboardHeight]);

  // 타이핑 시작 시 스크린리더 공지(웹 sr-only aria-live 등가).
  useEffect(() => {
    if (isSending) AccessibilityInfo.announceForAccessibility("답변을 준비하고 있어요");
  }, [isSending]);

  const handleChange = useCallback(
    (index: number) => {
      if (index === -1 && open) onClose();
    },
    [open, onClose],
  );

  const renderBackdrop = useCallback(
    (props: BottomSheetBackdropProps) => (
      <BottomSheetBackdrop
        {...props}
        appearsOnIndex={0}
        disappearsOnIndex={-1}
        pressBehavior="close"
      />
    ),
    [],
  );

  /** 내부 링크 탭 → 라우팅 + 패널 닫기(웹 Drawer.Close 상속 등가). */
  const navigateInternal = useCallback(
    (href: string) => {
      onClose();
      router.push(href as Href);
    },
    [onClose],
  );

  return (
    // ⚠️ 닫힘 상태에서 BottomSheet 백드롭이 화면 전체 터치를 삼키는 네이티브 버그 차단(실기기 확인 2026-06-20).
    // 비-모달 BottomSheet+백드롭은 항상 마운트되는데, 초기 닫힘(index -1)에서 백드롭 pointerEvents가 'none'으로
    // 떨어지기 전까지 투명하게 전 화면을 덮어 모든 터치를 가로챈다(FAB만 zIndex로 생존, 한 번 열었다 닫으면 풀림).
    // open일 때만 시트 서브트리가 터치를 받게 게이팅한다(닫히면 아래 화면으로 통과).
    <View style={StyleSheet.absoluteFill} pointerEvents={open ? 'auto' : 'none'}>
    <BottomSheet
      ref={sheetRef}
      index={-1}
      // 거의 전체 높이(웹 ChatbotPanel 미러 — 9.4 CHAT-2, 기존 80%에서 상향).
      snapPoints={["90%"]}
      enableDynamicSizing={false}
      enablePanDownToClose
      // 긴 대화 스크롤 시 콘텐츠 드래그가 시트를 움직이는 제스처 충돌 제거 — 콘텐츠 영역은 스크롤만 받고,
      // 시트 닫기는 핸들 드래그·X 버튼으로 한다(스크롤 vs 시트팬 충돌이 "스크롤하면 시트 전체가 움직임"으로
      // 나타났다 — 실기기 2026-06-20).
      enableContentPanningGesture={false}
      // 키보드 회피는 아래 RN Keyboard 이벤트 기반 수동 패딩으로 처리한다(edge-to-edge에선 @gorhom
      // interactive/adjustResize 무동작). extend는 단일 스냅(90%)이라 시트 위치 불변 = 중복 이동 방지.
      keyboardBehavior="extend"
      keyboardBlurBehavior="restore"
      android_keyboardInputMode="adjustResize"
      onChange={handleChange}
      backdropComponent={renderBackdrop}
      backgroundStyle={styles.sheetBackground}
      handleIndicatorStyle={styles.handle}
    >
      <BottomSheetView
        style={[
          styles.content,
          {
            height: sheetContentHeight,
            // 입력을 띄우는 하단 패딩 = 소프트키 인셋 + 키보드 높이 + 여백. RN이 보고하는 키보드 높이는
            // edge-to-edge에서 내비바 인셋을 빼고 주므로(실측 297.5) insets.bottom을 항상 더해야 키패드와
            // 안 겹친다(닫힘 시 keyboardHeight=0 → 소프트키 위 — KTH 실기기 확인 2026-06-20).
            paddingBottom: insets.bottom + keyboardHeight + Spacing[4],
          },
        ]}
      >
        {/* 헤더 — 제목 + 닫기 */}
        <View style={styles.header}>
          <ThemedText type="h3" themeColor="cardForeground">
            룸메이트
          </ThemedText>
          <Pressable
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel="챗봇 닫기"
            style={styles.close}
          >
            <ThemedText type="h3" themeColor="textSecondary">
              ✕
            </ThemedText>
          </Pressable>
        </View>

        {/* 메시지 영역 — flex:1로 채워 입력바를 시트 최하단에 고정한다(9.4 CHAT-1, 기존엔 콘텐츠
            높이로 줄어 입력바가 추천칩 바로 아래로 떠올랐음). */}
        <BottomSheetScrollView
          ref={scrollRef as never}
          style={styles.scrollArea}
          contentContainerStyle={styles.messages}
          accessibilityLiveRegion="polite"
          keyboardShouldPersistTaps="handled"
        >
          {!isAuthed ? (
            // 미로그인: 입력 대신 로그인 안내(401 위장 차단).
            <View style={styles.authGate}>
              <ThemedText type="bodySm" themeColor="textSecondary">
                로그인하면 룸메이트와 대화할 수 있어요.
              </ThemedText>
              <Pressable
                onPress={() => {
                  onClose();
                  router.push("/login?next=/" as Href);
                }}
                accessibilityRole="button"
                style={styles.primaryButton}
              >
                <ThemedText type="label" themeColor="primaryForeground">
                  로그인하기
                </ThemedText>
              </Pressable>
            </View>
          ) : isEmpty ? (
            // 첫 진입: 인사 + 제안 칩(탭=전송).
            <View style={styles.intro}>
              <ThemedText type="bodySm" themeColor="textSecondary">
                안녕하세요, 룸메이트예요. 무엇을 도와드릴까요?
              </ThemedText>
              <View style={styles.chips}>
                {SUGGESTION_CHIPS.map((chip) => (
                  <Pressable
                    key={chip}
                    onPress={() => send(chip)}
                    disabled={!isReady || isStreaming}
                    accessibilityRole="button"
                    style={[styles.chip, (!isReady || isStreaming) && styles.disabled]}
                  >
                    <ThemedText type="bodySm" themeColor="text">
                      {chip}
                    </ThemedText>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : (
            messages.map((m, i) => (
              <ChatBubble
                key={i}
                role={m.role}
                content={m.content}
                onNavigate={navigateInternal}
              />
            ))
          )}

          {/* 타이핑 인디케이터 — 전송~첫 토큰 사이만. */}
          {isSending ? (
            <View
              style={styles.typing}
              accessibilityLabel="답변을 준비하고 있어요"
              testID="chatbot-typing"
            >
              <ThemedText type="bodySm" themeColor="textSecondary">
                ···
              </ThemedText>
            </View>
          ) : null}

          {/* 전송 실패 — 에러 카피 + 재전송(스트림 종료 후에만). */}
          {isError && !isStreaming ? (
            <View style={styles.errorBox} accessibilityRole="alert">
              <ThemedText type="bodySm" themeColor="textSecondary">
                {ERROR_COPY}
              </ThemedText>
              <Pressable onPress={retry} accessibilityRole="button" style={styles.primaryButton}>
                <ThemedText type="label" themeColor="primaryForeground">
                  다시 보내기
                </ThemedText>
              </Pressable>
            </View>
          ) : null}
        </BottomSheetScrollView>

        {/* 입력 + 전송 */}
        <ChatInput
          inputRef={inputRef}
          disabled={!isReady || isStreaming || !isAuthed}
          isAuthed={isAuthed}
          onSend={send}
        />
      </BottomSheetView>
    </BottomSheet>
    </View>
  );
}

/** 입력창 + 전송 버튼 — 비제어 입력(전송 후 초기화). */
function ChatInput({
  inputRef,
  disabled,
  isAuthed,
  onSend,
}: {
  inputRef: React.RefObject<TextInput | null>;
  disabled: boolean;
  isAuthed: boolean;
  onSend: (text: string) => void;
}) {
  const valueRef = useRef("");
  const submit = () => {
    const text = valueRef.current;
    if (text.trim() === "") return;
    onSend(text);
    valueRef.current = "";
    inputRef.current?.clear();
  };
  return (
    <View style={styles.inputRow}>
      {/* @gorhom BottomSheetTextInput — 시트가 포커스된 입력을 추적해 키보드 위로 올린다(기본 RN
          TextInput은 시트가 인지 못해 키보드에 가려졌다 — 실기기 2026-06-20). */}
      <BottomSheetTextInput
        // @gorhom BottomSheetTextInput의 ref 타입은 gesture-handler TextInput이라 RN TextInput ref와
        // 안 맞는다(런타임은 RN TextInput으로 포워딩 — .clear() 동작). scrollRef as never와 동일 처리.
        ref={inputRef as never}
        onChangeText={(t) => {
          valueRef.current = t;
        }}
        onSubmitEditing={submit}
        editable={!disabled}
        placeholder={isAuthed ? "메시지를 입력하세요" : "로그인 후 이용할 수 있어요"}
        placeholderTextColor={Colors.light.textSecondary}
        accessibilityLabel="메시지 입력"
        returnKeyType="send"
        style={[styles.input, disabled && styles.disabled]}
      />
      <Pressable
        onPress={submit}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityLabel="전송"
        style={[styles.sendButton, disabled && styles.disabled]}
      >
        <ThemedText type="label" themeColor="primaryForeground">
          전송
        </ThemedText>
      </Pressable>
    </View>
  );
}

/** 마크다운 링크 href → 내부 경로(경로+쿼리)만 추출. 절대 URL(LLM 도메인 환각 포함)이면 도메인을 버리고
 *  pathname+search 만, 상대경로면 그대로. 그 외(스킴 등)는 null. 도메인을 신뢰하지 않아 오픈리다이렉트
 *  안전 — 최종 라우팅은 INTERNAL_HREF_RE 로 한 번 더 검증한다. */
function toInternalPath(href: string): string | null {
  if (/^https?:\/\//i.test(href)) {
    try {
      const u = new URL(href);
      return `${u.pathname}${u.search}`;
    } catch {
      return null;
    }
  }
  return href.startsWith("/") ? href : null;
}

/** 내부 경로 링크 1개 — 라벨 텍스트로 표시. 탭 시 라우팅 + 패널 닫기. */
function internalLink(
  href: string,
  label: string,
  key: string,
  onNavigate: (href: string) => void,
): ReactNode {
  return (
    <ThemedText
      key={key}
      type="bodySm"
      themeColor="primary"
      style={styles.link}
      onPress={() => onNavigate(href)}
    >
      {label}
    </ThemedText>
  );
}

/** 평문 조각에서 bare 내부 경로(라벨=경로)를 링크화한다(마크다운 링크 처리 후 안전망). */
function linkifyBarePaths(
  text: string,
  keyPrefix: string,
  onNavigate: (href: string) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = new RegExp(BARE_PATH_RE, "gu");
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const path = match[0];
    nodes.push(internalLink(path, path, `${keyPrefix}-${match.index}`, onNavigate));
    last = match.index + path.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/** 어시스턴트 content 렌더 분해: 마크다운 `[라벨](/경로)`는 라벨만 링크(내부 화이트리스트), bare 내부
 *  경로는 안전망 링크, 비-내부 URL은 링크하지 않는다(웹 renderAssistantContent 미러). */
function renderAssistantContent(
  content: string,
  onNavigate: (href: string) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = new RegExp(MD_LINK_RE.source, "g");
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = re.exec(content)) !== null) {
    if (match.index > last) {
      nodes.push(...linkifyBarePaths(content.slice(last, match.index), `seg${i}`, onNavigate));
    }
    const label = match[1];
    const path = toInternalPath(match[2]); // 절대 URL이어도 경로만 추출(URL 비노출 — KTH #7)
    if (path && INTERNAL_HREF_RE.test(path)) {
      nodes.push(internalLink(path, label, `md${i}`, onNavigate));
    } else {
      nodes.push(label); // 비-내부(잠재 악성 URL/스킴) → 라벨만 평문(링크·URL 비노출 — 신뢰 경계)
    }
    last = match.index + match[0].length;
    i += 1;
  }
  if (last < content.length) {
    nodes.push(...linkifyBarePaths(content.slice(last), "tail", onNavigate));
  }
  return nodes;
}

/** 대화 한 줄 버블 — user(우측 primary) / assistant(좌측 muted, 내부 경로 linkify). */
function ChatBubble({
  role,
  content,
  onNavigate,
}: {
  role: string;
  content: string;
  onNavigate: (href: string) => void;
}) {
  const isUser = role === "user";
  return (
    <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleAssistant]}>
      <ThemedText type="bodySm" themeColor={isUser ? "primaryForeground" : "text"}>
        {isUser ? content : renderAssistantContent(content, onNavigate)}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  sheetBackground: {
    backgroundColor: Colors.light.card,
    borderTopLeftRadius: Radius.xl,
    borderTopRightRadius: Radius.xl,
  },
  handle: { backgroundColor: Colors.light.border, width: 48 },
  content: { paddingHorizontal: Spacing[5], paddingBottom: Spacing[4] },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingBottom: Spacing[2],
  },
  close: { minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" },
  scrollArea: { flex: 1 },
  messages: { gap: Spacing[3], paddingVertical: Spacing[2], flexGrow: 1 },
  authGate: { gap: Spacing[3], alignItems: "flex-start" },
  intro: { gap: Spacing[3] },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: Spacing[2] },
  chip: {
    minHeight: 44,
    paddingHorizontal: Spacing[3],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.full,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.background,
  },
  bubble: {
    maxWidth: "85%",
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
    borderRadius: Radius.lg,
  },
  bubbleUser: { alignSelf: "flex-end", backgroundColor: Colors.light.primary },
  bubbleAssistant: { alignSelf: "flex-start", backgroundColor: Colors.light.backgroundElement },
  link: { textDecorationLine: "underline" },
  typing: {
    alignSelf: "flex-start",
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
    borderRadius: Radius.lg,
    backgroundColor: Colors.light.backgroundElement,
  },
  errorBox: { gap: Spacing[2], alignItems: "flex-start" },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: Spacing[2],
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: Colors.light.border,
    paddingTop: Spacing[3],
  },
  input: {
    flex: 1,
    minHeight: 44,
    borderWidth: 1,
    borderColor: Colors.light.border,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing[3],
    fontSize: 14,
    color: Colors.light.text,
    backgroundColor: Colors.light.background,
  },
  sendButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  primaryButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  disabled: { opacity: 0.5 },
});
