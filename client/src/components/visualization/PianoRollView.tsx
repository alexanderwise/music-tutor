import { useMemo, useState, useRef, useEffect } from "react";
import { type Note } from "../../types/analysis";
import { type ViewportState } from "../../hooks/useVisualization";
import { cn, scaleTime, formatTime } from "../../lib/utils";

// MIDI note names
const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

// Convert MIDI pitch to note name
function midiToNoteName(pitch: number): string {
  const octave = Math.floor(pitch / 12) - 1;
  const noteName = NOTE_NAMES[pitch % 12];
  return `${noteName}${octave}`;
}

// Check if a note is a black key
function isBlackKey(pitch: number): boolean {
  const note = pitch % 12;
  return [1, 3, 6, 8, 10].includes(note);
}

interface PianoRollViewProps {
  notes: Note[];
  viewport: ViewportState;
  speed: string;
  currentTime: number;
  stemName: string;
  onSeek: (time: number) => void;
}

interface TooltipInfo {
  x: number;
  y: number;
  note: Note & { scaledStart: number; scaledEnd: number };
}

// Color schemes for different stems
const STEM_COLORS: Record<string, { bg: string; border: string; playing: string }> = {
  vocals: { bg: "bg-purple-500", border: "border-purple-400", playing: "bg-purple-300" },
  bass: { bg: "bg-blue-500", border: "border-blue-400", playing: "bg-blue-300" },
  guitar: { bg: "bg-green-500", border: "border-green-400", playing: "bg-green-300" },
  piano: { bg: "bg-cyan-500", border: "border-cyan-400", playing: "bg-cyan-300" },
  other: { bg: "bg-orange-500", border: "border-orange-400", playing: "bg-orange-300" },
};

