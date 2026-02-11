"""
Global Configuration

Centralized configuration for the music-synchronized motor control system.
"""

from pathlib import Path
from dataclasses import dataclass


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
SONGS_DIR = PROJECT_ROOT / "songs"
SONGS_LEGACY_DIR = PROJECT_ROOT / "songs_legacy"
CONFIG_DIR = PROJECT_ROOT / "config"
LEGACY_DIR = SRC_DIR / "legacy"

# Ensure directories exist
SONGS_DIR.mkdir(parents=True, exist_ok=True)
SONGS_LEGACY_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class MotorConfig:
    """Motor and mechanical configuration."""
    gear_ratio: float = 15.0           # Motor turns : output turns
    max_amplitude: float = 7.5         # Maximum amplitude in motor turns
    control_rate_hz: float = 60.0      # Control loop rate

    # Motor velocity limits for amplitude attenuation
    # Turnigy SK8-6374 BLDC motor: 192 KV, physical max ~6144 RPM at 32V
    # Using conservative limit to prevent overcurrent/overvoltage at high BPM
    motor_rpm_max: float = 5500.0      # Conservative max motor RPM (below 6144 physical limit)
    motor_turns_per_sec_max: float = motor_rpm_max / 60.0  # ~83.3 turns/sec


@dataclass
class AudioConfig:
    """Audio configuration."""
    sample_rate: int = 44100           # Audio sample rate
    blocksize: int = 1024              # Audio buffer block size


@dataclass
class TrajectoryConfig:
    """Trajectory generation configuration."""
    resolution_ms: float = 10.0        # Trajectory time resolution


# Default configurations
MOTOR_CONFIG = MotorConfig()
AUDIO_CONFIG = AudioConfig()
TRAJECTORY_CONFIG = TrajectoryConfig()


def get_latency_config_path() -> Path:
    """Get path to latency calibration config."""
    return CONFIG_DIR / "latency.json"


def get_songs_index_path() -> Path:
    """Get path to song library index."""
    return SONGS_DIR / "index.json"
