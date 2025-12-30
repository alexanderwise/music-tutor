"""Pytest fixtures for Music Tutor tests."""

from pathlib import Path

import pytest


@pytest.fixture
def samples_dir() -> Path:
    """Return the path to the samples directory."""
    return Path(__file__).parent.parent / "samples"


@pytest.fixture
def sample_mp3(samples_dir: Path) -> Path:
    """Return a sample MP3 file for testing."""
    # Find any MP3 file in samples
    mp3_files = list(samples_dir.glob("*.mp3"))
    if not mp3_files:
        pytest.skip("No MP3 files found in samples directory")
    return mp3_files[0]


@pytest.fixture
def sample_flac(samples_dir: Path) -> Path:
    """Return a sample FLAC file for testing."""
    flac_files = list(samples_dir.glob("*.flac"))
    if not flac_files:
        pytest.skip("No FLAC files found in samples directory")
    return flac_files[0]


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Return a temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir
