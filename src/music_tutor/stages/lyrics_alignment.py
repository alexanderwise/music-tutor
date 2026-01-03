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
    Supports three sources for lyrics (in order of preference):
    1. Local file: If .lrc or .txt lyrics file exists alongside source audio
    2. lrclib.net: Searches online database using artist/title metadata
    3. Transcription: Falls back to Whisper transcription if no lyrics found

    Runs on the vocals stem when available, falls back to full mix.
    Uses the Whisper "base" model by default for good accuracy/speed balance.
    """

    DEFAULT_MODEL = "base"
    LRCLIB_USER_AGENT = "music-tutor/0.1.0 (https://github.com/alexwise/music-tutor)"

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
        # Priority: local file > lrclib.net > whisper transcription
        lyrics_text = None
        source: Literal["lrc", "txt", "lrclib", "transcribed"] = "transcribed"

        # 1. Check for local lyrics file
        if context.source_lyrics_path and context.source_lyrics_path.exists():
            lyrics_text, source = self._load_lyrics(context.source_lyrics_path)
            if lyrics_text:
                warnings.append(f"Using local {source} lyrics file for alignment")

        # 2. Try lrclib.net if no local file and we have metadata
        if not lyrics_text and context.title:
            lrclib_text = self._fetch_from_lrclib(
                track_name=context.title,
                artist_name=context.artist,
                album_name=context.album,
                duration=context.duration,
            )
            if lrclib_text:
                lyrics_text = lrclib_text
                source = "lrclib"
                warnings.append("Fetched lyrics from lrclib.net for alignment")

        try:
            # Load Whisper model
            model = stable_whisper.load_model(self.DEFAULT_MODEL)

            if lyrics_text:
                # Forced alignment mode
                lyrics_data = self._align_lyrics(
                    model, audio_path, lyrics_text, source
                )
            else:
                # 3. Transcription mode (fallback)
                warnings.append("No lyrics found (local or lrclib.net), transcribing audio")
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
    ) -> tuple[str | None, Literal["lrc", "txt", "lrclib", "transcribed"]]:
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

    def _fetch_from_lrclib(
        self,
        track_name: str,
        artist_name: str | None = None,
        album_name: str | None = None,
        duration: float | None = None,
    ) -> str | None:
        """Fetch lyrics from lrclib.net.

        Searches lrclib.net using song metadata and returns plain text lyrics
        (timestamps stripped) suitable for forced alignment.

        Args:
            track_name: Song title (required)
            artist_name: Artist name (optional, improves matching)
            album_name: Album name (optional, improves matching)
            duration: Song duration in seconds (optional, improves matching)

        Returns:
            Plain text lyrics (newlines separate lines) or None if not found
        """
        try:
            from lrclib import LrcLibAPI
        except ImportError:
            # lrclibapi not installed, silently skip
            return None

        try:
            api = LrcLibAPI(user_agent=self.LRCLIB_USER_AGENT)

            # Try exact match first with get_lyrics (more accurate)
            kwargs = {"track_name": track_name}
            if artist_name:
                kwargs["artist_name"] = artist_name
            if album_name:
                kwargs["album_name"] = album_name
            if duration:
                kwargs["duration"] = int(duration)

            try:
                lyrics = api.get_lyrics(**kwargs)
                if lyrics:
                    # Prefer synced lyrics (LRC format), fall back to plain
                    lyrics_text = lyrics.synced_lyrics or lyrics.plain_lyrics
                    if lyrics_text:
                        return self._strip_lrc_timestamps(lyrics_text)
            except Exception:
                # get_lyrics can fail if no exact match, fall through to search
                pass

            # Fall back to search if exact match fails
            results = api.search_lyrics(track_name=track_name)
            if not results:
                return None

            # Filter results by artist if provided
            if artist_name:
                artist_lower = artist_name.lower()
                matching = [
                    r for r in results
                    if r.artist_name and artist_lower in r.artist_name.lower()
                ]
                if matching:
                    results = matching

            # Get full lyrics for best match
            if results:
                best = results[0]
                full_lyrics = api.get_lyrics_by_id(best.id)
                if full_lyrics:
                    lyrics_text = full_lyrics.synced_lyrics or full_lyrics.plain_lyrics
                    if lyrics_text:
                        return self._strip_lrc_timestamps(lyrics_text)

        except Exception:
            # Any error with lrclib.net, silently fall back
            pass

        return None

    def _strip_lrc_timestamps(self, lyrics: str) -> str:
        """Strip LRC timestamps from synced lyrics.

        Args:
            lyrics: Lyrics text, potentially with [mm:ss.xx] timestamps

        Returns:
            Plain text with timestamps removed
        """
        lines = []
        for line in lyrics.splitlines():
            # Remove timestamp like [00:12.34] or [00:12:34]
            text = re.sub(r"\[\d+:\d+[.:]\d+\]", "", line).strip()
            # Skip metadata tags like [ar:Artist Name]
            if text and not text.startswith("["):
                lines.append(text)
        return "\n".join(lines)

    def _align_lyrics(
        self,
        model,  # stable_whisper Whisper model
        audio_path: Path,
        lyrics_text: str,
        source: Literal["lrc", "txt", "lrclib", "transcribed"],
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
        source: Literal["lrc", "txt", "lrclib", "transcribed"],
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
