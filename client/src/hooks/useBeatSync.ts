import { useMemo } from "react";
import { type BeatEvent, type PlaybackSpeed } from "../types/analysis";

interface BeatSyncState {
  isDownbeat: boolean;
  isBeat: boolean;
  currentBeatIndex: number;
  beatInMeasure: number | null;
}

/**
 * Hook to sync beat indicators with current playback position
 * Scales beat times based on playback speed
 */
export function useBeatSync(
  beats: BeatEvent[],
  currentTime: number,
  speed: PlaybackSpeed
): BeatSyncState {
  return useMemo(() => {
    if (!beats || beats.length === 0) {
      return {
        isDownbeat: false,
        isBeat: false,
        currentBeatIndex: -1,
        beatInMeasure: null,
      };
    }

    // Scale beat times based on speed
    // At 0.5x, a beat at 1.0s plays at 2.0s
    // At 1.25x, a beat at 1.0s plays at 0.8s
    const speedValue = parseFloat(speed.replace("x", ""));

    // Find the current beat (the most recent beat before or at currentTime)
    let currentBeatIndex = -1;
    let isDownbeat = false;
    let isBeat = false;
    let beatInMeasure: number | null = null;

    // Beat flash duration in seconds (how long the LED stays lit)
    const flashDuration = 0.1;

    for (let i = beats.length - 1; i >= 0; i--) {
      const scaledBeatTime = beats[i].time / speedValue;

      // Check if we're within the flash window of this beat
      if (currentTime >= scaledBeatTime && currentTime < scaledBeatTime + flashDuration) {
        currentBeatIndex = i;
        isDownbeat = beats[i].type === "downbeat";
        isBeat = beats[i].type === "beat";
        beatInMeasure = beats[i].beatInMeasure;
        break;
      }

      // If we're past the flash window, record the beat index but no flash
      if (currentTime >= scaledBeatTime + flashDuration) {
        currentBeatIndex = i;
        beatInMeasure = beats[i].beatInMeasure;
        break;
      }
    }

    return {
      isDownbeat,
      isBeat,
      currentBeatIndex,
      beatInMeasure,
    };
  }, [beats, currentTime, speed]);
}
