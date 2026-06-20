// 지역 콤보 (Story 3.4 — AC1·AC5). 시/군/구 → 동/읍/면 2단 shadcn Select.
//
// 데이터(useRegions)는 여기서 가져오되, **선택 상태는 부모(ExploreView)가 들고 내려준다**
// (지도/목록 토글 왕복 시 선택 보존 — AC5). 시군구 변경 시 동 선택을 리셋한다. 각 Select 는
// 접근 이름(aria-label)을 가진다(NFR-5 — 아이콘 단독 컨트롤 접근성).
import { useEffect } from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { dongsFor } from "./regions";
import { useRegions } from "./useRegions";

// 동 콤보의 "전체"(시군구 전체) 센티넬. Radix SelectItem 은 빈 문자열 value 를 허용하지 않으므로
// undefined(동 미선택=구 전체) 를 명시 옵션으로 표현한다 — 동을 골랐다가 다시 "전체"로 돌아올 수 있게.
const DONG_ALL = "__all__";

type RegionCombosProps = {
  sigunguCode: string | undefined;
  dongCode: string | undefined;
  onSigunguChange: (code: string | undefined) => void;
  onDongChange: (code: string | undefined) => void;
};

export function RegionCombos({
  sigunguCode,
  dongCode,
  onSigunguChange,
  onDongChange,
}: RegionCombosProps) {
  const { data: groups = [], isLoading, isError, refetch } = useRegions();
  const dongs = dongsFor(groups, sigunguCode);

  // [Review][Patch] stale 선택 조정 — 데이터 리페치(refetchOnMount:'always')로 선택했던 시군구/동이
  // 사라지면(룸 추가/삭제) 부모가 든 선택 상태를 정리한다. 미정리 시 콤보는 placeholder 를 보이지만
  // resolveRegionCode 가 stale 코드로 조회 → 시군구에 룸이 있어도 거짓 "이 지역엔 등록된 곳이 없어요".
  // 데이터가 준비된 뒤에만 수행(로딩/에러/빈 동안은 미조정 — 일시적 빈 dongs 로 정상 선택을 지우지 않게).
  useEffect(() => {
    if (isLoading || isError || groups.length === 0) return;
    if (sigunguCode && !groups.some((g) => g.code === sigunguCode)) {
      onSigunguChange(undefined);
      onDongChange(undefined);
      return;
    }
    const currentDongs = dongsFor(groups, sigunguCode);
    if (dongCode && !currentDongs.some((d) => d.code === dongCode)) {
      onDongChange(undefined);
    }
  }, [
    groups,
    sigunguCode,
    dongCode,
    isLoading,
    isError,
    onSigunguChange,
    onDongChange,
  ]);

  // [Review][Patch] 콤보 데이터 로드 실패 → 막다른 화면 금지(NFR-5). 콤보를 조용히 비활성화하면
  // 목록 모드가 막히므로(선택·재시도 불가), 목록 에러 분기(RoomList)와 동일하게 재시도를 노출한다.
  if (isError) {
    return (
      <div className="flex flex-col items-start gap-2 rounded-lg border border-border bg-card p-4">
        <p className="text-sm font-medium text-card-foreground">
          지역 목록을 못 불러왔어요.
        </p>
        <button
          type="button"
          onClick={() => refetch()}
          className="tap-target inline-flex items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
        >
          다시 시도
        </button>
      </div>
    );
  }

  const combosDisabled = isLoading || groups.length === 0;

  return (
    <div className="flex flex-wrap gap-2">
      {/* 1차: 시/군/구(시도 포함 라벨). 변경 시 동 선택 리셋. 빈 문자열=미선택(항상 controlled —
          undefined 로 두면 uncontrolled→controlled 전환 경고). 빈 문자열은 어떤 옵션과도 불일치라
          placeholder 가 표시된다. */}
      <Select
        value={sigunguCode ?? ""}
        onValueChange={(code) => {
          onSigunguChange(code);
          onDongChange(undefined); // 시군구 변경 → 동 리셋(AC1)
        }}
        disabled={combosDisabled}
      >
        <SelectTrigger aria-label="시/군/구 선택" className="min-w-44">
          <SelectValue placeholder="시/군/구" />
        </SelectTrigger>
        <SelectContent>
          {groups.map((g) => (
            <SelectItem key={g.code} value={g.code}>
              {g.name} ({g.room_count})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* 2차: 동/읍/면(선택 시군구의 dongsFor). 시군구 미선택이면 비활성. */}
      <Select
        value={dongCode ?? DONG_ALL}
        onValueChange={(code) =>
          onDongChange(code === DONG_ALL ? undefined : code)
        }
        disabled={combosDisabled || !sigunguCode}
      >
        <SelectTrigger aria-label="동/읍/면 선택" className="min-w-40">
          <SelectValue placeholder="동/읍/면 전체" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={DONG_ALL}>동/읍/면 전체</SelectItem>
          {dongs.map((d) => (
            <SelectItem key={d.code} value={d.code}>
              {d.name} ({d.room_count})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
