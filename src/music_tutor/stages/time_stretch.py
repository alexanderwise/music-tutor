"""Time stretching stage - creates speed variants using pyrubberband."""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

import soundfile as sf


@contextmanager
def suppress_stderr():
    """Temporarily suppress stderr output.

    Used to hide harmless ffmpeg "Broken pipe" errors from pyrubberband.
    These occur when pyrubberband closes the pipe before ffmpeg finishes
    its cleanup, but all audio data is already written.
    """
    stderr_fd = sys.stderr.fileno()
    old_stderr = os.dup(stderr_fd)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, stderr_fd)
    try:
        yield
    finally:
        os.dup2(old_stderr, stderr_fd)
        os.close(old_stderr)
        os.close(devnull)

from music_tutor.config import Settings
from music_tutor.models.pipeline import ProcessingContext, StageResult
from music_tutor.pipeline.base import PipelineStage


class TimeStretchStage(PipelineStage):
    """Stage 4: Time Stretching.

    Creates time-stretched versions of all stems at multiple speeds
    for instant speed-switching during playback. Uses rubberband for
    high-quality time stretching with pitch preservation.

    Speeds generated:
    - 0.5x: Half speed for detailed practice
    - 0.75x: Three-quarter speed for moderate practice
    - 1.0x: Original speed (copy/link, no processing)
    - 1.25x: Slightly faster for challenge
    """

    # Playback speeds to generate (rate for pyrubberband)
    SPEEDS = [0.5, 0.75, 1.0, 1.25]

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize with optional settings.

        Args:
            settings: Application settings (unused for now, for future config)
        """
        self.settings = settings

    @property
    def name(self) -> str:
        return "time_stretch"

    def execute(self, context: ProcessingContext) -> StageResult:
        """Execute time stretching on all stems."""
        warnings: list[str] = []

        # Check pyrubberband is available
        try:
            import pyrubberband  # noqa: F401
        except ImportError as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"pyrubberband not installed: {e}",
            )

        # Check we have stems to process
        if not context.stem_paths:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message="No stems available for time stretching",
            )

        # Create output directory for stretched stems
        stretched_dir = context.output_dir / "stems"
        stretched_dir.mkdir(parents=True, exist_ok=True)

        # Process each stem
        stems_processed = 0
        for stem_name, stem_path in context.stem_paths.items():
            if not stem_path.exists():
                warnings.append(f"Skipping {stem_name}: stem file not found")
                continue

            try:
                stem_speeds = self._stretch_stem(
                    stem_path=stem_path,
                    stem_name=stem_name,
                    output_dir=stretched_dir,
                )
                context.stretched_stems[stem_name] = stem_speeds
                stems_processed += 1

                speeds_str = ", ".join(f"{s}x" for s in stem_speeds.keys())
                warnings.append(f"{stem_name}: created {speeds_str}")

            except Exception as e:
                warnings.append(f"{stem_name}: time stretching failed - {e}")

        if stems_processed == 0:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message="No stems could be time-stretched",
            )

        return StageResult(
            success=True,
            stage_name=self.name,
            duration_seconds=0,
            warnings=warnings,
        )

    def _stretch_stem(
        self,
        stem_path: Path,
        stem_name: str,
        output_dir: Path,
    ) -> dict[str, Path]:
        """Create time-stretched versions of a single stem.

        Args:
            stem_path: Path to original stem audio
            stem_name: Name of the stem (vocals, drums, etc.)
            output_dir: Directory for output files

        Returns:
            Dict mapping speed string (e.g., "0.5x") to output path
        """
        import pyrubberband

        # Load audio
        y, sr = sf.read(stem_path)

        results: dict[str, Path] = {}

        for speed in self.SPEEDS:
            speed_key = f"{speed}x"
            output_path = output_dir / f"{stem_name}_{speed_key}.flac"

            if speed == 1.0:
                # No stretching needed - just copy
                # Use FLAC for lossless compression
                sf.write(output_path, y, sr)
            else:
                # Time stretch
                # Note: rate in pyrubberband is playback rate
                # rate > 1 = faster, rate < 1 = slower
                # To get 0.5x playback speed, we need rate=0.5
                # Suppress stderr to hide harmless ffmpeg pipe errors
                with suppress_stderr():
                    y_stretched = pyrubberband.time_stretch(y, sr, speed)
                sf.write(output_path, y_stretched, sr)

            results[speed_key] = output_path

        return results

    def _calculate_stretched_duration(
        self, original_duration: float, speed: float
    ) -> float:
        """Calculate duration of time-stretched audio.

        Args:
            original_duration: Duration of original audio in seconds
            speed: Playback speed (0.5 = half speed)

        Returns:
            Duration of stretched audio in seconds
        """
        # If playback is slower, duration is longer
        return original_duration / speed
