"""Pipeline stages for Music Tutor."""

from music_tutor.stages.beat_detection import BeatDetectionStage
from music_tutor.stages.finalize import FinalizeStage
from music_tutor.stages.ingest import IngestStage
from music_tutor.stages.lyrics_alignment import LyricsAlignmentStage
from music_tutor.stages.pitch_detection import PitchDetectionStage
from music_tutor.stages.separation import SeparationStage
from music_tutor.stages.strike_detection import StrikeDetectionStage
from music_tutor.stages.time_stretch import TimeStretchStage

__all__ = [
    "BeatDetectionStage",
    "FinalizeStage",
    "IngestStage",
    "LyricsAlignmentStage",
    "PitchDetectionStage",
    "SeparationStage",
    "StrikeDetectionStage",
    "TimeStretchStage",
]
