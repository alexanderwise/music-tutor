"""Core analysis data models for Music Tutor.

These models represent the analysis output that gets serialized to JSON
alongside the separated stems.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PitchBendPoint:
    """A point in a pitch bend curve."""

    time: float  # seconds (relative to note start)
    cents: float  # deviation in cents from base pitch


@dataclass
class Note:
    """A detected note with timing and pitch information."""

    start: float  # seconds
    end: float  # seconds
    pitch: int  # MIDI note number (0-127)
    velocity: float  # 0.0-1.0 (from basic-pitch confidence)
    pitch_bend: list[PitchBendPoint] | None = None  # optional pitch bend curve


@dataclass
class BeatEvent:
    """A beat or downbeat event."""

    time: float  # seconds (at 1.0x speed)
    type: Literal["beat", "downbeat"]
    beat_in_measure: int | None = None  # 1, 2, 3, 4 for 4/4 time


@dataclass
class DrumStrike:
    """A detected drum hit from an isolated drum stem."""

    time: float  # seconds (at 1.0x speed)
    velocity: float  # 0.0-1.0 (relative amplitude)


@dataclass
class LyricWord:
    """A single word with timing."""

    text: str
    start: float  # seconds
    end: float  # seconds
    confidence: float  # 0.0-1.0 (from alignment model)


@dataclass
class LyricLine:
    """A line of lyrics with word-level timing."""

    text: str  # full line text
    start: float  # seconds
    end: float  # seconds
    words: list[LyricWord] = field(default_factory=list)


@dataclass
class LyricsData:
    """Word-level lyrics with timing."""

    source: Literal["lrc", "txt", "transcribed"]  # how lyrics were obtained
    lines: list[LyricLine] = field(default_factory=list)


@dataclass
class StemInfo:
    """Information about a separated stem."""

    name: str  # "vocals", "drums", "bass", "other"

    # Relative paths to audio files at each speed
    paths: dict[str, str] = field(default_factory=dict)  # {"1.0x": "stems/vocals_1.0x.flac", ...}

    # Whether pitch detection was run on this stem
    has_notes: bool = False

    # Peak loudness for UI normalization
    peak_db: float = 0.0


@dataclass
class SongAnalysis:
    """Root analysis object, serialized to JSON alongside stems."""

    # Metadata
    title: str | None
    artist: str | None
    album: str | None
    original_duration: float  # seconds
    sample_rate: int
    tempo_bpm: float | None = None
    time_signature: tuple[int, int] | None = None  # e.g., (4, 4)

    # Processing info
    source_file: str = ""  # original filename
    processing_date: str = ""  # ISO format
    converter_version: str = ""

    # Stem availability (relative paths from analysis file)
    stems: dict[str, StemInfo] = field(default_factory=dict)

    # Analysis data (at 1.0x speed - scale for other speeds)
    beats: list[BeatEvent] = field(default_factory=list)
    notes: dict[str, list[Note]] = field(default_factory=dict)  # keyed by stem name
    lyrics: LyricsData | None = None

    # Drum strike analysis (keyed by drum stem: kick, snare, hh, etc.)
    drum_strikes: dict[str, list[DrumStrike]] = field(default_factory=dict)
