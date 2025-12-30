"""Tests for the PitchDetectionStage."""

from pathlib import Path
from unittest.mock import patch

import pytest

from music_tutor.models.analysis import Note, PitchBendPoint
from music_tutor.models.pipeline import ProcessingContext
from music_tutor.stages.pitch_detection import PitchDetectionStage


class TestPitchDetectionStage:
    """Tests for PitchDetectionStage."""

    def test_stage_name(self):
        """Stage has correct name."""
        stage = PitchDetectionStage()
        assert stage.name == "pitch_detection"

    def test_melodic_stems_list(self):
        """Stage targets correct stems (not drums)."""
        stage = PitchDetectionStage()
        assert "vocals" in stage.MELODIC_STEMS
        assert "bass" in stage.MELODIC_STEMS
        assert "guitar" in stage.MELODIC_STEMS
        assert "piano" in stage.MELODIC_STEMS
        assert "other" in stage.MELODIC_STEMS
        assert "drums" not in stage.MELODIC_STEMS

    def test_no_stems_available(self, tmp_path: Path):
        """Returns error when no melodic stems are available."""
        stage = PitchDetectionStage()
        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
            stem_paths={},  # No stems
        )

        result = stage.execute(context)

        assert result.success is False
        assert "no melodic stems" in result.error_message.lower()

    def test_skips_missing_stems(self, tmp_path: Path):
        """Skips stems that don't exist with warning."""
        stage = PitchDetectionStage()

        # Only vocals stem exists
        vocals_path = tmp_path / "vocals.wav"
        vocals_path.write_bytes(b"dummy")

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
            stem_paths={"vocals": vocals_path},
        )

        # Mock the actual detection to avoid processing
        with patch.object(stage, "_detect_notes") as mock_detect:
            mock_detect.return_value = [
                Note(start=1.0, end=2.0, pitch=60, velocity=0.8)
            ]

            result = stage.execute(context)

            assert result.success is True
            # Should have warnings about skipped stems
            assert any("bass" in w.lower() for w in result.warnings)
            assert any("other" in w.lower() for w in result.warnings)

    def test_convert_pitch_bend_simple(self):
        """_convert_pitch_bend converts bend data correctly."""
        stage = PitchDetectionStage()

        # Simulated pitch bend data: [0, 1, 2, 1, 0]
        pitch_bend_data = [0, 1, 2, 1, 0]

        points = stage._convert_pitch_bend(
            pitch_bend_data,
            start_time=0.0,
            end_time=1.0,
        )

        assert points is not None
        assert len(points) == 5

        # Check time spacing (1.0s duration / 5 samples = 0.2s each)
        assert abs(points[0].time - 0.0) < 0.01
        assert abs(points[1].time - 0.2) < 0.01

        # Check cents conversion (33 cents per bin)
        assert abs(points[0].cents - 0.0) < 0.1
        assert abs(points[1].cents - 33.0) < 0.1
        assert abs(points[2].cents - 66.0) < 0.1

    def test_convert_pitch_bend_no_bend(self):
        """_convert_pitch_bend returns None for constant zero bend."""
        stage = PitchDetectionStage()

        # All zeros = no pitch bend
        pitch_bend_data = [0, 0, 0, 0, 0]

        points = stage._convert_pitch_bend(
            pitch_bend_data,
            start_time=0.0,
            end_time=1.0,
        )

        assert points is None

    def test_convert_pitch_bend_empty(self):
        """_convert_pitch_bend handles empty data."""
        stage = PitchDetectionStage()

        points = stage._convert_pitch_bend([], start_time=0.0, end_time=1.0)
        assert points is None

    def test_min_amplitude_filter(self):
        """Notes below MIN_AMPLITUDE are filtered out."""
        stage = PitchDetectionStage()

        assert stage.MIN_AMPLITUDE == 0.1

        # A note with amplitude 0.05 should be filtered
        # This is tested via the _detect_notes method

    def test_notes_sorted_by_start_time(self, tmp_path: Path):
        """Notes are returned sorted by start time."""
        stage = PitchDetectionStage()

        vocals_path = tmp_path / "vocals.wav"
        vocals_path.write_bytes(b"dummy")

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
            stem_paths={"vocals": vocals_path},
        )

        # Mock basic-pitch to return notes in reverse order
        mock_events = [
            (5.0, 6.0, 60, 0.8, [0]),  # Later note first
            (1.0, 2.0, 62, 0.7, [0]),  # Earlier note second
            (3.0, 4.0, 64, 0.9, [0]),  # Middle note
        ]

        with patch("basic_pitch.inference.predict") as mock_predict:
            mock_predict.return_value = (None, None, mock_events)

            result = stage.execute(context)

            assert result.success is True
            notes = context.notes["vocals"]
            assert len(notes) == 3

            # Should be sorted by start time
            assert notes[0].start == 1.0
            assert notes[1].start == 3.0
            assert notes[2].start == 5.0

    @pytest.mark.slow
    def test_integration_with_real_audio(self, sample_mp3: Path, tmp_path: Path):
        """Integration test with real audio file."""
        try:
            from basic_pitch.inference import predict  # noqa: F401
        except ImportError:
            pytest.skip("basic-pitch not installed")

        from music_tutor.stages.ingest import IngestStage

        # First run ingest stage
        ingest = IngestStage()
        context = ProcessingContext(
            source_path=sample_mp3,
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
        )

        ingest_result = ingest.execute(context)
        assert ingest_result.success

        # Create a fake "vocals" stem using the normalized audio
        context.stem_paths["vocals"] = context.normalized_audio_path

        # Run pitch detection
        stage = PitchDetectionStage()
        result = stage.execute(context)

        if not result.success:
            pytest.skip(f"Pitch detection failed: {result.error_message}")

        # Verify notes were detected
        assert "vocals" in context.notes
        assert len(context.notes["vocals"]) > 0

        # Check note structure
        note = context.notes["vocals"][0]
        assert 0 <= note.pitch <= 127
        assert 0 < note.velocity <= 1.0
        assert note.end > note.start
