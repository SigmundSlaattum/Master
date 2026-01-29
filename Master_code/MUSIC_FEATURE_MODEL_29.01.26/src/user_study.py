#!/usr/bin/env python3
"""
User Study Module

Manages user study workflow for evaluating different motion patterns:
- Randomizes song and pattern order
- Tracks progress through the study
- Provides study configuration and state

Study Design:
- 3 songs selected by user, each with individual settings (library, tempo mode)
- For each song: 3 patterns in random order (no motion, simple, complex)
- Random order of songs (all 3 patterns completed for one song before next)
"""

import random
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum


class PatternType(Enum):
    """Motion pattern types for user study."""
    NONE = "none"      # No motion (amplitude = 0)
    SIMPLE = "simple"  # Single sinusoid
    COMPLEX = "complex"  # Dual sinusoid based on features


@dataclass
class SongConfig:
    """Configuration for a single song in the study."""
    song_id: str
    song_name: str
    library: str  # 'standard' or 'legacy'
    tempo_mode: str  # 'fixed' or 'dynamic'


@dataclass
class Trial:
    """A single trial in the study."""
    song_config: SongConfig
    pattern: PatternType
    trial_number: int  # Overall trial number (1-9 for 3 songs x 3 patterns)
    song_index: int  # Which song (0-2)
    pattern_index: int  # Which pattern for this song (0-2)


@dataclass
class UserStudyState:
    """State of an active user study."""
    song_configs: List[SongConfig]
    song_order: List[int]  # Randomized indices into song_configs
    pattern_orders: Dict[int, List[PatternType]]  # Randomized pattern order per song
    current_song_idx: int = 0  # Index into song_order
    current_pattern_idx: int = 0  # Index into pattern_orders[song]
    completed_trials: List[Trial] = field(default_factory=list)
    is_active: bool = True
    # Recording settings
    record_data: bool = True
    folder_name: str = ""


