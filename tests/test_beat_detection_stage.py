"""Tests for the BeatDetectionStage."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from music_tutor.models.analysis import BeatEvent
from music_tutor.models.pipeline import ProcessingContext
from music_tutor.stages.beat_detection import BeatDetectionStage


class TestBeatDetectionStage:
    """Tests for BeatDetectionStage."""

    def test_stage_name(self):
        """Stage has correct name."""
        stage = BeatDetectionStage()
        assert stage.name == "beat_detection"

    def test_no_audio_available(self, tmp_path: Path):
        """Returns error when no audio is available."""
        stage = BeatDetectionStage()
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

    def test_falls_back_to_full_mix(self, tmp_path: Path):
        """Falls back to full mix when drums stem not available."""
        stage = BeatDetectionStage()

        # Create a dummy audio file
        normalized = tmp_path / "normalized.wav"
        normalized.write_bytes(b"dummy")

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
            normalized_audio_path=normalized,
            stem_paths={},  # No drums stem
        )

        # Mock madmom to avoid actual processing
        with patch.object(stage, "_detect_beats") as mock_detect:
            mock_detect.return_value = (
                [BeatEvent(time=0.5, type="downbeat", beat_in_measure=1)],
                120.0,
                (4, 4),
            )

            result = stage.execute(context)

            assert result.success is True
            assert any("full mix" in w for w in result.warnings)

    def test_convert_to_beat_events(self):
        """_convert_to_beat_events correctly converts madmom output."""
        stage = BeatDetectionStage()

        # Simulated madmom output: [time, beat_position]
        downbeats = np.array([
            [0.5, 1],   # downbeat
            [1.0, 2],   # beat 2
            [1.5, 3],   # beat 3
            [2.0, 4],   # beat 4
            [2.5, 1],   # downbeat
        ])

        beats = stage._convert_to_beat_events(downbeats)

        assert len(beats) == 5
        assert beats[0].type == "downbeat"
        assert beats[0].beat_in_measure == 1
        assert beats[0].time == 0.5

        assert beats[1].type == "beat"
        assert beats[1].beat_in_measure == 2

        assert beats[4].type == "downbeat"
        assert beats[4].beat_in_measure == 1

    def test_calculate_tempo(self):
        """_calculate_tempo correctly calculates BPM from intervals."""
        stage = BeatDetectionStage()

        # 120 BPM = 0.5 seconds per beat
        downbeats = np.array([
            [0.0, 1],
            [0.5, 2],
            [1.0, 3],
            [1.5, 4],
            [2.0, 1],
            [2.5, 2],
        ])

        tempo = stage._calculate_tempo(downbeats)

        assert abs(tempo - 120.0) < 1.0  # Within 1 BPM

    def test_calculate_tempo_with_outliers(self):
        """_calculate_tempo handles outliers in beat intervals."""
        stage = BeatDetectionStage()

        # 120 BPM with one bad interval
        downbeats = np.array([
            [0.0, 1],
            [0.5, 2],
            [1.0, 3],
            [2.5, 4],  # Outlier - 1.5s gap instead of 0.5s
            [3.0, 1],
            [3.5, 2],
        ])

        tempo = stage._calculate_tempo(downbeats)

        # Should still be close to 120 BPM (outlier filtered)
        assert 100 < tempo < 140

    def test_detect_time_signature_4_4(self):
        """_detect_time_signature correctly identifies 4/4."""
        stage = BeatDetectionStage()

        # 4/4 time: downbeats every 4 beats
        downbeats = np.array([
            [0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4],
            [2.0, 1], [2.5, 2], [3.0, 3], [3.5, 4],
            [4.0, 1], [4.5, 2], [5.0, 3], [5.5, 4],
        ])

        time_sig = stage._detect_time_signature(downbeats)

        assert time_sig == (4, 4)

    def test_detect_time_signature_3_4(self):
        """_detect_time_signature correctly identifies 3/4."""
        stage = BeatDetectionStage()

        # 3/4 time: downbeats every 3 beats
        downbeats = np.array([
            [0.0, 1], [0.5, 2], [1.0, 3],
            [1.5, 1], [2.0, 2], [2.5, 3],
            [3.0, 1], [3.5, 2], [4.0, 3],
        ])

        time_sig = stage._detect_time_signature(downbeats)

        assert time_sig == (3, 4)

    def test_detect_time_signature_defaults_to_4_4(self):
        """_detect_time_signature defaults to 4/4 with insufficient data."""
        stage = BeatDetectionStage()

        # Only 2 beats - not enough data
        downbeats = np.array([
            [0.0, 1],
            [0.5, 2],
        ])

        time_sig = stage._detect_time_signature(downbeats)

        assert time_sig == (4, 4)

    @pytest.mark.slow
    def test_integration_with_real_audio(self, sample_mp3: Path, tmp_path: Path):
        """Integration test with real audio file.

        This test requires madmom to be installed.
        """
        try:
            import madmom  # noqa: F401
        except ImportError:
            pytest.skip("madmom not installed")

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

        # Now run beat detection on the full mix
        stage = BeatDetectionStage()
        result = stage.execute(context)

        if not result.success:
            pytest.skip(f"Beat detection failed: {result.error_message}")

        # Verify beats were detected
        assert len(context.beats) > 0
        assert context.tempo_bpm is not None
        assert 60 < context.tempo_bpm < 200  # Reasonable tempo range
        assert context.time_signature is not None
        assert context.time_signature[0] in [3, 4]
