/** Stem information from analysis.json */
export interface StemInfo {
  name: string;
  paths: Record<string, string>; // speed (e.g., "1.0x") -> relative path
  hasNotes: boolean;
  peakDb: number;
}

/** Beat event from analysis.json */
export interface BeatEvent {
  time: number;
  type: "beat" | "downbeat";
  beatInMeasure: number | null;
}

/** Note information (for future features) */
export interface Note {
  start: number;
  end: number;
  pitch: number;
  velocity: number;
  pitchBend?: { time: number; cents: number }[];
}

/** Lyric word with timing */
export interface LyricWord {
  text: string;
  start: number;
  end: number;
  confidence: number;
}

/** Lyric line with words */
export interface LyricLine {
  text: string;
  start: number;
  end: number;
  words: LyricWord[];
}

/** Lyrics data */
export interface LyricsData {
  source: "lrc" | "txt" | "transcribed";
  lines: LyricLine[];
}

/** Full song analysis from analysis.json */
export interface SongAnalysis {
  title: string | null;
  artist: string | null;
  album: string | null;
  originalDuration: number;
  sampleRate: number;
  tempoBpm: number | null;
  timeSignature: [number, number] | null;
  stems: Record<string, StemInfo>;
  beats: BeatEvent[];
  notes?: Record<string, Note[]>;
  lyrics?: LyricsData | null;
  sourceFile: string;
  processingDate: string;
  converterVersion: string;
}

/** Summary for song browser */
export interface SongSummary {
  path: string;
  title: string | null;
  artist: string | null;
  duration: number;
  stemCount: number;
}

/** Available playback speeds */
export const PLAYBACK_SPEEDS = ["0.5x", "0.75x", "1.0x", "1.25x"] as const;
export type PlaybackSpeed = (typeof PLAYBACK_SPEEDS)[number];

/** Stem colors for UI */
export const STEM_COLORS: Record<string, string> = {
  drums: "bg-red-500",
  bass: "bg-blue-500",
  vocals: "bg-purple-500",
  guitar: "bg-green-500",
  piano: "bg-cyan-500",
  other: "bg-orange-500",
};

/** Get color for a stem, with fallback */
export function getStemColor(stemName: string): string {
  const lowerName = stemName.toLowerCase();
  for (const [key, color] of Object.entries(STEM_COLORS)) {
    if (lowerName.includes(key)) {
      return color;
    }
  }
  return STEM_COLORS.other;
}
