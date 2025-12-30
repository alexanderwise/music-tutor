"""Pipeline processing models for Music Tutor.

These models track state as audio files move through the processing pipeline.
"""

from dataclasses import dataclass, field
from pathlib import Path

from music_tutor.models.analysis import BeatEvent, LyricsData, Note


@dataclass
class ProcessingContext:
    """Mutable state passed through pipeline stages."""

    # Input
    source_path: Path
    source_lyrics_path: Path | None = None  # .lrc or .txt if found

    # Directories
    temp_dir: Path = field(default_factory=lambda: Path("/tmp"))
    output_dir: Path = field(default_factory=lambda: Path("./output"))

    # Normalized audio (Stage 1)
    normalized_audio_path: Path | None = None
    duration: float | None = None
    sample_rate: int | None = None

    # Metadata extracted from tags
    title: str | None = None
    artist: str | None = None
    album: str | None = None

    # Extended metadata (genre, year, musicbrainz IDs, etc.)
    # Raw key-value pairs from audio file tags
    metadata: dict[str, str] = field(default_factory=dict)

    # Stem paths (Stage 2) - keys are stem names
    stem_paths: dict[str, Path] = field(default_factory=dict)

    # Beat data (Stage 3a)
    beats: list[BeatEvent] = field(default_factory=list)
    tempo_bpm: float | None = None
    time_signature: tuple[int, int] | None = None

    # Note data (Stage 3b) - keyed by stem name
    notes: dict[str, list[Note]] = field(default_factory=dict)

    # Lyrics data (Stage 3c)
    lyrics: LyricsData | None = None

    # Time-stretched stems (Stage 4) - stem_name -> speed -> path
    stretched_stems: dict[str, dict[str, Path]] = field(default_factory=dict)

    # Final output
    analysis_path: Path | None = None


@dataclass
class StageResult:
    """Result of a pipeline stage execution."""

    success: bool
    stage_name: str
    duration_seconds: float
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ProcessingResult:
    """Final result of the complete pipeline execution."""

    success: bool
    output_path: Path | None = None
    stages_completed: list[str] = field(default_factory=list)
    stages_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total_duration: float = 0.0
