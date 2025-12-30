"""Tests for data models."""

import json
from dataclasses import asdict

from music_tutor.models.analysis import (
    BeatEvent,
    LyricLine,
    LyricWord,
    LyricsData,
    Note,
    PitchBendPoint,
    SongAnalysis,
    StemInfo,
)


def test_beat_event_types():
    """BeatEvent validates type field."""
    downbeat = BeatEvent(time=0.5, type="downbeat", beat_in_measure=1)
    assert downbeat.type == "downbeat"
    assert downbeat.beat_in_measure == 1

    beat = BeatEvent(time=1.0, type="beat", beat_in_measure=2)
    assert beat.type == "beat"


def test_note_creation():
    """Note can be created with all fields."""
    note = Note(
        start=5.2,
        end=5.8,
        pitch=60,  # Middle C
        velocity=0.85,
        pitch_bend=[
            PitchBendPoint(time=0.1, cents=15),
            PitchBendPoint(time=0.3, cents=-10),
        ],
    )
    assert note.pitch == 60
    assert len(note.pitch_bend) == 2


def test_lyrics_data_creation():
    """LyricsData can be created with word-level timing."""
    lyrics = LyricsData(
        source="lrc",
        lines=[
            LyricLine(
                text="Hello world",
                start=5.0,
                end=6.5,
                words=[
                    LyricWord(text="Hello", start=5.0, end=5.5, confidence=0.95),
                    LyricWord(text="world", start=5.6, end=6.5, confidence=0.92),
                ],
            ),
        ],
    )
    assert lyrics.source == "lrc"
    assert len(lyrics.lines) == 1
    assert len(lyrics.lines[0].words) == 2


def test_stem_info_creation():
    """StemInfo can be created with paths for multiple speeds."""
    stem = StemInfo(
        name="vocals",
        paths={
            "0.5x": "stems/vocals/vocals_0.5x.flac",
            "0.75x": "stems/vocals/vocals_0.75x.flac",
            "1.0x": "stems/vocals/vocals_1.0x.flac",
            "1.25x": "stems/vocals/vocals_1.25x.flac",
        },
        has_notes=True,
        peak_db=-3.2,
    )
    assert stem.name == "vocals"
    assert len(stem.paths) == 4
    assert stem.has_notes is True


def test_song_analysis_serialization():
    """SongAnalysis round-trips through JSON."""
    analysis = SongAnalysis(
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        original_duration=245.32,
        sample_rate=44100,
        tempo_bpm=120.5,
        time_signature=(4, 4),
        source_file="test.mp3",
        processing_date="2025-12-27T15:30:00Z",
        converter_version="0.1.0",
        stems={
            "vocals": StemInfo(
                name="vocals",
                paths={"1.0x": "stems/vocals/vocals_1.0x.flac"},
                has_notes=True,
                peak_db=-3.2,
            ),
        },
        beats=[
            BeatEvent(time=0.5, type="downbeat", beat_in_measure=1),
            BeatEvent(time=1.0, type="beat", beat_in_measure=2),
        ],
        notes={
            "vocals": [
                Note(start=5.2, end=5.8, pitch=60, velocity=0.85),
            ],
        },
        lyrics=None,
    )

    # Convert to dict and back
    data = asdict(analysis)
    json_str = json.dumps(data)
    loaded = json.loads(json_str)

    assert loaded["title"] == "Test Song"
    assert loaded["tempo_bpm"] == 120.5
    assert len(loaded["beats"]) == 2
    assert loaded["beats"][0]["type"] == "downbeat"
