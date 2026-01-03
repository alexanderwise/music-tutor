import { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Play, Pause, Square, ArrowLeft, ChevronDown, ChevronRight, BarChart3 } from "lucide-react";
import { invoke } from "@tauri-apps/api/core";
import { type SongAnalysis, PLAYBACK_SPEEDS, getStemColor } from "../types/analysis";
import { useAudioEngine } from "../hooks/useAudioEngine";
import { useBeatSync } from "../hooks/useBeatSync";
import { useVisualization } from "../hooks/useVisualization";
import { VisualizationPanel } from "./visualization/VisualizationPanel";
import { formatTime, cn, scaleTime } from "../lib/utils";

// Drum component stems that should be grouped
const DRUM_COMPONENTS = new Set(["drumKick", "drumSnare", "drumHh", "drumRide", "drumCrash", "drumToms"]);

// Display names for drum components
const DRUM_DISPLAY_NAMES: Record<string, string> = {
  drumKick: "Kick",
  drumSnare: "Snare",
  drumHh: "Hi-Hat",
  drumRide: "Ride",
  drumCrash: "Crash",
  drumToms: "Toms",
};

interface StemRowProps {
  name: string;
  displayName: string;
  stem: { volume: number; isMuted: boolean };
  isSoloed: boolean;
  onToggleMute: () => void;
  onToggleSolo: () => void;
  onVolumeChange: (volume: number) => void;
  onToggleVisualization?: () => void;
  isVisualizationActive?: boolean;
  hasVisualizationData?: boolean;
  compact?: boolean;
}

function StemRow({
  name,
  displayName,
  stem,
  isSoloed,
  onToggleMute,
  onToggleSolo,
  onVolumeChange,
  onToggleVisualization,
  isVisualizationActive = false,
  hasVisualizationData = false,
  compact = false,
}: StemRowProps) {
  return (
    <div
      className={cn(
        "border-4 rounded-2xl bg-zinc-900 border-zinc-700",
        compact && "border-2 rounded-xl bg-zinc-800/50"
      )}
      style={{ boxShadow: compact ? "none" : "inset 0 2px 6px rgba(0,0,0,0.3)" }}
    >
      <div className={cn("flex items-center gap-4", compact ? "p-4" : "p-6 mb-4")}>
        <div className={cn("rounded", getStemColor(name), compact ? "w-3 h-3" : "w-4 h-4")} />
        <h3
          className={cn(
            "text-zinc-300 uppercase tracking-wider flex-1 capitalize",
            compact ? "text-base" : "text-xl"
          )}
        >
          {displayName}
        </h3>

        {/* Visualization toggle button */}
        {onToggleVisualization && (
          <button
            onClick={onToggleVisualization}
            disabled={!hasVisualizationData}
            className={cn(
              "rounded-lg border-3 text-sm uppercase tracking-wider transition-all flex items-center gap-1",
              compact ? "px-2 py-1.5 text-xs" : "px-3 py-2",
              isVisualizationActive
                ? "border-cyan-600 bg-cyan-500 text-zinc-900"
                : hasVisualizationData
                  ? "border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500"
                  : "border-zinc-700 bg-zinc-800 text-zinc-600 cursor-not-allowed"
            )}
            style={{
              boxShadow: isVisualizationActive
                ? "inset 0 2px 4px rgba(0,0,0,0.3)"
                : hasVisualizationData
                  ? "0 2px 0 0 rgb(63, 63, 70)"
                  : "none",
            }}
            title={hasVisualizationData ? "Toggle visualization" : "No visualization data"}
          >
            <BarChart3 className={cn(compact ? "w-3 h-3" : "w-4 h-4")} />
            {!compact && "Viz"}
          </button>
        )}

        <button
          onClick={onToggleMute}
          className={cn(
            "rounded-lg border-3 text-sm uppercase tracking-wider transition-all",
            compact ? "px-3 py-1.5 text-xs" : "px-4 py-2",
            stem.isMuted
              ? "border-red-600 bg-red-500 text-zinc-900"
              : "border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500"
          )}
          style={{
            boxShadow: stem.isMuted ? "inset 0 2px 4px rgba(0,0,0,0.3)" : "0 2px 0 0 rgb(63, 63, 70)",
          }}
        >
          Mute
        </button>

        <button
          onClick={onToggleSolo}
          className={cn(
            "rounded-lg border-3 text-sm uppercase tracking-wider transition-all",
            compact ? "px-3 py-1.5 text-xs" : "px-4 py-2",
            isSoloed
              ? "border-amber-600 bg-amber-500 text-zinc-900"
              : "border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500"
          )}
          style={{
            boxShadow: isSoloed ? "inset 0 2px 4px rgba(0,0,0,0.3)" : "0 2px 0 0 rgb(63, 63, 70)",
          }}
        >
          Solo
        </button>

        {/* Volume slider inline for compact mode */}
        {compact && (
          <>
            <div
              className="flex-1 max-w-32 h-6 bg-zinc-950 rounded-lg border-2 border-zinc-700 relative overflow-hidden"
              style={{ boxShadow: "inset 0 2px 4px rgba(0,0,0,0.5)" }}
            >
              <div
                className={cn("h-full transition-all", getStemColor(name))}
                style={{ width: `${stem.volume}%` }}
              />
              <input
                type="range"
                min="0"
                max="100"
                value={stem.volume}
                onChange={(e) => onVolumeChange(parseInt(e.target.value))}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
            </div>
            <span className="text-sm text-zinc-400 w-10 text-right">{stem.volume}%</span>
          </>
        )}
      </div>

      {/* Volume slider below for non-compact mode */}
      {!compact && (
        <div className="flex items-center gap-4 px-6 pb-6">
          <div
            className="flex-1 h-8 bg-zinc-950 rounded-lg border-3 border-zinc-700 relative overflow-hidden"
            style={{ boxShadow: "inset 0 3px 6px rgba(0,0,0,0.5)" }}
          >
            <div
              className={cn("h-full transition-all", getStemColor(name))}
              style={{ width: `${stem.volume}%` }}
            />
            <input
              type="range"
              min="0"
              max="100"
              value={stem.volume}
              onChange={(e) => onVolumeChange(parseInt(e.target.value))}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
          </div>
          <span className="text-lg text-zinc-400 w-12 text-right">{stem.volume}%</span>
        </div>
      )}
    </div>
  );
}

