"""Lyrics alignment stage - word-level timing using stable-ts."""

import re
from pathlib import Path
from typing import Literal

from music_tutor.models.analysis import LyricLine, LyricsData, LyricWord
from music_tutor.models.pipeline import ProcessingContext, StageResult
from music_tutor.pipeline.base import PipelineStage


class LyricsAlignmentStage(PipelineStage):
    """Stage 3c: Lyrics Alignment.

    Uses stable-ts (stable Whisper) to get word-level timing for lyrics.
    Supports two modes:
    1. Forced alignment: If .lrc or .txt lyrics file exists, align with audio
    2. Transcription: If no lyrics file, transcribe vocals and extract timing

    Runs on the vocals stem when available, falls back to full mix.
    Uses the Whisper "base" model by default for good accuracy/speed balance.
    """

    DEFAULT_MODEL = "base"

    @property
    def name(self) -> str:
        return "lyrics_alignment"

    def execute(self, context: ProcessingContext) -> StageResult:
        """Execute lyrics alignment on vocals."""
        warnings: list[str] = []

        # Check stable-ts is available
        try:
            import stable_whisper
        except ImportError as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"stable-ts not installed: {e}",
            )

        # Find audio to use (prefer vocals stem, fall back to normalized mix)
        audio_path = self._get_audio_path(context)
        if audio_path is None:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message="No audio available for lyrics alignment",
            )

        # Determine mode: alignment vs transcription
        lyrics_text = None
        source: Literal["lrc", "txt", "transcribed"] = "transcribed"

        if context.source_lyrics_path and context.source_lyrics_path.exists():
            lyrics_text, source = self._load_lyrics(context.source_lyrics_path)
            if lyrics_text:
                warnings.append(f"Using {source} lyrics file for alignment")

        try:
            # Load Whisper model
            model = stable_whisper.load_model(self.DEFAULT_MODEL)

            if lyrics_text:
                # Forced alignment mode
                lyrics_data = self._align_lyrics(
                    model, audio_path, lyrics_text, source
                )
            else:
                # Transcription mode
                warnings.append("No lyrics file found, transcribing audio")
                lyrics_data = self._transcribe_audio(model, audio_path)

            context.lyrics = lyrics_data
            warnings.append(f"Aligned {len(lyrics_data.lines)} lines of lyrics")

        except Exception as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"Lyrics alignment failed: {e}",
            )

        return StageResult(
            success=True,
            stage_name=self.name,
            duration_seconds=0,
            warnings=warnings,
        )

    def _get_audio_path(self, context: ProcessingContext) -> Path | None:
        """Get best audio path for lyrics processing.

        Prefers vocals stem (cleaner for speech recognition),
        falls back to normalized full mix.
        """
        # Prefer vocals stem
        vocals_path = context.stem_paths.get("vocals")
        if vocals_path and vocals_path.exists():
            return vocals_path

        # Fall back to full mix
        if context.normalized_audio_path and context.normalized_audio_path.exists():
            return context.normalized_audio_path

        return None

    def _load_lyrics(
        self, lyrics_path: Path
    ) -> tuple[str | None, Literal["lrc", "txt", "transcribed"]]:
        """Load lyrics from .lrc or .txt file.

        Args:
            lyrics_path: Path to lyrics file

        Returns:
            Tuple of (lyrics_text, source_type)
        """
        suffix = lyrics_path.suffix.lower()

        try:
            with open(lyrics_path, encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return None, "transcribed"

        if suffix == ".lrc":
            # Parse LRC format - remove timestamps
            lines = []
            for line in content.splitlines():
                # Remove timestamp like [00:12.34]
                text = re.sub(r"\[\d+:\d+[.:]\d+\]", "", line).strip()
                if text and not text.startswith("["):  # Skip metadata tags
                    lines.append(text)
            return "\n".join(lines), "lrc"

        elif suffix == ".txt":
            # Plain text - just strip empty lines
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            return "\n".join(lines), "txt"

        return None, "transcribed"

    def _align_lyrics(
        self,
        model,  # stable_whisper Whisper model
        audio_path: Path,
        lyrics_text: str,
        source: Literal["lrc", "txt", "transcribed"],
    ) -> LyricsData:
        """Align existing lyrics with audio using stable-ts.

        Args:
            model: Loaded Whisper model
            audio_path: Path to audio file
            lyrics_text: Plain text lyrics (newlines separate lines)
            source: Where lyrics came from

        Returns:
            LyricsData with word-level timing
        """
        import stable_whisper

        result = stable_whisper.alignment.align(
            model=model,
            audio=str(audio_path),
            text=lyrics_text,
            language="en",
            original_split=True,  # Preserve line structure from lyrics file
        )

        return self._convert_result(result, source)

    def _transcribe_audio(
        self,
        model,  # stable_whisper Whisper model
        audio_path: Path,
    ) -> LyricsData:
        """Transcribe audio and extract word-level timing.

        Args:
            model: Loaded Whisper model
            audio_path: Path to audio file

        Returns:
            LyricsData with word-level timing
        """
        result = model.transcribe(str(audio_path))
        return self._convert_result(result, "transcribed")

    def _convert_result(
        self,
        result,  # stable_whisper WhisperResult
        source: Literal["lrc", "txt", "transcribed"],
    ) -> LyricsData:
        """Convert stable-ts result to our LyricsData format.

        Args:
            result: WhisperResult from stable-ts
            source: Where lyrics came from

        Returns:
            LyricsData with word-level timing
        """
        lines: list[LyricLine] = []

        if result and result.segments:
            for segment in result.segments:
                words: list[LyricWord] = []

                if segment.words:
                    for word in segment.words:
                        words.append(
                            LyricWord(
                                text=word.word.strip(),
                                start=float(word.start),
                                end=float(word.end),
                                confidence=1.0,  # stable-ts doesn't provide per-word confidence
                            )
                        )

                # Use segment timing as line timing
                line = LyricLine(
                    text=segment.text.strip(),
                    start=float(segment.start),
                    end=float(segment.end),
                    words=words,
                )
                lines.append(line)

        return LyricsData(source=source, lines=lines)
