"""Configuration management for Music Tutor."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="MUSIC_TUTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Directories
    output_dir: Path = Field(
        default=Path("./output"),
        description="Default output directory for processed files",
    )
    temp_dir: Path = Field(
        default=Path("/tmp/music-tutor"),
        description="Temporary directory for intermediate files",
    )
    model_dir: Path = Field(
        default=Path("~/.cache/music-tutor/models").expanduser(),
        description="Directory for downloaded ML models",
    )

    # Stem separation
    separation_model: str = Field(
        default="htdemucs_6s.yaml",
        description="Model for stem separation. Options: htdemucs_6s.yaml (6-stem with guitar/piano), "
        "htdemucs_ft.yaml (4-stem highest quality), model_bs_roformer_ep_317_sdr_12.9755.ckpt (best vocals)",
    )
    separate_drums: bool = Field(
        default=False,
        description="Run DrumSep to separate drums into kick, snare, toms, hi-hat, ride, crash",
    )
    use_gpu: bool = Field(
        default=False,
        description="Use GPU acceleration if available",
    )

    # Time stretching
    speed_presets: list[float] = Field(
        default=[0.5, 0.75, 1.0, 1.25],
        description="Speed variants to generate",
    )

    # Output format
    output_format: str = Field(
        default="flac",
        description="Audio output format (flac, wav, opus)",
    )

    # Processing
    sample_rate: int = Field(
        default=44100,
        description="Target sample rate for processing",
    )
    keep_temp_files: bool = Field(
        default=False,
        description="Keep intermediate files for debugging",
    )


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def configure(**overrides: object) -> Settings:
    """Configure settings with overrides. Useful for testing."""
    global _settings
    _settings = Settings(**overrides)  # type: ignore[arg-type]
    return _settings
