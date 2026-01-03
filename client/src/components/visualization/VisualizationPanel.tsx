import { useMemo } from "react";
import { X, Eye, AudioWaveform, Lock, Unlock, ZoomIn, ZoomOut } from "lucide-react";
import { type BeatEvent, type SongAnalysis } from "../../types/analysis";
import { type ViewportState } from "../../hooks/useVisualization";
import { cn, scaleTime } from "../../lib/utils";
import { DrumTabView } from "./DrumTabView";
import { PianoRollView } from "./PianoRollView";
import { LyricsView } from "./LyricsView";
import { LyricsOverlay } from "./LyricsOverlay";

interface VisualizationPanelProps {
  analysis: SongAnalysis;
  activeStem: string | null;
  viewMode: "visualization" | "waveform";
  viewport: ViewportState;
  currentTime: number;
  speed: string;
  isExpanded: boolean;
  followPlayhead: boolean;
  loopStart: number | null;
  loopEnd: number | null;
  containerRef: React.RefObject<HTMLDivElement>;
  onClose: () => void;
  onToggleViewMode: () => void;
  onToggleFollowPlayhead: () => void;
  onZoom: (factor: number, centerTime?: number) => void;
  onScrollTo: (time: number) => void;
  onSeek: (time: number) => void;
}

export function VisualizationPanel({
  analysis,
  activeStem,
  viewMode,
  viewport,
  currentTime,
  speed,
  isExpanded,
  followPlayhead,
  loopStart,
  loopEnd,
  containerRef,
  onClose,
  onToggleViewMode,
  onToggleFollowPlayhead,
  onZoom,
  onScrollTo,
  onSeek,
}: VisualizationPanelProps) {
  if (!isExpanded || !activeStem) return null;

  const stemInfo = analysis.stems[activeStem];
  const hasVisualizationData = stemInfo?.hasNotes || activeStem.includes("drum");

  return (
    <div
      className="border-8 border-zinc-700 rounded-3xl bg-zinc-800 mb-8 overflow-hidden"
      style={{ boxShadow: "inset 0 6px 12px rgba(0,0,0,0.4), 0 8px 24px rgba(0,0,0,0.5)" }}
    >
      {/* Header */}
      <div className="flex items-center gap-4 p-4 border-b-4 border-zinc-700 bg-zinc-900">
        <h3 className="text-lg text-amber-400 uppercase tracking-wider flex-1">
          {activeStem} Visualization
        </h3>

        {/* View mode toggle */}
        {hasVisualizationData && (
          <button
            onClick={onToggleViewMode}
            className={cn(
              "px-3 py-1.5 rounded-lg border-2 text-sm uppercase tracking-wider transition-all flex items-center gap-2",
              viewMode === "visualization"
                ? "border-amber-600 bg-amber-500 text-zinc-900"
                : "border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500"
            )}
          >
            {viewMode === "visualization" ? (
              <>
                <Eye className="w-4 h-4" />
                Notes
              </>
            ) : (
              <>
                <AudioWaveform className="w-4 h-4" />
                Waveform
              </>
            )}
          </button>
        )}

        {/* Follow playhead toggle */}
        <button
          onClick={onToggleFollowPlayhead}
          className={cn(
            "px-3 py-1.5 rounded-lg border-2 text-sm uppercase tracking-wider transition-all flex items-center gap-2",
            followPlayhead
              ? "border-green-600 bg-green-500 text-zinc-900"
              : "border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500"
          )}
          title={followPlayhead ? "Auto-scroll enabled" : "Auto-scroll disabled"}
        >
          {followPlayhead ? <Lock className="w-4 h-4" /> : <Unlock className="w-4 h-4" />}
          Follow
        </button>

        {/* Zoom controls */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => onZoom(0.8)}
            className="p-2 rounded-lg border-2 border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500 transition-all"
            title="Zoom out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            onClick={() => onZoom(1.25)}
            className="p-2 rounded-lg border-2 border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500 transition-all"
            title="Zoom in"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
        </div>

        {/* Close button */}
        <button
          onClick={onClose}
          className="p-2 rounded-lg border-2 border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-red-500 hover:text-red-400 transition-all"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Visualization content */}
      <div ref={containerRef} className="relative h-64 overflow-hidden bg-zinc-950">
        {/* Time ruler */}
        <TimeRuler viewport={viewport} beats={analysis.beats} speed={speed} />

        {/* Beat grid */}
        <BeatGrid viewport={viewport} beats={analysis.beats} speed={speed} />

        {/* Loop region overlay */}
        {loopStart !== null && loopEnd !== null && (
          <LoopRegion viewport={viewport} loopStart={loopStart} loopEnd={loopEnd} />
        )}

        {/* Playhead */}
        <Playhead viewport={viewport} currentTime={currentTime} />

        {/* Visualization content */}
        {viewMode === "visualization" ? (
          <VisualizationContent
            analysis={analysis}
            activeStem={activeStem}
            viewport={viewport}
            speed={speed}
            currentTime={currentTime}
            onSeek={onSeek}
          />
        ) : (
          <div className="absolute inset-0 top-8 flex items-center justify-center text-zinc-600">
            <span>Waveform view coming soon</span>
          </div>
        )}

        {/* Click to seek */}
        <div
          className="absolute inset-0 top-8 cursor-pointer"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const time = viewport.startTime + x / viewport.pixelsPerSecond;
            onSeek(time);
          }}
        />
      </div>

      {/* Scroll bar / mini timeline */}
      <MiniTimeline
        viewport={viewport}
        duration={scaleTime(analysis.originalDuration, speed)}
        currentTime={currentTime}
        loopStart={loopStart}
        loopEnd={loopEnd}
        onScrollTo={onScrollTo}
      />
    </div>
  );
}

