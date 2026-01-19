"""
Offline processing module for song preparation.

This module contains tools for preparing songs:
- Feature extraction (BPM, RMS, complexity)
- Trajectory generation (pre-computed motor positions)
- Song management (library index)
"""

from .feature_extractor import FeatureExtractor, FeatureData, extract_features
from .trajectory_generator import (
    TrajectoryGenerator,
    TrajectoryConfig,
    generate_trajectory,
    save_trajectory,
    load_trajectory
)
from .song_manager import SongManager, SongMetadata, SongInfo, get_song_manager
from .prepare_song import prepare_song

__all__ = [
    # Feature extraction
    'FeatureExtractor',
    'FeatureData',
    'extract_features',

    # Trajectory generation
    'TrajectoryGenerator',
    'TrajectoryConfig',
    'generate_trajectory',
    'save_trajectory',
    'load_trajectory',

    # Song management
    'SongManager',
    'SongMetadata',
    'SongInfo',
    'get_song_manager',

    # CLI
    'prepare_song',
]
