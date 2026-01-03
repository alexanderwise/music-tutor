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
    SUPPORTED_TIME_SIGNATURES = [4, 3, 5]

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

        # Get neural network activations
        proc = madmom.features.downbeats.RNNDownBeatProcessor()
        activations = proc(str(audio_path))

        # Run DBN separately for each time signature and compare
        # This avoids madmom's implicit 4/4 bias when given multiple options
        results = {}
        scores = {}

        for beats_per_bar in self.SUPPORTED_TIME_SIGNATURES:
            dbn = madmom.features.downbeats.DBNDownBeatTrackingProcessor(
                beats_per_bar=[beats_per_bar],
                fps=100,
            )
            result = dbn(activations)
            results[beats_per_bar] = result
            scores[beats_per_bar] = self._calculate_consistency_score(result, beats_per_bar)

        # Choose best time signature
        # Since 4/4 is far more common, require other signatures to be noticeably
        # better to overcome the prior. For actual non-4/4 songs, the difference
        # is typically much larger (50%+), so these thresholds won't affect real detection.
        best_beats = 4  # default

        if 4 in scores:
            base_score = scores[4]
            # 3/4 must be >2% better than 4/4
            if 3 in scores and scores[3] > base_score * 1.02:
                best_beats = 3
                base_score = scores[3]
            # 5/4 must be >5% better (it's very rare)
            if 5 in scores and scores[5] > base_score * 1.05:
                best_beats = 5
        else:
            best_beats = max(scores, key=scores.get)

        downbeats = results[best_beats]
        best_time_sig = (best_beats, 4)

        # Convert to BeatEvent list
        beats = self._convert_to_beat_events(downbeats)

        # Calculate tempo from beat intervals
        tempo = self._calculate_tempo(downbeats)

        return beats, tempo, best_time_sig

    def _calculate_consistency_score(
        self, downbeats: np.ndarray, beats_per_bar: int
    ) -> float:
        """Calculate a consistency score for beat detection results.

        Uses both beat interval consistency AND downbeat interval consistency.
        Downbeat consistency is more important because it indicates proper
        measure boundaries.

        Args:
            downbeats: Array of shape (N, 2) with [time, beat_position]
            beats_per_bar: The number of beats per bar for this result

        Returns:
            Consistency score (higher = more consistent)
        """
        if len(downbeats) < 8:
            return 0.0

        beat_times = downbeats[:, 0]
        beat_positions = downbeats[:, 1]

        # Beat interval consistency
        beat_intervals = np.diff(beat_times)
        if len(beat_intervals) == 0:
            return 0.0

        beat_mean = np.mean(beat_intervals)
        if beat_mean == 0:
            return 0.0

        beat_cv = np.std(beat_intervals) / beat_mean

        # Downbeat interval consistency (more important)
        downbeat_mask = beat_positions == 1
        downbeat_times = beat_times[downbeat_mask]

        if len(downbeat_times) < 3:
            # Not enough downbeats, rely on beat consistency only
            return 1.0 / (1.0 + beat_cv * 10.0)

        downbeat_intervals = np.diff(downbeat_times)
        downbeat_mean = np.mean(downbeat_intervals)
        downbeat_cv = np.std(downbeat_intervals) / downbeat_mean

        # Expected downbeat interval based on beats_per_bar and beat interval
        expected_downbeat_interval = beat_mean * beats_per_bar
        downbeat_error = abs(downbeat_mean - expected_downbeat_interval) / expected_downbeat_interval

        # Combined score:
        # - Beat consistency (weight: 0.3)
        # - Downbeat consistency (weight: 0.4)
        # - Downbeat interval matches expected (weight: 0.3)
        beat_score = 1.0 / (1.0 + beat_cv * 10.0)
        downbeat_score = 1.0 / (1.0 + downbeat_cv * 10.0)
        match_score = 1.0 / (1.0 + downbeat_error * 5.0)

        return 0.3 * beat_score + 0.4 * downbeat_score + 0.3 * match_score

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