export function PlayerPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { songPath } = (location.state as { songPath: string }) || {};

  const [analysis, setAnalysis] = useState<SongAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drumSectionExpanded, setDrumSectionExpanded] = useState(true);

  // Load analysis on mount
  useEffect(() => {
    if (!songPath) {
      navigate("/");
      return;
    }

    async function loadAnalysis() {
      try {
        const data = await invoke<SongAnalysis>("load_analysis", { songDir: songPath });
        setAnalysis(data);
      } catch (err) {
        setError(String(err));
      }
    }

    loadAnalysis();
  }, [songPath, navigate]);

  const engine = useAudioEngine(analysis, songPath || "");
  const beatSync = useBeatSync(analysis?.beats || [], engine.currentTime, engine.speed);

  // Visualization state
  const scaledDuration = analysis ? scaleTime(analysis.originalDuration, engine.speed) : 0;
  const visualization = useVisualization(scaledDuration);

  // Update viewport to follow playhead during playback
  useEffect(() => {
    if (engine.isPlaying) {
      visualization.updateViewportForPlayhead(engine.currentTime);
    }
  }, [engine.currentTime, engine.isPlaying, visualization.updateViewportForPlayhead]);

  // Helper to check if stem has visualization data
  const stemHasVisualizationData = (stemName: string): boolean => {
    if (!analysis) return false;
    const stemInfo = analysis.stems[stemName];
    // Has notes, or is a drum component with strike data
    return (
      stemInfo?.hasNotes ||
      stemName.toLowerCase().includes("drum") ||
      stemName === "vocals" // vocals have lyrics
    );
  };

  if (error) {
    return (
      <div className="min-h-screen bg-zinc-900 flex items-center justify-center p-8">
        <div className="text-center">
          <p className="text-red-400 text-xl mb-4">Failed to load song</p>
          <p className="text-zinc-500">{error}</p>
          <button
            onClick={() => navigate("/")}
            className="mt-6 px-6 py-3 rounded-xl border-4 border-zinc-700 bg-zinc-800 text-zinc-300"
          >
            Go Back
          </button>
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="min-h-screen bg-zinc-900 flex items-center justify-center">
        <p className="text-zinc-500 text-xl">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-900 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-6 mb-8">
          <button
            onClick={() => {
              engine.stop();
              navigate("/");
            }}
            className="p-4 rounded-xl border-4 border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300 active:translate-y-1 transition-all"
            style={{ boxShadow: "0 4px 0 0 rgb(63, 63, 70), 0 6px 12px rgba(0,0,0,0.5)" }}
          >
            <ArrowLeft className="w-6 h-6" />
          </button>

          <div className="flex-1">
            <h1
              className="text-4xl text-amber-400 uppercase tracking-wider mb-1"
              style={{ textShadow: "3px 3px 0px rgba(0,0,0,0.8)" }}
            >
              {analysis.title || "Unknown Track"}
            </h1>
            <p className="text-xl text-zinc-500">{analysis.artist || "Unknown Artist"}</p>
          </div>

          {analysis.tempoBpm && (
            <div className="text-right">
              <p className="text-zinc-400 text-lg">{Math.round(analysis.tempoBpm)} BPM</p>
              {analysis.timeSignature && (
                <p className="text-zinc-500">
                  {analysis.timeSignature[0]}/{analysis.timeSignature[1]}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Control Panel */}
        <div
          className="border-8 border-zinc-700 rounded-3xl p-8 mb-8 bg-zinc-800"
          style={{ boxShadow: "inset 0 6px 12px rgba(0,0,0,0.4), 0 8px 24px rgba(0,0,0,0.5)" }}
        >
          {/* Progress Bar */}
          <div className="mb-8">
            <div className="flex items-center gap-4 mb-3">
              <span className="text-lg text-zinc-400 font-mono">{formatTime(engine.currentTime)}</span>
              <div
                className="flex-1 h-8 bg-zinc-950 rounded-lg border-4 border-zinc-700 relative overflow-hidden"
                style={{ boxShadow: "inset 0 3px 6px rgba(0,0,0,0.5)" }}
              >
                {/* Loop markers */}
                {engine.loopStart !== null && (
                  <div
                    className="absolute top-0 bottom-0 w-1 bg-green-400 z-10"
                    style={{ left: `${(engine.loopStart / engine.duration) * 100}%` }}
                  />
                )}
                {engine.loopEnd !== null && (
                  <div
                    className="absolute top-0 bottom-0 w-1 bg-red-400 z-10"
                    style={{ left: `${(engine.loopEnd / engine.duration) * 100}%` }}
                  />
                )}
                {/* Progress fill - no transition to allow instant loop jumps */}
                <div
                  className="h-full bg-amber-500"
                  style={{ width: `${(engine.currentTime / engine.duration) * 100}%` }}
                />
                <input
                  type="range"
                  min="0"
                  max={engine.duration || 1}
                  step="0.01"
                  value={engine.currentTime}
                  onChange={(e) => engine.seek(parseFloat(e.target.value))}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                />
              </div>
              <span className="text-lg text-zinc-400 font-mono">{formatTime(engine.duration)}</span>
            </div>
          </div>

          {/* Loop Controls */}
          <div className="mb-8">
            <div className="flex gap-4">
              <button
                onClick={engine.setLoopStart}
                className={cn(
                  "px-6 py-3 rounded-xl border-4 text-lg uppercase tracking-wider transition-all",
                  engine.loopStart !== null
                    ? "border-green-600 bg-green-500 text-zinc-900"
                    : "border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500"
                )}
                style={{
                  boxShadow:
                    engine.loopStart !== null
                      ? "inset 0 2px 4px rgba(0,0,0,0.3)"
                      : "0 3px 0 0 rgb(63, 63, 70), 0 5px 10px rgba(0,0,0,0.3)",
                }}
              >
                Loop Start {engine.loopStart !== null && `(${formatTime(engine.loopStart)})`}
              </button>

              <button
                onClick={engine.setLoopEnd}
                className={cn(
                  "px-6 py-3 rounded-xl border-4 text-lg uppercase tracking-wider transition-all",
                  engine.loopEnd !== null
                    ? "border-red-600 bg-red-500 text-zinc-900"
                    : "border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500"
                )}
                style={{
                  boxShadow:
                    engine.loopEnd !== null
                      ? "inset 0 2px 4px rgba(0,0,0,0.3)"
                      : "0 3px 0 0 rgb(63, 63, 70), 0 5px 10px rgba(0,0,0,0.3)",
                }}
              >
                Loop End {engine.loopEnd !== null && `(${formatTime(engine.loopEnd)})`}
              </button>

              {(engine.loopStart !== null || engine.loopEnd !== null) && (
                <button
                  onClick={engine.clearLoop}
                  className="px-6 py-3 rounded-xl border-4 border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500 text-lg uppercase tracking-wider transition-all"
                  style={{ boxShadow: "0 3px 0 0 rgb(63, 63, 70), 0 5px 10px rgba(0,0,0,0.3)" }}
                >
                  Clear Loop
                </button>
              )}
            </div>
          </div>

          {/* Playback Speed */}
          <div className="mb-8">
            <label className="block text-lg text-zinc-400 mb-4 uppercase tracking-wider">Playback Speed</label>
            <div className="flex gap-4">
              {PLAYBACK_SPEEDS.map((speed) => (
                <button
                  key={speed}
                  onClick={() => engine.setSpeed(speed)}
                  disabled={engine.isLoading}
                  className={cn(
                    "px-8 py-4 rounded-xl border-4 text-xl uppercase tracking-wider transition-all",
                    engine.speed === speed
                      ? "border-amber-600 bg-amber-500 text-zinc-900"
                      : "border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500",
                    engine.isLoading && "opacity-50 cursor-not-allowed"
                  )}
                  style={{
                    boxShadow:
                      engine.speed === speed
                        ? "inset 0 3px 6px rgba(0,0,0,0.3)"
                        : "0 4px 0 0 rgb(63, 63, 70), 0 6px 12px rgba(0,0,0,0.3)",
                  }}
                >
                  {speed}
                </button>
              ))}
            </div>
          </div>

          {/* Transport Controls & Beat Indicators */}
          <div className="flex items-center gap-6">
            <div className="flex gap-4">
              <button
                onClick={engine.isPlaying ? engine.pause : engine.play}
                disabled={engine.isLoading}
                className={cn(
                  "p-6 rounded-xl border-4 border-green-600 bg-green-500 text-zinc-900 hover:bg-green-400 active:translate-y-1 transition-all",
                  engine.isLoading && "opacity-50 cursor-not-allowed"
                )}
                style={{ boxShadow: "0 5px 0 0 rgb(22, 101, 52), 0 8px 16px rgba(0,0,0,0.5)" }}
              >
                {engine.isPlaying ? <Pause className="w-10 h-10" /> : <Play className="w-10 h-10" />}
              </button>

              <button
                onClick={engine.stop}
                className="p-6 rounded-xl border-4 border-red-600 bg-red-500 text-zinc-900 hover:bg-red-400 active:translate-y-1 transition-all"
                style={{ boxShadow: "0 5px 0 0 rgb(153, 27, 27), 0 8px 16px rgba(0,0,0,0.5)" }}
              >
                <Square className="w-10 h-10" />
              </button>
            </div>

            {/* LED Indicators */}
            <div className="flex gap-6 ml-8">
              <div className="flex flex-col items-center gap-2">
                <div
                  className={cn(
                    "w-12 h-12 rounded-full border-4 border-zinc-900 transition-all duration-75",
                    beatSync.isDownbeat ? "bg-red-500" : "bg-red-950"
                  )}
                  style={{
                    boxShadow: beatSync.isDownbeat
                      ? "0 0 30px rgba(239, 68, 68, 0.8), inset 0 -2px 4px rgba(0,0,0,0.3)"
                      : "inset 0 4px 8px rgba(0,0,0,0.6)",
                  }}
                />
                <span className="text-xs text-zinc-500 uppercase">Downbeat</span>
              </div>

              <div className="flex flex-col items-center gap-2">
                <div
                  className={cn(
                    "w-12 h-12 rounded-full border-4 border-zinc-900 transition-all duration-75",
                    beatSync.isBeat ? "bg-yellow-400" : "bg-yellow-950"
                  )}
                  style={{
                    boxShadow: beatSync.isBeat
                      ? "0 0 30px rgba(250, 204, 21, 0.8), inset 0 -2px 4px rgba(0,0,0,0.3)"
                      : "inset 0 4px 8px rgba(0,0,0,0.6)",
                  }}
                />
                <span className="text-xs text-zinc-500 uppercase">Beat</span>
              </div>
            </div>

            {/* Loading indicator */}
            {engine.isLoading && (
              <div className="ml-auto text-zinc-500 uppercase tracking-wider">Loading stems...</div>
            )}
          </div>
        </div>

        {/* Visualization Panel */}
        <VisualizationPanel
          analysis={analysis}
          activeStem={visualization.activeStem}
          viewMode={visualization.viewMode}
          viewport={visualization.viewport}
          currentTime={engine.currentTime}
          speed={engine.speed}
          isExpanded={visualization.isExpanded}
          followPlayhead={visualization.followPlayhead}
          loopStart={engine.loopStart}
          loopEnd={engine.loopEnd}
          containerRef={visualization.containerRef}
          onClose={visualization.closePanel}
          onToggleViewMode={visualization.toggleViewMode}
          onToggleFollowPlayhead={visualization.toggleFollowPlayhead}
          onZoom={visualization.zoom}
          onScrollTo={visualization.scrollTo}
          onSeek={engine.seek}
        />

        {/* Stems Section */}
        <div
          className="border-8 border-zinc-700 rounded-3xl p-8 bg-zinc-800"
          style={{ boxShadow: "inset 0 6px 12px rgba(0,0,0,0.4), 0 8px 24px rgba(0,0,0,0.5)" }}
        >
          <h2 className="text-2xl text-amber-400 mb-6 uppercase tracking-wider">Stems</h2>

          <div className="space-y-4">
            {/* Main stems (non-drum components, excluding combined drums if components exist) */}
            {(() => {
              const hasDrumComponents = Object.keys(engine.stems).some((name) => DRUM_COMPONENTS.has(name));
              return Object.entries(engine.stems)
                .filter(([name]) => {
                  // Exclude individual drum components
                  if (DRUM_COMPONENTS.has(name)) return false;
                  // Exclude combined drums if we have drum components (it'll show in the drum section)
                  if (name === "drums" && hasDrumComponents) return false;
                  return true;
                })
                .map(([name, stem]) => (
                  <StemRow
                    key={name}
                    name={name}
                    displayName={name}
                    stem={stem}
                    isSoloed={engine.soloedStems.has(name)}
                    onToggleMute={() => engine.toggleMute(name)}
                    onToggleSolo={() => engine.toggleSolo(name)}
                    onVolumeChange={(vol) => engine.setStemVolume(name, vol)}
                    onToggleVisualization={() => visualization.toggleStemVisualization(name)}
                    isVisualizationActive={visualization.activeStem === name && visualization.isExpanded}
                    hasVisualizationData={stemHasVisualizationData(name)}
                  />
                ));
            })()}

            {/* Drum section: combined drums as header with components nested */}
            {(() => {
              const hasCombinedDrums = "drums" in engine.stems;
              const drumComponentNames = Object.keys(engine.stems).filter((name) => DRUM_COMPONENTS.has(name));
              const hasDrumComponents = drumComponentNames.length > 0;

              // Only show this section if we have drum components
              if (!hasDrumComponents) return null;

              const combinedDrumsStem = hasCombinedDrums ? engine.stems["drums"] : null;

              return (
                <div
                  className="border-4 rounded-2xl bg-zinc-900 border-zinc-700 overflow-hidden"
                  style={{ boxShadow: "inset 0 2px 6px rgba(0,0,0,0.3)" }}
                >
                  {/* Drum group header - with controls if combined drums exists */}
                  <div className="flex items-center gap-4 p-6">
                    {/* Expand/collapse button */}
                    <button
                      onClick={() => setDrumSectionExpanded(!drumSectionExpanded)}
                      className="p-1 -m-1 hover:bg-zinc-800 rounded transition-colors"
                    >
                      {drumSectionExpanded ? (
                        <ChevronDown className="w-5 h-5 text-zinc-400" />
                      ) : (
                        <ChevronRight className="w-5 h-5 text-zinc-400" />
                      )}
                    </button>

                    <div className={cn("w-4 h-4 rounded", getStemColor("drums"))} />
                    <h3 className="text-xl text-zinc-300 uppercase tracking-wider flex-1">
                      Drums
                    </h3>

                    {/* Controls for combined drums stem */}
                    {combinedDrumsStem && (
                      <>
                        <button
                          onClick={() => engine.toggleMute("drums")}
                          className={cn(
                            "px-4 py-2 rounded-lg border-3 text-sm uppercase tracking-wider transition-all",
                            combinedDrumsStem.isMuted
                              ? "border-red-600 bg-red-500 text-zinc-900"
                              : "border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500"
                          )}
                          style={{
                            boxShadow: combinedDrumsStem.isMuted
                              ? "inset 0 2px 4px rgba(0,0,0,0.3)"
                              : "0 2px 0 0 rgb(63, 63, 70)",
                          }}
                        >
                          Mute
                        </button>

                        <button
                          onClick={() => engine.toggleSolo("drums")}
                          className={cn(
                            "px-4 py-2 rounded-lg border-3 text-sm uppercase tracking-wider transition-all",
                            engine.soloedStems.has("drums")
                              ? "border-amber-600 bg-amber-500 text-zinc-900"
                              : "border-zinc-600 bg-zinc-700 text-zinc-300 hover:border-zinc-500"
                          )}
                          style={{
                            boxShadow: engine.soloedStems.has("drums")
                              ? "inset 0 2px 4px rgba(0,0,0,0.3)"
                              : "0 2px 0 0 rgb(63, 63, 70)",
                          }}
                        >
                          Solo
                        </button>
                      </>
                    )}

                    {/* Track count badge */}
                    <span className="text-sm text-zinc-500">
                      {drumComponentNames.length} components
                    </span>
                  </div>

                  {/* Volume slider for combined drums */}
                  {combinedDrumsStem && (
                    <div className="flex items-center gap-4 px-6 pb-4">
                      <div className="w-5" /> {/* Spacer to align with content below chevron */}
                      <div
                        className="flex-1 h-8 bg-zinc-950 rounded-lg border-3 border-zinc-700 relative overflow-hidden"
                        style={{ boxShadow: "inset 0 3px 6px rgba(0,0,0,0.5)" }}
                      >
                        <div
                          className={cn("h-full transition-all", getStemColor("drums"))}
                          style={{ width: `${combinedDrumsStem.volume}%` }}
                        />
                        <input
                          type="range"
                          min="0"
                          max="100"
                          value={combinedDrumsStem.volume}
                          onChange={(e) => engine.setStemVolume("drums", parseInt(e.target.value))}
                          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                        />
                      </div>
                      <span className="text-lg text-zinc-400 w-12 text-right">{combinedDrumsStem.volume}%</span>
                    </div>
                  )}

                  {/* Expandable drum component tracks */}
                  {drumSectionExpanded && (
                    <div className="border-t border-zinc-700 p-4 space-y-3">
                      {drumComponentNames.map((name) => {
                        const stem = engine.stems[name];
                        return (
                          <StemRow
                            key={name}
                            name={name}
                            displayName={DRUM_DISPLAY_NAMES[name] || name}
                            stem={stem}
                            isSoloed={engine.soloedStems.has(name)}
                            onToggleMute={() => engine.toggleMute(name)}
                            onToggleSolo={() => engine.toggleSolo(name)}
                            onVolumeChange={(vol) => engine.setStemVolume(name, vol)}
                            onToggleVisualization={() => visualization.toggleStemVisualization(name)}
                            isVisualizationActive={visualization.activeStem === name && visualization.isExpanded}
                            hasVisualizationData={stemHasVisualizationData(name)}
                            compact
                          />
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        </div>
      </div>
    </div>
  );
}