class UserStudyManager:
    """
    Manages user study workflow.

    This class handles study setup, randomization, and progress tracking.
    It does NOT interact with playback or motor control directly - those
    are handled by app.py to keep CPU-heavy code out of this module.
    """

    def __init__(self):
        self.current_study: Optional[UserStudyState] = None

    def setup_study(self, song_configs: List[SongConfig],
                    record_data: bool = True, folder_name: str = "") -> bool:
        """
        Set up a new user study with the given song configurations.

        Args:
            song_configs: List of 3 SongConfig objects
            record_data: Whether to record data for each trial
            folder_name: Folder name for saving data files

        Returns:
            True if setup successful
        """
        if len(song_configs) != 3:
            raise ValueError("User study requires exactly 3 songs")

        # Randomize song order
        song_order = list(range(3))
        random.shuffle(song_order)

        # Randomize pattern order for each song
        patterns = [PatternType.NONE, PatternType.SIMPLE, PatternType.COMPLEX]
        pattern_orders = {}
        for i in range(3):
            order = patterns.copy()
            random.shuffle(order)
            pattern_orders[i] = order

        self.current_study = UserStudyState(
            song_configs=song_configs,
            song_order=song_order,
            pattern_orders=pattern_orders,
            current_song_idx=0,
            current_pattern_idx=0,
            record_data=record_data,
            folder_name=folder_name
        )

        return True

    def get_current_trial(self) -> Optional[Trial]:
        """
        Get the current trial to run.

        Returns:
            Trial object with song config and pattern, or None if study complete
        """
        if self.current_study is None or not self.current_study.is_active:
            return None

        study = self.current_study

        # Check if study is complete
        if study.current_song_idx >= 3:
            study.is_active = False
            return None

        # Get current song (in randomized order)
        song_idx = study.song_order[study.current_song_idx]
        song_config = study.song_configs[song_idx]

        # Get current pattern (in randomized order for this song)
        pattern = study.pattern_orders[song_idx][study.current_pattern_idx]

        # Calculate overall trial number
        trial_number = study.current_song_idx * 3 + study.current_pattern_idx + 1

        return Trial(
            song_config=song_config,
            pattern=pattern,
            trial_number=trial_number,
            song_index=study.current_song_idx,
            pattern_index=study.current_pattern_idx
        )

    def complete_current_trial(self) -> Optional[Trial]:
        """
        Mark the current trial as complete and advance to next.

        Returns:
            The next trial, or None if study complete
        """
        if self.current_study is None or not self.current_study.is_active:
            return None

        study = self.current_study

        # Get and record the completed trial
        completed_trial = self.get_current_trial()
        if completed_trial:
            study.completed_trials.append(completed_trial)

        # Advance to next pattern
        study.current_pattern_idx += 1

        # If all patterns for this song done, advance to next song
        if study.current_pattern_idx >= 3:
            study.current_pattern_idx = 0
            study.current_song_idx += 1

        # Check if study is complete
        if study.current_song_idx >= 3:
            study.is_active = False
            return None

        return self.get_current_trial()

    def get_study_progress(self) -> dict:
        """
        Get study progress information.

        Returns:
            Dict with progress info
        """
        if self.current_study is None:
            return {
                'active': False,
                'total_trials': 0,
                'completed_trials': 0,
                'current_trial': None,
                'songs_completed': 0
            }

        study = self.current_study
        current_trial = self.get_current_trial()

        return {
            'active': study.is_active,
            'total_trials': 9,  # 3 songs x 3 patterns
            'completed_trials': len(study.completed_trials),
            'songs_completed': study.current_song_idx,
            'current_trial': {
                'song_id': current_trial.song_config.song_id if current_trial else None,
                'song_name': current_trial.song_config.song_name if current_trial else None,
                'library': current_trial.song_config.library if current_trial else None,
                'pattern': current_trial.pattern.value if current_trial else None,
                'trial_number': current_trial.trial_number if current_trial else None,
                'song_index': current_trial.song_index if current_trial else None,
                'pattern_index': current_trial.pattern_index if current_trial else None
            } if current_trial else None
        }

    def get_trajectory_filename(self, trial: Trial) -> str:
        """
        Get the trajectory filename for a trial.

        Args:
            trial: The trial to get trajectory for

        Returns:
            Trajectory filename (e.g., 'trajectory.npy', 'trajectory_simple_dynamic.npy')
        """
        pattern = trial.pattern
        tempo_mode = trial.song_config.tempo_mode

        # No motion pattern uses standard trajectory but amplitude=0
        # So we still need a trajectory file (just won't move)
        if pattern == PatternType.NONE:
            # Use complex trajectory (doesn't matter since amplitude=0)
            if tempo_mode == 'dynamic':
                return 'trajectory_dynamic.npy'
            return 'trajectory.npy'

        if pattern == PatternType.SIMPLE:
            if tempo_mode == 'dynamic':
                return 'trajectory_simple_dynamic.npy'
            return 'trajectory_simple.npy'

        # COMPLEX
        if tempo_mode == 'dynamic':
            return 'trajectory_dynamic.npy'
        return 'trajectory.npy'

    def get_user_amplitude(self, pattern: PatternType) -> float:
        """
        Get the user amplitude for a pattern.

        Args:
            pattern: The pattern type

        Returns:
            User amplitude (0.0 for NONE, 0.5 for others)
        """
        if pattern == PatternType.NONE:
            return 0.0
        return 0.5  # Default starting amplitude for simple/complex

    def cancel_study(self):
        """Cancel the current study."""
        if self.current_study:
            self.current_study.is_active = False
        self.current_study = None

    def is_active(self) -> bool:
        """Check if a study is currently active."""
        return self.current_study is not None and self.current_study.is_active

    def should_record_data(self) -> bool:
        """Check if data recording is enabled for this study."""
        if self.current_study is None:
            return False
        return self.current_study.record_data

    def get_folder_name(self) -> str:
        """Get the folder name for saving data."""
        if self.current_study is None:
            return ""
        return self.current_study.folder_name

    def get_trial_filename(self, trial: Trial, file_type: str) -> str:
        """
        Generate a filename for trial data.

        Args:
            trial: The trial
            file_type: Type of file (e.g., 'data', 'plot_separate', 'plot_combined')

        Returns:
            Filename like: songName__pattern__type
        """
        if self.current_study is None:
            return ""

        # Sanitize song name (remove special characters)
        song_name = trial.song_config.song_name.replace(' ', '_').replace('/', '-')
        song_name = ''.join(c for c in song_name if c.isalnum() or c in ('_', '-'))
        pattern = trial.pattern.value

        return f"{song_name}__{pattern}__{file_type}"

    def get_completed_trials_summary(self) -> List[dict]:
        """
        Get summary of completed trials.

        Returns:
            List of dicts with trial info
        """
        if self.current_study is None:
            return []

        summary = []
        for trial in self.current_study.completed_trials:
            summary.append({
                'trial_number': trial.trial_number,
                'song_name': trial.song_config.song_name,
                'library': trial.song_config.library,
                'tempo_mode': trial.song_config.tempo_mode,
                'pattern': trial.pattern.value
            })

        return summary
