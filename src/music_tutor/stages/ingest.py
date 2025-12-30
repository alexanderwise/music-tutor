"""Ingest stage - validates and normalizes input audio."""

import subprocess
from pathlib import Path

from music_tutor.models.pipeline import ProcessingContext, StageResult
from music_tutor.pipeline.base import PipelineStage


class IngestStage(PipelineStage):
    """Stage 1: Ingest & Normalize.

    - Validates audio file exists and is a supported format
    - Extracts metadata (title, artist, album) from tags
    - Converts to normalized WAV (44.1kHz, 16-bit, stereo)
    - Detects accompanying .lrc/.txt lyrics files
    """

    SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".wma"}

    @property
    def name(self) -> str:
        return "ingest"

    def execute(self, context: ProcessingContext) -> StageResult:
        """Execute the ingest stage."""
        warnings: list[str] = []

        # Validate file exists
        if not context.source_path.exists():
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"File not found: {context.source_path}",
            )

        # Validate extension
        ext = context.source_path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"Unsupported format: {ext}. Supported: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}",
            )

        # Extract metadata
        try:
            self._extract_metadata(context)
        except Exception as e:
            warnings.append(f"Could not extract metadata: {e}")

        # Convert to normalized WAV
        try:
            normalized_path = self._normalize_audio(context)
            context.normalized_audio_path = normalized_path
        except Exception as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"Audio normalization failed: {e}",
            )

        # Get audio info (duration, sample rate)
        try:
            self._get_audio_info(context)
        except Exception as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"Could not read audio info: {e}",
            )

        # Check for lyrics file (already set by orchestrator, just log)
        if context.source_lyrics_path:
            ext = context.source_lyrics_path.suffix.lower()
            warnings.append(f"Found lyrics file: {context.source_lyrics_path.name} ({ext})")

        return StageResult(
            success=True,
            stage_name=self.name,
            duration_seconds=0,
            warnings=warnings,
        )

    def _extract_metadata(self, context: ProcessingContext) -> None:
        """Extract metadata from audio file using mutagen.

        Extracts both common tags (title, artist, album) and extended metadata
        including genre, year, and MusicBrainz identifiers.
        """
        from mutagen import File as MutagenFile

        # First try with easy=True for common tags
        audio_easy = MutagenFile(context.source_path, easy=True)
        if audio_easy is not None:
            context.title = self._get_tag(audio_easy, ["title"])
            context.artist = self._get_tag(audio_easy, ["artist", "albumartist"])
            context.album = self._get_tag(audio_easy, ["album"])

            # Extended metadata via easy interface
            context.metadata["genre"] = self._get_tag(audio_easy, ["genre"]) or ""
            context.metadata["date"] = self._get_tag(audio_easy, ["date", "year"]) or ""
            context.metadata["tracknumber"] = self._get_tag(audio_easy, ["tracknumber"]) or ""
            context.metadata["discnumber"] = self._get_tag(audio_easy, ["discnumber"]) or ""

        # Now get raw tags for MusicBrainz IDs and other extended metadata
        audio_raw = MutagenFile(context.source_path, easy=False)
        if audio_raw is not None:
            self._extract_musicbrainz_tags(audio_raw, context)
            self._extract_extended_tags(audio_raw, context)

    def _extract_musicbrainz_tags(self, audio: object, context: ProcessingContext) -> None:
        """Extract MusicBrainz identifiers from raw tags.

        MusicBrainz tags vary by format:
        - ID3 (MP3): TXXX:MusicBrainz * or UFID
        - Vorbis (FLAC/OGG): MUSICBRAINZ_*
        - MP4 (M4A): ----:com.apple.iTunes:MusicBrainz *
        """
        # Common MusicBrainz tag mappings
        mb_tags = {
            "musicbrainz_trackid": [
                "TXXX:MusicBrainz Release Track Id",
                "TXXX:MUSICBRAINZ_TRACKID",
                "musicbrainz_trackid",
                "MUSICBRAINZ_TRACKID",
                "----:com.apple.iTunes:MusicBrainz Track Id",
            ],
            "musicbrainz_albumid": [
                "TXXX:MusicBrainz Album Id",
                "TXXX:MUSICBRAINZ_ALBUMID",
                "musicbrainz_albumid",
                "MUSICBRAINZ_ALBUMID",
                "----:com.apple.iTunes:MusicBrainz Album Id",
            ],
            "musicbrainz_artistid": [
                "TXXX:MusicBrainz Artist Id",
                "TXXX:MUSICBRAINZ_ARTISTID",
                "musicbrainz_artistid",
                "MUSICBRAINZ_ARTISTID",
                "----:com.apple.iTunes:MusicBrainz Artist Id",
            ],
            "musicbrainz_albumartistid": [
                "TXXX:MusicBrainz Album Artist Id",
                "TXXX:MUSICBRAINZ_ALBUMARTISTID",
                "musicbrainz_albumartistid",
                "MUSICBRAINZ_ALBUMARTISTID",
                "----:com.apple.iTunes:MusicBrainz Album Artist Id",
            ],
            "musicbrainz_releasegroupid": [
                "TXXX:MusicBrainz Release Group Id",
                "TXXX:MUSICBRAINZ_RELEASEGROUPID",
                "musicbrainz_releasegroupid",
                "MUSICBRAINZ_RELEASEGROUPID",
                "----:com.apple.iTunes:MusicBrainz Release Group Id",
            ],
            "musicbrainz_recordingid": [
                "TXXX:MusicBrainz Recording Id",
                "UFID:http://musicbrainz.org",
                "musicbrainz_recordingid",
                "MUSICBRAINZ_RECORDINGID",
            ],
        }

        for key, tag_names in mb_tags.items():
            value = self._get_raw_tag(audio, tag_names)
            if value:
                context.metadata[key] = value

    def _extract_extended_tags(self, audio: object, context: ProcessingContext) -> None:
        """Extract additional extended tags like composer, conductor, etc."""
        extended_tags = {
            "composer": ["TCOM", "composer", "©wrt"],
            "conductor": ["TPE3", "conductor"],
            "lyricist": ["TEXT", "lyricist"],
            "label": ["TPUB", "label", "publisher", "©pub"],
            "isrc": ["TSRC", "isrc", "ISRC"],
            "bpm": ["TBPM", "bpm", "BPM", "tmpo"],
            "compilation": ["TCMP", "compilation", "cpil"],
            "copyright": ["TCOP", "copyright", "©cpy"],
            "encoded_by": ["TENC", "encoded-by", "encodedby"],
            "encoder": ["TSSE", "encoder"],
            "language": ["TLAN", "language"],
            "mood": ["TMOO", "mood"],
            "media": ["TMED", "media"],
            "acoustid_id": [
                "TXXX:Acoustid Id",
                "TXXX:ACOUSTID_ID",
                "acoustid_id",
                "ACOUSTID_ID",
            ],
        }

        for key, tag_names in extended_tags.items():
            if key not in context.metadata or not context.metadata[key]:
                value = self._get_raw_tag(audio, tag_names)
                if value:
                    context.metadata[key] = value

    def _get_tag(self, audio: object, keys: list[str]) -> str | None:
        """Get the first available tag value from easy tags."""
        for key in keys:
            try:
                value = audio.get(key)  # type: ignore[union-attr]
                if value:
                    return str(value[0]) if isinstance(value, list) else str(value)
            except (KeyError, IndexError, TypeError):
                continue
        return None

    def _get_raw_tag(self, audio: object, keys: list[str]) -> str | None:
        """Get the first available tag value from raw tags."""
        for key in keys:
            try:
                value = audio.get(key)  # type: ignore[union-attr]
                if value:
                    # Handle different tag value types
                    if hasattr(value, "text"):
                        # ID3 frames with text attribute
                        text = value.text
                        if isinstance(text, list):
                            return str(text[0]) if text else None
                        return str(text) if text else None
                    elif hasattr(value, "data"):
                        # UFID frames (MusicBrainz recording ID)
                        return value.data.decode("utf-8", errors="ignore")
                    elif isinstance(value, list):
                        return str(value[0]) if value else None
                    else:
                        return str(value)
            except (KeyError, IndexError, TypeError, AttributeError):
                continue
        return None

    def _normalize_audio(self, context: ProcessingContext) -> Path:
        """Convert audio to normalized WAV using ffmpeg."""
        output_path = context.temp_dir / "normalized.wav"

        # ffmpeg command: convert to 44.1kHz, 16-bit, stereo WAV
        cmd = [
            "ffmpeg",
            "-y",  # overwrite output
            "-i", str(context.source_path),
            "-ar", "44100",  # sample rate
            "-ac", "2",  # stereo
            "-sample_fmt", "s16",  # 16-bit
            "-f", "wav",
            str(output_path),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr}")

        if not output_path.exists():
            raise RuntimeError("ffmpeg did not produce output file")

        return output_path

    def _get_audio_info(self, context: ProcessingContext) -> None:
        """Get audio duration and sample rate using soundfile."""
        import soundfile as sf

        if context.normalized_audio_path is None:
            raise RuntimeError("No normalized audio path set")

        info = sf.info(str(context.normalized_audio_path))
        context.duration = info.duration
        context.sample_rate = info.samplerate
