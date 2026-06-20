import { useState } from "react";
import { Platform, Pressable, StyleSheet, TextInput, View } from "react-native";
import { router, type Href } from "expo-router";

import { ThemedText } from "@/components/themed-text";
import { ComboSelect, type ComboOption } from "@/components/ComboSelect";
import { Colors, Radius, Spacing } from "@/constants/theme";
import { AMENITY_LABELS, ROOM_TYPE_LABELS } from "@/features/map/roomSummary";
import { RoomLocationMap } from "@/features/detail/RoomLocationMap";
import { registerErrorCopy } from "@/features/auth/authCopy";
import {
  clearPendingSignup,
  getPendingSignup,
  type PendingSignup,
} from "@/features/auth/pendingSignup";
import { useRegister } from "@/features/auth/useAuth";
import type {
  GeocodeResult,
  ProviderRoomDetail,
  RoomCreateRequest,
} from "@/lib/api-client";

import { GeocoderWebView } from "./GeocoderWebView";
import {
  AMENITY_CODES,
  ROOM_TYPES,
  WEEKDAYS,
  initialHours,
  type DayHours,
} from "./roomFields";
import {
  saveRoomErrorCopy,
  useGeocode,
  useMyRoom,
  useSaveRoom,
} from "./useProviderRoom";

// 스터디룸 등록/수정 폼 — 웹 RoomForm.tsx RN 포팅 (Story 9.3 — AC4·§범위 2). 이름·주소검색(지오코딩)·
// 수용·시간당 금액·룸형태·부대시설·영업시간을 입력해 저장한다. 보유 룸이 있으면 prefill(수정), 없으면
// 생성. 가입 전(pendingSignup)이면 저장이 회원가입→룸 생성을 원자 처리한다(떠도는 계정 방지). 백엔드
// 호출은 생성 SDK 경유 훅(useProviderRoom)만. 지오코딩은 로그인=백엔드 geocode / 가입 전=WebView 카카오.

// 24h "HH:MM" → 12h 표기 "오전/오후 hh:mm"(9.4 ROOM-1 — 웹 <input type=time>의 12h 표시 정본).
// value(저장·검증용)는 24h "HH:MM"을 유지하고 **표시 라벨만** 12h로 바꾼다(와이어 "HH:MM:00"·
// close>open 문자열 검증 불변).
function to12h(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  const period = h < 12 ? "오전" : "오후";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${period} ${String(h12).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

// 영업시간 선택지 — 30분 단위(RN엔 <input type=time>이 없어 ComboSelect로 대체·무효입력 방지·분 정밀·
// Expo Web 호환). value=24h "HH:MM"(저장·검증), label=12h 표기(웹 정본 표시). 그리드 밖 값(예: 보유 룸
// 09:15)은 선택지에 없어도 저장값은 보존된다.
const TIME_OPTIONS: ComboOption[] = Array.from({ length: 48 }, (_, i) => {
  const hh = String(Math.floor(i / 2)).padStart(2, "0");
  const mm = i % 2 === 0 ? "00" : "30";
  const v = `${hh}:${mm}`;
  return { value: v, label: to12h(v) };
});

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <ThemedText type="label" themeColor="text">
      {children}
    </ThemedText>
  );
}

