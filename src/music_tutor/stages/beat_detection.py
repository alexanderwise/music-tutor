"""Beat detection stage - extracts beats, tempo, and time signature using madmom."""

from pathlib import Path

import numpy as np

from music_tutor.models.analysis import BeatEvent
from music_tutor.models.pipeline import ProcessingContext, StageResult
from music_tutor.pipeline.base import PipelineStage


class BeatDetectionStage(PipelineStage):
    """Stage 3a: Beat Detection.

    Uses madmom's neural network-based beat and downbeat tracking to extract:
    - Beat positions (time in seconds)
    - Downbeat positions (beat 1 of each measure)
    - Beat position within measure (1, 2, 3, 4 for 4/4)
    - Tempo (BPM) calculated from beat intervals
    - Time signature (4/4 or 3/4) inferred from downbeat pattern

    NOTE: This stage intentionally has NO fallback to librosa. librosa's beat_track
    uses onset detection which cannot identify downbeats and performs poorly on
    syncopated music. For a music learning app, incorrect beat data is worse than
    no beat data. If madmom fails, we fail loudly.
    """

    # Supported time signatures (beats per bar)
    SUPPORTED_TIME_SIGNATURES = [4, 3]

    @property
    def name(self) -> str:
        return "beat_detection"

    def execute(self, context: ProcessingContext) -> StageResult:
        """Execute beat detection on the drums stem."""
        warnings: list[str] = []

        # Prefer drums stem, fall back to full mix if needed
        audio_path = context.stem_paths.get("drums")
        source_desc = "drums stem"

        if audio_path is None:
            # Fall back to normalized audio (full mix)
            audio_path = context.normalized_audio_path
            source_desc = "full mix"
            warnings.append("No drums stem available, using full mix for beat detection")

        if audio_path is None:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message="No audio available for beat detection",
            )

        # Check madmom is available
        try:
            import madmom  # noqa: F401
        except ImportError as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=(
                    f"madmom not installed: {e}. "
                    "Install with: uv pip install 'madmom @ git+https://github.com/"
                    "The-Africa-Channel/madmom-py3.10-compat.git'"
                ),
            )

        # Run beat detection
        try:
            beats, tempo, time_sig = self._detect_beats(audio_path)
            context.beats = beats
            context.tempo_bpm = tempo
            context.time_signature = time_sig

            warnings.append(f"Detected {len(beats)} beats from {source_desc}")
            warnings.append(f"Tempo: {tempo:.1f} BPM, Time signature: {time_sig[0]}/{time_sig[1]}")

        except Exception as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=0,
                error_message=f"Beat detection failed: {e}",
            )

        return StageResult(
            success=True,
            stage_name=self.name,
            duration_seconds=0,
            warnings=warnings,
        )

    def _detect_beats(
        self, audio_path: Path
    ) -> tuple[list[BeatEvent], float, tuple[int, int]]:
        """Detect beats using madmom's RNN downbeat processor.

        Args:
            audio_path: Path to audio file (preferably drums stem)

        Returns:
            Tuple of (beats list, tempo BPM, time signature)
        """
        import madmom

        # Apply PyTorch compatibility patch for older model checkpoints
        self._apply_torch_patch()

        # Create processors
        proc = madmom.features.downbeats.RNNDownBeatProcessor()
        dbn = madmom.features.downbeats.DBNDownBeatTrackingProcessor(
            beats_per_bar=self.SUPPORTED_TIME_SIGNATURES,
            fps=100,
        )

        # Process audio
        activations = proc(str(audio_path))
        downbeats = dbn(activations)

        # Convert to BeatEvent list
        beats = self._convert_to_beat_events(downbeats)

        # Calculate tempo from beat intervals
        tempo = self._calculate_tempo(downbeats)

        # Detect time signature from beat pattern
        time_sig = self._detect_time_signature(downbeats)

        return beats, tempo, time_sig

    def _apply_torch_patch(self) -> None:
        """Apply PyTorch compatibility patch for older madmom model checkpoints.

        Older checkpoints may trigger warnings or errors with newer PyTorch
        versions due to changes in torch.load() defaults.
        """
        import torch

        _original_load = torch.load

        def _patched_load(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return _original_load(*args, **kwargs)

        torch.load = _patched_load

    def _convert_to_beat_events(self, downbeats: np.ndarray) -> list[BeatEvent]:
        """Convert madmom output to BeatEvent list.

        Args:
            downbeats: Array of shape (N, 2) with [time, beat_position]
                       beat_position: 1 = downbeat, 2-4 = other beats

        Returns:
            List of BeatEvent objects
        """
        beats = []
        for time, beat_pos in downbeats:
            beat_in_measure = int(beat_pos)
            beats.append(
                BeatEvent(
                    time=float(time),
                    type="downbeat" if beat_in_measure == 1 else "beat",
                    beat_in_measure=beat_in_measure,
                )
            )
        return beats

    def _calculate_tempo(self, downbeats: np.ndarray) -> float:
        """Calculate tempo in BPM from beat intervals.

        Args:
            downbeats: Array of shape (N, 2) with [time, beat_position]

        Returns:
            Tempo in beats per minute
        """
        if len(downbeats) < 2:
            return 120.0  # Default fallback

        beat_times = downbeats[:, 0]
        intervals = np.diff(beat_times)

        # Remove outliers (more than 2 std from mean)
        mean_interval = np.mean(intervals)
        std_interval = np.std(intervals)
        valid_intervals = intervals[
            np.abs(intervals - mean_interval) < 2 * std_interval
        ]

        if len(valid_intervals) == 0:
            valid_intervals = intervals

        avg_interval = np.median(valid_intervals)
        tempo = 60.0 / avg_interval

        return float(tempo)

    def _detect_time_signature(self, downbeats: np.ndarray) -> tuple[int, int]:
        """Detect time signature from downbeat pattern.

        Args:
            downbeats: Array of shape (N, 2) with [time, beat_position]

        Returns:
            Time signature as (numerator, denominator), e.g., (4, 4)
        """
        if len(downbeats) < 4:
            return (4, 4)  # Default fallback

        beat_positions = downbeats[:, 1]
        downbeat_indices = np.where(beat_positions == 1)[0]

        if len(downbeat_indices) < 2:
            return (4, 4)

        # Calculate beats between downbeats
        beats_per_measure = np.diff(downbeat_indices)

        # Use median to be robust to errors
        beats = int(np.median(beats_per_measure))

        # Clamp to supported values
        if beats not in self.SUPPORTED_TIME_SIGNATURES:
            beats = 4

        return (beats, 4)  # Always quarter note = 1 beat
