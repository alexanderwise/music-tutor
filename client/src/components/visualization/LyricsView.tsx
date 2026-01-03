import { useMemo, useRef, useEffect } from "react";
import { type LyricsData, type LyricLine, type LyricWord } from "../../types/analysis";
import { scaleTime } from "../../lib/utils";
import { cn } from "../../lib/utils";

interface LyricsViewProps {
  lyrics: LyricsData;
  speed: string;
  currentTime: number;
  onSeek: (time: number) => void;
}

export function LyricsView({ lyrics, speed, currentTime, onSeek }: LyricsViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Scale all line and word times to current speed
  const scaledLines = useMemo(() => {
    return lyrics.lines.map((line) => ({
      ...line,
      scaledStart: scaleTime(line.start, speed),
      scaledEnd: scaleTime(line.end, speed),
      words: line.words.map((word) => ({
        ...word,
        scaledStart: scaleTime(word.start, speed),
        scaledEnd: scaleTime(word.end, speed),
      })),
    }));
  }, [lyrics, speed]);

  // Find current line index
  const currentLineIndex = useMemo(() => {
    for (let i = 0; i < scaledLines.length; i++) {
      const line = scaledLines[i];
      // Current line: we're within its time range, or between it and the next line
      if (currentTime >= line.scaledStart && currentTime <= line.scaledEnd) {
        return i;
      }
      // Check if we're in the gap before the next line
      if (i < scaledLines.length - 1) {
        const nextLine = scaledLines[i + 1];
        if (currentTime > line.scaledEnd && currentTime < nextLine.scaledStart) {
          // Show the upcoming line during gaps
          return i + 1;
        }
      }
    }
    // Before first line
    if (scaledLines.length > 0 && currentTime < scaledLines[0].scaledStart) {
      return 0;
    }
    // After last line
    return scaledLines.length - 1;
  }, [scaledLines, currentTime]);

  // Auto-scroll to keep current line visible
  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    const currentLineElement = container.querySelector(`[data-line-index="${currentLineIndex}"]`);
    if (currentLineElement) {
      currentLineElement.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [currentLineIndex]);

  if (scaledLines.length === 0) {
    return (
      <div className="absolute inset-0 top-8 flex items-center justify-center text-zinc-600">
        <span>No lyrics available</span>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 top-8 overflow-y-auto px-8 py-4 scroll-smooth"
    >
      <div className="max-w-3xl mx-auto space-y-4">
        {scaledLines.map((line, lineIndex) => {
          const isCurrentLine = lineIndex === currentLineIndex;
          const isPastLine = lineIndex < currentLineIndex;
          const isFutureLine = lineIndex > currentLineIndex;

          return (
            <LyricLineDisplay
              key={lineIndex}
              line={line}
              lineIndex={lineIndex}
              isCurrentLine={isCurrentLine}
              isPastLine={isPastLine}
              isFutureLine={isFutureLine}
              currentTime={currentTime}
              onSeek={onSeek}
            />
          );
        })}
      </div>
    </div>
  );
}

interface ScaledLyricLine extends LyricLine {
  scaledStart: number;
  scaledEnd: number;
  words: Array<LyricWord & { scaledStart: number; scaledEnd: number }>;
}

function LyricLineDisplay({
  line,
  lineIndex,
  isCurrentLine,
  isPastLine,
  isFutureLine,
  currentTime,
  onSeek,
}: {
  line: ScaledLyricLine;
  lineIndex: number;
  isCurrentLine: boolean;
  isPastLine: boolean;
  isFutureLine: boolean;
  currentTime: number;
  onSeek: (time: number) => void;
}) {
  return (
    <div
      data-line-index={lineIndex}
      className={cn(
        "text-center py-2 transition-all duration-300 cursor-pointer rounded-lg",
        isCurrentLine && "bg-zinc-800/50 scale-105",
        isPastLine && "opacity-40",
        isFutureLine && "opacity-60"
      )}
      onClick={() => onSeek(line.scaledStart)}
    >
      <p
        className={cn(
          "text-lg leading-relaxed transition-all duration-300",
          isCurrentLine && "text-2xl font-medium"
        )}
      >
        {line.words.map((word, wordIndex) => {
          const isWordPast = currentTime >= word.scaledEnd;
          const isWordCurrent =
            currentTime >= word.scaledStart && currentTime < word.scaledEnd;
          const isWordFuture = currentTime < word.scaledStart;

          // Calculate progress through current word (0-1)
          let wordProgress = 0;
          if (isWordCurrent) {
            wordProgress =
              (currentTime - word.scaledStart) / (word.scaledEnd - word.scaledStart);
          }

          return (
            <span
              key={wordIndex}
              className={cn(
                "inline-block mx-0.5 px-1 py-0.5 rounded cursor-pointer transition-all duration-100",
                // Past words: fully highlighted
                isWordPast && isCurrentLine && "text-amber-400",
                isWordPast && !isCurrentLine && "text-zinc-400",
                // Current word: animated highlight
                isWordCurrent && "text-amber-300 bg-amber-500/20 scale-110",
                // Future words: dimmed
                isWordFuture && isCurrentLine && "text-zinc-300",
                isWordFuture && !isCurrentLine && "text-zinc-500",
                // Low confidence indicator
                word.confidence < 0.7 && "italic"
              )}
              onClick={(e) => {
                e.stopPropagation();
                onSeek(word.scaledStart);
              }}
              style={
                isWordCurrent
                  ? {
                      // Gradient fill effect based on word progress
                      background: `linear-gradient(90deg,
                        rgba(245, 158, 11, 0.3) 0%,
                        rgba(245, 158, 11, 0.3) ${wordProgress * 100}%,
                        transparent ${wordProgress * 100}%,
                        transparent 100%)`,
                    }
                  : undefined
              }
            >
              {word.text}
            </span>
          );
        })}
      </p>
    </div>
  );
}
