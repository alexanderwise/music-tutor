import { useMemo } from "react";
import { type LyricsData, type LyricWord } from "../../types/analysis";
import { scaleTime } from "../../lib/utils";
import { cn } from "../../lib/utils";

interface LyricsOverlayProps {
  lyrics: LyricsData;
  speed: string;
  currentTime: number;
  onSeek: (time: number) => void;
}

interface ScaledWord extends LyricWord {
  scaledStart: number;
  scaledEnd: number;
}

interface ScaledLine {
  text: string;
  scaledStart: number;
  scaledEnd: number;
  words: ScaledWord[];
}

/**
 * Compact lyrics overlay for the piano roll visualization.
 * Shows current line with karaoke-style word highlighting.
 */
export function LyricsOverlay({ lyrics, speed, currentTime, onSeek }: LyricsOverlayProps) {
  // Scale all line and word times to current speed
  const scaledLines = useMemo((): ScaledLine[] => {
    return lyrics.lines.map((line) => ({
      text: line.text,
      scaledStart: scaleTime(line.start, speed),
      scaledEnd: scaleTime(line.end, speed),
      words: line.words.map((word) => ({
        ...word,
        scaledStart: scaleTime(word.start, speed),
        scaledEnd: scaleTime(word.end, speed),
      })),
    }));
  }, [lyrics, speed]);

  // Find current and next line
  const { currentLine, nextLine } = useMemo(() => {
    let current: ScaledLine | null = null;
    let next: ScaledLine | null = null;

    for (let i = 0; i < scaledLines.length; i++) {
      const line = scaledLines[i];

      // Current line: we're within its time range
      if (currentTime >= line.scaledStart && currentTime <= line.scaledEnd) {
        current = line;
        next = scaledLines[i + 1] || null;
        break;
      }

      // Check if we're in the gap before this line (upcoming)
      if (currentTime < line.scaledStart) {
        // Show the upcoming line as "current" when in gap
        current = line;
        next = scaledLines[i + 1] || null;
        break;
      }
    }

    // After last line - show last line
    if (!current && scaledLines.length > 0) {
      current = scaledLines[scaledLines.length - 1];
    }

    return { currentLine: current, nextLine: next };
  }, [scaledLines, currentTime]);

  if (!currentLine) {
    return null;
  }

  return (
    <div className="absolute bottom-0 left-0 right-0 bg-zinc-900/95 backdrop-blur-sm border-t border-zinc-700 px-4 py-3 z-10">
      {/* Current line with word highlighting */}
      <div className="text-center">
        <p className="text-lg leading-relaxed">
          {currentLine.words.map((word, wordIndex) => (
            <WordHighlight
              key={wordIndex}
              word={word}
              currentTime={currentTime}
              onSeek={onSeek}
            />
          ))}
        </p>
      </div>

      {/* Next line preview */}
      {nextLine && (
        <div className="text-center mt-1">
          <p
            className="text-sm text-zinc-500 cursor-pointer hover:text-zinc-400 transition-colors"
            onClick={() => onSeek(nextLine.scaledStart)}
          >
            {nextLine.text}
          </p>
        </div>
      )}
    </div>
  );
}

function WordHighlight({
  word,
  currentTime,
  onSeek,
}: {
  word: ScaledWord;
  currentTime: number;
  onSeek: (time: number) => void;
}) {
  const isWordPast = currentTime >= word.scaledEnd;
  const isWordCurrent = currentTime >= word.scaledStart && currentTime < word.scaledEnd;
  const isWordFuture = currentTime < word.scaledStart;

  // Calculate progress through current word (0-1)
  let wordProgress = 0;
  if (isWordCurrent) {
    const duration = word.scaledEnd - word.scaledStart;
    wordProgress = duration > 0 ? (currentTime - word.scaledStart) / duration : 1;
  }

  return (
    <span
      className={cn(
        "inline-block mx-0.5 px-1 py-0.5 rounded cursor-pointer transition-all duration-100",
        // Past words: fully highlighted
        isWordPast && "text-amber-400",
        // Current word: animated highlight with scale
        isWordCurrent && "text-amber-300 scale-105",
        // Future words: dimmed
        isWordFuture && "text-zinc-400",
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
                rgba(245, 158, 11, 0.4) 0%,
                rgba(245, 158, 11, 0.4) ${wordProgress * 100}%,
                rgba(245, 158, 11, 0.15) ${wordProgress * 100}%,
                rgba(245, 158, 11, 0.15) 100%)`,
            }
          : undefined
      }
    >
      {word.text}
    </span>
  );
}
