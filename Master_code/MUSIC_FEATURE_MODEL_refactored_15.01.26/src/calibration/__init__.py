"""
Calibration module for latency measurement and compensation.

Provides tools for measuring and calibrating system latency:
- Motor response latency
- Audio output latency
- Interactive fine-tuning
"""

from .calibrator import (
    LatencyCalibrator,
    CalibrationResult,
    get_calibrator
)

__all__ = [
    'LatencyCalibrator',
    'CalibrationResult',
    'get_calibrator',
]
