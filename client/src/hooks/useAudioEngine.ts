import { useState, useRef, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { type SongAnalysis, type PlaybackSpeed } from "../types/analysis";
import { convertFileSrc } from "@tauri-apps/api/core";

interface StemState {
  name: string;
  volume: number;
  isMuted: boolean;
  buffer: AudioBuffer | null;
  source: AudioBufferSourceNode | null;
  gainNode: GainNode | null;
}

interface AudioEngineState {
  isLoading: boolean;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  speed: PlaybackSpeed;
  stems: Record<string, StemState>;
  soloedStems: Set<string>;  // Multiple stems can be soloed (Pro Tools style)
  loopStart: number | null;
  loopEnd: number | null;
}

export function useAudioEngine(analysis: SongAnalysis | null, songDir: string) {
  const audioContextRef = useRef<AudioContext | null>(null);
  const startTimeRef = useRef<number>(0);
  const pauseTimeRef = useRef<number>(0);
  const rafIdRef = useRef<number | null>(null);
  // Use a ref for playing state to avoid race conditions with async state updates
  const isPlayingRef = useRef<boolean>(false);

  const [state, setState] = useState<AudioEngineState>({
    isLoading: false,
    isPlaying: false,
    currentTime: 0,
    duration: 0,
    speed: "1.0x",
    stems: {},
    soloedStems: new Set<string>(),
    loopStart: null,
    loopEnd: null,
  });

  // Initialize audio context and load stems when analysis changes
  useEffect(() => {
    if (!analysis || !songDir) return;

    const initAudio = async () => {
      setState((prev) => ({ ...prev, isLoading: true }));

      // Create audio context if needed
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext();
      }
      const ctx = audioContextRef.current;

      // Initialize stem states
      const stemStates: Record<string, StemState> = {};
      for (const [name] of Object.entries(analysis.stems)) {
        const gainNode = ctx.createGain();
        gainNode.gain.value = 1.0; // Full volume by default
        gainNode.connect(ctx.destination);

        stemStates[name] = {
          name,
          volume: 100,
          isMuted: false,
          buffer: null,
          source: null,
          gainNode,
        };
      }

      // Calculate duration based on current speed
      const speed = parseFloat(state.speed.replace("x", ""));
      const duration = analysis.originalDuration / speed;

      setState((prev) => ({
        ...prev,
        stems: stemStates,
        duration,
        isLoading: false,
      }));

      // Load the default speed stems
      await loadStemsForSpeed(state.speed, stemStates);
    };

    initAudio();

    // Cleanup on unmount - stop all audio
    return () => {
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
      }
      // Stop all playing sources
      Object.values(sourceNodesRef.current).forEach((source) => {
        try {
          source.stop();
        } catch {
          // Ignore if already stopped
        }
      });
      sourceNodesRef.current = {};
      // Close the audio context
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
    };
  }, [analysis, songDir]);

  // Load audio buffers for a specific speed
  const loadStemsForSpeed = useCallback(
    async (speed: PlaybackSpeed, currentStems?: Record<string, StemState>) => {
      if (!analysis || !songDir || !audioContextRef.current) return;

      const ctx = audioContextRef.current;
      const stems = currentStems || state.stems;

      setState((prev) => ({ ...prev, isLoading: true }));

      for (const [name, info] of Object.entries(analysis.stems)) {
        const relativePath = info.paths[speed];
        if (!relativePath) continue;

        try {
          // Get absolute path from Tauri
          const absolutePath = await invoke<string>("get_stem_path", {
            songDir,
            relativePath,
          });

          // Convert to asset URL for Tauri
          const assetUrl = convertFileSrc(absolutePath);

          // Fetch and decode audio
          const response = await fetch(assetUrl);
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }
          const arrayBuffer = await response.arrayBuffer();
          const audioBuffer = await ctx.decodeAudioData(arrayBuffer);

          if (stems[name]) {
            stems[name].buffer = audioBuffer;
          }
        } catch (error) {
          console.error(`Failed to load stem ${name}:`, error);
        }
      }

      // Update duration for new speed
      const speedValue = parseFloat(speed.replace("x", ""));
      const duration = analysis.originalDuration / speedValue;

      setState((prev) => ({
        ...prev,
        stems: { ...stems },
        duration,
        isLoading: false,
      }));
    },
    [analysis, songDir, state.stems]
  );

  // Store loop points in refs to avoid stale closure issues
  const loopStartRef = useRef<number | null>(null);
  const loopEndRef = useRef<number | null>(null);
  const durationRef = useRef<number>(0);
  const stemsRef = useRef<Record<string, StemState>>({});

  // Keep refs in sync with state
  useEffect(() => {
    loopStartRef.current = state.loopStart;
    loopEndRef.current = state.loopEnd;
    durationRef.current = state.duration;
    stemsRef.current = state.stems;
  }, [state.loopStart, state.loopEnd, state.duration, state.stems]);

  // Store active source nodes separately from state to avoid mutation issues
  const sourceNodesRef = useRef<Record<string, AudioBufferSourceNode>>({});

  // Helper to stop all source nodes
  const stopAllSources = useCallback(() => {
    Object.values(sourceNodesRef.current).forEach((source) => {
      try {
        source.stop();
      } catch {
        // Ignore if already stopped
      }
    });
    sourceNodesRef.current = {};
  }, []);

  // Internal stop used by updateTime
  const stopPlayback = useCallback(() => {
    if (!audioContextRef.current) return;

    stopAllSources();

    isPlayingRef.current = false;
    pauseTimeRef.current = 0;
    setState((prev) => ({ ...prev, isPlaying: false, currentTime: 0 }));
  }, [stopAllSources]);

  // Restart audio sources at a specific position (used for looping)
  const restartAudioAt = useCallback((position: number) => {
    const ctx = audioContextRef.current;
    if (!ctx) return;

    // Stop all current sources
    stopAllSources();

    // Restart all stems at the new position
    Object.entries(stemsRef.current).forEach(([name, stem]) => {
      if (!stem.buffer || !stem.gainNode) return;

      const source = ctx.createBufferSource();
      source.buffer = stem.buffer;
      source.connect(stem.gainNode);
      source.start(0, position);

      sourceNodesRef.current[name] = source;
    });

    // Update time tracking
    pauseTimeRef.current = position;
    startTimeRef.current = ctx.currentTime;
  }, [stopAllSources]);

  // Update playback position
  const updateTime = useCallback(() => {
    // Use ref for playing state to avoid race conditions
    if (!audioContextRef.current || !isPlayingRef.current) return;

    const elapsed = audioContextRef.current.currentTime - startTimeRef.current;
    const currentTime = pauseTimeRef.current + elapsed;

    // Handle looping - use refs for consistent values
    if (loopEndRef.current !== null && currentTime >= loopEndRef.current) {
      const loopStart = loopStartRef.current ?? 0;

      // Actually restart the audio at loop start position
      restartAudioAt(loopStart);
      setState((prev) => ({ ...prev, currentTime: loopStart }));
      rafIdRef.current = requestAnimationFrame(updateTime);
      return;
    }

    // Handle end of track
    if (currentTime >= durationRef.current) {
      stopPlayback();
      return;
    }

    setState((prev) => ({ ...prev, currentTime }));
    rafIdRef.current = requestAnimationFrame(updateTime);
  }, [stopPlayback, restartAudioAt]);

  // Start playback position updates
  useEffect(() => {
    if (state.isPlaying) {
      rafIdRef.current = requestAnimationFrame(updateTime);
    }
    return () => {
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
      }
    };
  }, [state.isPlaying, updateTime]);

  // Play all stems
  const play = useCallback(async () => {
    if (!audioContextRef.current) return;

    const ctx = audioContextRef.current;
    const offset = pauseTimeRef.current;

    // Resume context if suspended (critical for macOS)
    if (ctx.state === "suspended") {
      await ctx.resume();
    }

    // Clear any existing source nodes
    stopAllSources();

    // Create and start source nodes for all stems
    Object.entries(state.stems).forEach(([name, stem]) => {
      if (!stem.buffer || !stem.gainNode) return;

      // Ensure gain is set correctly (Pro Tools style: solo mutes non-soloed stems)
      const isSoloActive = state.soloedStems.size > 0;
      const shouldPlay = !stem.isMuted && (!isSoloActive || state.soloedStems.has(name));
      stem.gainNode.gain.value = shouldPlay ? stem.volume / 100 : 0;

      const source = ctx.createBufferSource();
      source.buffer = stem.buffer;
      source.connect(stem.gainNode);
      source.start(0, offset);

      sourceNodesRef.current[name] = source;
    });

    startTimeRef.current = ctx.currentTime;
    isPlayingRef.current = true;

    setState((prev) => ({ ...prev, isPlaying: true }));
  }, [state.stems, state.soloedStems, stopAllSources]);

  // Pause playback
  const pause = useCallback(() => {
    if (!audioContextRef.current) return;
    // Guard against being called when already paused
    if (!isPlayingRef.current) return;

    // Calculate current position
    const elapsed = audioContextRef.current.currentTime - startTimeRef.current;
    pauseTimeRef.current += elapsed;

    // Stop all sources
    stopAllSources();

    isPlayingRef.current = false;
    setState((prev) => ({ ...prev, isPlaying: false }));
  }, [stopAllSources]);

  // Stop playback and reset position (public API)
  const stop = useCallback(() => {
    stopPlayback();
  }, [stopPlayback]);

  // Seek to position
  const seek = useCallback(
    (time: number) => {
      const wasPlaying = isPlayingRef.current;
      const ctx = audioContextRef.current;

      if (wasPlaying) {
        stopAllSources();
      }

      // Update both refs together to maintain consistency
      pauseTimeRef.current = time;
      if (ctx) {
        startTimeRef.current = ctx.currentTime;
      }

      setState((prev) => ({ ...prev, currentTime: time }));

      if (wasPlaying) {
        // Small delay to ensure state is updated, then restart playback
        setTimeout(() => play(), 10);
      }
    },
    [play, stopAllSources]
  );

  // Change playback speed
  const setSpeed = useCallback(
    async (speed: PlaybackSpeed) => {
      const wasPlaying = isPlayingRef.current;
      const currentPosition = pauseTimeRef.current +
        (wasPlaying && audioContextRef.current
          ? audioContextRef.current.currentTime - startTimeRef.current
          : 0);
      const currentDuration = durationRef.current;

      // Pause if playing
      if (wasPlaying) {
        pause();
      }

      // Calculate position ratio to maintain relative position
      const newSpeedValue = parseFloat(speed.replace("x", ""));
      const positionRatio = currentDuration > 0 ? currentPosition / currentDuration : 0;

      setState((prev) => ({ ...prev, speed }));

      // Load new stem files
      await loadStemsForSpeed(speed);

      // Calculate new position
      const newDuration = analysis!.originalDuration / newSpeedValue;
      const newPosition = positionRatio * newDuration;

      pauseTimeRef.current = newPosition;
      if (audioContextRef.current) {
        startTimeRef.current = audioContextRef.current.currentTime;
      }
      setState((prev) => ({
        ...prev,
        currentTime: newPosition,
        duration: newDuration,
      }));

      // Resume if was playing
      if (wasPlaying) {
        setTimeout(() => play(), 100);
      }
    },
    [analysis, pause, play, loadStemsForSpeed]
  );

  // Set stem volume
  const setStemVolume = useCallback((stemName: string, volume: number) => {
    setState((prev) => {
      const stem = prev.stems[stemName];
      if (!stem || !stem.gainNode) return prev;

      // Apply volume (considering mute and solo states)
      const isSoloActive = prev.soloedStems.size > 0;
      const shouldPlay = !stem.isMuted && (!isSoloActive || prev.soloedStems.has(stemName));
      stem.gainNode.gain.value = shouldPlay ? volume / 100 : 0;

      return {
        ...prev,
        stems: {
          ...prev.stems,
          [stemName]: { ...stem, volume },
        },
      };
    });
  }, []);

  // Toggle stem mute
  const toggleMute = useCallback((stemName: string) => {
    setState((prev) => {
      const stem = prev.stems[stemName];
      if (!stem || !stem.gainNode) return prev;

      const isMuted = !stem.isMuted;
      const isSoloActive = prev.soloedStems.size > 0;
      const shouldPlay = !isMuted && (!isSoloActive || prev.soloedStems.has(stemName));
      stem.gainNode.gain.value = shouldPlay ? stem.volume / 100 : 0;

      return {
        ...prev,
        stems: {
          ...prev.stems,
          [stemName]: { ...stem, isMuted },
        },
      };
    });
  }, []);

  // Toggle stem solo (Pro Tools style: multiple stems can be soloed)
  const toggleSolo = useCallback((stemName: string) => {
    setState((prev) => {
      const newSoloedStems = new Set(prev.soloedStems);
      if (newSoloedStems.has(stemName)) {
        newSoloedStems.delete(stemName);
      } else {
        newSoloedStems.add(stemName);
      }

      // Update all stem volumes based on solo state
      const newStems = { ...prev.stems };
      for (const [name, stem] of Object.entries(newStems)) {
        if (!stem.gainNode) continue;

        if (newSoloedStems.size === 0) {
          // No solo - respect mute state
          stem.gainNode.gain.value = stem.isMuted ? 0 : stem.volume / 100;
        } else {
          // Solo active - only play soloed stems (mute others)
          const isSoloed = newSoloedStems.has(name);
          stem.gainNode.gain.value = isSoloed && !stem.isMuted ? stem.volume / 100 : 0;
        }
      }

      return {
        ...prev,
        stems: newStems,
        soloedStems: newSoloedStems,
      };
    });
  }, []);

  // Set loop points
  const setLoopStart = useCallback(() => {
    setState((prev) => ({ ...prev, loopStart: prev.currentTime }));
  }, []);

  const setLoopEnd = useCallback(() => {
    setState((prev) => ({ ...prev, loopEnd: prev.currentTime }));
  }, []);

  const clearLoop = useCallback(() => {
    setState((prev) => ({ ...prev, loopStart: null, loopEnd: null }));
  }, []);

  return {
    ...state,
    play,
    pause,
    stop,
    seek,
    setSpeed,
    setStemVolume,
    toggleMute,
    toggleSolo,
    setLoopStart,
    setLoopEnd,
    clearLoop,
  };
}
