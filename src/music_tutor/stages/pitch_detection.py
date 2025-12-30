"""Pitch detection stage - extracts MIDI notes using basic-pitch."""

from pathlib import Path

from music_tutor.models.analysis import Note, PitchBendPoint
from music_tutor.models.pipeline import ProcessingContext, StageResult
from music_tutor.pipeline.base import PipelineStage


class PitchDetectionStage(PipelineStage):
    """Stage 3b: Pitch Detection.

    Uses Spotify's basic-pitch neural network to extract MIDI notes from
    melodic stems (vocals, bass, other - not drums).

    For each note, extracts:
    - Start/end time in seconds
    - MIDI pitch (0-127)
    - Velocity/amplitude (0.0-1.0)
    - Pitch bend curve (deviation from quantized pitch)

    basic-pitch is instrument-agnostic and works well on vocals, bass,
    guitar, piano, etc.
    """

    # Stems to analyze (drums excluded - no pitched content)
    # Includes guitar and piano for 6-stem models
    MELODIC_STEMS = ["vocals", "bass", "guitar", "piano", "other"]

    # Pitch bend values from basic-pitch are in bins (roughly 1/3 semitone each)
    # Convert to cents: 100 cents = 1 semitone, so ~33 cents per bin
    PITCH_BEND_CENTS_PER_BIN = 33.0

    # Minimum note amplitude to include (filter noise)
    MIN_AMPLITUDE = 0.1

    @property
    def name(self) -> str:
        return "pitch_detection"

    def execute(self, context: ProcessingContext) -> StageResult:
        """Execute pitch detection on melodic stems."""
        warnings: list[str] = []

        # Check basic-pitch is available
        try:
            from basic_pitch.inference import predict  # noqa: F401
        except ImportError as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"basic-pitch not installed: {e}",
            )

        # Process each melodic stem
        stems_processed = 0
        for stem_name in self.MELODIC_STEMS:
            stem_path = context.stem_paths.get(stem_name)
            if stem_path is None or not stem_path.exists():
                warnings.append(f"Skipping {stem_name}: stem not available")
                continue

            try:
                notes = self._detect_notes(stem_path)
                context.notes[stem_name] = notes
                stems_processed += 1
                warnings.append(f"{stem_name}: {len(notes)} notes detected")
            except Exception as e:
                warnings.append(f"{stem_name}: pitch detection failed - {e}")

        if stems_processed == 0:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message="No melodic stems available for pitch detection",
            )

        return StageResult(
            success=True,
            stage_name=self.name,
            duration_seconds=0,
            warnings=warnings,
        )

    def _detect_notes(self, audio_path: Path) -> list[Note]:
        """Detect notes in an audio file using basic-pitch.

        Args:
            audio_path: Path to audio file

        Returns:
            List of Note objects with timing, pitch, velocity, and pitch bend
        """
        from basic_pitch.inference import predict

        # Run prediction (returns model_output, midi_data, note_events)
        _, _, note_events = predict(str(audio_path))

        # Convert to Note objects
        notes = []
        for event in note_events:
            start_time, end_time, pitch, amplitude = event[:4]
            pitch_bend_data = event[4] if len(event) > 4 else None

            # Filter low-amplitude notes (likely noise)
            if amplitude < self.MIN_AMPLITUDE:
                continue

            # Convert pitch bend to our format
            pitch_bend = None
            if pitch_bend_data is not None and len(pitch_bend_data) > 0:
                pitch_bend = self._convert_pitch_bend(
                    pitch_bend_data, float(start_time), float(end_time)
                )

            notes.append(
                Note(
                    start=float(start_time),
                    end=float(end_time),
                    pitch=int(pitch),
                    velocity=float(amplitude),
                    pitch_bend=pitch_bend,
                )
            )

        # Sort by start time (basic-pitch returns in reverse order)
        notes.sort(key=lambda n: n.start)

        return notes

    def _convert_pitch_bend(
        self,
        pitch_bend_data: list,
        start_time: float,
        end_time: float,
    ) -> list[PitchBendPoint] | None:
        """Convert basic-pitch pitch bend data to PitchBendPoint list.

        basic-pitch outputs pitch bend as a list of integer bin offsets,
        where each bin is roughly 1/3 semitone (33 cents).

        Args:
            pitch_bend_data: List of integer bend values from basic-pitch
            start_time: Note start time
            end_time: Note end time

        Returns:
            List of PitchBendPoint with time relative to note start
        """
        if not pitch_bend_data:
            return None

        # Calculate time step between samples
        duration = end_time - start_time
        if duration <= 0 or len(pitch_bend_data) < 2:
            return None

        time_step = duration / len(pitch_bend_data)

        # Convert to PitchBendPoint list
        # Skip if all values are the same (no bend)
        unique_values = set(int(v) for v in pitch_bend_data)
        if len(unique_values) == 1 and 0 in unique_values:
            return None

        points = []
        for i, bend_value in enumerate(pitch_bend_data):
            cents = float(bend_value) * self.PITCH_BEND_CENTS_PER_BIN
            points.append(
                PitchBendPoint(
                    time=i * time_step,
                    cents=cents,
                )
            )

        return points if points else None
