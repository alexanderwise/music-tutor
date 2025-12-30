"""Pipeline orchestrator for Music Tutor."""

import shutil
import tempfile
import time
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from music_tutor.config import Settings
from music_tutor.models.pipeline import ProcessingContext, ProcessingResult
from music_tutor.pipeline.base import PipelineStage

console = Console()


class Pipeline:
    """Orchestrates the execution of pipeline stages."""

    def __init__(self, stages: list[PipelineStage], settings: Settings) -> None:
        """Initialize the pipeline.

        Args:
            stages: Ordered list of stages to execute.
            settings: Application settings.
        """
        self.stages = stages
        self.settings = settings

    def run(self, source_path: Path, output_dir: Path) -> ProcessingResult:
        """Run the full pipeline on an audio file.

        Args:
            source_path: Path to the input audio file.
            output_dir: Directory for output files.

        Returns:
            ProcessingResult with success status and details.
        """
        start_time = time.time()

        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="music-tutor-"))

        # Initialize context
        context = ProcessingContext(
            source_path=source_path,
            temp_dir=temp_dir,
            output_dir=output_dir,
        )

        # Look for lyrics file with same base name
        context.source_lyrics_path = self._find_lyrics_file(source_path)

        result = ProcessingResult(success=True)

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                for stage in self.stages:
                    task = progress.add_task(f"[cyan]{stage.name}[/cyan]...", total=None)

                    stage_result = stage.run(context)

                    progress.remove_task(task)

                    if stage_result.success:
                        result.stages_completed.append(stage.name)
                        result.warnings.extend(stage_result.warnings)
                        console.print(
                            f"  [green]{stage.name}[/green] "
                            f"({stage_result.duration_seconds:.1f}s)"
                        )
                    else:
                        result.success = False
                        result.errors.append(
                            f"{stage.name}: {stage_result.error_message}"
                        )
                        console.print(
                            f"  [red]{stage.name}[/red] failed: "
                            f"{stage_result.error_message}"
                        )
                        break

            if result.success:
                result.output_path = context.analysis_path or output_dir

        finally:
            # Cleanup temp directory unless keep_temp_files is set
            if not self.settings.keep_temp_files and temp_dir.exists():
                shutil.rmtree(temp_dir)

        result.total_duration = time.time() - start_time
        return result

    def _find_lyrics_file(self, audio_path: Path) -> Path | None:
        """Find a lyrics file with the same base name as the audio file."""
        base = audio_path.stem
        parent = audio_path.parent

        for ext in [".lrc", ".txt"]:
            lyrics_path = parent / f"{base}{ext}"
            if lyrics_path.exists():
                return lyrics_path

        return None


def create_default_pipeline(settings: Settings) -> Pipeline:
    """Create a pipeline with all default stages.

    Args:
        settings: Application settings.

    Returns:
        Configured Pipeline instance.
    """
    from music_tutor.stages import (
        BeatDetectionStage,
        FinalizeStage,
        IngestStage,
        LyricsAlignmentStage,
        PitchDetectionStage,
        SeparationStage,
        TimeStretchStage,
    )

    stages: list[PipelineStage] = [
        IngestStage(),
        SeparationStage(settings),
        BeatDetectionStage(),
        PitchDetectionStage(),
        LyricsAlignmentStage(),
        TimeStretchStage(settings),
        FinalizeStage(),
    ]

    return Pipeline(stages, settings)
