"""
Core runtime module for music-synchronized motor control.

This module contains the CPU-light components for real-time playback:
- AudioPlayer: Sample-accurate audio playback (master clock)
- TrajectoryPlayer: Pre-computed position lookup
- MotorDriver: ODrive interface
- PlaybackController: Main orchestrator
"""

from .audio_player import AudioPlayer, get_audio_player
from .trajectory_player import TrajectoryPlayer, load_trajectory_player
from .motor_driver import MotorDriver, create_motor_driver
from .playback_controller import (
    PlaybackController,
    PlaybackStats,
    create_playback_controller
)

__all__ = [
    # Audio
    'AudioPlayer',
    'get_audio_player',

    # Trajectory
    'TrajectoryPlayer',
    'load_trajectory_player',

    # Motor
    'MotorDriver',
    'create_motor_driver',

    # Controller
    'PlaybackController',
    'PlaybackStats',
    'create_playback_controller',
]
