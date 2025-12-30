"""Tests for the IngestStage."""

from pathlib import Path

import pytest

from music_tutor.models.pipeline import ProcessingContext
from music_tutor.stages.ingest import IngestStage


class TestIngestStage:
    """Tests for IngestStage."""

    def test_stage_name(self):
        """Stage has correct name."""
        stage = IngestStage()
        assert stage.name == "ingest"

    def test_file_not_found(self, tmp_path: Path):
        """Returns error for missing file."""
        stage = IngestStage()
        context = ProcessingContext(
            source_path=tmp_path / "nonexistent.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
        )

        result = stage.execute(context)

        assert result.success is False
        assert "not found" in result.error_message.lower()

    def test_unsupported_format(self, tmp_path: Path):
        """Returns error for unsupported file format."""
        # Create a dummy file with unsupported extension
        bad_file = tmp_path / "test.xyz"
        bad_file.write_text("not audio")

        stage = IngestStage()
        context = ProcessingContext(
            source_path=bad_file,
            temp_dir=tmp_path,
            output_dir=tmp_path,
        )

        result = stage.execute(context)

        assert result.success is False
        assert "unsupported" in result.error_message.lower()

    def test_supported_extensions(self):
        """Verifies list of supported extensions."""
        stage = IngestStage()

        expected = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".wma"}
        assert stage.SUPPORTED_EXTENSIONS == expected

    @pytest.mark.skipif(
        not Path("/usr/bin/ffmpeg").exists() and not Path("/opt/homebrew/bin/ffmpeg").exists(),
        reason="ffmpeg not installed",
    )
    def test_ingest_real_mp3(self, sample_mp3: Path, tmp_path: Path):
        """Integration test with real MP3 file."""
        stage = IngestStage()
        context = ProcessingContext(
            source_path=sample_mp3,
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
        )

        result = stage.execute(context)

        assert result.success is True
        assert context.normalized_audio_path is not None
        assert context.normalized_audio_path.exists()
        assert context.duration is not None
        assert context.duration > 0
        assert context.sample_rate == 44100

    @pytest.mark.skipif(
        not Path("/usr/bin/ffmpeg").exists() and not Path("/opt/homebrew/bin/ffmpeg").exists(),
        reason="ffmpeg not installed",
    )
    def test_ingest_real_flac(self, sample_flac: Path, tmp_path: Path):
        """Integration test with real FLAC file."""
        stage = IngestStage()
        context = ProcessingContext(
            source_path=sample_flac,
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
        )

        result = stage.execute(context)

        assert result.success is True
        assert context.normalized_audio_path is not None
        assert context.duration is not None

    def test_metadata_dict_initialized(self, tmp_path: Path):
        """ProcessingContext metadata dict is initialized empty."""
        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
        )
        assert context.metadata == {}
        assert isinstance(context.metadata, dict)

    def test_get_tag_helper(self):
        """_get_tag correctly extracts values from easy tags."""
        stage = IngestStage()

        # Mock audio object with dict-like access
        class MockAudio:
            def get(self, key):
                return {"title": ["Test Title"], "artist": ["Artist Name"]}.get(key)

        audio = MockAudio()

        assert stage._get_tag(audio, ["title"]) == "Test Title"
        assert stage._get_tag(audio, ["artist"]) == "Artist Name"
        assert stage._get_tag(audio, ["nonexistent"]) is None
        # Fallback keys
        assert stage._get_tag(audio, ["missing", "title"]) == "Test Title"

    def test_get_raw_tag_helper_text_attribute(self):
        """_get_raw_tag handles ID3 frames with text attribute."""
        stage = IngestStage()

        class MockFrame:
            text = ["Frame Value"]

        class MockAudio:
            def get(self, key):
                return {"TCOM": MockFrame()}.get(key)

        audio = MockAudio()
        assert stage._get_raw_tag(audio, ["TCOM"]) == "Frame Value"

    def test_get_raw_tag_helper_data_attribute(self):
        """_get_raw_tag handles UFID frames with data attribute."""
        stage = IngestStage()

        class MockUFID:
            data = b"abc123-uuid"

        class MockAudio:
            def get(self, key):
                return {"UFID:http://musicbrainz.org": MockUFID()}.get(key)

        audio = MockAudio()
        assert stage._get_raw_tag(audio, ["UFID:http://musicbrainz.org"]) == "abc123-uuid"

    def test_get_raw_tag_helper_list_value(self):
        """_get_raw_tag handles list values (Vorbis comments)."""
        stage = IngestStage()

        class MockAudio:
            def get(self, key):
                return {"MUSICBRAINZ_ALBUMID": ["album-uuid-123"]}.get(key)

        audio = MockAudio()
        assert stage._get_raw_tag(audio, ["MUSICBRAINZ_ALBUMID"]) == "album-uuid-123"

    def test_musicbrainz_tag_keys(self):
        """IngestStage attempts all known MusicBrainz tag formats."""
        stage = IngestStage()

        # Check that the method exists and attempts multiple key formats
        # This is a basic check; integration tests verify actual extraction
        mb_tag_prefixes = [
            "TXXX:MusicBrainz",  # ID3
            "musicbrainz_",     # Vorbis lowercase
            "MUSICBRAINZ_",     # Vorbis uppercase
            "----:com.apple.iTunes:",  # MP4
        ]

        # Verify method handles missing tags gracefully
        class EmptyAudio:
            def get(self, key):
                return None

        context = ProcessingContext(
            source_path=Path("/tmp/test.mp3"),
            temp_dir=Path("/tmp"),
            output_dir=Path("/tmp"),
        )

        # Should not raise
        stage._extract_musicbrainz_tags(EmptyAudio(), context)
        # No tags extracted
        assert "musicbrainz_trackid" not in context.metadata

    def test_extended_tag_keys(self):
        """IngestStage extracts extended tags like composer, ISRC, etc."""
        stage = IngestStage()

        class MockAudio:
            def __init__(self):
                self.tags = {
                    "TCOM": type("Frame", (), {"text": ["John Composer"]})(),
                    "TSRC": type("Frame", (), {"text": ["USRC12345678"]})(),
                    "TBPM": type("Frame", (), {"text": ["120"]})(),
                }

            def get(self, key):
                return self.tags.get(key)

        context = ProcessingContext(
            source_path=Path("/tmp/test.mp3"),
            temp_dir=Path("/tmp"),
            output_dir=Path("/tmp"),
        )

        stage._extract_extended_tags(MockAudio(), context)

        assert context.metadata.get("composer") == "John Composer"
        assert context.metadata.get("isrc") == "USRC12345678"
        assert context.metadata.get("bpm") == "120"