function RoomFormInner({
  initial,
  pendingSignup,
}: {
  initial: ProviderRoomDetail | null;
  pendingSignup: PendingSignup | null;
}) {
  const geocode = useGeocode();
  const save = useSaveRoom(initial?.room_id ?? null);
  const register = useRegister();

  const [name, setName] = useState(initial?.name ?? "");
  // 신규 등록은 빈 값 + placeholder(기본값 미리 넣지 않음 — KTH 2026-06-19). 수정은 기존값 prefill.
  const [capacity, setCapacity] = useState(initial ? String(initial.capacity) : "");
  const [price, setPrice] = useState(initial ? String(initial.price_per_hour) : "");
  const [roomType, setRoomType] = useState<string>(initial?.room_type ?? "open");
  const [amenities, setAmenities] = useState<Set<string>>(
    new Set(initial?.amenities ?? ["wifi"]),
  );
  const [hours, setHours] = useState<DayHours[]>(() => initialHours(initial));

  // 주소(지오코딩으로 확정) — 좌표·지역은 직접 못 넣고 검색 결과 선택으로만 채운다.
  const [query, setQuery] = useState(initial?.address ?? "");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [noUsable, setNoUsable] = useState(false); // 결과는 있으나 등록불가(b_code 없음)
  const [noResults, setNoResults] = useState(false); // 0건(못 찾음)
  const [picked, setPicked] = useState<GeocodeResult | null>(
    initial
      ? {
          address: initial.address ?? "",
          lat: initial.lat,
          lng: initial.lng,
          admin_dong_code: initial.admin_dong_code,
        }
      : null,
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);
  // 가입 전 WebView 지오코더 검색 트리거(nonce 증가 = 검색 실행).
  const [geocodeNonce, setGeocodeNonce] = useState(0);

  function toggleAmenity(code: string) {
    setAmenities((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  function setDay(i: number, patch: Partial<DayHours>) {
    setHours((prev) => prev.map((d, idx) => (idx === i ? { ...d, ...patch } : d)));
  }

  /** 지오코딩 결과(로그인 백엔드/가입 전 WebView 공통)를 usable 필터·상태에 반영한다(웹 runGeocode 동형). */
  function applyGeocodeResults(all: GeocodeResult[]) {
    // 등록엔 지역 코드가 필수 — 도로명만(b_code 없는) 결과는 거른다. 0건과 "결과 있으나 등록불가"를 구분.
    const usable = all.filter((r) => r.admin_dong_code);
    setResults(usable);
    setNoResults(all.length === 0);
    setNoUsable(all.length > 0 && usable.length === 0);
    if (usable.length === 0) setPicked(null);
  }

  async function runGeocode() {
    if (!query.trim() || searching) return;
    // 새 검색마다 이전 결과·안내를 비운다(옛 후보 잔존 방지).
    setResults([]);
    setNoUsable(false);
    setNoResults(false);
    setSearchFailed(false);
    setSearching(true);
    if (pendingSignup) {
      // 가입 전: 미인증이라 백엔드 geocode 불가 → WebView 카카오 Geocoder(nonce 트리거·결과는 콜백).
      // Expo Web은 react-native-webview 미지원 → 즉시 graceful degrade(검증 불가 인지·맵 동형).
      if (Platform.OS === "web") {
        setSearching(false);
        setSearchFailed(true);
        return;
      }
      setGeocodeNonce((n) => n + 1); // onResults/onError가 setSearching(false) 마무리
      return;
    }
    // 로그인 provider: 백엔드 geocode(provider 전용·Expo Web 동작).
    try {
      const all = await geocode.mutateAsync(query.trim());
      applyGeocodeResults(all);
    } catch {
      setSearchFailed(true);
    } finally {
      setSearching(false);
    }
  }

  function selectResult(r: GeocodeResult) {
    setPicked(r);
    setQuery(r.address);
    setResults([]);
    setNoUsable(false);
    setNoResults(false);
  }

  function submit() {
    setFormError(null);
    if (!name.trim()) {
      setFormError("스터디룸 이름을 입력해 주세요.");
      return;
    }
    if (!picked) {
      setFormError("주소를 검색해 선택해 주세요.");
      return;
    }
    const capacityNum = Number(capacity);
    if (!capacity.trim() || !Number.isInteger(capacityNum) || capacityNum < 1) {
      setFormError("수용 인원을 1명 이상 입력해 주세요.");
      return;
    }
    const priceNum = Number(price);
    if (!price.trim() || !Number.isInteger(priceNum) || priceNum < 0) {
      setFormError("시간당 금액을 0원 이상 정수로 입력해 주세요.");
      return;
    }
    if (!roomType) {
      setFormError("룸 형태를 선택해 주세요.");
      return;
    }
    const businessHours = hours
      .map((d, weekday) => ({ d, weekday }))
      .filter(({ d }) => d.on)
      .map(({ d, weekday }) => ({
        weekday,
        open_time: `${d.open}:00`,
        close_time: `${d.close}:00`,
      }));
    if (businessHours.length === 0) {
      setFormError("영업하는 요일을 하나 이상 선택해 주세요.");
      return;
    }
    if (businessHours.some((b) => b.close_time <= b.open_time)) {
      setFormError("영업 종료 시각은 시작 시각보다 늦어야 해요.");
      return;
    }
    const payload: RoomCreateRequest = {
      name: name.trim(),
      price_per_hour: Number(price),
      capacity: Number(capacity),
      room_type: roomType as RoomCreateRequest["room_type"],
      amenities: [...amenities] as RoomCreateRequest["amenities"],
      lat: picked.lat,
      lng: picked.lng,
      admin_dong_code: picked.admin_dong_code,
      address: picked.address,
      business_hours: businessHours,
    };
    const goProvider = () => router.replace("/provider/reservations" as Href);
    if (pendingSignup) {
      // 가입 대기: 회원가입(→자동 로그인) 성공 후에만 룸을 생성(원자 처리). 가입 실패면 룸 미생성.
      register.mutate(
        { email: pendingSignup.email, password: pendingSignup.password, role: "provider" },
        {
          onSuccess: () => {
            save.mutate(payload, {
              onSuccess: () => {
                clearPendingSignup();
                goProvider();
              },
            });
          },
        },
      );
      return;
    }
    save.mutate(payload, { onSuccess: goProvider });
  }

  const submitting = save.isPending || register.isPending;
  const submitLabel = submitting
    ? "처리 중…"
    : pendingSignup
      ? "가입하고 등록하기"
      : initial
        ? "수정 저장"
        : "등록하기";
  const errorCopy = formError
    ? formError
    : save.error
      ? saveRoomErrorCopy(save.error.failure)
      : register.error
        ? registerErrorCopy(register.error.failure)
        : null;

  return (
    <View style={styles.wrap}>
      {/* 가입 전 WebView 지오코더(보이지 않음) — 네이티브에서만 실동작(웹 degrade). */}
      {pendingSignup ? (
        <GeocoderWebView
          query={query.trim()}
          nonce={geocodeNonce}
          onResults={(all) => {
            applyGeocodeResults(all);
            setSearching(false);
          }}
          onError={() => {
            setSearchFailed(true);
            setSearching(false);
          }}
        />
      ) : null}

      <View style={styles.header}>
        <ThemedText type="h2" themeColor="text">
          {initial ? "스터디룸 수정" : "스터디룸 등록"}
        </ThemedText>
        <ThemedText type="bodySm" themeColor="textSecondary">
          MVP에서는 제공자당 한 개의 스터디룸을 등록할 수 있어요.
        </ThemedText>
        {pendingSignup ? (
          <ThemedText type="caption" themeColor="destructive" style={styles.bold}>
            이 정보를 등록하면 회원가입이 함께 완료돼요.
          </ThemedText>
        ) : null}
      </View>

      {/* 이름 */}
      <View style={styles.field}>
        <FieldLabel>스터디룸 이름</FieldLabel>
        <TextInput
          value={name}
          onChangeText={setName}
          placeholder="예: 미사 스터디카페 A룸"
          placeholderTextColor={Colors.light.textSecondary}
          style={styles.input}
        />
      </View>

      {/* 주소 검색 */}
      <View style={styles.field}>
        <View style={styles.labelRow}>
          <FieldLabel>주소</FieldLabel>
          <ThemedText type="caption" themeColor="destructive" style={styles.bold}>
            정확하지 않으면 지도에 안 보여요
          </ThemedText>
        </View>
        <View style={styles.searchRow}>
          <TextInput
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => void runGeocode()}
            placeholder="도로명·지번 주소 검색"
            placeholderTextColor={Colors.light.textSecondary}
            style={[styles.input, styles.searchInput]}
          />
          <Pressable
            onPress={() => void runGeocode()}
            disabled={searching}
            accessibilityRole="button"
            accessibilityLabel="주소 검색"
            style={[styles.outlineButton, searching && styles.disabled]}
          >
            <ThemedText type="label" themeColor="cardForeground">
              {searching ? "검색 중" : "검색"}
            </ThemedText>
          </Pressable>
        </View>

        {/* 선택된 주소 + 위치 미니 지도(9.2 RoomLocationMap 재사용 — Expo Web degrade). */}
        {picked ? (
          <View style={styles.field}>
            <ThemedText type="bodySm" themeColor="text">
              📍 {picked.address}
            </ThemedText>
            {/* 수정 폼은 위치 확인용이라 지도를 둘러볼 수 있게 interactive(드래그/줌). 룸 상세는 정적. */}
            <RoomLocationMap
              lat={picked.lat}
              lng={picked.lng}
              name={picked.address}
              interactive
            />
          </View>
        ) : null}

        {/* 검색 결과 후보 — "선택"하라고 명시. */}
        {results.length > 0 ? (
          <View style={styles.resultsBox}>
            <ThemedText type="bodySm" themeColor="textSecondary">
              검색된 주소예요. 아래에서 정확한 주소를 선택해 주세요.
            </ThemedText>
            {results.map((r) => (
              <Pressable
                key={`${r.lat},${r.lng},${r.address}`}
                onPress={() => selectResult(r)}
                accessibilityRole="button"
                style={styles.resultItem}
              >
                <ThemedText type="bodySm" themeColor="cardForeground">
                  📍 {r.address}
                </ThemedText>
              </Pressable>
            ))}
          </View>
        ) : null}

        {noResults ? (
          <ThemedText type="bodySm" themeColor="textSecondary">
            검색 결과가 없어요. 지번 또는 도로명 주소(번지 포함)로 다시 검색해 주세요.
          </ThemedText>
        ) : null}
        {noUsable ? (
          <ThemedText type="bodySm" themeColor="textSecondary">
            번지까지 포함한 구체적인 주소로 검색해 주세요(도로명만으로는 등록할 수 없어요).
          </ThemedText>
        ) : null}
        {searchFailed ? (
          <ThemedText type="bodySm" themeColor="destructive">
            주소 검색에 실패했어요. 다시 시도해 주세요.
          </ThemedText>
        ) : null}
      </View>

      {/* 수용 인원 · 시간당 금액 */}
      <View style={styles.twoCol}>
        <View style={[styles.field, styles.flex1]}>
          <FieldLabel>수용 인원</FieldLabel>
          <TextInput
            value={capacity}
            onChangeText={setCapacity}
            keyboardType="number-pad"
            placeholder="예: 4"
            placeholderTextColor={Colors.light.textSecondary}
            style={styles.input}
          />
        </View>
        <View style={[styles.field, styles.flex1]}>
          <FieldLabel>시간당 금액(원)</FieldLabel>
          <TextInput
            value={price}
            onChangeText={setPrice}
            keyboardType="number-pad"
            placeholder="예: 10000"
            placeholderTextColor={Colors.light.textSecondary}
            style={styles.input}
          />
        </View>
      </View>

      {/* 룸 형태 — 웹 RoomForm.tsx:394-414 미러: 반폭 테두리 박스 2개(개방형 | 독립룸). 선택=primary
          테두리 + secondary(만다린 크림, 웹 bg-primary/10 등가) 배경 + foreground 텍스트(9.4 ROOM-2).
          공용 SegmentedControl(컴팩트 pill)을 쓰지 않고 부대시설 칩과 동일 패턴의 박스로 렌더해
          map/list·반경 토글 회귀를 막는다. */}
      <View style={styles.field}>
        <FieldLabel>룸 형태</FieldLabel>
        <View
          accessibilityRole="radiogroup"
          accessibilityLabel="룸 형태 선택"
          style={styles.roomTypeRow}
        >
          {ROOM_TYPES.map((t) => {
            const active = roomType === t;
            return (
              <Pressable
                key={t}
                onPress={() => setRoomType(t)}
                accessibilityRole="radio"
                accessibilityState={{ selected: active }}
                accessibilityLabel={ROOM_TYPE_LABELS[t]}
                style={[
                  styles.roomTypeBox,
                  active ? styles.chipActive : styles.chipInactive,
                ]}
              >
                <ThemedText type="label" themeColor={active ? "text" : "textSecondary"}>
                  {ROOM_TYPE_LABELS[t]}
                </ThemedText>
              </Pressable>
            );
          })}
        </View>
      </View>

      {/* 부대시설 */}
      <View style={styles.field}>
        <FieldLabel>부대시설</FieldLabel>
        <View style={styles.chipRow}>
          {AMENITY_CODES.map((code) => {
            const active = amenities.has(code);
            return (
              <Pressable
                key={code}
                onPress={() => toggleAmenity(code)}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: active }}
                accessibilityLabel={AMENITY_LABELS[code]}
                style={[styles.chip, active ? styles.chipActive : styles.chipInactive]}
              >
                <ThemedText type="bodySm" themeColor={active ? "text" : "textSecondary"}>
                  {AMENITY_LABELS[code]}
                </ThemedText>
              </Pressable>
            );
          })}
        </View>
      </View>

      {/* 영업시간 */}
      <View style={styles.field}>
        <FieldLabel>영업시간</FieldLabel>
        <View style={styles.hoursList}>
          {hours.map((d, i) => (
            <View key={WEEKDAYS[i]} style={styles.hourRow}>
              <Pressable
                onPress={() => setDay(i, { on: !d.on })}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: d.on }}
                accessibilityLabel={`${WEEKDAYS[i]}요일 영업`}
                style={styles.dayToggle}
              >
                <View style={[styles.checkbox, d.on && styles.checkboxOn]}>
                  {d.on ? (
                    <ThemedText type="caption" themeColor="primaryForeground">
                      ✓
                    </ThemedText>
                  ) : null}
                </View>
                <ThemedText type="bodySm" themeColor="text">
                  {WEEKDAYS[i]}
                </ThemedText>
              </Pressable>
              {d.on ? (
                <View style={styles.timeRow}>
                  <ComboSelect
                    accessibilityLabel={`${WEEKDAYS[i]}요일 영업 시작 시각`}
                    placeholder="시작"
                    value={d.open}
                    options={TIME_OPTIONS}
                    onChange={(v) => setDay(i, { open: v })}
                  />
                  <ThemedText type="bodySm" themeColor="textSecondary">
                    –
                  </ThemedText>
                  <ComboSelect
                    accessibilityLabel={`${WEEKDAYS[i]}요일 영업 종료 시각`}
                    placeholder="종료"
                    value={d.close}
                    options={TIME_OPTIONS}
                    onChange={(v) => setDay(i, { close: v })}
                  />
                </View>
              ) : (
                <ThemedText type="bodySm" themeColor="textSecondary">
                  휴무
                </ThemedText>
              )}
            </View>
          ))}
        </View>
      </View>

      {errorCopy ? (
        <View accessibilityRole="alert" style={styles.errorBox}>
          <ThemedText type="bodySm" themeColor="destructive">
            {errorCopy}
          </ThemedText>
        </View>
      ) : null}

      <Pressable
        onPress={submit}
        disabled={submitting}
        accessibilityRole="button"
        style={[styles.submitButton, submitting && styles.disabled]}
      >
        <ThemedText type="label" themeColor="primaryForeground">
          {submitLabel}
        </ThemedText>
      </Pressable>
    </View>
  );
}

