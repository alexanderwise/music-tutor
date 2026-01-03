"""Main CLI entry point for Music Tutor."""

from pathlib import Path

import click
from rich.console import Console

from music_tutor import __version__
from music_tutor.config import get_settings

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="music-tutor")
def main() -> None:
    """Music Tutor - Audio processing for music practice.

    Separate stems, detect beats and notes, align lyrics, and generate
    time-stretched versions for practice at different speeds.
    """
    pass


@main.command()
@click.argument("audio_file", type=click.Path(path_type=Path), required=False)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output directory (default: ./output/<song_name>)",
)
@click.option(
    "--model",
    type=str,
    help="Stem separation model to use",
)
@click.option(
    "--gpu/--no-gpu",
    default=None,
    help="Enable/disable GPU acceleration",
)
@click.option(
    "--keep-temp",
    is_flag=True,
    help="Keep temporary files for debugging",
)
@click.option(
    "--drum-sep/--no-drum-sep",
    default=None,
    help="Separate drums into kick, snare, toms, hi-hat, ride, crash",
)
@click.option(
    "--reanalyze",
    is_flag=True,
    help="Re-run analysis stages only (skip stem separation and time stretching)",
)
def convert(
    audio_file: Path | None,
    output: Path | None,
    model: str | None,
    gpu: bool | None,
    keep_temp: bool,
    drum_sep: bool | None,
    reanalyze: bool,
) -> None:
    """Convert an audio file for practice.

    Processes AUDIO_FILE through the full pipeline:

    \b
    1. Ingest & normalize audio
    2. Separate into stems (vocals, drums, bass, other)
    3. Detect beats, notes, and align lyrics
    4. Generate time-stretched versions
    5. Output analysis.json with all metadata

    Use --reanalyze to re-run only the analysis stages on existing stems.
    """
    from music_tutor.pipeline import (
        create_analysis_pipeline,
        create_default_pipeline,
    )

    # Validate arguments based on mode
    if reanalyze:
        if output is None:
            console.print("[red]Error: --output is required when using --reanalyze[/red]")
            raise SystemExit(1)
    else:
        if audio_file is None:
            console.print("[red]Error: AUDIO_FILE is required[/red]")
            raise SystemExit(1)
        if not audio_file.exists():
            console.print(f"[red]Error: File not found: {audio_file}[/red]")
            raise SystemExit(1)

    settings = get_settings()

    # Apply CLI overrides
    if model:
        settings.separation_model = model
    if gpu is not None:
        settings.use_gpu = gpu
    if keep_temp:
        settings.keep_temp_files = True
    if drum_sep is not None:
        settings.separate_drums = drum_sep

    # Determine output directory
    if output is None:
        assert audio_file is not None  # Already validated above
        song_name = audio_file.stem
        output = settings.output_dir / song_name

    console.print(f"[bold blue]Music Tutor[/bold blue] v{__version__}")

    if reanalyze:
        # Reanalyze mode: use existing stems, re-run analysis stages only
        analysis_path = output / "analysis.json"
        if not analysis_path.exists():
            console.print(f"[red]Error: No existing analysis.json found at {output}[/red]")
            console.print("Run without --reanalyze first to create stems.")
            raise SystemExit(1)

        console.print(f"[yellow]Reanalyzing:[/yellow] [green]{output}[/green]")
        console.print("(Skipping stem separation and time stretching)")
        console.print()

        pipeline = create_analysis_pipeline(settings)
        result = pipeline.reanalyze(output)
    else:
        console.print(f"Processing: [green]{audio_file}[/green]")
        console.print(f"Output: [green]{output}[/green]")
        console.print()

        # Create and run full pipeline
        pipeline = create_default_pipeline(settings)
        result = pipeline.run(audio_file, output)

    # Display results
    if result.success:
        console.print("[bold green]Processing complete![/bold green]")
        console.print(f"Output: {result.output_path}")
        console.print(f"Stages completed: {', '.join(result.stages_completed)}")
        if result.warnings:
            console.print("[yellow]Warnings:[/yellow]")
            for warning in result.warnings:
                console.print(f"  - {warning}")
    else:
        console.print("[bold red]Processing failed![/bold red]")
        for error in result.errors:
            console.print(f"[red]Error: {error}[/red]")
        raise SystemExit(1)


@main.command()
def info() -> None:
    """Show current configuration and detected tools."""
    settings = get_settings()

    console.print("[bold]Configuration[/bold]")
    console.print(f"  Output directory: {settings.output_dir}")
    console.print(f"  Temp directory: {settings.temp_dir}")
    console.print(f"  Model directory: {settings.model_dir}")
    console.print(f"  Separation model: {settings.separation_model}")
    console.print(f"  GPU enabled: {settings.use_gpu}")
    console.print(f"  Speed presets: {settings.speed_presets}")
    console.print(f"  Output format: {settings.output_format}")
    console.print()

    # Check for required tools
    console.print("[bold]Tool availability[/bold]")
    _check_tool("ffmpeg", "ffmpeg -version")
    _check_tool("rubberband", "rubberband --version")
    _check_tool("audio-separator", "audio-separator --version")


def _check_tool(name: str, command: str) -> None:
    """Check if a tool is available."""
    import subprocess

    try:
        result = subprocess.run(
            command.split(),
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            console.print(f"  [green]{name}[/green]: available")
        else:
            console.print(f"  [red]{name}[/red]: not working")
    except FileNotFoundError:
        console.print(f"  [red]{name}[/red]: not found")
    except subprocess.TimeoutExpired:
        console.print(f"  [yellow]{name}[/yellow]: timeout")


if __name__ == "__main__":
    main()
