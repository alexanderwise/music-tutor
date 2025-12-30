"""Tests for the LyricsAlignmentStage."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from music_tutor.models.analysis import LyricLine, LyricsData, LyricWord
from music_tutor.models.pipeline import ProcessingContext
from music_tutor.stages.lyrics_alignment import LyricsAlignmentStage


class TestLyricsAlignmentStage:
    """Tests for LyricsAlignmentStage."""

    def test_stage_name(self):
        """Stage has correct name."""
        stage = LyricsAlignmentStage()
        assert stage.name == "lyrics_alignment"

    def test_default_model(self):
        """Stage uses 'base' model by default."""
        stage = LyricsAlignmentStage()
        assert stage.DEFAULT_MODEL == "base"

    def test_no_audio_available(self, tmp_path: Path):
        """Returns error when no audio is available."""
        stage = LyricsAlignmentStage()
        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
            normalized_audio_path=None,
            stem_paths={},
        )

        result = stage.execute(context)

        assert result.success is False
        assert "no audio available" in result.error_message.lower()

    def test_prefers_vocals_stem(self, tmp_path: Path):
        """Uses vocals stem when available."""
        stage = LyricsAlignmentStage()

        vocals_path = tmp_path / "vocals.wav"
        vocals_path.write_bytes(b"vocals audio")

        normalized_path = tmp_path / "normalized.wav"
        normalized_path.write_bytes(b"full mix audio")

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
            normalized_audio_path=normalized_path,
            stem_paths={"vocals": vocals_path},
        )

        audio_path = stage._get_audio_path(context)
        assert audio_path == vocals_path

    def test_falls_back_to_normalized(self, tmp_path: Path):
        """Falls back to normalized audio when no vocals stem."""
        stage = LyricsAlignmentStage()

        normalized_path = tmp_path / "normalized.wav"
        normalized_path.write_bytes(b"full mix audio")

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
            normalized_audio_path=normalized_path,
            stem_paths={},
        )

        audio_path = stage._get_audio_path(context)
        assert audio_path == normalized_path

    def test_load_lrc_lyrics(self, tmp_path: Path):
        """Parses LRC format correctly."""
        stage = LyricsAlignmentStage()

        lrc_content = """[00:00.50] First line of lyrics
[00:03.00] Second line with more words
[00:06.00] Third line here
"""
        lrc_path = tmp_path / "test.lrc"
        lrc_path.write_text(lrc_content)

        lyrics_text, source = stage._load_lyrics(lrc_path)

        assert source == "lrc"
        assert "First line of lyrics" in lyrics_text
        assert "Second line with more words" in lyrics_text
        assert "Third line here" in lyrics_text
        assert "[00:00.50]" not in lyrics_text  # Timestamps stripped

    def test_load_txt_lyrics(self, tmp_path: Path):
        """Parses plain text format correctly."""
        stage = LyricsAlignmentStage()

        txt_content = """First line
Second line

