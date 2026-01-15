"""
Audio Player

Sample-accurate audio playback using sounddevice.OutputStream.
The audio timestamp is tracked via sample count and serves as
the master clock for motor synchronization.
"""

import threading
import numpy as np
import sounddevice as sd
from pathlib import Path
from typing import Optional, Callable
import scipy.io.wavfile as wavfile


class AudioPlayer:
    """
    Sample-accurate audio player using sounddevice.

    Uses a callback-based OutputStream for precise timing control.
    The sample count is tracked atomically and can be read from
    another thread to get the current playback position.
    """

    def __init__(
        self,
        wav_path: str,
        device: Optional[str] = None,
        blocksize: int = 1024
    ):
        """
        Initialize the audio player.

        Args:
            wav_path: Path to the WAV file
            device: Audio output device (None for default)
            blocksize: Audio buffer block size
        """
        self.wav_path = Path(wav_path)
        self.device = device
        self.blocksize = blocksize

        if not self.wav_path.exists():
            raise FileNotFoundError(f"WAV file not found: {wav_path}")

        # Load audio file
        self.sample_rate, self.audio_data = wavfile.read(str(self.wav_path))

        # Convert to float32 in range [-1, 1]
        if self.audio_data.dtype == np.int16:
            self.audio_data = self.audio_data.astype(np.float32) / 32768.0
        elif self.audio_data.dtype == np.int32:
            self.audio_data = self.audio_data.astype(np.float32) / 2147483648.0
        elif self.audio_data.dtype != np.float32:
            self.audio_data = self.audio_data.astype(np.float32)

        # Ensure stereo
        if len(self.audio_data.shape) == 1:
            self.audio_data = np.column_stack([self.audio_data, self.audio_data])

        self.num_channels = self.audio_data.shape[1]
        self.total_samples = len(self.audio_data)
        self.duration = self.total_samples / self.sample_rate

        # Playback state (protected by lock)
        self._lock = threading.Lock()
        self._sample_index = 0
        self._is_playing = False
        self._is_paused = False
        self._finished = False

        # Stream
        self._stream: Optional[sd.OutputStream] = None

        # Callbacks
        self._on_finished: Optional[Callable[[], None]] = None

    def _audio_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        time_info,
        status
    ) -> None:
        """Audio callback invoked by sounddevice."""
        if status:
            print(f"Audio status: {status}")

        with self._lock:
            if self._is_paused:
                # Output silence when paused
                outdata.fill(0)
                return

            start = self._sample_index
            end = start + frames

            if end >= self.total_samples:
                # Reached end of audio
                valid_frames = self.total_samples - start
                if valid_frames > 0:
                    outdata[:valid_frames] = self.audio_data[start:self.total_samples]
                outdata[valid_frames:] = 0
                self._sample_index = self.total_samples
                self._finished = True
                raise sd.CallbackStop()
            else:
                outdata[:] = self.audio_data[start:end]
                self._sample_index = end

    @property
    def current_time_seconds(self) -> float:
        """
        Get current playback time in seconds.

        This property is thread-safe and can be called from the
        motor control thread to get the current audio position.
        """
        with self._lock:
            return self._sample_index / self.sample_rate

    @property
    def current_sample(self) -> int:
        """Get current sample index."""
        with self._lock:
            return self._sample_index

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        with self._lock:
            return self._is_playing and not self._is_paused

    @property
    def is_finished(self) -> bool:
        """Check if playback has finished."""
        with self._lock:
            return self._finished

    @property
    def is_paused(self) -> bool:
        """Check if playback is paused."""
        with self._lock:
            return self._is_paused

    def start(self) -> None:
        """Start audio playback."""
        if self._stream is not None:
            return

        with self._lock:
            self._sample_index = 0
            self._is_playing = True
            self._is_paused = False
            self._finished = False

        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.num_channels,
            dtype=np.float32,
            blocksize=self.blocksize,
            device=self.device,
            callback=self._audio_callback,
            finished_callback=self._on_stream_finished
        )
        self._stream.start()

    def _on_stream_finished(self) -> None:
        """Called when stream finishes."""
        with self._lock:
            self._is_playing = False
            self._finished = True

        if self._on_finished:
            self._on_finished()

    def stop(self) -> None:
        """Stop audio playback."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            self._is_playing = False

    def pause(self) -> None:
        """Pause audio playback."""
        with self._lock:
            self._is_paused = True

    def resume(self) -> None:
        """Resume audio playback."""
        with self._lock:
            self._is_paused = False

    def seek(self, time_seconds: float) -> None:
        """
        Seek to a specific time position.

        Args:
            time_seconds: Time position in seconds
        """
        sample_index = int(time_seconds * self.sample_rate)
        sample_index = max(0, min(sample_index, self.total_samples - 1))

        with self._lock:
            self._sample_index = sample_index
            self._finished = False

    def set_on_finished(self, callback: Callable[[], None]) -> None:
        """Set callback to be called when playback finishes."""
        self._on_finished = callback

    def get_duration(self) -> float:
        """Get total duration in seconds."""
        return self.duration

    def get_sample_rate(self) -> int:
        """Get sample rate."""
        return self.sample_rate

    @staticmethod
    def get_output_latency(device: str = None) -> float:
        """
        Get the output latency of the audio device.

        Args:
            device: Device name (None for default)

        Returns:
            Latency in seconds
        """
        device_info = sd.query_devices(device, kind='output')
        return device_info['default_low_output_latency']


def get_audio_player(wav_path: str, device: str = None) -> AudioPlayer:
    """Create an AudioPlayer instance."""
    return AudioPlayer(wav_path, device)


if __name__ == "__main__":
    import sys
    import time

    if len(sys.argv) < 2:
        print("Usage: python audio_player.py <wav_file>")
        sys.exit(1)

    wav_path = sys.argv[1]
    player = AudioPlayer(wav_path)

    print(f"Audio file: {wav_path}")
    print(f"Duration: {player.get_duration():.2f}s")
    print(f"Sample rate: {player.get_sample_rate()} Hz")
    print(f"Output latency: {AudioPlayer.get_output_latency()*1000:.1f}ms")

    print("\nPlaying... (Ctrl+C to stop)")
    player.start()

    try:
        while not player.is_finished:
            print(f"\rTime: {player.current_time_seconds:.2f}s / {player.duration:.2f}s", end="")
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        player.stop()
        print("\nStopped.")
