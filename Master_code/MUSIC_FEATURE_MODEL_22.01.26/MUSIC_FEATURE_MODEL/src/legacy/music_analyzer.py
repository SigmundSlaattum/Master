import librosa
import numpy as np
import threading
import time


class MusicAnalyzer:
    """
    Real-time music feature extraction using librosa with sliding window analysis.
    Extracts BPM, RMS energy, and complexity (spectral features) from audio.
    """

    def __init__(self, audio_file, window_size=2.0, hop_length=512):
        """
        Initialize the music analyzer.

        Args:
            audio_file: Path to the audio file to analyze
            window_size: Size of the sliding window in seconds (default: 5.0)
            hop_length: Number of samples between successive frames (default: 512)
        """
        self.audio_file = audio_file
        self.window_size = window_size
        self.hop_length = hop_length

        # Load audio file
        print(f"Loading audio file: {audio_file}")
        self.y, self.sr = librosa.load(audio_file, sr=None)
        self.duration = librosa.get_duration(y=self.y, sr=self.sr)
        print(f"Audio loaded: {self.duration:.2f} seconds, sample rate: {self.sr} Hz")

        # Calculate global BPM and beat timing
        self.global_bpm, self.beat_times = self._extract_global_bpm_and_beats()

        # Extract onset envelope for beat-accurate timing
        self.onset_env = librosa.onset.onset_strength(y=self.y, sr=self.sr, hop_length=self.hop_length)
        self.onset_frames = librosa.onset.onset_detect(onset_envelope=self.onset_env, sr=self.sr, hop_length=self.hop_length)
        self.onset_times = librosa.frames_to_time(self.onset_frames, sr=self.sr, hop_length=self.hop_length)
        print(f"Detected {len(self.onset_times)} onsets")

        # Current feature values
        self.current_bpm = self.global_bpm
        self.current_rms = 0.0
        self.current_complexity = 0.0
        self.current_beat_phase = 0.0  # Phase within current beat (0-1)

        # Thread control
        self._running = False
        self._thread = None

    def _extract_global_bpm_and_beats(self):
        """Extract the global BPM and beat times from the entire track."""
        tempo, beat_frames = librosa.beat.beat_track(y=self.y, sr=self.sr, hop_length=self.hop_length)
        bpm = float(tempo)
        beat_times = librosa.frames_to_time(beat_frames, sr=self.sr, hop_length=self.hop_length)
        print(f"Detected global BPM: {bpm:.2f}")
        print(f"Detected {len(beat_times)} beats")
        return bpm, beat_times

    def get_beat_phase(self, current_time):
        """
        Get the phase within the current beat (0.0 to 1.0).

        Args:
            current_time: Current playback time in seconds

        Returns:
            float: Phase within beat (0.0 = beat start, 1.0 = next beat)
        """
        if len(self.beat_times) == 0:
            # Fallback to calculated phase based on BPM
            beat_duration = 60.0 / self.global_bpm
            return (current_time % beat_duration) / beat_duration

        # Find the nearest beat before current time
        beat_idx = np.searchsorted(self.beat_times, current_time) - 1

        if beat_idx < 0:
            beat_idx = 0

        if beat_idx >= len(self.beat_times) - 1:
            # Use last beat and calculated interval
            beat_duration = 60.0 / self.global_bpm
            time_since_last_beat = current_time - self.beat_times[-1]
            return (time_since_last_beat % beat_duration) / beat_duration

        # Calculate phase between two detected beats
        current_beat_time = self.beat_times[beat_idx]
        next_beat_time = self.beat_times[beat_idx + 1]
        beat_duration = next_beat_time - current_beat_time

        time_since_beat = current_time - current_beat_time
        phase = time_since_beat / beat_duration

        return np.clip(phase, 0.0, 1.0)

    def _extract_features_at_time(self, current_time):
        """
        Extract music features for a sliding window centered at current_time.

        Args:
            current_time: Current playback time in seconds

        Returns:
            tuple: (bpm, rms, complexity)
        """
        # Calculate window boundaries
        window_start = max(0, current_time - self.window_size / 2)
        window_end = min(self.duration, current_time + self.window_size / 2)

        # Convert time to sample indices
        start_sample = int(window_start * self.sr)
        end_sample = int(window_end * self.sr)

        # Extract audio segment
        audio_segment = self.y[start_sample:end_sample]

        if len(audio_segment) == 0:
            return self.global_bpm, 0.0, 0.0

        # Extract RMS energy
        rms = librosa.feature.rms(y=audio_segment, hop_length=self.hop_length)[0]
        rms_mean = float(np.mean(rms))

        # Calculate spectral complexity using multiple features
        # 1. Spectral Centroid - brightness/center of mass of spectrum
        spectral_centroid = librosa.feature.spectral_centroid(y=audio_segment, sr=self.sr, hop_length=self.hop_length)[0]
        centroid_mean = float(np.mean(spectral_centroid))
        centroid_std = float(np.std(spectral_centroid))

        # 2. Spectral Bandwidth - spread of frequency content
        spectral_bandwidth = librosa.feature.spectral_bandwidth(y=audio_segment, sr=self.sr, hop_length=self.hop_length)[0]
        bandwidth_mean = float(np.mean(spectral_bandwidth))

        # 3. Spectral Rolloff - frequency below which 85% of energy is contained
        spectral_rolloff = librosa.feature.spectral_rolloff(y=audio_segment, sr=self.sr, hop_length=self.hop_length)[0]
        rolloff_mean = float(np.mean(spectral_rolloff))

        # 4. Zero Crossing Rate - percussiveness/noisiness
        zcr = librosa.feature.zero_crossing_rate(y=audio_segment, hop_length=self.hop_length)[0]
        zcr_mean = float(np.mean(zcr))
        
        # 5. Spectral Flux - rate of change in spectrum (captures dynamics)
        spectral_flux = np.sum(np.abs(np.diff(librosa.stft(y=audio_segment))), axis=0)
        flux_mean = float(np.mean(spectral_flux))
        flux_norm = np.clip(flux_mean / 1000.0, 0.0, 1.0)
        
        # Combine features into a complexity metric
        # Normalize each component to 0-1 range based on typical values
        # Old values commented out for referance. Trying to improve complexity metrics
        #centroid_norm = np.clip(centroid_mean / (self.sr / 2), 0.0, 1.0)  # Normalize by Nyquist frequency
        #centroid_var_norm = np.clip(centroid_std / 1000.0, 0.0, 1.0)  # Variation in brightness
        #bandwidth_norm = np.clip(bandwidth_mean / (self.sr / 2), 0.0, 1.0)
        #rolloff_norm = np.clip(rolloff_mean / (self.sr / 2), 0.0, 1.0)
        #zcr_norm = np.clip(zcr_mean * 10, 0.0, 1.0)  # ZCR is typically 0-0.1

        centroid_norm = np.clip((centroid_mean - 500) / 3500, 0.0, 1.0)  # 500-4000Hz range
        centroid_var_norm = np.clip(centroid_std / 500.0, 0.0, 1.0)  # More sensitive variance
        bandwidth_norm = np.clip((bandwidth_mean - 1000) / 4000, 0.0, 1.0)  # 1000-5000Hz range
        rolloff_norm = np.clip((rolloff_mean - 2000) / 6000, 0.0, 1.0)  # 2000-8000Hz range
        zcr_norm = np.clip(zcr_mean * 20, 0.0, 1.0)  # More sensitive to percussiveness

        # Weighted combination - higher weight on variation and bandwidth
        complexity = (
            0.10 * centroid_norm +      # Brightness initial: 0.15
            0.25 * centroid_var_norm +  # Variation in brightness (important!) initial: 0.30
            0.25 * bandwidth_norm +     # Frequency spread initial: 0.3
            0.15 * rolloff_norm +       # High frequency content initial: 0.15
            0.10 * zcr_norm +            # Percussiveness initial: 0.1
            0.15 * flux_norm            # Dynamics
        )

        # Use global BPM (or could extract local tempo if needed)
        bpm = self.global_bpm

        return bpm, rms_mean, complexity

    def get_features(self, current_time):
        """
        Get current music features at the specified time.

        Args:
            current_time: Current playback time in seconds

        Returns:
            dict: Dictionary containing 'bpm', 'rms', 'complexity', and 'beat_phase'
        """
        bpm, rms, complexity = self._extract_features_at_time(current_time)
        beat_phase = self.get_beat_phase(current_time)

        return {
            'bpm': bpm,
            'rms': rms,
            'complexity': complexity,
            'beat_phase': beat_phase
        }

    def start_continuous_analysis(self, get_current_time_func):
        """
        Start continuous feature extraction in a background thread.

        Args:
            get_current_time_func: Function that returns the current playback time in seconds
        """
        if self._running:
            print("Analyzer already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._analysis_loop,
            args=(get_current_time_func,),
            daemon=True
        )
        self._thread.start()
        print("Music analysis started")

    def _analysis_loop(self, get_current_time_func):
        """Background thread that continuously updates features."""
        update_rate = 10  # Hz - update features 10 times per second

        while self._running:
            try:
                current_time = get_current_time_func()

                if current_time >= self.duration:
                    break

                # Extract features
                features = self.get_features(current_time)
                self.current_bpm = features['bpm']
                self.current_rms = features['rms']
                self.current_complexity = features['complexity']
                self.current_beat_phase = features['beat_phase']

                time.sleep(1.0 / update_rate)

            except Exception as e:
                print(f"Error in analysis loop: {e}")
                break

    def stop(self):
        """Stop the continuous analysis thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        print("Music analysis stopped")

    def get_duration(self):
        """Get the duration of the audio file in seconds."""
        return self.duration


# Example usage and testing
if __name__ == "__main__":
    # Test the analyzer
    audio_file = "Made_Me_Like_This.mp3"  # Replace with your audio file

    try:
        analyzer = MusicAnalyzer(audio_file, window_size=5.0)

        print("\n--- Testing feature extraction at different times ---")
        test_times = [0, 10, 30, 60, 90]

        for t in test_times:
            if t < analyzer.duration:
                features = analyzer.get_features(t)
                print(f"\nTime: {t}s")
                print(f"  BPM: {features['bpm']:.2f}")
                print(f"  RMS: {features['rms']:.4f}")
                print(f"  Complexity: {features['complexity']:.4f}")

        print("\n--- Testing continuous analysis ---")

        # Simulate playback with a simple counter
        playback_time = [0.0]

        def get_time():
            return playback_time[0]

        analyzer.start_continuous_analysis(get_time)

        # Simulate 10 seconds of playback
        for i in range(100):
            playback_time[0] = i * 0.1
            print(f"\rTime: {playback_time[0]:.1f}s | "
                  f"BPM: {analyzer.current_bpm:.1f} | "
                  f"RMS: {analyzer.current_rms:.4f} | "
                  f"Complexity: {analyzer.current_complexity:.4f}", end="")
            time.sleep(0.1)

        print("\n")
        analyzer.stop()

    except FileNotFoundError:
        print(f"Audio file '{audio_file}' not found. Please provide a valid audio file.")
    except Exception as e:
        print(f"Error: {e}")