/** Routes to the appropriate visualization based on stem type */
function VisualizationContent({
  analysis,
  activeStem,
  viewport,
  speed,
  currentTime,
  onSeek,
}: {
  analysis: SongAnalysis;
  activeStem: string;
  viewport: ViewportState;
  speed: string;
  currentTime: number;
  onSeek: (time: number) => void;
}) {
  const stemLower = activeStem.toLowerCase();

  // Drum visualization
  if (stemLower.includes("drum")) {
    const drumStrikes = analysis.drumStrikes || {};
    return (
      <DrumTabView
        drumStrikes={drumStrikes}
        viewport={viewport}
        speed={speed}
        currentTime={currentTime}
        onSeek={onSeek}
      />
    );
  }

  // Piano roll for stems with note data
  const stemInfo = analysis.stems[activeStem];
  const notes = analysis.notes?.[activeStem];
  const hasNotes = stemInfo?.hasNotes && notes && notes.length > 0;
  const hasLyrics = analysis.lyrics && analysis.lyrics.lines.length > 0;

  // Vocals with both notes and lyrics: show piano roll with lyrics overlay
  if (stemLower === "vocals" && hasNotes && hasLyrics) {
    return (
      <>
        <PianoRollView
          notes={notes}
          viewport={viewport}
          speed={speed}
          currentTime={currentTime}
          stemName={activeStem}
          onSeek={onSeek}
        />
        <LyricsOverlay
          lyrics={analysis.lyrics!}
          speed={speed}
          currentTime={currentTime}
          onSeek={onSeek}
        />
      </>
    );
  }

  // Piano roll for other stems with notes (no overlay)
  if (hasNotes) {
    return (
      <PianoRollView
        notes={notes}
        viewport={viewport}
        speed={speed}
        currentTime={currentTime}
        stemName={activeStem}
        onSeek={onSeek}
      />
    );
  }

  // Lyrics view for vocals without notes (full view)
  if (stemLower === "vocals" && hasLyrics) {
    return (
      <LyricsView
        lyrics={analysis.lyrics!}
        speed={speed}
        currentTime={currentTime}
        onSeek={onSeek}
      />
    );
  }

  return (
    <div className="absolute inset-0 top-8 flex items-center justify-center text-zinc-600">
      <span>No visualization data for {activeStem}</span>
    </div>
  );
}

