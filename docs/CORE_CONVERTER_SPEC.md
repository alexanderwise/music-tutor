# Music Tutor: Core Converter Specification

> **Version:** 0.1.0-draft
> **Last Updated:** 2025-12-27
> **Status:** Ready for Implementation

## Table of Contents

1. [Overview](#overview)
2. [Goals and Non-Goals](#goals-and-non-goals)
3. [Architecture](#architecture)
4. [Data Models](#data-models)
5. [Processing Pipeline](#processing-pipeline)
6. [Tool Integration](#tool-integration)
7. [File Organization](#file-organization)
8. [Research Spikes](#research-spikes)
9. [Performance Considerations](#performance-considerations)
10. [Testing Strategy](#testing-strategy)
11. [Implementation Phases](#implementation-phases)
12. [Dependencies](#dependencies)

---

## Overview

The Music Tutor Core Converter transforms audio files (MP3, FLAC, M4A, etc.) into a structured analysis format containing:

- **Separated stems** (vocals, drums, bass, other) at multiple playback speeds
- **Beat/tempo data** extracted from rhythmic stems
- **Pitch/note data** extracted from melodic stems as MIDI note tuples
- **Lyrics timing** (when available) synchronized across playback speeds

This enables a practice interface where musicians can:
- Mute/solo individual instruments
- Slow down playback to 0.5x, 0.75x, 1.0x, or 1.25x
- Loop specific sections for focused practice
- View note/chord information per stem

---

## Goals and Non-Goals

### Goals

1. **High-quality stem separation** using Mel-Band Roformer (SOTA as of 2024)
2. **Accurate beat detection** with downbeat tracking for proper measure alignment
3. **Pitch detection** with pitch bend information for expressive playing
4. **Pre-computed time-stretched versions** for instant speed switching during playback
5. **Portable output format** that can be consumed by web, desktop, or mobile clients
6. **Robust error handling** with graceful degradation when tools fail

### Non-Goals (for this phase)

- Real-time audio processing during playback
- Chord recognition/harmonic analysis (future enhancement)
- Key detection (future enhancement)
- Music notation rendering
- User interface implementation
- Audio recording/comparison features

---

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Input Audio File                            │
│                    (MP3, FLAC, M4A, WAV, etc.)                      │
└─────────────────────────────────────────┬───────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Stage 1: Ingest & Normalize                     │
│  • Validate audio format                                            │
│  • Convert to WAV (44.1kHz, stereo) if needed                       │
│  • Extract metadata (duration, sample rate)                         │
│  • Detect accompanying .lrc/.txt lyrics files                       │
└─────────────────────────────────────────┬───────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Stage 2: Stem Separation                        │
│  • Run Mel-Band Roformer via audio-separator                        │
│  • Output: vocals, drums, bass, other stems (WAV)                   │
│  • Store paths in processing context                                │
└─────────────────────────────────────────┬───────────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐
│  Stage 3a: Beat       │  │  Stage 3b: Pitch      │  │  Stage 3c: Lyrics     │
│  Detection            │  │  Detection            │  │  Alignment            │
│  • madmom on drums    │  │  • basic-pitch on     │  │  • stable-ts on       │
│  • Extract beats +    │  │    vocals, bass,      │  │    vocals stem        │
│    downbeats          │  │    other              │  │  • Word-level timing  │
│  • Calculate tempo    │  │  • MIDI note tuples   │  │    with confidence    │
└───────────┬───────────┘  └───────────┬───────────┘  └───────────┬───────────┘
            │                          │                          │
            └──────────────────────────┼──────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Stage 4: Time Stretching                        │
│  • Run pyrubberband on each stem                                    │
│  • Generate 0.5x, 0.75x, 1.25x versions                             │
│  • Scale all timestamps in analysis data                            │
└─────────────────────────────────────────┬───────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Stage 5: Finalize                               │
│  • Write analysis JSON file                                         │
│  • Organize stems into output directory                             │
│  • Generate manifest for client consumption                         │
└─────────────────────────────────────────────────────────────────────┘
```

### Design Principles (from karaoke-homelab-app learnings)

1. **Stage-based pipeline** - Each stage is a separate class with `execute(context) -> StageResult`
2. **Mutable context** - `ProcessingContext` accumulates results as it passes through stages
3. **Graceful degradation** - Try primary tool, fall back to secondary (e.g., madmom → librosa)
4. **Subprocess execution** - Shell out to CLI tools rather than deep library integration
5. **Venv-aware command resolution** - Check venv bin directory before PATH
6. **File-based output** - All analysis data saved alongside stems for portability

---

## Data Models

### Core Analysis Structure

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class SongAnalysis:
    """Root analysis object, serialized to JSON alongside stems."""

    # Metadata
    title: str | None
    artist: str | None
    album: str | None
    original_duration: float  # seconds
    sample_rate: int
    tempo_bpm: float | None
    time_signature: tuple[int, int] | None  # e.g., (4, 4)

    # Processing info
    source_file: str  # original filename
    processing_date: str  # ISO format
    converter_version: str

    # Stem availability (relative paths from analysis file)
    stems: dict[str, StemInfo]  # {"vocals": ..., "drums": ..., "bass": ..., "other": ...}

    # Analysis data (at 1.0x speed - scale for other speeds)
    beats: list[BeatEvent]
    notes: dict[str, list[Note]]  # keyed by stem name
    lyrics: LyricsData | None


@dataclass
class StemInfo:
    """Information about a separated stem."""
    name: str  # "vocals", "drums", "bass", "other"

    # Relative paths to audio files at each speed
    paths: dict[str, str]  # {"1.0x": "stems/vocals_1.0x.flac", ...}

    # Whether pitch detection was run on this stem
    has_notes: bool

    # Peak loudness for UI normalization
    peak_db: float


@dataclass
class BeatEvent:
    """A beat or downbeat event."""
    time: float  # seconds (at 1.0x speed)
    type: Literal["beat", "downbeat"]
    beat_in_measure: int | None  # 1, 2, 3, 4 for 4/4 time


@dataclass
class Note:
    """A detected note with timing and pitch information."""
    start: float  # seconds
    end: float  # seconds
    pitch: int  # MIDI note number (0-127)
    velocity: float  # 0.0-1.0 (from basic-pitch confidence)
    pitch_bend: list[PitchBendPoint] | None  # optional pitch bend curve


@dataclass
class PitchBendPoint:
    """A point in a pitch bend curve."""
    time: float  # seconds (relative to note start)
    cents: float  # deviation in cents from base pitch


@dataclass
class LyricsData:
    """Word-level lyrics with timing."""
    source: Literal["lrc", "txt", "transcribed"]  # how lyrics were obtained
    lines: list[LyricLine]


@dataclass
class LyricLine:
    """A line of lyrics with word-level timing."""
    text: str  # full line text
    start: float  # seconds
    end: float  # seconds
    words: list[LyricWord]


@dataclass
class LyricWord:
    """A single word with timing."""
    text: str
    start: float  # seconds
    end: float  # seconds
    confidence: float  # 0.0-1.0 (from alignment model)
```

### Processing Context

```python
@dataclass
class ProcessingContext:
    """Mutable state passed through pipeline stages."""

    # Input
    source_path: Path
    source_lyrics_path: Path | None  # .lrc or .txt if found

    # Directories
    temp_dir: Path  # for intermediate files
    output_dir: Path  # final output location

    # Normalized audio (Stage 1)
    normalized_audio_path: Path | None = None
    duration: float | None = None
    sample_rate: int | None = None

    # Metadata extracted from tags
    title: str | None = None
    artist: str | None = None
    album: str | None = None

    # Stem paths (Stage 2) - keys are stem names
    stem_paths: dict[str, Path] = field(default_factory=dict)

    # Beat data (Stage 3a)
    beats: list[BeatEvent] = field(default_factory=list)
    tempo_bpm: float | None = None
    time_signature: tuple[int, int] | None = None

    # Note data (Stage 3b) - keyed by stem name
    notes: dict[str, list[Note]] = field(default_factory=dict)

    # Lyrics data (Stage 3c)
    lyrics: LyricsData | None = None

    # Time-stretched stems (Stage 4) - stem_name -> speed -> path
    stretched_stems: dict[str, dict[str, Path]] = field(default_factory=dict)

    # Final output
    analysis_path: Path | None = None


@dataclass
class StageResult:
    """Result of a pipeline stage execution."""
    success: bool
    stage_name: str
    duration_seconds: float
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)
```

---

## Processing Pipeline

### Stage 1: Ingest & Normalize

**Purpose:** Prepare audio for processing, extract metadata, detect lyrics files.

**Input:** Path to audio file (any format supported by ffmpeg)
**Output:** WAV file (44.1kHz, 16-bit, stereo), metadata populated in context

**Implementation:**

```python
class IngestStage(PipelineStage):
    name = "ingest"

    def execute(self, context: ProcessingContext) -> StageResult:
        # 1. Validate file exists and is audio
        # 2. Extract metadata using mutagen
        # 3. Convert to normalized WAV using ffmpeg
        # 4. Look for .lrc or .txt lyrics file with same base name
        # 5. Calculate duration and sample rate
        pass
```

**Key Decisions:**
- Use ffmpeg for format conversion (universal support)
- Output 44.1kHz to match common audio-separator model training
- Stereo output even for mono sources (models expect stereo)

### Stage 2: Stem Separation

**Purpose:** Separate audio into constituent stems using Mel-Band Roformer.

**Input:** Normalized WAV
**Output:** Individual stem WAV files (vocals, drums, bass, other)

**Implementation:**

```python
class SeparationStage(PipelineStage):
    name = "separation"

    # Model options (see Research Spikes for comparison)
    MODEL_OPTIONS = {
        "mel_band_roformer": "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt",
        "mel_band_roformer_kim": "vocals_mel_band_roformer.ckpt",  # 12.6 SDR
        "htdemucs": "htdemucs",  # fallback
    }

    def execute(self, context: ProcessingContext) -> StageResult:
        # 1. Run audio-separator CLI
        # 2. Parse output to find stem files
        # 3. Rename/organize stems
        # 4. Validate all expected stems exist
        pass
```

**audio-separator CLI invocation:**
```bash
audio-separator \
    --model_filename "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt" \
    --model_file_dir "/path/to/models" \
    --output_dir "/path/to/temp" \
    --output_format "wav" \
    "/path/to/input.wav"
```

**Expected output files pattern:**
- `{input}_(Vocals)_model.wav`
- `{input}_(Drums)_model.wav`
- `{input}_(Bass)_model.wav`
- `{input}_(Other)_model.wav`

### Stage 3a: Beat Detection

**Purpose:** Extract beat positions and tempo from drums stem.

**Input:** Drums stem WAV
**Output:** List of BeatEvents, tempo BPM, time signature

**Implementation:**

```python
class BeatDetectionStage(PipelineStage):
    name = "beat_detection"

    def execute(self, context: ProcessingContext) -> StageResult:
        """Detect beats using madmom. Fails if madmom unavailable."""
        drums_path = context.stem_paths.get("drums")
        if not drums_path:
            return StageResult(
                success=False,
                stage_name=self.name,
                error_message="No drums stem available for beat detection",
            )

        try:
            import madmom
        except ImportError as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                error_message=f"madmom not installed correctly: {e}. "
                    "See docs for uv installation instructions.",
            )

        return self._detect_beats_madmom(context, drums_path)

    def _detect_beats_madmom(
        self, context: ProcessingContext, drums_path: Path
    ) -> StageResult:
        """Detect beats and downbeats using madmom's neural network."""
        import madmom

        # RNNDownBeatProcessor -> DBNDownBeatTrackingProcessor
        # Returns: [(time, beat_position), ...]
        # beat_position: 1 = downbeat, 2-4 = other beats in measure
        pass
```

**madmom implementation detail:**
```python
import madmom

proc = madmom.features.downbeats.RNNDownBeatProcessor()
dbn = madmom.features.downbeats.DBNDownBeatTrackingProcessor(
    beats_per_bar=[4, 3],  # support 4/4 and 3/4
    fps=100,
)

activations = proc(str(drums_stem_path))
downbeats = dbn(activations)

# downbeats: np.array of shape (N, 2)
# Column 0: time in seconds
# Column 1: beat position (1 = downbeat)
```

### Stage 3b: Pitch Detection

**Purpose:** Extract MIDI note information from melodic stems.

**Input:** Vocals, bass, and other stems
**Output:** Note lists with pitch, timing, velocity, and pitch bend

**Implementation:**

```python
class PitchDetectionStage(PipelineStage):
    name = "pitch_detection"

    # Which stems to analyze
    MELODIC_STEMS = ["vocals", "bass", "other"]

    def execute(self, context: ProcessingContext) -> StageResult:
        for stem_name in self.MELODIC_STEMS:
            stem_path = context.stem_paths.get(stem_name)
            if stem_path:
                notes = self._detect_notes(stem_path)
                context.notes[stem_name] = notes
        return StageResult(success=True, ...)

    def _detect_notes(self, audio_path: Path) -> list[Note]:
        from basic_pitch.inference import predict
        from basic_pitch import ICASSP_2022_MODEL_PATH

        model_output, midi_data, note_events = predict(str(audio_path))

        # note_events: list of (start_time, end_time, pitch, velocity, pitch_bend)
        # pitch_bend is optional array of (time, cents) tuples

        return [
            Note(
                start=e[0],
                end=e[1],
                pitch=e[2],
                velocity=e[3],
                pitch_bend=self._convert_pitch_bend(e[4]) if len(e) > 4 else None
            )
            for e in note_events
        ]
```

**basic-pitch output format:**
- Returns `(model_output, midi_data, note_events)`
- `note_events`: List of tuples with start, end, pitch (MIDI), amplitude, pitch_bend
- Pitch bend is raw model output that needs conversion to cents

### Stage 3c: Lyrics Alignment

**Purpose:** Align lyrics to vocal stem with word-level timing.

**Input:** Vocals stem + optional .lrc/.txt lyrics file
**Output:** LyricsData with word-level timing

**Implementation:**

```python
class LyricsAlignmentStage(PipelineStage):
    name = "lyrics_alignment"

    def execute(self, context: ProcessingContext) -> StageResult:
        if not context.stem_paths.get("vocals"):
            return StageResult(success=True, warnings=["No vocals stem"])

        if context.source_lyrics_path:
            # Forced alignment with existing lyrics
            return self._forced_align(context)
        else:
            # Full transcription
            return self._transcribe(context)

    def _forced_align(self, context: ProcessingContext) -> StageResult:
        """Use stable-ts to align existing lyrics to audio."""
        import stable_whisper

        model = stable_whisper.load_model("base")
        result = model.align(
            str(context.stem_paths["vocals"]),
            self._load_lyrics_text(context.source_lyrics_path),
            language="en",
        )
        # Convert to LyricsData
        pass

    def _transcribe(self, context: ProcessingContext) -> StageResult:
        """Use stable-ts to transcribe and align."""
        import stable_whisper

        model = stable_whisper.load_model("base")
        result = model.transcribe(str(context.stem_paths["vocals"]))
        # Convert to LyricsData
        pass
```

**stable-ts output format:**
- Returns result with `.segments` containing word-level timing
- Each segment has `.words` list with start, end, word, probability

### Stage 4: Time Stretching

**Purpose:** Create time-stretched versions of all stems.

**Input:** All stem WAV files at 1.0x
**Output:** Additional stems at 0.5x, 0.75x, 1.25x speeds

**Implementation:**

```python
class TimeStretchStage(PipelineStage):
    name = "time_stretch"

    SPEEDS = [0.5, 0.75, 1.25]  # 1.0x is the original

    def execute(self, context: ProcessingContext) -> StageResult:
        for stem_name, stem_path in context.stem_paths.items():
            context.stretched_stems[stem_name] = {"1.0x": stem_path}

            for speed in self.SPEEDS:
                stretched = self._stretch(stem_path, speed)
                context.stretched_stems[stem_name][f"{speed}x"] = stretched

        return StageResult(success=True, ...)

    def _stretch(self, audio_path: Path, rate: float) -> Path:
        import librosa
        import pyrubberband
        import soundfile as sf

        y, sr = librosa.load(str(audio_path), sr=None, mono=False)
        y_stretched = pyrubberband.time_stretch(y, sr, rate)

        output_path = audio_path.with_stem(f"{audio_path.stem}_{rate}x")
        sf.write(str(output_path), y_stretched.T, sr)

        return output_path
```

**pyrubberband notes:**
- `rate > 1.0` = faster playback (time compression)
- `rate < 1.0` = slower playback (time stretch)
- Preserves pitch while changing tempo

### Stage 5: Finalize

**Purpose:** Generate analysis JSON and organize output files.

**Input:** Fully populated ProcessingContext
**Output:** Organized output directory with analysis.json and stems

**Implementation:**

```python
class FinalizeStage(PipelineStage):
    name = "finalize"

    def execute(self, context: ProcessingContext) -> StageResult:
        # 1. Create output directory structure
        # 2. Copy/move stems to final locations
        # 3. Convert stems to FLAC for space efficiency
        # 4. Build SongAnalysis object
        # 5. Write analysis.json
        # 6. Cleanup temp directory
        pass
```

---

## Tool Integration

### audio-separator

**Package:** [nomadkaraoke/python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator)
**Installation:** `pip install audio-separator[cpu]` or `audio-separator[gpu]`

**Model Selection:**
The default model is `model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt`. See Research Spikes for comparison testing.

**GPU Support:**
- CUDA: `pip install audio-separator[gpu]`
- CoreML (macOS): Should work automatically
- CPU fallback: Slower but reliable

**CLI vs Python API:**
Prefer CLI invocation (subprocess) for:
- Better isolation from Python version conflicts
- Easier debugging (can reproduce manually)
- Consistent with karaoke-homelab-app patterns

### madmom

**Package:** [CPJKU/madmom](https://github.com/CPJKU/madmom)

**⚠️ CRITICAL: Packaging Issues Require uv**

madmom has complex dependency conflicts with modern Python (3.11+) and PyTorch versions. The karaoke-homelab-app project resolved this by switching to `uv` for dependency management. **pip alone cannot reliably resolve madmom's dependencies.**

**Installation (requires uv):**
```bash
# Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install madmom from the compatibility fork
uv pip install "madmom @ git+https://github.com/The-Africa-Channel/madmom-py3.10-compat.git"
```

**Why uv is required:**
- madmom's PyPI release (0.12) only supports Python ≤3.9
- The main repo now claims 3.11/3.12 support but has transitive dependency conflicts
- uv's resolver handles the numpy/cython/pytorch version matrix that breaks pip

**PyTorch Compatibility Workaround:**
May need pre-import patch for older model checkpoints:

```python
# Apply BEFORE importing madmom
import torch
_original_load = torch.load
def _patched_load(*args, **kwargs):
    kwargs.setdefault('weights_only', False)
    return _original_load(*args, **kwargs)
torch.load = _patched_load
```

**No Fallback Strategy:**
We intentionally do NOT fall back to librosa for beat detection. librosa's `beat_track` uses onset strength envelope detection (finds "loud moments") rather than learned musical beat patterns. It cannot detect downbeats and performs poorly on syncopated music. For a music learning application, incorrect beat data is worse than no beat data.

If madmom fails, the pipeline should **fail loudly** so we can fix the installation rather than silently producing unusable beat data.

### basic-pitch

**Package:** [spotify/basic-pitch](https://github.com/spotify/basic-pitch)
**Installation:** `pip install basic-pitch`

**Model Backend Selection:**
- macOS: CoreML (default)
- Linux: TensorFlowLite (default)
- Windows: ONNX (default)
- TensorFlow: `pip install basic-pitch[tf]`

**Performance Notes:**
- ~17K parameters, <20MB peak memory
- Fast inference suitable for batch processing
- Instrument-agnostic (works on vocals, bass, guitar, etc.)

**Pitch Bend Extraction:**
basic-pitch provides raw pitch contour data. To extract pitch bend:

```python
# model_output contains continuous pitch estimates
# Compare to quantized MIDI pitch to get bend in cents
pitch_bend = (continuous_pitch - midi_pitch) * 100  # cents
```

### pyrubberband

**Package:** [bmcfee/pyrubberband](https://github.com/bmcfee/pyrubberband)
**Installation:** `pip install pyrubberband`

**System Dependency:**
Requires `rubberband` CLI tool:
- macOS: `brew install rubberband`
- Ubuntu: `apt install rubberband-cli`
- Windows: Download from [Rubber Band releases](https://breakfastquay.com/rubberband/)

**Usage Notes:**
- Processes via temp files (not real-time)
- High quality time stretching with pitch preservation
- `time_stretch(y, sr, rate)` where rate > 1 = faster

### stable-ts

**Package:** [jianfch/stable-ts](https://github.com/jianfch/stable-ts)
**Installation:** `pip install stable-ts`

**Features Used:**
- `model.align()` - Forced alignment with existing lyrics
- `model.transcribe()` - Full transcription with alignment
- Word-level timing with confidence scores

**Model Selection:**
- `base` - Good balance of speed and accuracy
- `small` or `medium` - Better accuracy, slower
- See Research Spikes for testing

---

## File Organization

### Output Directory Structure

```
{song_name}/
├── analysis.json           # SongAnalysis serialized
├── stems/
│   ├── vocals/
│   │   ├── vocals_0.5x.flac
│   │   ├── vocals_0.75x.flac
│   │   ├── vocals_1.0x.flac
│   │   └── vocals_1.25x.flac
│   ├── drums/
│   │   ├── drums_0.5x.flac
│   │   └── ...
│   ├── bass/
│   │   └── ...
│   └── other/
│       └── ...
└── source/
    └── original.{ext}      # Copy of original file (optional)
```

### analysis.json Schema

```json
{
  "$schema": "https://music-tutor.local/schemas/analysis-v1.json",
  "version": "1.0.0",
  "metadata": {
    "title": "Song Title",
    "artist": "Artist Name",
    "album": "Album Name",
    "originalDuration": 245.32,
    "sampleRate": 44100,
    "tempoBpm": 120.5,
    "timeSignature": [4, 4]
  },
  "processing": {
    "sourceFile": "song.mp3",
    "processingDate": "2025-12-27T15:30:00Z",
    "converterVersion": "0.1.0",
    "separationModel": "mel_band_roformer_ep_3005",
    "beatDetectionMethod": "madmom",
    "pitchDetectionModel": "basic-pitch-icassp-2022"
  },
  "stems": {
    "vocals": {
      "name": "vocals",
      "paths": {
        "0.5x": "stems/vocals/vocals_0.5x.flac",
        "0.75x": "stems/vocals/vocals_0.75x.flac",
        "1.0x": "stems/vocals/vocals_1.0x.flac",
        "1.25x": "stems/vocals/vocals_1.25x.flac"
      },
      "hasNotes": true,
      "peakDb": -3.2
    }
  },
  "beats": [
    {"time": 0.5, "type": "downbeat", "beatInMeasure": 1},
    {"time": 1.0, "type": "beat", "beatInMeasure": 2}
  ],
  "notes": {
    "vocals": [
      {
        "start": 5.2,
        "end": 5.8,
        "pitch": 60,
        "velocity": 0.85,
        "pitchBend": [
          {"time": 0.1, "cents": 15},
          {"time": 0.3, "cents": -10}
        ]
      }
    ]
  },
  "lyrics": {
    "source": "lrc",
    "lines": [
      {
        "text": "Hello world",
        "start": 5.0,
        "end": 6.5,
        "words": [
          {"text": "Hello", "start": 5.0, "end": 5.5, "confidence": 0.95},
          {"text": "world", "start": 5.6, "end": 6.5, "confidence": 0.92}
        ]
      }
    ]
  }
}
```

---

## Research Spikes

### Spike 1: Separation Model Comparison

**Goal:** Determine best audio-separator model for stem quality.

**Test Matrix:**

| Model | Vocals SDR | Drums SDR | Bass SDR | Other SDR | Speed |
|-------|-----------|----------|---------|----------|-------|
| mel_band_roformer (default) | ? | ? | ? | ? | ? |
| vocals_mel_band_roformer | ? | ? | ? | ? | ? |
| htdemucs | ? | ? | ? | ? | ? |

**Test Files:**
- `samples/06 Stevie Nix.mp3` - Clear vocals, standard rock
- `samples/28.-Under Pressure (Feat. Queen).flac` - Duet, complex arrangement
- `samples/boygenius - the record - 05 Cool About It.mp3` - Multiple voices

**Evaluation Criteria:**
1. Subjective quality (listening test)
2. Separation artifacts (bleeding between stems)
3. Processing time
4. Note detection accuracy on separated stems

**Deliverable:** Recommendation document with model choice and rationale.

### Spike 2: Beat Detection Reliability

**Goal:** Validate madmom installation and evaluate beat/downbeat detection accuracy.

**Test Matrix:**

| Track | Actual BPM | madmom BPM | Downbeat Accuracy | Install Issues |
|-------|-----------|-----------|-------------------|----------------|
| Standard 4/4 rock | ? | ? | ?/4 correct | |
| 3/4 waltz | ? | ? | ?/3 correct | |
| Syncopated funk | ? | ? | ?/4 correct | |
| Variable tempo | ? | ? | tracks changes? | |

**Installation Validation:**
1. Confirm madmom imports without errors on Python 3.11+
2. Verify PyTorch compatibility patch works
3. Test on both macOS and Linux if possible
4. Document any additional workarounds needed

**Evaluation Criteria:**
1. BPM accuracy (within 1 BPM of known tempo)
2. Beat placement accuracy (within 50ms of actual beat)
3. Downbeat detection reliability (correct on >80% of measures)
4. Handling of tempo changes

**Deliverable:** Installation guide and accuracy report. No fallback - if madmom doesn't work reliably, we need to fix it or find an alternative neural beat tracker.

### Spike 3: Lyrics Alignment Quality

**Goal:** Evaluate stable-ts alignment accuracy with separated vocals.

**Test Cases:**
1. Clear vocals with existing LRC → forced alignment
2. Clear vocals without LRC → transcription
3. Backing vocals present → transcription accuracy

**Evaluation Criteria:**
1. Word boundary accuracy (±100ms)
2. Transcription word error rate
3. Handling of overlapping vocals

**Deliverable:** Alignment confidence thresholds and fallback strategies.

### Spike 4: Time Stretch Quality

**Goal:** Verify pyrubberband quality at extreme stretch ratios.

**Test Points:**
- 0.5x (half speed) - most extreme stretch
- 0.75x - common practice speed
- 1.25x - slight speedup

**Evaluation Criteria:**
1. Artifacts at 0.5x (warbling, phasing)
2. Transient preservation in drums
3. Pitch stability in vocals

**Deliverable:** Acceptable speed range and quality notes.

### Spike 5: Output Format Optimization

**Goal:** Balance file size vs quality for stretched stems.

**Options:**
1. FLAC (lossless, larger)
2. Opus (lossy, smaller, good quality)
3. AAC (lossy, universal support)

**Evaluation:**
- File size per track at each format/quality
- Audible quality degradation
- Client compatibility

**Deliverable:** Recommended output format and encoding settings.

---

## Performance Considerations

### Processing Time Estimates

| Stage | Estimated Time (5-min track) | GPU Acceleration |
|-------|------------------------------|-----------------|
| Ingest | 5-10s | No |
| Separation | 2-5 min (CPU), 30-60s (GPU) | Yes |
| Beat Detection | 10-30s | No |
| Pitch Detection | 30-60s per stem | Partial |
| Lyrics Alignment | 30-60s | Yes (Whisper) |
| Time Stretching | 30-60s per stem per speed | No |
| Finalize | 10-20s | No |

**Total:** ~10-20 minutes per track (CPU), ~3-5 minutes (GPU)

### Parallelization Opportunities

1. **Stage 3a/3b/3c** - Beat, pitch, and lyrics can run in parallel
2. **Time stretching** - Multiple stems can stretch in parallel
3. **Pitch detection** - Multiple stems can analyze in parallel

### Memory Considerations

- audio-separator: ~4-8GB VRAM for GPU, ~8GB RAM for CPU
- basic-pitch: <20MB peak memory
- pyrubberband: Loads full audio into memory (~50MB per 5-min stereo track)

### Disk Space

Per 5-minute track:
- Stems at 1.0x: ~200MB (4 stems × ~50MB WAV, ~40MB FLAC)
- All speeds: ~800MB WAV, ~160MB FLAC
- Analysis JSON: ~50-500KB depending on note density

---

## Testing Strategy

### Unit Tests

```python
# test_data_models.py
def test_song_analysis_serialization():
    """SongAnalysis round-trips through JSON."""

def test_beat_event_types():
    """BeatEvent validates type field."""

# test_stages.py
def test_ingest_extracts_metadata():
    """IngestStage extracts artist/title from tags."""

def test_ingest_finds_lrc_file():
    """IngestStage detects adjacent .lrc file."""
```

### Integration Tests

```python
# test_pipeline.py
def test_full_pipeline_with_sample():
    """Process samples/04 California English.mp3 end-to-end."""

def test_pipeline_without_lyrics():
    """Process samples/Grady Scott.mp3 (no LRC) end-to-end."""

def test_pipeline_with_flac():
    """Process samples/28.-Under Pressure.flac end-to-end."""
```

### Sample Files Available

| File | Has LRC | Notes |
|------|---------|-------|
| 02 - Masterpiece (2023 Remaster).mp3 | .txt only | Test txt lyrics handling |
| 04 California English.mp3 | Yes | Standard test case |
| 06 Stevie Nix.mp3 | Yes | Rock with clear vocals |
| 07-the_hold_steady-you_can_make_him_like_you.mp3 | Yes | Fast lyrics |
| 10-The Chain-Fleetwood Mac.mp3 | Yes | Multi-voice, tempo changes |
| 11-r.e.m.-nightswimming.mp3 | Yes | Piano-heavy, sparse vocals |
| 28.-Under Pressure.flac | Yes | Duet, high quality source |
| Grady Scott.mp3 | No | Test transcription |
| Stevie Nicks & Tom Petty - Stop Draggin' My Heart Around.mp3 | .txt only | Duet |
| Tom Petty & Bob Dylan - Knockin' On Heaven's Door.mp3 | Yes (sparse) | Test minimal LRC |
| boygenius - the record - 05 Cool About It.mp3 | Yes | Harmony vocals |

---

## Implementation Phases

### Phase 1: Project Setup & Basic Pipeline

**Deliverables:**
- [ ] Project structure with pyproject.toml, uv support
- [ ] Configuration management (pydantic-settings)
- [ ] CLI skeleton with Click
- [ ] Pipeline framework (base stage, orchestrator, context)
- [ ] IngestStage implementation
- [ ] Basic test infrastructure

**Exit Criteria:** Can run `music-tutor convert samples/test.mp3` and see ingestion output.

### Phase 2: Stem Separation

**Deliverables:**
- [ ] SeparationStage with audio-separator integration
- [ ] Model configuration options
- [ ] Stem file handling and validation
- [ ] Integration test with sample file

**Exit Criteria:** Can produce 4 separated stems from any input audio.

### Phase 3: Analysis Stages

**Deliverables:**
- [ ] BeatDetectionStage (madmom + librosa fallback)
- [ ] PitchDetectionStage (basic-pitch)
- [ ] LyricsAlignmentStage (stable-ts)
- [ ] Parallel execution of analysis stages

**Exit Criteria:** Analysis JSON contains beats, notes, and lyrics data.

### Phase 4: Time Stretching

**Deliverables:**
- [ ] TimeStretchStage (pyrubberband)
- [ ] Configurable speed presets
- [ ] FLAC output encoding
- [ ] Timestamp scaling for stretched versions

**Exit Criteria:** Output directory contains stems at all speed variants.

### Phase 5: Finalization & Polish

**Deliverables:**
- [ ] FinalizeStage with JSON generation
- [ ] Output directory organization
- [ ] Progress reporting/callbacks
- [ ] Error handling and recovery
- [ ] Documentation and usage examples

**Exit Criteria:** Full end-to-end processing with clean output.

### Phase 6: Research Spikes

**Deliverables:**
- [ ] Spike 1: Model comparison results
- [ ] Spike 2: Beat detection evaluation
- [ ] Spike 3: Lyrics alignment evaluation
- [ ] Spike 4: Time stretch quality evaluation
- [ ] Spike 5: Output format decision

**Exit Criteria:** Configuration defaults updated based on findings.

---

## Dependencies

### Package Manager: uv (Required)

This project uses [uv](https://github.com/astral-sh/uv) for dependency management. **pip cannot reliably resolve the dependency conflicts** between madmom, PyTorch, numpy, and cython on Python 3.11+.

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### pyproject.toml

```toml
[project]
name = "music-tutor"
version = "0.1.0"
requires-python = ">=3.11,<3.14"

dependencies = [
    # CLI and config
    "click>=8.1.0",
    "rich>=13.0.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",

    # Audio I/O
    "librosa>=0.10.0",
    "soundfile>=0.12.0",
    "mutagen>=1.47.0",  # metadata extraction

    # Stem separation
    "audio-separator>=0.25.0",
    "onnxruntime>=1.16.0",

    # Beat detection - MUST be installed via uv from git (see below)
    # Cannot be listed here due to packaging issues

    # Pitch detection
    "basic-pitch>=0.3.0",

    # Lyrics alignment
    "stable-ts>=2.15.0",

    # Time stretching
    "pyrubberband>=0.3.0",
]

[project.optional-dependencies]
gpu = [
    "audio-separator[gpu]",
]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
]

[project.scripts]
music-tutor = "music_tutor.cli:main"
```

### Installation

```bash
# System dependencies (macOS)
brew install ffmpeg rubberband

# System dependencies (Ubuntu/Debian)
apt install ffmpeg rubberband-cli

# Create venv and install project
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Install madmom separately (packaging conflicts prevent listing in pyproject.toml)
uv pip install "madmom @ git+https://github.com/The-Africa-Channel/madmom-py3.10-compat.git"
```

### Why madmom Can't Be in pyproject.toml

madmom has known packaging issues:
1. PyPI version (0.12) only supports Python ≤3.9
2. Requires specific numpy/cython versions that conflict with other deps
3. Has circular dependency issues with PyTorch

The workaround is to install it separately after the main dependencies. uv's resolver can handle this when done as a separate step.

---

## References

- [audio-separator GitHub](https://github.com/nomadkaraoke/python-audio-separator)
- [Mel-Band RoFormer paper](https://arxiv.org/abs/2310.01809)
- [basic-pitch GitHub](https://github.com/spotify/basic-pitch)
- [madmom GitHub](https://github.com/CPJKU/madmom)
- [pyrubberband GitHub](https://github.com/bmcfee/pyrubberband)
- [stable-ts GitHub](https://github.com/jianfch/stable-ts)
- [karaoke-homelab-app](~/git/karaoke-homelab-app) - Architecture patterns

---

## Appendix A: Timestamp Scaling for Time-Stretched Audio

When playing audio at different speeds, all timestamp-based data must be scaled:

```python
def scale_timestamp(original_time: float, speed: float) -> float:
    """Scale timestamp for different playback speeds.

    Args:
        original_time: Time in seconds at 1.0x speed
        speed: Playback speed (0.5 = half speed, 2.0 = double speed)

    Returns:
        Time in seconds at the given speed
    """
    return original_time / speed

# Examples:
# 10.0s at 1.0x → 20.0s at 0.5x (slowed down, takes longer)
# 10.0s at 1.0x → 13.33s at 0.75x
# 10.0s at 1.0x → 8.0s at 1.25x (sped up, happens sooner)
```

The analysis.json always stores timestamps at 1.0x speed. Clients scale on-the-fly based on selected speed.

---

## Appendix B: Error Handling Strategy

### Recoverable Errors

| Error | Recovery |
|-------|----------|
| Lyrics file not found | Skip lyrics stage, continue |
| Single stem fails pitch detection | Log warning, continue with others |
| Time stretch fails for one speed | Log warning, omit that speed |

### Fatal Errors

| Error | Behavior |
|-------|----------|
| Input file not found | Abort with clear message |
| Input not audio | Abort with format error |
| Separation fails completely | Abort (core functionality) |
| madmom import/execution fails | Abort with install instructions (no fallback) |
| Output directory not writable | Abort with permission error |

### Error Reporting

```python
@dataclass
class ProcessingResult:
    success: bool
    output_path: Path | None
    stages_completed: list[str]
    stages_skipped: list[str]
    errors: list[str]
    warnings: list[str]
    total_duration: float
```
