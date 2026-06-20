// Expo SDK56 Metro 설정 (Story 1.6).
// 첫 워크스페이스 import(@desknow/ui TS 소스) 대비 명시 배치.
// getDefaultConfig 가 모노레포 심볼릭/exports/노드모듈 TS 트랜스파일을 자동 처리한다
// (Expo SDK56 기준 transpilePackages 불필요).
const { getDefaultConfig } = require('expo/metro-config');

module.exports = getDefaultConfig(__dirname);
