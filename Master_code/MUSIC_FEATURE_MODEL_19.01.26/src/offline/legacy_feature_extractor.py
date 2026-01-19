"""
Legacy Feature Extractor

Uses the original MusicAnalyzer sliding window approach for feature extraction.
This produces more dynamic, music-responsive features compared to the standard extractor.

Key differences from standard extractor:
- Larger sliding window (2 seconds) centered at each timestamp
- Higher sample rate (20Hz = 50ms intervals)
- Features calculated fresh for each timestamp (not interpolated)
"""

import librosa
import numpy as np
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LegacyFeatureData:
    """Container for legacy extracted audio features."""
    # Global properties
    bpm: float
    duration: float
    sample_rate: int

    # Time-indexed arrays (at 50ms intervals for 20Hz update rate)
    timestamps: np.ndarray      # Shape (num_frames,) - time in seconds
    rms: np.ndarray             # Shape (num_frames,) - RMS energy 0-1
    complexity: np.ndarray      # Shape (num_frames,) - spectral complexity 0-1
    local_tempo: np.ndarray     # Shape (num_frames,) - local BPM at each timestamp

    # Beat information
    beat_times: np.ndarray      # Shape (num_beats,) - beat positions in seconds


class LegacyFeatureExtractor:
    """
    Feature extractor using the original MusicAnalyzer sliding window approach.

    This produces more dynamic features that respond better to musical transients.
    Uses a 2-second sliding window centered at each timestamp.
    """

    def __init__(self, audio_path: str, window_size: float = 2.0, hop_length: int = 512):
        """
        Initialize the legacy feature extractor.

        Args:
            audio_path: Path to the audio file
            window_size: Size of the sliding window in seconds (default: 2.0)
            hop_length: Librosa hop length for spectral features
        """
        self.audio_path = Path(audio_path)
        self.window_size = window_size
        self.hop_length = hop_length

        if not self.audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

    def extract(self, frame_duration: float = 0.05) -> LegacyFeatureData:
        """
        Extract features using the legacy sliding window approach.

        Args:
            frame_duration: Duration between feature samples in seconds (default: 0.05 = 20Hz)

        Returns:
            LegacyFeatureData containing all extracted features
        """
        print(f"Loading audio: {self.audio_path.name}")
        y, sr = librosa.load(str(self.audio_path), sr=None)
        duration = librosa.get_duration(y=y, sr=sr)
        print(f"  Duration: {duration:.2f}s, Sample rate: {sr} Hz")

        # Extract global BPM and beat times
        print("Extracting beats...")
        bpm, beat_times = self._extract_beats(y, sr)
        print(f"  BPM: {bpm:.1f}, Beats: {len(beat_times)}")

        # Create timestamps at frame_duration intervals (20Hz = 50ms default)
        num_frames = int(duration / frame_duration) + 1
        timestamps = np.linspace(0, duration, num_frames)
        print(f"Extracting features at {num_frames} timestamps ({1/frame_duration:.0f}Hz)...")

        # Pre-allocate arrays
        rms_values = np.zeros(num_frames)
        complexity_values = np.zeros(num_frames)

        # Extract features using sliding window (the key difference!)
        for i, t in enumerate(timestamps):
            if i % 100 == 0:
                print(f"  Processing: {t:.1f}s / {duration:.1f}s", end='\r')

            rms, complexity = self._extract_features_at_time(y, sr, t, duration)
            rms_values[i] = rms
            complexity_values[i] = complexity

        print(f"  Processing complete: {num_frames} frames")

        # Extract local tempo from beat intervals
        print("Extracting local tempo...")
        local_tempo = self._extract_local_tempo(beat_times, timestamps, bpm)
        tempo_range = local_tempo.max() - local_tempo.min()
        print(f"  Local tempo range: {local_tempo.min():.1f} - {local_tempo.max():.1f} BPM (variance: {tempo_range:.1f})")

        return LegacyFeatureData(
            bpm=bpm,
            duration=duration,
            sample_rate=sr,
            timestamps=timestamps,
            rms=rms_values,
            complexity=complexity_values,
            local_tempo=local_tempo,
            beat_times=beat_times
        )

    def _extract_beats(self, y: np.ndarray, sr: int) -> tuple[float, np.ndarray]:
        """Extract global BPM and beat times."""
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=self.hop_length)
        bpm = float(tempo) if np.isscalar(tempo) else float(tempo[0])
        beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=self.hop_length)
        return bpm, beat_times

    def _extract_features_at_time(self, y: np.ndarray, sr: int, current_time: float, duration: float) -> tuple[float, float]:
        """
        Extract music features for a sliding window centered at current_time.

        This is the key method from the original MusicAnalyzer - uses a 2-second
        sliding window centered at the current time.

        Args:
            y: Audio signal
            sr: Sample rate
            current_time: Current time in seconds
            duration: Total duration

        Returns:
            tuple: (rms, complexity)
        """
        # Calculate window boundaries (centered at current_time)
        window_start = max(0, current_time - self.window_size / 2)
        window_end = min(duration, current_time + self.window_size / 2)

        # Convert time to sample indices
        start_sample = int(window_start * sr)
        end_sample = int(window_end * sr)

        # Extract audio segment
        audio_segment = y[start_sample:end_sample]

        if len(audio_segment) < sr * 0.05:  # Skip if segment too short
            return 0.0, 0.0

        # Extract RMS energy
        rms = librosa.feature.rms(y=audio_segment, hop_length=self.hop_length)[0]
        rms_mean = float(np.mean(rms))
        # Normalize to 0-1 range
        rms_normalized = min(rms_mean * 3.0, 1.0)

        # Calculate spectral complexity
        complexity = self._calculate_complexity(audio_segment, sr)

        return rms_normalized, complexity

    def _calculate_complexity(self, segment: np.ndarray, sr: int) -> float:
        """
        Calculate spectral complexity for an audio segment.

        Uses the same weighted combination as the original MusicAnalyzer:
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
        flux_norm = np.clip(flux_mean / 1000.0, 0.0, 1.0)

        # Normalize each component to 0-1 range (same as original)
        centroid_norm = np.clip((centroid_mean - 500) / 3500, 0.0, 1.0)      # 500-4000Hz range
        centroid_var_norm = np.clip(centroid_std / 500.0, 0.0, 1.0)          # Variation
        bandwidth_norm = np.clip((bandwidth_mean - 1000) / 4000, 0.0, 1.0)   # 1000-5000Hz range
        rolloff_norm = np.clip((rolloff_mean - 2000) / 6000, 0.0, 1.0)       # 2000-8000Hz range
        zcr_norm = np.clip(zcr_mean * 20, 0.0, 1.0)                          # Percussiveness
        # flux_norm already normalized above

        # Weighted combination (same weights as original MusicAnalyzer)
        complexity = (
            0.10 * centroid_norm +       # Brightness
            0.25 * centroid_var_norm +   # Variation in brightness
            0.25 * bandwidth_norm +      # Frequency spread
            0.15 * rolloff_norm +        # High frequency content
            0.10 * zcr_norm +            # Percussiveness
            0.15 * flux_norm             # Dynamics
        )

        return float(complexity)

    def _extract_local_tempo(self, beat_times: np.ndarray, timestamps: np.ndarray, global_bpm: float) -> np.ndarray:
        """
        Extract local tempo (BPM) at each timestamp from beat intervals.

        Args:
            beat_times: Array of detected beat positions in seconds
            timestamps: Target timestamps for local tempo values
            global_bpm: Global BPM to use as fallback

        Returns:
            Array of local BPM values at each timestamp
        """
        if len(beat_times) < 3:
            return np.full(len(timestamps), global_bpm)

        # Calculate inter-beat intervals (IBI) and their midpoint times
        ibis = np.diff(beat_times)
        ibi_times = (beat_times[:-1] + beat_times[1:]) / 2

        # Convert IBIs to instantaneous BPM
        local_bpms = 60.0 / ibis

        # Filter out unrealistic tempo values (20-300 BPM range)
        valid_mask = (local_bpms >= 20) & (local_bpms <= 300)
        if np.sum(valid_mask) < 2:
            return np.full(len(timestamps), global_bpm)

        valid_times = ibi_times[valid_mask]
        valid_bpms = local_bpms[valid_mask]

        # Smooth the tempo curve using a simple moving average (5-beat window)
        window_size = min(5, len(valid_bpms))
        if window_size > 1:
            kernel = np.ones(window_size) / window_size
            smoothed_bpms = np.convolve(valid_bpms, kernel, mode='same')
        else:
            smoothed_bpms = valid_bpms

        # Interpolate to target timestamps
        local_tempo = np.interp(
            timestamps,
            valid_times,
            smoothed_bpms,
            left=smoothed_bpms[0],
            right=smoothed_bpms[-1]
        )

        return local_tempo


def extract_legacy_features(audio_path: str, window_size: float = 2.0, frame_duration: float = 0.05) -> LegacyFeatureData:
    """
    Convenience function to extract features using the legacy approach.

    Args:
        audio_path: Path to the audio file
        window_size: Sliding window size in seconds (default: 2.0)
        frame_duration: Duration between samples in seconds (default: 0.05 = 20Hz)

    Returns:
        LegacyFeatureData containing all extracted features
    """
    extractor = LegacyFeatureExtractor(audio_path, window_size=window_size)
    return extractor.extract(frame_duration=frame_duration)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python legacy_feature_extractor.py <audio_file>")
        sys.exit(1)

    audio_path = sys.argv[1]
    features = extract_legacy_features(audio_path)

    print(f"\nExtracted legacy features:")
    print(f"  BPM: {features.bpm:.1f}")
    print(f"  Duration: {features.duration:.2f}s")
    print(f"  Beats: {len(features.beat_times)}")
    print(f"  Frames: {len(features.timestamps)} ({1/(features.timestamps[1]-features.timestamps[0]):.0f}Hz)")
    print(f"  RMS range: {features.rms.min():.3f} - {features.rms.max():.3f}")
    print(f"  Complexity range: {features.complexity.min():.3f} - {features.complexity.max():.3f}")
    print(f"  Local tempo range: {features.local_tempo.min():.1f} - {features.local_tempo.max():.1f} BPM")
