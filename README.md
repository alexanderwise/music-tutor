# Music Tutor

Audio processing pipeline for music practice. Separates stems, detects beats and notes, aligns lyrics, and generates time-stretched versions.

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
