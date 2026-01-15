"""
Offline Feature Extractor

Extracts music features from audio files for trajectory pre-computation.
All heavy librosa operations happen here, offline, not during playback.
"""

import librosa
import numpy as np
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class FeatureData:
    """Container for extracted audio features."""
    # Global properties
    bpm: float
    duration: float
    sample_rate: int

    # Time-indexed arrays (at ~100ms intervals)
    timestamps: np.ndarray      # Shape (num_frames,) - time in seconds
    rms: np.ndarray             # Shape (num_frames,) - RMS energy 0-1
    complexity: np.ndarray      # Shape (num_frames,) - spectral complexity 0-1

    # Beat information
    beat_times: np.ndarray      # Shape (num_beats,) - beat positions in seconds


class FeatureExtractor:
    """
    Extracts music features from an audio file.

    This class performs all heavy librosa operations offline,
    producing data that can be used for trajectory generation.
    """

    def __init__(self, audio_path: str, hop_length: int = 512, frame_duration: float = 0.1):
        """
        Initialize the feature extractor.

        Args:
            audio_path: Path to the audio file
            hop_length: Librosa hop length for spectral features
            frame_duration: Duration of each analysis frame in seconds (~100ms default)
        """
        self.audio_path = Path(audio_path)
        self.hop_length = hop_length
        self.frame_duration = frame_duration

        if not self.audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

    def extract(self) -> FeatureData:
        """
        Extract all features from the audio file.

        Returns:
            FeatureData containing all extracted features
        """
        print(f"Loading audio: {self.audio_path.name}")
        y, sr = librosa.load(str(self.audio_path), sr=None)
        duration = librosa.get_duration(y=y, sr=sr)
        print(f"  Duration: {duration:.2f}s, Sample rate: {sr} Hz")

        # Extract global BPM and beat times
        print("Extracting beats...")
        bpm, beat_times = self._extract_beats(y, sr)
        print(f"  BPM: {bpm:.1f}, Beats: {len(beat_times)}")

        # Create time-indexed feature arrays
        print("Extracting frame-by-frame features...")
        timestamps, rms, complexity = self._extract_frame_features(y, sr, duration)
        print(f"  Frames: {len(timestamps)} at {self.frame_duration*1000:.0f}ms intervals")

        return FeatureData(
            bpm=bpm,
            duration=duration,
            sample_rate=sr,
            timestamps=timestamps,
            rms=rms,
            complexity=complexity,
            beat_times=beat_times
        )

    def _extract_beats(self, y: np.ndarray, sr: int) -> tuple[float, np.ndarray]:
        """Extract global BPM and beat times."""
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=self.hop_length)
        bpm = float(tempo) if np.isscalar(tempo) else float(tempo[0])
        beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=self.hop_length)
        return bpm, beat_times

    def _extract_frame_features(self, y: np.ndarray, sr: int, duration: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Extract RMS and complexity at regular intervals.

        Returns:
            (timestamps, rms, complexity) arrays
        """
        # Create timestamps at frame_duration intervals
        num_frames = int(duration / self.frame_duration) + 1
        timestamps = np.linspace(0, duration, num_frames)

        # Pre-allocate arrays
        rms_values = np.zeros(num_frames)
        complexity_values = np.zeros(num_frames)

        # Window size in samples (centered on each timestamp)
        window_samples = int(self.frame_duration * sr * 2)  # 2x frame duration for overlap

        for i, t in enumerate(timestamps):
            # Get audio segment centered at time t
            center_sample = int(t * sr)
            start_sample = max(0, center_sample - window_samples // 2)
            end_sample = min(len(y), center_sample + window_samples // 2)

            segment = y[start_sample:end_sample]

            if len(segment) < sr * 0.05:  # Skip if segment too short
                continue

            # Extract RMS
            rms = librosa.feature.rms(y=segment, hop_length=self.hop_length)[0]
            rms_mean = float(np.mean(rms))
            # Normalize to 0-1 range (multiply by 3, cap at 1)
            rms_values[i] = min(rms_mean * 3.0, 1.0)

            # Extract complexity
            complexity_values[i] = self._calculate_complexity(segment, sr)

        return timestamps, rms_values, complexity_values

    def _calculate_complexity(self, segment: np.ndarray, sr: int) -> float:
        """
        Calculate spectral complexity for an audio segment.

        Uses weighted combination of:
        - Spectral centroid (brightness)
        - Spectral centroid variance (variation)
        - Spectral bandwidth (frequency spread)
        - Spectral rolloff (high frequency content)
        - Zero crossing rate (percussiveness)
        - Spectral flux (dynamics)
        """
        # Spectral Centroid
        spectral_centroid = librosa.feature.spectral_centroid(
            y=segment, sr=sr, hop_length=self.hop_length
        )[0]
        centroid_mean = float(np.mean(spectral_centroid))
        centroid_std = float(np.std(spectral_centroid))

        # Spectral Bandwidth
        spectral_bandwidth = librosa.feature.spectral_bandwidth(
            y=segment, sr=sr, hop_length=self.hop_length
        )[0]
        bandwidth_mean = float(np.mean(spectral_bandwidth))

        # Spectral Rolloff
        spectral_rolloff = librosa.feature.spectral_rolloff(
            y=segment, sr=sr, hop_length=self.hop_length
        )[0]
        rolloff_mean = float(np.mean(spectral_rolloff))

        # Zero Crossing Rate
        zcr = librosa.feature.zero_crossing_rate(
            y=segment, hop_length=self.hop_length
        )[0]
        zcr_mean = float(np.mean(zcr))

        # Spectral Flux
        stft = librosa.stft(y=segment)
        spectral_flux = np.sum(np.abs(np.diff(stft)), axis=0)
        flux_mean = float(np.mean(spectral_flux))

        # Normalize each component to 0-1 range
        centroid_norm = np.clip((centroid_mean - 500) / 3500, 0.0, 1.0)      # 500-4000Hz range
        centroid_var_norm = np.clip(centroid_std / 500.0, 0.0, 1.0)          # Variance
        bandwidth_norm = np.clip((bandwidth_mean - 1000) / 4000, 0.0, 1.0)   # 1000-5000Hz range
        rolloff_norm = np.clip((rolloff_mean - 2000) / 6000, 0.0, 1.0)       # 2000-8000Hz range
        zcr_norm = np.clip(zcr_mean * 20, 0.0, 1.0)                          # Percussiveness
        flux_norm = np.clip(flux_mean / 1000.0, 0.0, 1.0)                    # Dynamics

        # Weighted combination (same weights as original music_analyzer.py)
        complexity = (
            0.10 * centroid_norm +       # Brightness
            0.25 * centroid_var_norm +   # Variation in brightness
            0.25 * bandwidth_norm +      # Frequency spread
            0.15 * rolloff_norm +        # High frequency content
            0.10 * zcr_norm +            # Percussiveness
            0.15 * flux_norm             # Dynamics
        )

        return float(complexity)


def extract_features(audio_path: str, frame_duration: float = 0.1) -> FeatureData:
    """
    Convenience function to extract features from an audio file.

    Args:
        audio_path: Path to the audio file
        frame_duration: Duration of each analysis frame in seconds

    Returns:
        FeatureData containing all extracted features
    """
    extractor = FeatureExtractor(audio_path, frame_duration=frame_duration)
    return extractor.extract()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python feature_extractor.py <audio_file>")
        sys.exit(1)

    audio_path = sys.argv[1]
    features = extract_features(audio_path)

    print(f"\nExtracted features:")
    print(f"  BPM: {features.bpm:.1f}")
    print(f"  Duration: {features.duration:.2f}s")
    print(f"  Beats: {len(features.beat_times)}")
    print(f"  Frames: {len(features.timestamps)}")
    print(f"  RMS range: {features.rms.min():.3f} - {features.rms.max():.3f}")
    print(f"  Complexity range: {features.complexity.min():.3f} - {features.complexity.max():.3f}")