export function PianoRollView({
  notes,
  viewport,
  speed,
  currentTime,
  stemName,
  onSeek,
}: PianoRollViewProps) {
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const keyboardRef = useRef<HTMLDivElement>(null);

  // Get color scheme for this stem
  const colors = STEM_COLORS[stemName.toLowerCase()] || STEM_COLORS.other;

  // Calculate pitch range from notes
  const { minPitch, maxPitch, visibleNotes } = useMemo(() => {
    if (notes.length === 0) {
      return { minPitch: 48, maxPitch: 72, visibleNotes: [] };
    }

    let min = 127;
    let max = 0;
    const visible: Array<Note & { scaledStart: number; scaledEnd: number }> = [];

    for (const note of notes) {
      min = Math.min(min, note.pitch);
      max = Math.max(max, note.pitch);

      const scaledStart = scaleTime(note.start, speed);
      const scaledEnd = scaleTime(note.end, speed);

      // Check if note is in viewport (including partial overlap)
      if (scaledEnd >= viewport.startTime && scaledStart <= viewport.endTime) {
        visible.push({ ...note, scaledStart, scaledEnd });
      }
    }

    // Add some padding to the pitch range
    return {
      minPitch: Math.max(0, min - 2),
      maxPitch: Math.min(127, max + 2),
      visibleNotes: visible,
    };
  }, [notes, speed, viewport]);

  const pitchRange = maxPitch - minPitch + 1;
  // Use fixed row height for better visibility
  const rowHeight = 12;
  const totalHeight = pitchRange * rowHeight;

  // Find currently playing notes to auto-scroll vertically
  const currentlyPlayingPitches = useMemo(() => {
    return visibleNotes
      .filter((n) => currentTime >= n.scaledStart && currentTime <= n.scaledEnd)
      .map((n) => n.pitch);
  }, [visibleNotes, currentTime]);

  // Auto-scroll to show currently playing notes
  useEffect(() => {
    if (currentlyPlayingPitches.length === 0 || !scrollContainerRef.current) return;

    const avgPitch =
      currentlyPlayingPitches.reduce((a, b) => a + b, 0) / currentlyPlayingPitches.length;
    const targetY = (maxPitch - avgPitch) * rowHeight;
    const container = scrollContainerRef.current;
    const containerHeight = container.clientHeight;

    // Only scroll if target is outside visible area
    const currentScrollTop = container.scrollTop;
    const visibleTop = currentScrollTop;
    const visibleBottom = currentScrollTop + containerHeight;

    if (targetY < visibleTop + 50 || targetY > visibleBottom - 50) {
      container.scrollTo({
        top: Math.max(0, targetY - containerHeight / 2),
        behavior: "smooth",
      });
    }
  }, [currentlyPlayingPitches, maxPitch, rowHeight]);

  // Sync keyboard scroll with main content
  const handleScroll = () => {
    if (scrollContainerRef.current && keyboardRef.current) {
      keyboardRef.current.scrollTop = scrollContainerRef.current.scrollTop;
    }
  };

  if (notes.length === 0) {
    return (
      <div className="absolute inset-0 top-8 flex items-center justify-center text-zinc-600">
        <span>No note data available for this stem</span>
      </div>
    );
  }

  return (
    <div className="absolute inset-0 top-8 overflow-hidden flex">
      {/* Piano keyboard labels on the left - synced scroll */}
      <div
        ref={keyboardRef}
        className="w-12 bg-zinc-900/95 border-r border-zinc-800 z-10 overflow-hidden flex-shrink-0"
      >
        <div style={{ height: `${totalHeight}px` }}>
          {Array.from({ length: pitchRange }, (_, i) => {
            const pitch = maxPitch - i;
            const isBlack = isBlackKey(pitch);
            const isC = pitch % 12 === 0;

            return (
              <div
                key={pitch}
                className={cn(
                  "flex items-center justify-end pr-1 text-xs border-b border-zinc-800",
                  isBlack ? "bg-zinc-800 text-zinc-400" : "bg-zinc-900 text-zinc-500",
                  isC && "font-medium text-amber-400"
                )}
                style={{ height: `${rowHeight}px` }}
              >
                {midiToNoteName(pitch)}
              </div>
            );
          })}
        </div>
      </div>

      {/* Scrollable note grid */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto overflow-x-hidden"
        onScroll={handleScroll}
      >
        <div className="relative" style={{ height: `${totalHeight}px` }}>
          {/* Grid lines for each pitch */}
          {Array.from({ length: pitchRange }, (_, i) => {
            const pitch = maxPitch - i;
            const isBlack = isBlackKey(pitch);
            const isC = pitch % 12 === 0;

            return (
              <div
                key={pitch}
                className={cn(
                  "absolute w-full border-b",
                  isBlack ? "bg-zinc-900/50 border-zinc-800" : "bg-zinc-950/30 border-zinc-800/50",
                  isC && "border-zinc-700"
                )}
                style={{
                  top: `${i * rowHeight}px`,
                  height: `${rowHeight}px`,
                }}
              />
            );
          })}

          {/* Notes */}
          {visibleNotes.map((note, i) => {
            const x = (note.scaledStart - viewport.startTime) * viewport.pixelsPerSecond;
            const width = Math.max(
              2,
              (note.scaledEnd - note.scaledStart) * viewport.pixelsPerSecond
            );
            const y = (maxPitch - note.pitch) * rowHeight;
            const isPlaying =
              currentTime >= note.scaledStart && currentTime <= note.scaledEnd;

            return (
              <div
                key={i}
                className={cn(
                  "absolute rounded-sm cursor-pointer transition-all border",
                  isPlaying ? colors.playing : colors.bg,
                  colors.border,
                  isPlaying && "ring-1 ring-white z-10"
                )}
                style={{
                  left: `${x}px`,
                  top: `${y}px`,
                  width: `${width}px`,
                  height: `${rowHeight - 2}px`,
                  opacity: 0.5 + note.velocity * 0.5,
                }}
                onClick={() => onSeek(note.scaledStart)}
                onMouseEnter={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect();
                  setTooltip({
                    x: rect.left + rect.width / 2,
                    y: rect.top,
                    note,
                  });
                }}
                onMouseLeave={() => setTooltip(null)}
              />
            );
          })}
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-xs text-zinc-300 pointer-events-none"
          style={{
            left: tooltip.x,
            top: tooltip.y - 44,
            transform: "translateX(-50%)",
          }}
        >
          <div className="font-medium text-amber-400">
            {midiToNoteName(tooltip.note.pitch)}
          </div>
          <div className="text-zinc-400">
            {formatTime(tooltip.note.scaledStart)} - {formatTime(tooltip.note.scaledEnd)}
          </div>
          <div className="text-zinc-500">
            Velocity: {Math.round(tooltip.note.velocity * 100)}%
          </div>
        </div>
      )}
    </div>
  );
}