/** 로그인된 provider — 내 룸 로드 후 prefill로 렌더(생성/수정 분기). 로드 전엔 안내. */
function ExistingRoomForm() {
  const { data, isLoading, isError } = useMyRoom();
  if (isLoading) {
    return (
      <ThemedText type="bodySm" themeColor="textSecondary">
        불러오는 중…
      </ThemedText>
    );
  }
  if (isError) {
    return (
      <ThemedText type="bodySm" themeColor="destructive">
        내 스터디룸 정보를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.
      </ThemedText>
    );
  }
  return <RoomFormInner initial={data ?? null} pendingSignup={null} />;
}

/** 가입 대기(provider 신규) vs 로그인된 provider 분기 — mount 1회 캡처(ProviderGuard와 동일 패턴). */
export function RoomForm() {
  const [pending] = useState(() => getPendingSignup());
  if (pending) {
    return <RoomFormInner initial={null} pendingSignup={pending} />;
  }
  return <ExistingRoomForm />;
}

const styles = StyleSheet.create({
  wrap: { gap: Spacing[5] },
  header: { gap: Spacing[1] },
  bold: { fontWeight: "600" },
  field: { gap: Spacing[2] },
  flex1: { flex: 1 },
  labelRow: { flexDirection: "row", flexWrap: "wrap", alignItems: "baseline", gap: Spacing[2] },
  input: {
    minHeight: 44,
    borderWidth: 1,
    borderColor: Colors.light.border,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing[3],
    fontSize: 14,
    color: Colors.light.text,
    backgroundColor: Colors.light.background,
  },
  searchRow: { flexDirection: "row", gap: Spacing[2] },
  searchInput: { flex: 1 },
  outlineButton: {
    minHeight: 44,
    paddingHorizontal: Spacing[4],
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.light.border,
    backgroundColor: Colors.light.card,
  },
  resultsBox: {
    gap: Spacing[1],
    borderWidth: 1,
    borderColor: Colors.light.border,
    borderRadius: Radius.md,
    padding: Spacing[3],
    backgroundColor: Colors.light.card,
  },
  resultItem: {
    minHeight: 44,
    justifyContent: "center",
    paddingVertical: Spacing[2],
  },
  twoCol: { flexDirection: "row", gap: Spacing[3] },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: Spacing[2] },
  chip: {
    minHeight: 36,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
    borderRadius: Radius.full,
    borderWidth: 1,
    justifyContent: "center",
  },
  chipActive: { borderColor: Colors.light.primary, backgroundColor: Colors.light.secondary },
  chipInactive: { borderColor: Colors.light.border, backgroundColor: Colors.light.background },
  roomTypeRow: { flexDirection: "row", gap: Spacing[2] },
  roomTypeBox: {
    flex: 1,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: Spacing[2],
    paddingHorizontal: Spacing[3],
    borderRadius: Radius.md,
    borderWidth: 1,
  },
  hoursList: { gap: Spacing[2] },
  hourRow: { flexDirection: "row", alignItems: "center", gap: Spacing[3] },
  dayToggle: {
    width: 64,
    flexDirection: "row",
    alignItems: "center",
    gap: Spacing[2],
    minHeight: 44,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.light.border,
    alignItems: "center",
    justifyContent: "center",
  },
  checkboxOn: { backgroundColor: Colors.light.primary, borderColor: Colors.light.primary },
  timeRow: { flexDirection: "row", alignItems: "center", gap: Spacing[2] },
  errorBox: {
    borderWidth: 1,
    borderColor: Colors.light.destructive,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing[3],
    paddingVertical: Spacing[2],
    backgroundColor: Colors.light.background,
  },
  submitButton: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: Radius.md,
    backgroundColor: Colors.light.primary,
  },
  disabled: { opacity: 0.5 },
});