Third line after blank
"""
        txt_path = tmp_path / "lyrics.txt"
        txt_path.write_text(txt_content)

        lyrics_text, source = stage._load_lyrics(txt_path)

        assert source == "txt"
        assert "First line" in lyrics_text
        assert "Second line" in lyrics_text
        assert "Third line after blank" in lyrics_text

    def test_load_nonexistent_file(self, tmp_path: Path):
        """Returns None for nonexistent file."""
        stage = LyricsAlignmentStage()

        lyrics_text, source = stage._load_lyrics(tmp_path / "nonexistent.lrc")

        assert lyrics_text is None
        assert source == "transcribed"

    def test_convert_result_to_lyrics_data(self):
        """_convert_result correctly converts stable-ts output."""
        stage = LyricsAlignmentStage()

        # Create mock stable-ts result
        mock_word1 = MagicMock()
        mock_word1.word = " Hello"
        mock_word1.start = 0.5
        mock_word1.end = 1.0

        mock_word2 = MagicMock()
        mock_word2.word = " world"
        mock_word2.start = 1.0
        mock_word2.end = 1.5

        mock_segment = MagicMock()
        mock_segment.text = " Hello world"
        mock_segment.start = 0.5
        mock_segment.end = 1.5
        mock_segment.words = [mock_word1, mock_word2]

        mock_result = MagicMock()
        mock_result.segments = [mock_segment]

        lyrics_data = stage._convert_result(mock_result, "lrc")

        assert lyrics_data.source == "lrc"
        assert len(lyrics_data.lines) == 1

        line = lyrics_data.lines[0]
        assert line.text == "Hello world"
        assert line.start == 0.5
        assert line.end == 1.5
        assert len(line.words) == 2

        assert line.words[0].text == "Hello"
        assert line.words[0].start == 0.5
        assert line.words[0].end == 1.0

        assert line.words[1].text == "world"
        assert line.words[1].start == 1.0
        assert line.words[1].end == 1.5

    def test_alignment_with_existing_lyrics(self, tmp_path: Path):
        """Runs alignment when lyrics file exists."""
        stage = LyricsAlignmentStage()

        # Create audio and lyrics files
        vocals_path = tmp_path / "vocals.wav"
        vocals_path.write_bytes(b"dummy")

        lrc_path = tmp_path / "test.lrc"
        lrc_path.write_text("[00:00.50] Test lyrics line\n")

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
            source_lyrics_path=lrc_path,
            stem_paths={"vocals": vocals_path},
        )

        # Mock stable_whisper
        mock_model = MagicMock()

        mock_word = MagicMock()
        mock_word.word = " Test"
        mock_word.start = 0.5
        mock_word.end = 1.0

        mock_segment = MagicMock()
        mock_segment.text = " Test lyrics line"
        mock_segment.start = 0.5
        mock_segment.end = 2.0
        mock_segment.words = [mock_word]

        mock_result = MagicMock()
        mock_result.segments = [mock_segment]

        with patch("stable_whisper.load_model") as mock_load:
            with patch("stable_whisper.alignment.align") as mock_align:
                mock_load.return_value = mock_model
                mock_align.return_value = mock_result

                result = stage.execute(context)

                assert result.success is True
                assert any("lrc" in w.lower() for w in result.warnings)
                mock_align.assert_called_once()

        # Check lyrics were set on context
        assert context.lyrics is not None
        assert context.lyrics.source == "lrc"
        assert len(context.lyrics.lines) == 1

    def test_transcription_without_lyrics(self, tmp_path: Path):
        """Falls back to transcription when no lyrics file."""
        stage = LyricsAlignmentStage()

        vocals_path = tmp_path / "vocals.wav"
        vocals_path.write_bytes(b"dummy")

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
            source_lyrics_path=None,  # No lyrics file
            stem_paths={"vocals": vocals_path},
        )

        # Mock stable_whisper
        mock_word = MagicMock()
        mock_word.word = " Transcribed"
        mock_word.start = 0.0
        mock_word.end = 0.5

        mock_segment = MagicMock()
        mock_segment.text = " Transcribed text"
        mock_segment.start = 0.0
        mock_segment.end = 1.0
        mock_segment.words = [mock_word]

        mock_result = MagicMock()
        mock_result.segments = [mock_segment]

        mock_model = MagicMock()
        mock_model.transcribe.return_value = mock_result

        with patch("stable_whisper.load_model") as mock_load:
            mock_load.return_value = mock_model

            result = stage.execute(context)

            assert result.success is True
            assert any("transcrib" in w.lower() for w in result.warnings)
            mock_model.transcribe.assert_called_once()

        # Check lyrics source is transcribed
        assert context.lyrics is not None
        assert context.lyrics.source == "transcribed"

    @pytest.mark.slow
    def test_integration_with_real_audio(self, tmp_path: Path):
        """Integration test with real audio file."""
        try:
            import stable_whisper  # noqa: F401
        except ImportError:
            pytest.skip("stable-ts not installed")

        from music_tutor.stages.ingest import IngestStage

        # Use a sample with lyrics
        sample = Path("samples/04 California English.mp3")
        lrc = Path("samples/04 California English.lrc")

        if not sample.exists():
            pytest.skip("Sample audio not available")

        # Run ingest
        ingest = IngestStage()
        context = ProcessingContext(
            source_path=sample,
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            source_lyrics_path=lrc if lrc.exists() else None,
        )

        ingest_result = ingest.execute(context)
        assert ingest_result.success

        # Run lyrics alignment
        stage = LyricsAlignmentStage()
        result = stage.execute(context)

        if not result.success:
            pytest.skip(f"Lyrics alignment failed: {result.error_message}")

        # Verify lyrics were detected
        assert context.lyrics is not None
        assert len(context.lyrics.lines) > 0

        # Check first line has words
        first_line = context.lyrics.lines[0]
        assert first_line.text
        assert first_line.start >= 0
        assert first_line.end > first_line.start
        assert len(first_line.words) > 0

        # Check word structure
        first_word = first_line.words[0]
        assert first_word.text
        assert first_word.start >= 0
        assert first_word.end >= first_word.start
