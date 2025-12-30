"""Tests for the FinalizeStage."""

import json
from pathlib import Path

import pytest

from music_tutor.models.analysis import (
    BeatEvent,
    LyricLine,
    LyricsData,
    LyricWord,
    Note,
    PitchBendPoint,
)
from music_tutor.models.pipeline import ProcessingContext
from music_tutor.stages.finalize import CONVERTER_VERSION, FinalizeStage


class TestFinalizeStage:
    """Tests for FinalizeStage."""

    def test_stage_name(self):
        """Stage has correct name."""
        stage = FinalizeStage()
        assert stage.name == "finalize"

    def test_creates_analysis_json(self, tmp_path: Path):
        """Creates analysis.json in output directory."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=120.5,
            sample_rate=44100,
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
        )

        result = stage.execute(context)

        assert result.success is True
        assert (tmp_path / "output" / "analysis.json").exists()
        assert context.analysis_path == tmp_path / "output" / "analysis.json"

    def test_analysis_json_structure(self, tmp_path: Path):
        """Analysis JSON has correct structure."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=120.5,
            sample_rate=44100,
            title="Test Song",
            artist="Test Artist",
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        stage.execute(context)

        with open(tmp_path / "output" / "analysis.json") as f:
            data = json.load(f)

        # Check metadata fields (camelCase)
        assert data["title"] == "Test Song"
        assert data["artist"] == "Test Artist"
        assert data["originalDuration"] == 120.5
        assert data["sampleRate"] == 44100
        assert data["tempoBpm"] == 120.0
        assert data["timeSignature"] == [4, 4]

    def test_includes_beats(self, tmp_path: Path):
        """Analysis JSON includes beat data."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=60.0,
            sample_rate=44100,
            beats=[
                BeatEvent(time=0.5, type="downbeat", beat_in_measure=1),
                BeatEvent(time=1.0, type="beat", beat_in_measure=2),
            ],
        )

        stage.execute(context)

        with open(tmp_path / "output" / "analysis.json") as f:
            data = json.load(f)

        assert len(data["beats"]) == 2
        assert data["beats"][0]["time"] == 0.5
        assert data["beats"][0]["type"] == "downbeat"
        assert data["beats"][0]["beatInMeasure"] == 1

    def test_includes_notes(self, tmp_path: Path):
        """Analysis JSON includes note data."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=60.0,
            sample_rate=44100,
            notes={
                "vocals": [
                    Note(
                        start=1.0,
                        end=2.0,
                        pitch=60,
                        velocity=0.8,
                        pitch_bend=[
                            PitchBendPoint(time=0.1, cents=10),
                            PitchBendPoint(time=0.3, cents=-5),
                        ],
                    ),
                ],
            },
        )

        stage.execute(context)

        with open(tmp_path / "output" / "analysis.json") as f:
            data = json.load(f)

        assert "vocals" in data["notes"]
        assert len(data["notes"]["vocals"]) == 1

        note = data["notes"]["vocals"][0]
        assert note["start"] == 1.0
        assert note["end"] == 2.0
        assert note["pitch"] == 60
        assert note["velocity"] == 0.8
        assert len(note["pitchBend"]) == 2

    def test_includes_lyrics(self, tmp_path: Path):
        """Analysis JSON includes lyrics data."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=60.0,
            sample_rate=44100,
            lyrics=LyricsData(
                source="lrc",
                lines=[
                    LyricLine(
                        text="Hello world",
                        start=1.0,
                        end=3.0,
                        words=[
                            LyricWord(text="Hello", start=1.0, end=1.5, confidence=0.95),
                            LyricWord(text="world", start=2.0, end=3.0, confidence=0.90),
                        ],
                    ),
                ],
            ),
        )

        stage.execute(context)

        with open(tmp_path / "output" / "analysis.json") as f:
            data = json.load(f)

        assert data["lyrics"]["source"] == "lrc"
        assert len(data["lyrics"]["lines"]) == 1

        line = data["lyrics"]["lines"][0]
        assert line["text"] == "Hello world"
        assert len(line["words"]) == 2

    def test_includes_stems(self, tmp_path: Path):
        """Analysis JSON includes stem paths."""
        stage = FinalizeStage()

        # Create fake stretched stems
        stems_dir = tmp_path / "output" / "stems"
        stems_dir.mkdir(parents=True)
        (stems_dir / "vocals_1.0x.flac").touch()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=60.0,
            sample_rate=44100,
            stretched_stems={
                "vocals": {
                    "1.0x": stems_dir / "vocals_1.0x.flac",
                },
            },
            notes={"vocals": [Note(start=1.0, end=2.0, pitch=60, velocity=0.8)]},
        )

        stage.execute(context)

        with open(tmp_path / "output" / "analysis.json") as f:
            data = json.load(f)

        assert "vocals" in data["stems"]
        assert data["stems"]["vocals"]["name"] == "vocals"
        assert data["stems"]["vocals"]["paths"]["1.0x"] == "stems/vocals_1.0x.flac"
        assert data["stems"]["vocals"]["hasNotes"] is True

    def test_includes_processing_info(self, tmp_path: Path):
        """Analysis JSON includes processing metadata."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "my_song.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=60.0,
            sample_rate=44100,
        )

        stage.execute(context)

        with open(tmp_path / "output" / "analysis.json") as f:
            data = json.load(f)

        assert data["sourceFile"] == "my_song.mp3"
        assert data["converterVersion"] == CONVERTER_VERSION
        assert "processingDate" in data  # ISO format date string

    def test_camel_case_conversion(self):
        """_to_camel_case converts snake_case correctly."""
        stage = FinalizeStage()

        assert stage._to_camel_case("hello_world") == "helloWorld"
        assert stage._to_camel_case("original_duration") == "originalDuration"
        assert stage._to_camel_case("beat_in_measure") == "beatInMeasure"
        assert stage._to_camel_case("simple") == "simple"

    def test_warns_on_missing_data(self, tmp_path: Path):
        """Adds warnings for missing analysis data."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=60.0,
            sample_rate=44100,
            # No beats, notes, or lyrics
        )

        result = stage.execute(context)

        assert result.success is True
        assert any("beat" in w.lower() for w in result.warnings)
        assert any("note" in w.lower() for w in result.warnings)
        assert any("lyrics" in w.lower() for w in result.warnings)

    def test_creates_output_directory(self, tmp_path: Path):
        """Creates output directory if it doesn't exist."""
        stage = FinalizeStage()

        output_dir = tmp_path / "nested" / "output" / "dir"
        assert not output_dir.exists()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=output_dir,
            duration=60.0,
            sample_rate=44100,
        )

        result = stage.execute(context)

        assert result.success is True
        assert (output_dir / "analysis.json").exists()

    def test_json_is_valid_utf8(self, tmp_path: Path):
        """Analysis JSON uses UTF-8 encoding for international characters."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=60.0,
            sample_rate=44100,
            title="Café ♫ 日本語",
            artist="Björk",
        )

        stage.execute(context)

        with open(tmp_path / "output" / "analysis.json", encoding="utf-8") as f:
            data = json.load(f)

        assert data["title"] == "Café ♫ 日本語"
        assert data["artist"] == "Björk"

    def test_handles_null_values(self, tmp_path: Path):
        """Handles None values gracefully."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=60.0,
            sample_rate=44100,
            title=None,
            artist=None,
            album=None,
            tempo_bpm=None,
            time_signature=None,
        )

        result = stage.execute(context)

        assert result.success is True

        with open(tmp_path / "output" / "analysis.json") as f:
            data = json.load(f)

        assert data["title"] is None
        assert data["artist"] is None
        assert data["tempoBpm"] is None

    def test_creates_nfo_file(self, tmp_path: Path):
        """Creates metadata.nfo file alongside analysis.json."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=120.5,
            sample_rate=44100,
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
        )

        result = stage.execute(context)

        assert result.success is True
        assert (tmp_path / "output" / "metadata.nfo").exists()

    def test_nfo_file_structure(self, tmp_path: Path):
        """NFO file has correct XML structure with basic metadata."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=120.5,
            sample_rate=44100,
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        stage.execute(context)

        nfo_content = (tmp_path / "output" / "metadata.nfo").read_text(encoding="utf-8")

        assert '<?xml version="1.0" encoding="UTF-8"?>' in nfo_content
        assert "<musicinfo>" in nfo_content
        assert "</musicinfo>" in nfo_content
        assert "<title>Test Song</title>" in nfo_content
        assert "<artist>Test Artist</artist>" in nfo_content
        assert "<album>Test Album</album>" in nfo_content
        assert "<source_file>test.mp3</source_file>" in nfo_content
        assert f"<converter_version>{CONVERTER_VERSION}</converter_version>" in nfo_content

    def test_nfo_includes_extended_metadata(self, tmp_path: Path):
        """NFO file includes extended metadata from context.metadata dict."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=120.5,
            sample_rate=44100,
            title="Test Song",
            artist="Test Artist",
        )
        context.metadata["genre"] = "Rock"
        context.metadata["date"] = "2023"
        context.metadata["musicbrainz_trackid"] = "abc123-def456"
        context.metadata["isrc"] = "USRC12345678"

        stage.execute(context)

        nfo_content = (tmp_path / "output" / "metadata.nfo").read_text(encoding="utf-8")

        assert "<genre>Rock</genre>" in nfo_content
        assert "<date>2023</date>" in nfo_content
        assert "<musicbrainz_trackid>abc123-def456</musicbrainz_trackid>" in nfo_content
        assert "<isrc>USRC12345678</isrc>" in nfo_content

    def test_nfo_escapes_xml_characters(self, tmp_path: Path):
        """NFO file properly escapes XML special characters."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=60.0,
            sample_rate=44100,
            title="Rock & Roll <Live>",
            artist="The \"Best\" Band",
        )

        stage.execute(context)

        nfo_content = (tmp_path / "output" / "metadata.nfo").read_text(encoding="utf-8")

        assert "<title>Rock &amp; Roll &lt;Live&gt;</title>" in nfo_content
        assert '<artist>The &quot;Best&quot; Band</artist>' in nfo_content

    def test_escape_xml_method(self):
        """_escape_xml correctly escapes all special characters."""
        stage = FinalizeStage()

        assert stage._escape_xml("&") == "&amp;"
        assert stage._escape_xml("<") == "&lt;"
        assert stage._escape_xml(">") == "&gt;"
        assert stage._escape_xml('"') == "&quot;"
        assert stage._escape_xml("'") == "&apos;"
        assert stage._escape_xml("Rock & Roll <Live>") == "Rock &amp; Roll &lt;Live&gt;"

    def test_nfo_includes_processing_info(self, tmp_path: Path):
        """NFO file includes processing section with detected values."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=120.5,
            sample_rate=44100,
            tempo_bpm=125.5,
            time_signature=(4, 4),
        )

        stage.execute(context)

        nfo_content = (tmp_path / "output" / "metadata.nfo").read_text(encoding="utf-8")

        assert "<processing>" in nfo_content
        assert "</processing>" in nfo_content
        assert "<duration>120.50</duration>" in nfo_content
        assert "<sample_rate>44100</sample_rate>" in nfo_content
        assert "<detected_bpm>125.5</detected_bpm>" in nfo_content
        assert "<time_signature>4/4</time_signature>" in nfo_content

    def test_nfo_handles_utf8(self, tmp_path: Path):
        """NFO file handles UTF-8 characters properly."""
        stage = FinalizeStage()

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            duration=60.0,
            sample_rate=44100,
            title="Café ♫ 日本語",
            artist="Björk",
        )

        stage.execute(context)

        nfo_content = (tmp_path / "output" / "metadata.nfo").read_text(encoding="utf-8")

        assert "<title>Café ♫ 日本語</title>" in nfo_content
        assert "<artist>Björk</artist>" in nfo_content
