import { useState } from 'react';
import { Dimensions, StyleSheet } from 'react-native';
import Animated, { Easing, Keyframe, useReducedMotion } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import { colors } from '@desknow/ui';

// 부팅 스플래시 오버레이 — 만다린 단색이 줌아웃하며 사라지는 장식 모션 (Story 1.6).
// 색은 토큰 단일출처(@desknow/ui colors.primary)에서 가져온다.
// (app.json 의 expo-splash-screen backgroundColor #FF8A1E 와 시각적으로 일치해야 한다.)
const INITIAL_SCALE_FACTOR = Dimensions.get('screen').height / 90;
const DURATION = 600;

export function AnimatedSplashOverlay() {
  const [visible, setVisible] = useState(true);
  const reduceMotion = useReducedMotion();

  if (!visible) return null;
  // AC3: 스플래시는 장식 모션 — reduced-motion 시 생략하고 즉시 콘텐츠를 보여준다.
  if (reduceMotion) return null;

  const splashKeyframe = new Keyframe({
    0: {
      transform: [{ scale: INITIAL_SCALE_FACTOR }],
      opacity: 1,
    },
    20: {
      opacity: 1,
    },
    70: {
      opacity: 0,
      easing: Easing.elastic(0.7),
    },
    100: {
      opacity: 0,
      transform: [{ scale: 1 }],
      easing: Easing.elastic(0.7),
    },
  });

  return (
    <Animated.View
      entering={splashKeyframe.duration(DURATION).withCallback((finished) => {
        'worklet';
        if (finished) {
          scheduleOnRN(setVisible, false);
        }
      })}
      style={styles.backgroundSolidColor}
    />
  );
}

const styles = StyleSheet.create({
  backgroundSolidColor: {
    ...StyleSheet.absoluteFill,
    backgroundColor: colors.primary,
    zIndex: 1000,
  },
});
