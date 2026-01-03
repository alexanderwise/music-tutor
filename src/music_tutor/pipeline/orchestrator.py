"""Pipeline orchestrator for Music Tutor."""

import json
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

    def reanalyze(self, output_dir: Path) -> ProcessingResult:
        """Re-run analysis stages on existing stems.

        Loads existing analysis.json and stem files, then runs only the
        analysis stages (beat detection, pitch detection, strike detection,
        lyrics alignment, finalize).

        Args:
            output_dir: Directory containing existing processed song.

        Returns:
            ProcessingResult with success status and details.
        """
        start_time = time.time()

        # Load existing analysis
        analysis_path = output_dir / "analysis.json"
        with open(analysis_path, encoding="utf-8") as f:
            existing = json.load(f)

        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="music-tutor-reanalyze-"))

        # Initialize context from existing analysis
        context = ProcessingContext(
            source_path=Path(existing.get("sourceFile", "unknown")),
            temp_dir=temp_dir,
            output_dir=output_dir,
            duration=existing.get("originalDuration"),
            sample_rate=existing.get("sampleRate", 44100),
            title=existing.get("title"),
            artist=existing.get("artist"),
            album=existing.get("album"),
            tempo_bpm=existing.get("tempoBpm"),
            time_signature=tuple(existing["timeSignature"]) if existing.get("timeSignature") else None,
        )

        # Populate stem_paths from existing stems (use 1.0x versions for analysis)
        stems_data = existing.get("stems", {})
        for stem_name, stem_info in stems_data.items():
            paths = stem_info.get("paths", {})
            if "1.0x" in paths:
                stem_path = output_dir / paths["1.0x"]
                if stem_path.exists():
                    # Convert camelCase back to snake_case for drum stems
                    if stem_name.startswith("drum") and stem_name != "drums":
                        # drumKick -> drum_kick, drumHh -> drum_hh
                        snake_name = stem_name[0].lower()
                        for c in stem_name[1:]:
                            if c.isupper():
                                snake_name += "_" + c.lower()
                            else:
                                snake_name += c
                        context.stem_paths[snake_name] = stem_path
                    else:
                        context.stem_paths[stem_name] = stem_path

        # Populate stretched_stems for finalize stage
        for stem_name, stem_info in stems_data.items():
            paths = stem_info.get("paths", {})
            speed_paths = {}
            for speed_key, rel_path in paths.items():
                full_path = output_dir / rel_path
                if full_path.exists():
                    speed_paths[speed_key] = full_path
            if speed_paths:
                # Use original stem name (may need snake_case conversion)
                if stem_name.startswith("drum") and stem_name != "drums":
                    snake_name = stem_name[0].lower()
                    for c in stem_name[1:]:
                        if c.isupper():
                            snake_name += "_" + c.lower()
                        else:
                            snake_name += c
                    context.stretched_stems[snake_name] = speed_paths
                else:
                    context.stretched_stems[stem_name] = speed_paths

        result = ProcessingResult(success=True)
        result.stages_skipped = ["ingest", "separation", "time_stretch"]

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
            # Cleanup temp directory
            if not self.settings.keep_temp_files and temp_dir.exists():
                shutil.rmtree(temp_dir)

        result.total_duration = time.time() - start_time
        return result


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
        StrikeDetectionStage,
        TimeStretchStage,
    )

    stages: list[PipelineStage] = [
        IngestStage(),
        SeparationStage(settings),
        BeatDetectionStage(),
        PitchDetectionStage(),
        StrikeDetectionStage(),
        LyricsAlignmentStage(),
        TimeStretchStage(settings),
        FinalizeStage(),
    ]

    return Pipeline(stages, settings)


def create_analysis_pipeline(settings: Settings) -> Pipeline:
    """Create a pipeline with only analysis stages.

    This pipeline is used for re-analyzing existing stems without
    re-running separation or time stretching.

    Args:
        settings: Application settings.

    Returns:
        Configured Pipeline instance with analysis stages only.
    """
    from music_tutor.stages import (
        BeatDetectionStage,
        FinalizeStage,
        LyricsAlignmentStage,
        PitchDetectionStage,
        StrikeDetectionStage,
    )

    stages: list[PipelineStage] = [
        BeatDetectionStage(),
        PitchDetectionStage(),
        StrikeDetectionStage(),
        LyricsAlignmentStage(),
        FinalizeStage(),
    ]

    return Pipeline(stages, settings)
