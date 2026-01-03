"""Strike detection stage - detects individual hits in separated drum stems."""

from pathlib import Path

import librosa
import numpy as np

from music_tutor.models.analysis import DrumStrike
from music_tutor.models.pipeline import ProcessingContext, StageResult
from music_tutor.pipeline.base import PipelineStage


class StrikeDetectionStage(PipelineStage):
    """Stage 3d: Drum Strike Detection.

    Analyzes separated drum stems (kick, snare, toms, hi-hat, ride, crash)
    to detect individual strike timings and relative velocities.

    Only runs if drum separation was enabled and drum stems are available.
    Uses librosa's onset detection which works well on isolated percussion.

    Thresholds were empirically tuned to minimize false positives from
    bleed/noise while capturing real hits. A 50ms minimum gap filter
    removes double-triggers.
    """

    # Drum stems to analyze (from DrumSep output)
    DRUM_STEMS = ["kick", "snare", "toms", "hh", "ride", "crash"]

    # Minimum time between strikes (filters double-triggers from bleed)
    MIN_GAP_SEC = 0.050  # 50ms

    # Detection parameters empirically tuned per stem type
    # delta = onset strength threshold (higher = less sensitive)
    STEM_PARAMS = {
        # Kick: clean separation, can use lower threshold
        "kick": {"hop_length": 512, "backtrack": True, "delta": 0.05},
        # Snare: prone to bleed, needs higher threshold
        "snare": {"hop_length": 512, "backtrack": True, "delta": 0.25},
        # Toms: moderate threshold
        "toms": {"hop_length": 512, "backtrack": True, "delta": 0.12},
        # Hi-hat: high threshold to filter bleed
        "hh": {"hop_length": 512, "backtrack": False, "delta": 0.30},
        # Ride: similar to hi-hat
        "ride": {"hop_length": 512, "backtrack": False, "delta": 0.30},
        # Crash: moderate threshold (sparse hits)
        "crash": {"hop_length": 512, "backtrack": True, "delta": 0.12},
    }

    # Default params for unknown stems
    DEFAULT_PARAMS = {"hop_length": 512, "backtrack": True, "delta": 0.15}

    @property
    def name(self) -> str:
        return "strike_detection"

    def execute(self, context: ProcessingContext) -> StageResult:
        """Detect strikes in separated drum stems."""
        warnings: list[str] = []

        # Find drum stems (prefixed with "drum_" by separation stage)
        drum_stem_paths: dict[str, Path] = {}
        for stem_name, stem_path in context.stem_paths.items():
            if stem_name.startswith("drum_"):
                # Remove "drum_" prefix to get the actual drum name
                drum_name = stem_name[5:]  # "drum_kick" -> "kick"
                drum_stem_paths[drum_name] = stem_path

        if not drum_stem_paths:
            warnings.append("No separated drum stems found - skipping strike detection")
            return StageResult(
                success=True,
                stage_name=self.name,
                duration_seconds=0,
                warnings=warnings,
            )

        warnings.append(f"Analyzing {len(drum_stem_paths)} drum stems: {', '.join(drum_stem_paths.keys())}")

        # Detect strikes for each drum stem
        for drum_name, stem_path in drum_stem_paths.items():
            try:
                strikes = self._detect_strikes(stem_path, drum_name)
                context.drum_strikes[drum_name] = strikes
                warnings.append(f"  {drum_name}: {len(strikes)} strikes detected")
            except Exception as e:
                warnings.append(f"  {drum_name}: detection failed - {e}")

        return StageResult(
            success=True,
            stage_name=self.name,
            duration_seconds=0,
            warnings=warnings,
        )

    def _detect_strikes(self, audio_path: Path, stem_type: str) -> list[DrumStrike]:
        """Detect strike times and velocities from a drum stem.

        Args:
            audio_path: Path to the drum stem audio file
            stem_type: Type of drum (kick, snare, hh, etc.)

        Returns:
            List of DrumStrike objects with timing and velocity
        """
        # Load audio
        y, sr = librosa.load(audio_path, sr=44100)

        # Get parameters for this stem type
        params = self.STEM_PARAMS.get(stem_type, self.DEFAULT_PARAMS)

        # Compute onset strength envelope
        onset_env = librosa.onset.onset_strength(
            y=y,
            sr=sr,
            hop_length=params["hop_length"],
        )

        # Detect onsets using peak picking
        onset_frames = librosa.onset.onset_detect(
            y=y,
            sr=sr,
            hop_length=params["hop_length"],
            backtrack=params["backtrack"],
            delta=params["delta"],
        )

        # Convert frames to times
        onset_times = librosa.frames_to_time(
            onset_frames,
            sr=sr,
            hop_length=params["hop_length"],
        )

        # Get velocity (relative amplitude) at each onset
        # Normalize to 0-1 range based on max onset strength
        max_strength = onset_env.max() if onset_env.max() > 0 else 1.0
        velocities = onset_env[onset_frames] / max_strength

        # Apply minimum gap filter to remove double-triggers
        onset_times, velocities = self._filter_min_gap(onset_times, velocities)

        # Build list of DrumStrike objects
        strikes = [
            DrumStrike(time=float(t), velocity=float(v))
            for t, v in zip(onset_times, velocities)
        ]

        return strikes

    def _filter_min_gap(
        self, times: np.ndarray, velocities: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Remove onsets that are too close together.

        When two onsets are within MIN_GAP_SEC, keeps the one with higher velocity.

        Args:
            times: Array of onset times
            velocities: Array of onset velocities

        Returns:
            Filtered (times, velocities) tuple
        """
        if len(times) == 0:
            return times, velocities

        filtered_times = [times[0]]
        filtered_vels = [velocities[0]]

        for t, v in zip(times[1:], velocities[1:]):
            if t - filtered_times[-1] >= self.MIN_GAP_SEC:
                # Far enough apart, keep it
                filtered_times.append(t)
                filtered_vels.append(v)
            elif v > filtered_vels[-1]:
                # Too close but louder, replace previous
                filtered_times[-1] = t
                filtered_vels[-1] = v
            # else: too close and quieter, skip it

        return np.array(filtered_times), np.array(filtered_vels)
