"""Tests for the TimeStretchStage."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from music_tutor.models.pipeline import ProcessingContext
from music_tutor.stages.time_stretch import TimeStretchStage


class TestTimeStretchStage:
    """Tests for TimeStretchStage."""

    def test_stage_name(self):
        """Stage has correct name."""
        stage = TimeStretchStage()
        assert stage.name == "time_stretch"

    def test_default_speeds(self):
        """Stage has expected default speeds."""
        stage = TimeStretchStage()
        assert stage.SPEEDS == [0.5, 0.75, 1.0, 1.25]

    def test_no_stems_available(self, tmp_path: Path):
        """Returns error when no stems are available."""
        stage = TimeStretchStage()
        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            stem_paths={},
        )

        result = stage.execute(context)

        assert result.success is False
        assert "no stems" in result.error_message.lower()

    def test_skips_missing_stem_files(self, tmp_path: Path):
        """Skips stems where file doesn't exist."""
        stage = TimeStretchStage()

        # Create one real stem, reference one that doesn't exist
        vocals_path = tmp_path / "vocals.wav"
        sample_rate = 44100
        duration = 1.0  # 1 second
        y = np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sample_rate * duration)))
        sf.write(vocals_path, y, sample_rate)

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            stem_paths={
                "vocals": vocals_path,
                "drums": tmp_path / "drums_nonexistent.wav",
            },
        )

        result = stage.execute(context)

        assert result.success is True
        assert any("drums" in w.lower() and "not found" in w.lower() for w in result.warnings)
        assert "vocals" in context.stretched_stems
        assert "drums" not in context.stretched_stems

    def test_creates_all_speeds(self, tmp_path: Path):
        """Creates time-stretched versions at all speeds."""
        stage = TimeStretchStage()

        # Create test audio
        vocals_path = tmp_path / "vocals.wav"
        sample_rate = 44100
        duration = 1.0
        y = np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sample_rate * duration)))
        sf.write(vocals_path, y, sample_rate)

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            stem_paths={"vocals": vocals_path},
        )

        result = stage.execute(context)

        assert result.success is True
        assert "vocals" in context.stretched_stems

        speeds = context.stretched_stems["vocals"]
        assert "0.5x" in speeds
        assert "0.75x" in speeds
        assert "1.0x" in speeds
        assert "1.25x" in speeds

        # Check all files exist
        for speed_key, path in speeds.items():
            assert path.exists(), f"Missing output for {speed_key}"

    def test_output_file_format(self, tmp_path: Path):
        """Output files are FLAC format."""
        stage = TimeStretchStage()

        vocals_path = tmp_path / "vocals.wav"
        sample_rate = 44100
        duration = 0.5
        y = np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sample_rate * duration)))
        sf.write(vocals_path, y, sample_rate)

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            stem_paths={"vocals": vocals_path},
        )

        stage.execute(context)

        for path in context.stretched_stems["vocals"].values():
            assert path.suffix == ".flac"

    def test_output_file_naming(self, tmp_path: Path):
        """Output files follow naming convention."""
        stage = TimeStretchStage()

        vocals_path = tmp_path / "vocals.wav"
        sample_rate = 44100
        duration = 0.5
        y = np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sample_rate * duration)))
        sf.write(vocals_path, y, sample_rate)

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            stem_paths={"vocals": vocals_path},
        )

        stage.execute(context)

        speeds = context.stretched_stems["vocals"]
        assert speeds["0.5x"].name == "vocals_0.5x.flac"
        assert speeds["0.75x"].name == "vocals_0.75x.flac"
        assert speeds["1.0x"].name == "vocals_1.0x.flac"
        assert speeds["1.25x"].name == "vocals_1.25x.flac"

    def test_stretched_duration_half_speed(self, tmp_path: Path):
        """0.5x speed audio is approximately 2x the duration."""
        stage = TimeStretchStage()

        vocals_path = tmp_path / "vocals.wav"
        sample_rate = 44100
        original_duration = 2.0  # 2 seconds
        samples = int(sample_rate * original_duration)
        y = np.sin(2 * np.pi * 440 * np.linspace(0, original_duration, samples))
        sf.write(vocals_path, y, sample_rate)

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            stem_paths={"vocals": vocals_path},
        )

        stage.execute(context)

        # Read stretched audio
        stretched_path = context.stretched_stems["vocals"]["0.5x"]
        y_stretched, sr = sf.read(stretched_path)

        # Duration should be approximately 2x (some tolerance for rubberband)
        stretched_duration = len(y_stretched) / sr
        expected_duration = original_duration / 0.5  # 4 seconds

        assert abs(stretched_duration - expected_duration) < 0.1  # Within 100ms

    def test_original_speed_no_stretch(self, tmp_path: Path):
        """1.0x speed is just a copy (same duration)."""
        stage = TimeStretchStage()

        vocals_path = tmp_path / "vocals.wav"
        sample_rate = 44100
        original_duration = 1.0
        samples = int(sample_rate * original_duration)
        y = np.sin(2 * np.pi * 440 * np.linspace(0, original_duration, samples))
        sf.write(vocals_path, y, sample_rate)

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            stem_paths={"vocals": vocals_path},
        )

        stage.execute(context)

        # Read 1.0x version
        original_path = context.stretched_stems["vocals"]["1.0x"]
        y_copy, sr = sf.read(original_path)

        # Should be same duration
        copy_duration = len(y_copy) / sr
        assert abs(copy_duration - original_duration) < 0.01

    def test_multiple_stems(self, tmp_path: Path):
        """Processes multiple stems correctly."""
        stage = TimeStretchStage()

        sample_rate = 44100
        duration = 0.5

        # Create multiple stem files
        for stem_name in ["vocals", "drums", "bass"]:
            path = tmp_path / f"{stem_name}.wav"
            y = np.sin(2 * np.pi * 440 * np.linspace(0, duration, int(sample_rate * duration)))
            sf.write(path, y, sample_rate)

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            stem_paths={
                "vocals": tmp_path / "vocals.wav",
                "drums": tmp_path / "drums.wav",
                "bass": tmp_path / "bass.wav",
            },
        )

        result = stage.execute(context)

        assert result.success is True
        assert len(context.stretched_stems) == 3
        assert "vocals" in context.stretched_stems
        assert "drums" in context.stretched_stems
        assert "bass" in context.stretched_stems

        # Each stem should have all speeds
        for stem_speeds in context.stretched_stems.values():
            assert len(stem_speeds) == 4

    def test_calculate_stretched_duration(self):
        """_calculate_stretched_duration works correctly."""
        stage = TimeStretchStage()

        # Half speed = double duration
        assert stage._calculate_stretched_duration(10.0, 0.5) == 20.0

        # Original speed = same duration
        assert stage._calculate_stretched_duration(10.0, 1.0) == 10.0

        # 1.25x speed = shorter duration
        assert stage._calculate_stretched_duration(10.0, 1.25) == 8.0

    @pytest.mark.slow
    def test_integration_stereo_audio(self, tmp_path: Path):
        """Works with stereo audio files."""
        stage = TimeStretchStage()

        # Create stereo audio
        vocals_path = tmp_path / "vocals.wav"
        sample_rate = 44100
        duration = 1.0
        samples = int(sample_rate * duration)
        t = np.linspace(0, duration, samples)
        left = np.sin(2 * np.pi * 440 * t)
        right = np.sin(2 * np.pi * 880 * t)
        stereo = np.column_stack([left, right])
        sf.write(vocals_path, stereo, sample_rate)

        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
            stem_paths={"vocals": vocals_path},
        )

        result = stage.execute(context)

        assert result.success is True

        # Check output is still stereo
        for path in context.stretched_stems["vocals"].values():
            y, sr = sf.read(path)
            assert y.ndim == 2, "Output should be stereo"
            assert y.shape[1] == 2, "Output should have 2 channels"
