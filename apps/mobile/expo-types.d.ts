// CI 커밋용 Expo 타입 참조 — expo-env.d.ts(Expo 자동생성·.gitignore)가 제공하는
// `/// <reference types="expo/types" />`를 추적되는 파일로도 둔다. CSS(`@/global.css`)·정적
// 에셋 모듈 타입이 expo/types에서 오므로, 이게 없으면 CI(체크아웃에 expo-env.d.ts 부재)에서
// tsc check-types가 "Cannot find module ... '@/global.css'"로 실패한다(2026-06-20).
/// <reference types="expo/types" />
