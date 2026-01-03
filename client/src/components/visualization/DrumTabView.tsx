import { useMemo, useState } from "react";
import { type DrumStrikes, type DrumStrike } from "../../types/analysis";
import { type ViewportState } from "../../hooks/useVisualization";
import { cn, scaleTime, formatTime } from "../../lib/utils";

// Drum component display order (top to bottom: cymbals to kick)
const DRUM_ORDER = ["crash", "ride", "hh", "snare", "toms", "kick"] as const;

// Display names and colors for each drum component
const DRUM_CONFIG: Record<
  string,
  { name: string; color: string; hoverColor: string }
> = {
  crash: { name: "Crash", color: "bg-yellow-400", hoverColor: "bg-yellow-300" },
  ride: { name: "Ride", color: "bg-amber-400", hoverColor: "bg-amber-300" },
  hh: { name: "Hi-Hat", color: "bg-cyan-400", hoverColor: "bg-cyan-300" },
  snare: { name: "Snare", color: "bg-red-400", hoverColor: "bg-red-300" },
  toms: { name: "Toms", color: "bg-orange-400", hoverColor: "bg-orange-300" },
  kick: { name: "Kick", color: "bg-purple-400", hoverColor: "bg-purple-300" },
};

interface DrumTabViewProps {
  drumStrikes: DrumStrikes;
  viewport: ViewportState;
  speed: string;
  currentTime: number;
  onSeek: (time: number) => void;
}

interface TooltipInfo {
  x: number;
  y: number;
  time: number;
  velocity: number;
  component: string;
}

export function DrumTabView({
  drumStrikes,
  viewport,
  speed,
  currentTime,
  onSeek,
}: DrumTabViewProps) {
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);

  // Get visible drum components (only show rows with strikes)
  const visibleComponents = useMemo(() => {
    return DRUM_ORDER.filter((key) => {
      const strikes = drumStrikes[key];
      return strikes && strikes.length > 0;
    });
  }, [drumStrikes]);

  // Calculate visible strikes for each component
  const visibleStrikes = useMemo(() => {
    const result: Record<string, Array<DrumStrike & { scaledTime: number }>> = {};

    for (const key of visibleComponents) {
      const strikes = drumStrikes[key];
      if (!strikes) continue;

      result[key] = strikes
        .map((strike) => ({
          ...strike,
          scaledTime: scaleTime(strike.time, speed),
        }))
        .filter(
          (strike) =>
            strike.scaledTime >= viewport.startTime &&
            strike.scaledTime <= viewport.endTime
        );
    }

    return result;
  }, [drumStrikes, visibleComponents, speed, viewport]);

  // Check if we have any data
  const hasData = visibleComponents.length > 0;

  if (!hasData) {
    return (
      <div className="absolute inset-0 top-8 flex flex-col items-center justify-center text-zinc-500 gap-2">
        <p>No drum strike data available</p>
        <p className="text-sm text-zinc-600">
          Process the song with --drum-sep to enable drum visualization
        </p>
      </div>
    );
  }

  const rowHeight = Math.min(40, Math.max(24, 200 / visibleComponents.length));

  return (
    <div className="absolute inset-0 top-8 overflow-hidden">
      {/* Drum rows */}
      <div className="absolute inset-0 flex flex-col">
        {visibleComponents.map((key) => {
          const config = DRUM_CONFIG[key];
          const strikes = visibleStrikes[key] || [];

          return (
            <div
              key={key}
              className="relative border-b border-zinc-800 flex items-center"
              style={{ height: `${rowHeight}px` }}
            >
              {/* Row label */}
              <div className="absolute left-0 top-0 bottom-0 w-16 bg-zinc-900/90 border-r border-zinc-800 flex items-center justify-end pr-2 z-10">
                <span className="text-xs text-zinc-500 uppercase tracking-wide">
                  {config.name}
                </span>
              </div>

              {/* Strike markers */}
              <div className="absolute inset-0 left-16">
                {strikes.map((strike, i) => {
                  const x =
                    (strike.scaledTime - viewport.startTime) *
                    viewport.pixelsPerSecond;
                  // Size based on velocity (4-12px)
                  const size = 4 + strike.velocity * 8;
                  const isCurrentlyPlaying =
                    Math.abs(strike.scaledTime - currentTime) < 0.05;

                  return (
                    <div
                      key={i}
                      className={cn(
                        "absolute rounded-full cursor-pointer transition-transform hover:scale-125",
                        config.color,
                        isCurrentlyPlaying && "ring-2 ring-white scale-125"
                      )}
                      style={{
                        left: `${x}px`,
                        top: "50%",
                        width: `${size}px`,
                        height: `${size}px`,
                        transform: `translate(-50%, -50%)`,
                        opacity: 0.6 + strike.velocity * 0.4,
                      }}
                      onClick={() => onSeek(strike.scaledTime)}
                      onMouseEnter={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        setTooltip({
                          x: rect.left + rect.width / 2,
                          y: rect.top,
                          time: strike.scaledTime,
                          velocity: strike.velocity,
                          component: config.name,
                        });
                      }}
                      onMouseLeave={() => setTooltip(null)}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-xs text-zinc-300 pointer-events-none"
          style={{
            left: tooltip.x,
            top: tooltip.y - 36,
            transform: "translateX(-50%)",
          }}
        >
          <div className="font-medium">{tooltip.component}</div>
          <div className="text-zinc-400">
            {formatTime(tooltip.time)} &bull; {Math.round(tooltip.velocity * 100)}%
          </div>
        </div>
      )}
    </div>
  );
}
