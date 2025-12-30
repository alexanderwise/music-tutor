"""Separation stage - separates audio into stems using audio-separator."""

import re
import shutil
from pathlib import Path

from music_tutor.config import Settings, get_settings
from music_tutor.models.pipeline import ProcessingContext, StageResult
from music_tutor.pipeline.base import PipelineStage


def _disable_mps_if_needed() -> None:
    """Disable MPS (Apple Silicon GPU) for Demucs models.

    The htdemucs model doesn't work with MPS due to channel count limits.
    This must be called before importing audio_separator.
    """
    import torch

    # Patch MPS availability to force CPU mode
    torch.backends.mps.is_available = lambda: False
    torch.backends.mps.is_built = lambda: False


class SeparationStage(PipelineStage):
    """Stage 2: Stem Separation.

    Uses audio-separator to separate audio into stems. Supports multiple models:

    - htdemucs_6s.yaml (default): 6 stems - vocals, drums, bass, guitar, piano, other
    - htdemucs_ft.yaml: 4 stems - vocals, drums, bass, other (highest quality)
    - BS-RoFormer models: 2 stems - vocals, instrumental (best vocal isolation)

    Optionally runs DrumSep to further separate drums into:
    kick, snare, toms, hi-hat, ride, crash
    """

    # Stem names by model type
    STEMS_4 = ["vocals", "drums", "bass", "other"]
    STEMS_6 = ["vocals", "drums", "bass", "guitar", "piano", "other"]
    STEMS_2 = ["vocals", "instrumental"]
    DRUM_STEMS = ["kick", "snare", "toms", "hh", "ride", "crash"]

    # Model for drum separation
    DRUMSEP_MODEL = "MDX23C-DrumSep-aufr33-jarredou.ckpt"

    # Model configurations
    MODEL_INFO = {
        "htdemucs_6s.yaml": {"stems": STEMS_6, "type": "demucs"},
        "htdemucs_ft.yaml": {"stems": STEMS_4, "type": "demucs"},
        "htdemucs.yaml": {"stems": STEMS_4, "type": "demucs"},
        "hdemucs_mmi.yaml": {"stems": STEMS_4, "type": "demucs"},
        "model_bs_roformer_ep_317_sdr_12.9755.ckpt": {"stems": STEMS_2, "type": "roformer"},
        "model_bs_roformer_ep_368_sdr_12.9628.ckpt": {"stems": STEMS_2, "type": "roformer"},
        "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt": {"stems": STEMS_2, "type": "roformer"},
    }

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the separation stage.

        Args:
            settings: Application settings. Uses global settings if not provided.
        """
        self.settings = settings or get_settings()
        self._mps_disabled = False

    @property
    def name(self) -> str:
        return "separation"

    @property
    def expected_stems(self) -> list[str]:
        """Get expected stems based on configured model."""
        model = self.settings.separation_model
        if model in self.MODEL_INFO:
            return self.MODEL_INFO[model]["stems"]
        # Default to 4-stem for unknown models
        return self.STEMS_4

    def execute(self, context: ProcessingContext) -> StageResult:
        """Execute stem separation."""
        warnings: list[str] = []

        if context.normalized_audio_path is None:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message="No normalized audio path available. Run ingest stage first.",
            )

        # Check audio-separator is available
        if not self._check_audio_separator():
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message="audio-separator not found. Install with: pip install audio-separator",
            )

        # Create output directory for stems
        stems_dir = context.temp_dir / "stems"
        stems_dir.mkdir(exist_ok=True)

        # Log which model we're using
        warnings.append(f"Using model: {self.settings.separation_model}")

        # Run audio-separator
        try:
            output_files = self._run_separator(
                context.normalized_audio_path,
                stems_dir,
                self.settings.separation_model,
            )
            if not output_files:
                raise RuntimeError("No output files produced")
        except Exception as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"Stem separation failed: {e}",
            )

        # Find and organize stems
        try:
            stem_paths = self._find_stems(stems_dir, context.normalized_audio_path.stem)
            context.stem_paths = stem_paths
        except Exception as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"Failed to locate separated stems: {e}",
            )

        # Optionally run DrumSep on the drums stem
        if self.settings.separate_drums and "drums" in context.stem_paths:
            try:
                drum_stems = self._run_drum_separation(
                    context.stem_paths["drums"],
                    stems_dir,
                )
                # Add drum sub-stems to context (prefixed with "drum_")
                for drum_name, drum_path in drum_stems.items():
                    context.stem_paths[f"drum_{drum_name}"] = drum_path
                warnings.append(
                    f"Separated drums into: {', '.join(drum_stems.keys())}"
                )
            except Exception as e:
                warnings.append(f"DrumSep failed (continuing without): {e}")

        # Validate we got expected stems
        expected = set(self.expected_stems)
        found = set(context.stem_paths.keys())
        # Only check base stems, not drum sub-stems
        base_found = {s for s in found if not s.startswith("drum_")}
        missing_stems = expected - base_found
        if missing_stems:
            warnings.append(f"Missing stems: {', '.join(missing_stems)}")

        found_stems = list(context.stem_paths.keys())
        warnings.append(f"Total stems: {len(found_stems)} ({', '.join(sorted(found_stems))})")

        return StageResult(
            success=True,
            stage_name=self.name,
            duration_seconds=0,
            warnings=warnings,
        )

    def _check_audio_separator(self) -> bool:
        """Check if audio-separator is available."""
        try:
            from audio_separator.separator import Separator  # noqa: F401

            return True
        except ImportError:
            return False

    def _run_separator(
        self, audio_path: Path, output_dir: Path, model_name: str
    ) -> list[str]:
        """Run audio-separator on the input file.

        Uses the Python API with MPS disabled to ensure CPU mode on Apple Silicon.

        Args:
            audio_path: Path to input audio file
            output_dir: Directory for output stems
            model_name: Model filename to use

        Returns:
            List of output filenames
        """
        # Disable MPS for Demucs models (required on Apple Silicon)
        if not self._mps_disabled:
            _disable_mps_if_needed()
            self._mps_disabled = True

        from audio_separator.separator import Separator

        # Ensure model directory exists
        self.settings.model_dir.mkdir(parents=True, exist_ok=True)

        separator = Separator(
            output_dir=str(output_dir),
            output_format="WAV",
            model_file_dir=str(self.settings.model_dir),
        )

        # Load model
        separator.load_model(model_name)

        # Run separation
        output_files = separator.separate(str(audio_path))

        return output_files

    def _run_drum_separation(
        self, drums_path: Path, output_dir: Path
    ) -> dict[str, Path]:
        """Run DrumSep model on the drums stem.

        Separates drums into: kick, snare, toms, hi-hat (hh), ride, crash.

        Args:
            drums_path: Path to drums stem
            output_dir: Directory for output

        Returns:
            Dict mapping drum component name to path
        """
        from audio_separator.separator import Separator

        # Create subdirectory for drum stems
        drum_dir = output_dir / "drums_separated"
        drum_dir.mkdir(exist_ok=True)

        separator = Separator(
            output_dir=str(drum_dir),
            output_format="WAV",
            model_file_dir=str(self.settings.model_dir),
        )

        # Load DrumSep model
        separator.load_model(self.DRUMSEP_MODEL)

        # Run separation
        output_files = separator.separate(str(drums_path))

        # Find and organize drum stems
        drum_stems: dict[str, Path] = {}
        drum_pattern = re.compile(r"\((\w+)\)", re.IGNORECASE)

        for file_path in drum_dir.glob("*.wav"):
            match = drum_pattern.search(file_path.name)
            if match:
                drum_name = match.group(1).lower()
                if drum_name in self.DRUM_STEMS:
                    clean_path = drum_dir / f"{drum_name}.wav"
                    if file_path != clean_path:
                        shutil.move(str(file_path), str(clean_path))
                    drum_stems[drum_name] = clean_path

        return drum_stems

    def _find_stems(self, stems_dir: Path, input_stem: str) -> dict[str, Path]:
        """Find and rename separated stem files.

        audio-separator outputs files with patterns like:
        - {input}_(Vocals)_{model}.wav
        - {input}_(Drums)_{model}.wav
        - {input}_(Bass)_{model}.wav
        - {input}_(Guitar)_{model}.wav  (6-stem model)
        - {input}_(Piano)_{model}.wav   (6-stem model)
        - {input}_(Other)_{model}.wav

        We rename these to simpler names.
        """
        stem_paths: dict[str, Path] = {}

        # All possible stem names across different models
        all_valid_stems = set(self.STEMS_2 + self.STEMS_4 + self.STEMS_6)

        # Pattern to match stem files: look for (StemName) in filename
        stem_pattern = re.compile(r"\((\w+)\)", re.IGNORECASE)

        for file_path in stems_dir.glob("*.wav"):
            # Skip files in subdirectories (like drums_separated)
            if file_path.parent != stems_dir:
                continue

            match = stem_pattern.search(file_path.name)
            if match:
                stem_name = match.group(1).lower()

                # Normalize stem names
                if stem_name in ("vocal", "vocals"):
                    stem_name = "vocals"
                elif stem_name in ("drum", "drums"):
                    stem_name = "drums"
                # "instrumental" stays as-is for 2-stem models

                if stem_name in all_valid_stems:
                    # Rename to clean name
                    clean_path = stems_dir / f"{stem_name}.wav"
                    if file_path != clean_path:
                        shutil.move(str(file_path), str(clean_path))
                    stem_paths[stem_name] = clean_path

        if not stem_paths:
            # List what files we actually found for debugging
            found_files = list(stems_dir.glob("*"))
            raise RuntimeError(
                f"No stem files found in {stems_dir}. "
                f"Files present: {[f.name for f in found_files]}"
            )

        return stem_paths
