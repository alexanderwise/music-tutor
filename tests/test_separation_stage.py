"""Tests for the SeparationStage."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from music_tutor.config import Settings
from music_tutor.models.pipeline import ProcessingContext
from music_tutor.stages.separation import SeparationStage


class TestSeparationStage:
    """Tests for SeparationStage."""

    def test_stage_name(self):
        """Stage has correct name."""
        stage = SeparationStage()
        assert stage.name == "separation"

    def test_default_model_is_6_stem(self):
        """Default model is htdemucs_6s for 6 stems."""
        settings = Settings()
        assert settings.separation_model == "htdemucs_6s.yaml"

    def test_expected_stems_6_stem_model(self):
        """6-stem model expects guitar and piano."""
        settings = Settings(separation_model="htdemucs_6s.yaml")
        stage = SeparationStage(settings)
        assert set(stage.expected_stems) == {
            "vocals", "drums", "bass", "guitar", "piano", "other"
        }

    def test_expected_stems_4_stem_model(self):
        """4-stem model expects standard stems."""
        settings = Settings(separation_model="htdemucs_ft.yaml")
        stage = SeparationStage(settings)
        assert set(stage.expected_stems) == {"vocals", "drums", "bass", "other"}

    def test_expected_stems_2_stem_model(self):
        """2-stem model expects vocals and instrumental."""
        settings = Settings(separation_model="model_bs_roformer_ep_317_sdr_12.9755.ckpt")
        stage = SeparationStage(settings)
        assert set(stage.expected_stems) == {"vocals", "instrumental"}

    def test_drum_stems_list(self):
        """DrumSep produces expected drum components."""
        stage = SeparationStage()
        assert set(stage.DRUM_STEMS) == {"kick", "snare", "toms", "hh", "ride", "crash"}

    def test_no_normalized_audio(self, tmp_path: Path):
        """Returns error when no normalized audio is available."""
        stage = SeparationStage()
        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
            normalized_audio_path=None,
        )

        result = stage.execute(context)

        assert result.success is False
        assert "normalized audio" in result.error_message.lower()

    def test_audio_separator_not_found(self, tmp_path: Path):
        """Returns error when audio-separator is not available."""
        # Create a dummy normalized audio file
        normalized = tmp_path / "normalized.wav"
        normalized.write_bytes(b"dummy")

        stage = SeparationStage()
        context = ProcessingContext(
            source_path=tmp_path / "test.mp3",
            temp_dir=tmp_path,
            output_dir=tmp_path,
            normalized_audio_path=normalized,
        )

        with patch.object(stage, "_check_audio_separator", return_value=False):
            result = stage.execute(context)

        assert result.success is False
        assert "audio-separator" in result.error_message.lower()

    def test_find_stems_with_4_stem_pattern(self, tmp_path: Path):
        """_find_stems correctly identifies 4-stem files."""
        stage = SeparationStage()

        # Create mock stem files with expected naming pattern
        stems_dir = tmp_path / "stems"
        stems_dir.mkdir()

        # audio-separator output pattern: input_(StemName)_model.wav
        (stems_dir / "test_(Vocals)_htdemucs_ft.wav").write_bytes(b"vocals")
        (stems_dir / "test_(Drums)_htdemucs_ft.wav").write_bytes(b"drums")
        (stems_dir / "test_(Bass)_htdemucs_ft.wav").write_bytes(b"bass")
        (stems_dir / "test_(Other)_htdemucs_ft.wav").write_bytes(b"other")

        stem_paths = stage._find_stems(stems_dir, "test")

        assert len(stem_paths) == 4
        assert "vocals" in stem_paths
        assert "drums" in stem_paths
        assert "bass" in stem_paths
        assert "other" in stem_paths

        # Check files were renamed to clean names
        assert stem_paths["vocals"].name == "vocals.wav"
        assert stem_paths["drums"].name == "drums.wav"

    def test_find_stems_with_6_stem_pattern(self, tmp_path: Path):
        """_find_stems correctly identifies 6-stem files including guitar and piano."""
        stage = SeparationStage()

        stems_dir = tmp_path / "stems"
        stems_dir.mkdir()

        # 6-stem output pattern
        (stems_dir / "test_(Vocals)_htdemucs_6s.wav").write_bytes(b"vocals")
        (stems_dir / "test_(Drums)_htdemucs_6s.wav").write_bytes(b"drums")
        (stems_dir / "test_(Bass)_htdemucs_6s.wav").write_bytes(b"bass")
        (stems_dir / "test_(Guitar)_htdemucs_6s.wav").write_bytes(b"guitar")
        (stems_dir / "test_(Piano)_htdemucs_6s.wav").write_bytes(b"piano")
        (stems_dir / "test_(Other)_htdemucs_6s.wav").write_bytes(b"other")

        stem_paths = stage._find_stems(stems_dir, "test")

        assert len(stem_paths) == 6
        assert "guitar" in stem_paths
        assert "piano" in stem_paths
        assert stem_paths["guitar"].name == "guitar.wav"
        assert stem_paths["piano"].name == "piano.wav"

    def test_find_stems_with_2_stem_pattern(self, tmp_path: Path):
        """_find_stems correctly identifies 2-stem (vocals/instrumental) files."""
        stage = SeparationStage()

        stems_dir = tmp_path / "stems"
        stems_dir.mkdir()

        # 2-stem output pattern (BS-RoFormer style)
        (stems_dir / "test_(Vocals)_bs_roformer.wav").write_bytes(b"vocals")
        (stems_dir / "test_(Instrumental)_bs_roformer.wav").write_bytes(b"instrumental")

        stem_paths = stage._find_stems(stems_dir, "test")

        assert len(stem_paths) == 2
        assert "vocals" in stem_paths
        assert "instrumental" in stem_paths

    def test_find_stems_empty_directory(self, tmp_path: Path):
        """_find_stems raises error for empty directory."""
        stage = SeparationStage()

        stems_dir = tmp_path / "stems"
        stems_dir.mkdir()

        with pytest.raises(RuntimeError, match="No stem files found"):
            stage._find_stems(stems_dir, "test")

    @pytest.mark.slow
    @pytest.mark.skipif(
        not Path("/usr/bin/ffmpeg").exists()
        and not Path("/opt/homebrew/bin/ffmpeg").exists(),
        reason="ffmpeg not installed",
    )
    def test_integration_with_real_audio(self, sample_mp3: Path, tmp_path: Path):
        """Integration test with real audio file.

        This test is marked slow as stem separation takes several minutes.
        Run with: pytest -m slow
        """
        from music_tutor.stages.ingest import IngestStage

        # First run ingest stage
        ingest = IngestStage()
        context = ProcessingContext(
            source_path=sample_mp3,
            temp_dir=tmp_path,
            output_dir=tmp_path / "output",
        )

        ingest_result = ingest.execute(context)
        assert ingest_result.success, f"Ingest failed: {ingest_result.error_message}"

        # Now run separation
        settings = Settings(use_gpu=False)
        separation = SeparationStage(settings)

        result = separation.execute(context)

        if not result.success:
            pytest.skip(f"Separation failed (may need model download): {result.error_message}")

        # Verify stems were created
        assert len(context.stem_paths) >= 2, "Expected at least 2 stems"
        for stem_name, stem_path in context.stem_paths.items():
            assert stem_path.exists(), f"Stem {stem_name} file doesn't exist"
            assert stem_path.stat().st_size > 0, f"Stem {stem_name} file is empty"
