"""
Latency Calibrator

Measures and calibrates the total system latency including:
- Motor response latency (command to movement)
- Audio output latency (buffer to speaker)

The calibrated latency offset is used by the PlaybackController
to look ahead in the trajectory and compensate for delays.
"""

import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime

import sounddevice as sd
import numpy as np


@dataclass
class CalibrationResult:
    """Results from latency calibration."""
    motor_latency_ms: float
    audio_latency_ms: float
    total_latency_ms: float
    fine_tune_offset_ms: float
    final_offset_ms: float
    audio_device: str
    calibrated_at: str


class LatencyCalibrator:
    """
    Calibrates system latency for audio-motor synchronization.

    The calibration process:
    1. Measure motor response latency (step command → encoder movement)
    2. Query audio device output latency
    3. Interactive fine-tuning with user feedback
    4. Save results to config file
    """

    def __init__(
        self,
        odrv0=None,
        audio_device: Optional[str] = None,
        config_path: str = None
    ):
        """
        Initialize the calibrator.

        Args:
            odrv0: ODrive object (required for calibration, optional for loading saved values)
            audio_device: Audio device name (None for default)
            config_path: Path to save calibration results
        """
        self.odrv0 = odrv0
        self.audio_device = audio_device

        if config_path is None:
            src_dir = Path(__file__).parent.parent
            config_path = src_dir.parent / "config" / "latency.json"

        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def measure_motor_latency(self, num_tests: int = 10) -> float:
        """
        Measure motor response latency.

        Sends step commands and measures time until encoder shows movement.

        Args:
            num_tests: Number of test iterations to average

        Returns:
            Average motor latency in milliseconds

        Raises:
            ValueError: If ODrive is not connected
        """
        if self.odrv0 is None:
            raise ValueError("ODrive connection required for motor latency measurement")

        print(f"Measuring motor latency ({num_tests} tests)...")
        latencies = []

        for i in range(num_tests):
            # Get current position
            start_pos = self.odrv0.axis0.encoder.pos_estimate
            target_pos = start_pos + 0.5  # Small step

            # Send command and start timer
            start_time = time.perf_counter()
            self.odrv0.axis0.controller.input_pos = target_pos

            # Poll encoder until movement detected
            threshold = 0.1  # 10% of step size
            while True:
                current_pos = self.odrv0.axis0.encoder.pos_estimate
                if abs(current_pos - start_pos) > threshold * 0.5:
                    break
                if time.perf_counter() - start_time > 0.5:  # Timeout
                    break

            latency = (time.perf_counter() - start_time) * 1000  # ms
            latencies.append(latency)

            # Return to start position
            self.odrv0.axis0.controller.input_pos = start_pos
            time.sleep(0.2)

            print(f"  Test {i+1}/{num_tests}: {latency:.1f} ms")

        avg_latency = np.mean(latencies)
        print(f"Average motor latency: {avg_latency:.1f} ms")

        return avg_latency

    def measure_audio_latency(self) -> float:
        """
        Get audio device output latency.

        Returns:
            Audio latency in milliseconds
        """
        try:
            device_info = sd.query_devices(self.audio_device, kind='output')
            latency_s = device_info['default_low_output_latency']
            latency_ms = latency_s * 1000

            device_name = device_info['name']
            print(f"Audio device: {device_name}")
            print(f"Audio latency: {latency_ms:.1f} ms")

            return latency_ms
        except Exception as e:
            print(f"Could not query audio latency: {e}")
            return 20.0  # Typical value

    def run_calibration(self) -> CalibrationResult:
        """
        Run the full calibration process.

        Returns:
            CalibrationResult with measured latencies

        Raises:
            ValueError: If ODrive is not connected
        """
        if self.odrv0 is None:
            raise ValueError("ODrive connection required for calibration")

        print("\n" + "="*50)
        print("LATENCY CALIBRATION")
        print("="*50 + "\n")

        # Measure motor latency
        motor_latency = self.measure_motor_latency()

        print()

        # Measure audio latency
        audio_latency = self.measure_audio_latency()

        # Calculate total
        total_latency = motor_latency + audio_latency

        print(f"\nTotal system latency: {total_latency:.1f} ms")

        # Get audio device name
        try:
            device_info = sd.query_devices(self.audio_device, kind='output')
            audio_device_name = device_info['name']
        except:
            audio_device_name = "Unknown"

        result = CalibrationResult(
            motor_latency_ms=motor_latency,
            audio_latency_ms=audio_latency,
            total_latency_ms=total_latency,
            fine_tune_offset_ms=0.0,
            final_offset_ms=total_latency,
            audio_device=audio_device_name,
            calibrated_at=datetime.now().isoformat()
        )

        return result

    def interactive_fine_tune(
        self,
        result: CalibrationResult,
        test_audio_path: str = None
    ) -> CalibrationResult:
        """
        Interactive fine-tuning of latency offset.

        Plays test audio and asks user if motor is early/late/good.
        Uses binary search to refine the offset.

        Args:
            result: Initial calibration result
            test_audio_path: Path to test audio file

        Returns:
            Updated CalibrationResult with fine-tuned offset
        """
        print("\n" + "="*50)
        print("INTERACTIVE FINE-TUNING")
        print("="*50)
        print("\nListen to the audio and watch the motor.")
        print("Answer whether the motor movement is:")
        print("  [E]arly - motor moves before the beat")
        print("  [L]ate  - motor moves after the beat")
        print("  [G]ood  - motor is in sync")
        print("  [Q]uit  - keep current offset")
        print()

        current_offset = result.total_latency_ms
        adjustment = 10.0  # Start with 10ms adjustments

        while True:
            print(f"Current offset: {current_offset:.1f} ms")

            response = input("Motor is [E]arly / [L]ate / [G]ood / [Q]uit? ").strip().lower()

            if response == 'q':
                break
            elif response == 'g':
                print("Calibration complete!")
                break
            elif response == 'e':
                # Motor is early -> need less lookahead
                current_offset -= adjustment
                adjustment = max(adjustment * 0.7, 1.0)  # Reduce step size
            elif response == 'l':
                # Motor is late -> need more lookahead
                current_offset += adjustment
                adjustment = max(adjustment * 0.7, 1.0)
            else:
                print("Please enter E, L, G, or Q")

        fine_tune = current_offset - result.total_latency_ms
        result.fine_tune_offset_ms = fine_tune
        result.final_offset_ms = current_offset

        print(f"\nFinal offset: {current_offset:.1f} ms")
        print(f"  (Base: {result.total_latency_ms:.1f} ms + Fine-tune: {fine_tune:+.1f} ms)")

        return result

    def save_calibration(self, result: CalibrationResult) -> None:
        """Save calibration result to config file."""
        data = {
            'version': 1,
            **asdict(result)
        }

        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"Calibration saved to: {self.config_path}")

    def load_calibration(self) -> Optional[CalibrationResult]:
        """Load calibration from config file."""
        if not self.config_path.exists():
            return None

        with open(self.config_path, 'r') as f:
            data = json.load(f)

        # Remove version field before creating dataclass
        data.pop('version', None)

        return CalibrationResult(**data)

    def get_latency_offset_seconds(self) -> float:
        """
        Get the calibrated latency offset in seconds.

        Returns:
            Latency offset in seconds, or default if not calibrated
        """
        result = self.load_calibration()
        if result is None:
            print("No calibration found, using default 35ms")
            return 0.035

        return result.final_offset_ms / 1000.0


def get_calibrator(odrv0=None, config_path: str = None) -> LatencyCalibrator:
    """Create a LatencyCalibrator instance."""
    return LatencyCalibrator(odrv0, config_path=config_path)


if __name__ == "__main__":
    import odrive

    print("Searching for ODrive...")
    odrv0 = odrive.find_any(timeout=10)
    if odrv0 is None:
        print("ODrive not found. Please connect ODrive and try again.")
        exit(1)

    print(f"Found ODrive: {odrv0.serial_number}")

    calibrator = LatencyCalibrator(odrv0=odrv0)

    # Run calibration
    result = calibrator.run_calibration()

    # Save result
    calibrator.save_calibration(result)

    # Load and display
    loaded = calibrator.load_calibration()
    if loaded:
        print(f"\nLoaded calibration:")
        print(f"  Motor latency: {loaded.motor_latency_ms:.1f} ms")
        print(f"  Audio latency: {loaded.audio_latency_ms:.1f} ms")
        print(f"  Final offset: {loaded.final_offset_ms:.1f} ms")
