# Music Tutor

A music practice application that separates songs into individual instrument stems and provides tools for musicians to practice at various speeds with granular control over each instrument.

## What It Does

Music Tutor transforms audio files into structured, analyzable formats optimized for music practice:

- **Stem Separation** - Isolates vocals, drums, bass, guitar, piano, and other instruments using neural network models (htdemucs, Mel-Band RoFormer)
- **Beat Detection** - Identifies beats, tempo (BPM), time signatures, and downbeats using madmom
- **Pitch Detection** - Extracts MIDI notes with pitch bend curves from melodic stems via Spotify's basic-pitch
- **Lyrics Alignment** - Provides word-level timing through Whisper transcription
- **Speed Variants** - Pre-computes multiple playback speeds (0.5x, 0.75x, 1.0x, 1.25x) with pitch preservation

## Technology Stack

**Backend (Python):**
- Audio processing: librosa, soundfile, pyrubberband
- Stem separation: audio-separator (htdemucs, Mel-Band RoFormer)
- Beat detection: madmom
- Pitch detection: basic-pitch
- Lyrics: stable-ts, lrclibapi

**Frontend (React + Tauri):**
- React 18.3 with TypeScript
- Tauri 2 for cross-platform desktop
- TailwindCSS 4
- Web Audio API for stem mixing and playback

## Features

### Processing Pipeline
1. Ingest and normalize audio (44.1kHz stereo)
2. Separate into instrument stems
3. Detect beats, tempo, and time signature
4. Extract pitch/note information
5. Align lyrics with timing
6. Generate speed variants
7. Output analysis.json with complete metadata

### Player Interface
- Stem mixer with volume and mute controls
- Pro Tools-style soloing (multiple stems can solo simultaneously)
- Instant speed switching between pre-computed variants
- Loop points for focused section practice
- Beat and note visualization overlays

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv):

```bash
# System dependencies (macOS)
brew install ffmpeg rubberband

# Install with uv
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# Install madmom separately (packaging conflicts)
uv pip install "madmom @ git+https://github.com/The-Africa-Channel/madmom-py3.10-compat.git"
```

## Usage

```bash
# Process an audio file
music-tutor convert song.mp3

# Check configuration and tool availability
music-tutor info

# Re-analyze existing stems
music-tutor convert --output ./output/song --reanalyze
```

## Output Structure

```
output/song-name/
├── analysis.json          # Complete metadata
└── stems/
    ├── vocals_1.0x.flac
    ├── vocals_0.75x.flac
    ├── drums_1.0x.flac
    └── ...
```

## Development

```bash
# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check src/
```

---

## Background: Claude Code + Figma Integration Experiment

This project was created in late 2025 as an experiment to understand how Claude Code integrates with Figma's design tools. At the time, Anthropic had released MCP (Model Context Protocol) servers that allowed Claude Code to connect directly to Figma files, enabling a workflow where:

1. **Figma designs** could be referenced directly in Claude Code conversations
2. **Design context** (component structure, styles, spacing, colors) could be extracted automatically
3. **Code generation** could be informed by actual design specifications rather than verbal descriptions

The goal was to explore whether this integration could meaningfully accelerate the design-to-code workflow for a real application. Music Tutor served as the test case—a moderately complex UI with a player interface, stem controls, waveform visualizations, and song browsing that would benefit from precise design implementation.

### What Worked Well
- Extracting design tokens and color schemes directly from Figma
- Understanding component hierarchy and layout relationships
- Generating boilerplate React components that matched design structure
- The `get_design_context` tool provided useful CSS and layout information for individual components

### Challenges
- Complex interactive components (like the audio waveform and stem mixer) required significant manual refinement beyond what the Figma context could provide
- Design handoff worked best when Figma files were well-organized with clear naming conventions
- Real-time audio features and Web Audio API integration were outside the scope of what design tools could inform

### Lessons Learned
- The Figma MCP integration is most valuable for initial scaffolding and ensuring visual consistency with designs
- For applications with significant interactive or real-time components, the design context serves as a starting point rather than a complete specification
- Having both the design file and Claude Code in the same workflow reduced context-switching significantly compared to traditional design handoff processes

This experiment informed how AI-assisted development tools might better bridge the gap between design and implementation.