/** Time ruler showing timestamps and measure numbers */
function TimeRuler({
  viewport,
  beats,
  speed,
}: {
  viewport: ViewportState;
  beats: BeatEvent[];
  speed: string;
  tempoBpm?: number | null;
  timeSignature?: [number, number] | null;
}) {
  const markers = useMemo(() => {
    const result: { time: number; label: string; isMeasure: boolean }[] = [];

    // Calculate appropriate interval based on zoom level
    const viewportWidth = viewport.endTime - viewport.startTime;
    let interval: number;
    if (viewportWidth > 60) interval = 10;
    else if (viewportWidth > 30) interval = 5;
    else if (viewportWidth > 10) interval = 2;
    else interval = 1;

    // Add time markers
    const startSecond = Math.floor(viewport.startTime / interval) * interval;
    for (let t = startSecond; t <= viewport.endTime; t += interval) {
      if (t >= viewport.startTime) {
        const mins = Math.floor(t / 60);
        const secs = Math.floor(t % 60);
        result.push({
          time: t,
          label: `${mins}:${secs.toString().padStart(2, "0")}`,
          isMeasure: false,
        });
      }
    }

    // Add measure numbers from downbeats
    let measureNum = 0;
    beats.forEach((beat) => {
      if (beat.type === "downbeat") {
        measureNum++;
        const scaledTime = scaleTime(beat.time, speed);
        if (scaledTime >= viewport.startTime && scaledTime <= viewport.endTime) {
          result.push({
            time: scaledTime,
            label: `M${measureNum}`,
            isMeasure: true,
          });
        }
      }
    });

    return result;
  }, [viewport, beats, speed]);

  return (
    <div className="absolute top-0 left-0 right-0 h-8 border-b border-zinc-800 bg-zinc-900/80 overflow-hidden">
      {markers.map((marker, i) => {
        const x = (marker.time - viewport.startTime) * viewport.pixelsPerSecond;
        return (
          <div
            key={`${marker.label}-${i}`}
            className="absolute top-0 h-full flex flex-col justify-end"
            style={{ left: `${x}px` }}
          >
            <span
              className={cn(
                "text-xs px-1 whitespace-nowrap",
                marker.isMeasure ? "text-amber-500 font-medium" : "text-zinc-500"
              )}
            >
              {marker.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Grid of beat markers */
function BeatGrid({
  viewport,
  beats,
  speed,
}: {
  viewport: ViewportState;
  beats: BeatEvent[];
  speed: string;
}) {
  const visibleBeats = useMemo(() => {
    return beats
      .map((beat) => ({
        ...beat,
        scaledTime: scaleTime(beat.time, speed),
      }))
      .filter(
        (beat) => beat.scaledTime >= viewport.startTime && beat.scaledTime <= viewport.endTime
      );
  }, [beats, speed, viewport]);

  return (
    <div className="absolute inset-0 top-8 pointer-events-none">
      {visibleBeats.map((beat, i) => {
        const x = (beat.scaledTime - viewport.startTime) * viewport.pixelsPerSecond;
        return (
          <div
            key={i}
            className={cn(
              "absolute top-0 bottom-0 w-px",
              beat.type === "downbeat" ? "bg-zinc-600" : "bg-zinc-800"
            )}
            style={{ left: `${x}px` }}
          />
        );
      })}
    </div>
  );
}

/** Playhead indicator */
function Playhead({ viewport, currentTime }: { viewport: ViewportState; currentTime: number }) {
  // Only show if within viewport
  if (currentTime < viewport.startTime || currentTime > viewport.endTime) return null;

  const x = (currentTime - viewport.startTime) * viewport.pixelsPerSecond;

  return (
    <div
      className="absolute top-0 bottom-0 w-0.5 bg-amber-500 z-20 pointer-events-none"
      style={{ left: `${x}px` }}
    >
      {/* Playhead cap */}
      <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-3 h-3 bg-amber-500 rotate-45" />
    </div>
  );
}

/** Loop region overlay */
function LoopRegion({
  viewport,
  loopStart,
  loopEnd,
}: {
  viewport: ViewportState;
  loopStart: number;
  loopEnd: number;
}) {
  const startX = Math.max(0, (loopStart - viewport.startTime) * viewport.pixelsPerSecond);
  const endX = (loopEnd - viewport.startTime) * viewport.pixelsPerSecond;
  const width = endX - startX;

  if (width <= 0 || startX > viewport.endTime * viewport.pixelsPerSecond) return null;

  return (
    <>
      {/* Dimmed area before loop */}
      {loopStart > viewport.startTime && (
        <div
          className="absolute top-8 bottom-0 bg-zinc-900/60 pointer-events-none"
          style={{ left: 0, width: `${startX}px` }}
        />
      )}
      {/* Loop region highlight */}
      <div
        className="absolute top-8 bottom-0 bg-amber-500/10 border-l-2 border-r-2 border-amber-500/50 pointer-events-none"
        style={{ left: `${startX}px`, width: `${width}px` }}
      />
      {/* Dimmed area after loop */}
      <div
        className="absolute top-8 bottom-0 right-0 bg-zinc-900/60 pointer-events-none"
        style={{ left: `${endX}px` }}
      />
    </>
  );
}

/** Mini timeline for navigation */
function MiniTimeline({
  viewport,
  duration,
  currentTime,
  loopStart,
  loopEnd,
  onScrollTo,
}: {
  viewport: ViewportState;
  duration: number;
  currentTime: number;
  loopStart: number | null;
  loopEnd: number | null;
  onScrollTo: (time: number) => void;
}) {
  const viewportPercent = ((viewport.endTime - viewport.startTime) / duration) * 100;
  const viewportStart = (viewport.startTime / duration) * 100;
  const playheadPercent = (currentTime / duration) * 100;

  return (
    <div
      className="h-6 bg-zinc-900 border-t-4 border-zinc-700 relative cursor-pointer"
      onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const percent = x / rect.width;
        const time = percent * duration - (viewport.endTime - viewport.startTime) / 2;
        onScrollTo(Math.max(0, time));
      }}
    >
      {/* Loop region indicator */}
      {loopStart !== null && loopEnd !== null && (
        <div
          className="absolute top-0 bottom-0 bg-amber-500/30"
          style={{
            left: `${(loopStart / duration) * 100}%`,
            width: `${((loopEnd - loopStart) / duration) * 100}%`,
          }}
        />
      )}

      {/* Viewport indicator */}
      <div
        className="absolute top-1 bottom-1 bg-zinc-700 rounded border border-zinc-600"
        style={{
          left: `${viewportStart}%`,
          width: `${viewportPercent}%`,
        }}
      />

      {/* Playhead position */}
      <div
        className="absolute top-0 bottom-0 w-0.5 bg-amber-500"
        style={{ left: `${playheadPercent}%` }}
      />
    </div>
  );
}
