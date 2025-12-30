"""Finalize stage - generates analysis.json and organizes output."""

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from music_tutor.models.analysis import SongAnalysis, StemInfo
from music_tutor.models.pipeline import ProcessingContext, StageResult
from music_tutor.pipeline.base import PipelineStage

# Version of the converter
CONVERTER_VERSION = "0.1.0"


class FinalizeStage(PipelineStage):
    """Stage 5: Finalize.

    Generates the final analysis.json file, metadata.nfo file, and organizes
    the output directory. Collects all analysis data from the ProcessingContext
    and serializes it to JSON format.

    Output directory structure:
    {song_name}/
    ├── analysis.json           # SongAnalysis serialized
    ├── metadata.nfo            # Extended metadata (genre, MusicBrainz IDs, etc.)
    └── stems/
        ├── vocals_0.5x.flac
        ├── vocals_0.75x.flac
        └── ...
    """

    @property
    def name(self) -> str:
        return "finalize"

    def execute(self, context: ProcessingContext) -> StageResult:
        """Generate analysis.json, metadata.nfo, and finalize output."""
        warnings: list[str] = []

        try:
            # Build SongAnalysis object
            analysis = self._build_analysis(context, warnings)

            # Ensure output directory exists
            context.output_dir.mkdir(parents=True, exist_ok=True)

            # Write analysis.json
            analysis_path = context.output_dir / "analysis.json"
            with open(analysis_path, "w", encoding="utf-8") as f:
                json.dump(
                    self._to_serializable(analysis),
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

            context.analysis_path = analysis_path
            warnings.append(f"Wrote {analysis_path}")

            # Write metadata.nfo
            nfo_path = context.output_dir / "metadata.nfo"
            self._write_nfo(context, nfo_path)
            warnings.append(f"Wrote {nfo_path}")

        except Exception as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"Failed to write analysis: {e}",
            )

        return StageResult(
            success=True,
            stage_name=self.name,
            duration_seconds=0,
            warnings=warnings,
        )

    def _write_nfo(self, context: ProcessingContext, nfo_path: Path) -> None:
        """Write metadata to a .nfo file.

        The .nfo file contains all extracted metadata in a human-readable
        and machine-parseable format (XML-like structure for compatibility
        with media applications like Kodi/Jellyfin).

        Args:
            context: Processing context with metadata
            nfo_path: Path to write the .nfo file
        """
        lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<musicinfo>"]

        # Basic metadata
        if context.title:
            lines.append(f"  <title>{self._escape_xml(context.title)}</title>")
        if context.artist:
            lines.append(f"  <artist>{self._escape_xml(context.artist)}</artist>")
        if context.album:
            lines.append(f"  <album>{self._escape_xml(context.album)}</album>")

        # Extended metadata from context.metadata dict
        metadata_order = [
            "genre",
            "date",
            "tracknumber",
            "discnumber",
            "composer",
            "conductor",
            "lyricist",
            "label",
            "isrc",
            "bpm",
            "language",
            "mood",
            "copyright",
            # MusicBrainz IDs
            "musicbrainz_trackid",
            "musicbrainz_recordingid",
            "musicbrainz_albumid",
            "musicbrainz_artistid",
            "musicbrainz_albumartistid",
            "musicbrainz_releasegroupid",
            # Other IDs
            "acoustid_id",
        ]

        for key in metadata_order:
            value = context.metadata.get(key, "")
            if value:
                lines.append(f"  <{key}>{self._escape_xml(value)}</{key}>")

        # Add any additional metadata not in the standard order
        for key, value in context.metadata.items():
            if key not in metadata_order and value:
                lines.append(f"  <{key}>{self._escape_xml(value)}</{key}>")

        # Processing info
        lines.append("  <processing>")
        lines.append(f"    <source_file>{self._escape_xml(context.source_path.name)}</source_file>")
        lines.append(f"    <processing_date>{datetime.now(timezone.utc).isoformat()}</processing_date>")
        lines.append(f"    <converter_version>{CONVERTER_VERSION}</converter_version>")
        if context.duration:
            lines.append(f"    <duration>{context.duration:.2f}</duration>")
        if context.sample_rate:
            lines.append(f"    <sample_rate>{context.sample_rate}</sample_rate>")
        if context.tempo_bpm:
            lines.append(f"    <detected_bpm>{context.tempo_bpm:.1f}</detected_bpm>")
        if context.time_signature:
            lines.append(f"    <time_signature>{context.time_signature[0]}/{context.time_signature[1]}</time_signature>")
        lines.append("  </processing>")

        lines.append("</musicinfo>")

        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _escape_xml(self, text: str) -> str:
        """Escape special XML characters.

        Args:
            text: Text to escape

        Returns:
            XML-safe text
        """
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    def _build_analysis(
        self, context: ProcessingContext, warnings: list[str]
    ) -> SongAnalysis:
        """Build SongAnalysis from ProcessingContext.

        Args:
            context: Processing context with all analysis data
            warnings: List to append warnings to

        Returns:
            Populated SongAnalysis object
        """
        # Build stem info from stretched_stems
        stems: dict[str, StemInfo] = {}
        for stem_name, speed_paths in context.stretched_stems.items():
            # Convert paths to relative paths from output_dir
            relative_paths = {}
            for speed_key, path in speed_paths.items():
                try:
                    rel_path = path.relative_to(context.output_dir)
                    relative_paths[speed_key] = str(rel_path)
                except ValueError:
                    # Path not relative to output_dir, use absolute
                    relative_paths[speed_key] = str(path)

            stems[stem_name] = StemInfo(
                name=stem_name,
                paths=relative_paths,
                has_notes=stem_name in context.notes,
                peak_db=0.0,  # TODO: Calculate peak dB
            )

        # Convert notes dict with Note objects to plain structure
        notes: dict[str, list] = {}
        for stem_name, note_list in context.notes.items():
            notes[stem_name] = note_list

        analysis = SongAnalysis(
            title=context.title,
            artist=context.artist,
            album=context.album,
            original_duration=context.duration or 0.0,
            sample_rate=context.sample_rate or 44100,
            tempo_bpm=context.tempo_bpm,
            time_signature=context.time_signature,
            source_file=context.source_path.name,
            processing_date=datetime.now(timezone.utc).isoformat(),
            converter_version=CONVERTER_VERSION,
            stems=stems,
            beats=context.beats,
            notes=notes,
            lyrics=context.lyrics,
        )

        # Add warnings for missing data
        if not context.beats:
            warnings.append("No beat data available")
        if not context.notes:
            warnings.append("No note data available")
        if not context.lyrics:
            warnings.append("No lyrics data available")

        return analysis

    def _to_serializable(self, obj) -> dict:
        """Convert dataclass hierarchy to JSON-serializable dict.

        Handles nested dataclasses, lists, and special types.
        Converts all snake_case field names to camelCase.

        Args:
            obj: Object to serialize (dataclass or dict)

        Returns:
            JSON-serializable dictionary
        """
        if hasattr(obj, "__dataclass_fields__"):
            # Use asdict which recursively converts nested dataclasses
            raw_dict = asdict(obj)
            return self._convert_dict_keys(raw_dict)
        elif isinstance(obj, dict):
            return self._convert_dict_keys(obj)
        else:
            return obj

    def _convert_dict_keys(self, d: dict) -> dict:
        """Recursively convert dict keys from snake_case to camelCase.

        Args:
            d: Dictionary with snake_case keys

        Returns:
            Dictionary with camelCase keys
        """
        result = {}
        for key, value in d.items():
            # Only convert string keys that look like snake_case
            if isinstance(key, str) and "_" in key:
                camel_key = self._to_camel_case(key)
            else:
                camel_key = key

            result[camel_key] = self._process_value(value)
        return result

    def _process_value(self, value):
        """Process a value for JSON serialization.

        Args:
            value: Value to process

        Returns:
            JSON-serializable value
        """
        if hasattr(value, "__dataclass_fields__"):
            return self._to_serializable(value)
        elif isinstance(value, dict):
            return self._convert_dict_keys(value)
        elif isinstance(value, list):
            return [self._process_value(item) for item in value]
        elif isinstance(value, tuple):
            return list(value)
        elif isinstance(value, Path):
            return str(value)
        else:
            return value

    def _to_camel_case(self, snake_str: str) -> str:
        """Convert snake_case to camelCase.

        Args:
            snake_str: String in snake_case

        Returns:
            String in camelCase
        """
        components = snake_str.split("_")
        return components[0] + "".join(x.title() for x in components[1:])
