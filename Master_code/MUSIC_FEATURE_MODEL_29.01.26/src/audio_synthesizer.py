"""
Audio Synthesizer Module

Generates real-time audio based on motor position.
Maps motor position to frequency for audible feedback.
"""

import numpy as np
import pyaudio
import threading
from typing import Callable, Optional


class AudioSynthesizer:
    """
    Real-time audio synthesizer that generates sound based on motor position.
    """

    def __init__(self,
                 sample_rate: int = 44100,
                 chunk_size: int = 1024,
                 base_frequency: float = 440.0,
                 frequency_range: tuple = (100, 2000),
                 position_to_freq_scale: float = 20.0,
                 amplitude: float = 0.2):
        """
        Initialize audio synthesizer.

        Args:
            sample_rate: Audio sample rate in Hz (default: 44100)
            chunk_size: Audio buffer chunk size (default: 1024)
            base_frequency: Base frequency in Hz (default: 440.0 = A4)
            frequency_range: Min and max frequency limits (default: 100-2000 Hz)
            position_to_freq_scale: Scale factor for position to frequency mapping
            amplitude: Audio amplitude (0.0-1.0, default: 0.2)
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.base_frequency = base_frequency
        self.freq_min, self.freq_max = frequency_range
        self.position_to_freq_scale = position_to_freq_scale
        self.amplitude = amplitude

        self.running = False
        self.thread = None
        self.p = None
        self.stream = None
        self.phase = 0.0

        # Position callback
        self.get_position: Optional[Callable[[], float]] = None

    def set_position_callback(self, callback: Callable[[], float]):
        """
        Set callback function to get current motor position.

        Args:
            callback: Function that returns current motor position as float
        """
        self.get_position = callback

    def _map_position_to_frequency(self, position: float) -> float:
        """
        Map motor position to audio frequency.

        Args:
            position: Motor position (typically -10 to +10)

        Returns:
            Frequency in Hz
        """
        freq = self.base_frequency + (position * self.position_to_freq_scale)
        return np.clip(freq, self.freq_min, self.freq_max)

    def _synthesis_loop(self):
        """
        Main synthesis loop (runs in separate thread).
        """
        print("✓ Audio synthesis started")

        try:
            while self.running:
                # Get current motor position
                position = 0.0
                if self.get_position is not None:
                    try:
                        position = self.get_position()
                    except Exception as e:
                        print(f"Warning: Error getting position for audio synthesis: {e}")

                # Map to frequency
                freq = self._map_position_to_frequency(position)

                # Generate audio samples
                samples = np.zeros(self.chunk_size, dtype=np.float32)

                for i in range(self.chunk_size):
                    samples[i] = self.amplitude * np.sin(self.phase)
                    self.phase += 2.0 * np.pi * freq / self.sample_rate

                    # Keep phase wrapped to prevent overflow
                    if self.phase > 2.0 * np.pi:
                        self.phase -= 2.0 * np.pi

                # Write to audio stream
                self.stream.write(samples.tobytes())

        except Exception as e:
            print(f"Audio synthesis error: {e}")
        finally:
            print("✓ Audio synthesis stopped")

    def start(self):
        """Start audio synthesis in background thread."""
        if self.running:
            print("Audio synthesizer already running")
            return

        # Initialize PyAudio
        self.p = pyaudio.PyAudio()

        try:
            self.stream = self.p.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=self.chunk_size
            )

            self.running = True
            self.thread = threading.Thread(target=self._synthesis_loop, daemon=True)
            self.thread.start()

        except Exception as e:
            print(f"Failed to start audio synthesis: {e}")
            if self.p is not None:
                self.p.terminate()
            raise

    def stop(self):
        """Stop audio synthesis and cleanup resources."""
        if not self.running:
            return

        self.running = False

        # Wait for thread to finish
        if self.thread is not None:
            self.thread.join(timeout=2.0)

        # Cleanup audio resources
        if self.stream is not None:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass

        if self.p is not None:
            try:
                self.p.terminate()
            except:
                pass

    def is_running(self) -> bool:
        """Check if synthesizer is running."""
        return self.running

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically cleanup."""
        self.stop()


def create_synthesizer(position_callback: Optional[Callable[[], float]] = None) -> AudioSynthesizer:
    """
    Factory function to create an audio synthesizer.

    Args:
        position_callback: Optional callback function to get motor position

    Returns:
        AudioSynthesizer instance
    """
    synth = AudioSynthesizer()
    if position_callback is not None:
        synth.set_position_callback(position_callback)
    return synth