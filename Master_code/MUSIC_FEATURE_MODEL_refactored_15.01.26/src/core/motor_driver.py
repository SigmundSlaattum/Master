"""
Motor Driver

Thin interface to the ODrive motor controller.
Provides basic position control and status reading.
"""

from typing import Optional
import time


class MotorDriver:
    """
    Minimal ODrive motor driver interface.

    This is the thin layer between the playback controller and the
    ODrive hardware.
    """

    def __init__(
        self,
        odrv0,
        initial_offset: float = 0.0
    ):
        """
        Initialize the motor driver.

        Args:
            odrv0: ODrive object (required)
            initial_offset: Initial motor position offset
        """
        if odrv0 is None:
            raise ValueError("ODrive object is required")

        self.odrv0 = odrv0
        self.initial_offset = initial_offset

        # Statistics
        self._last_command = initial_offset
        self._command_count = 0

    def set_position(self, position: float) -> None:
        """
        Set motor position.

        This is the hot path called at 60Hz.

        Args:
            position: Target position in motor turns
        """
        self._last_command = position
        self._command_count += 1

        try:
            self.odrv0.axis0.controller.input_pos = position
        except (AttributeError, OSError) as e:
            print(f"Motor command error: {e}")

    def get_position(self) -> float:
        """
        Get current motor position from encoder.

        Returns:
            Current position in motor turns
        """
        try:
            return self.odrv0.axis0.encoder.pos_estimate
        except (AttributeError, OSError) as e:
            print(f"Encoder read error: {e}")
            return self._last_command

    def get_velocity(self) -> float:
        """
        Get current motor velocity.

        Returns:
            Current velocity in turns/second
        """
        try:
            return self.odrv0.axis0.encoder.vel_estimate
        except (AttributeError, OSError):
            return 0.0

    def check_errors(self) -> bool:
        """
        Check for motor/axis errors.

        Returns:
            True if error detected, False otherwise
        """
        try:
            axis_error = self.odrv0.axis0.error
            motor_error = self.odrv0.axis0.motor.error
            encoder_error = self.odrv0.axis0.encoder.error

            if axis_error != 0:
                print(f"Axis error: {axis_error}")
                return True
            if motor_error != 0:
                print(f"Motor error: {motor_error}")
                return True
            if encoder_error != 0:
                print(f"Encoder error: {encoder_error}")
                return True

            return False
        except (AttributeError, OSError) as e:
            print(f"Error check failed: {e}")
            return True

    def clear_errors(self) -> None:
        """Clear any motor errors."""
        try:
            self.odrv0.clear_errors()
        except (AttributeError, OSError) as e:
            print(f"Clear errors failed: {e}")

    def get_command_count(self) -> int:
        """Get total number of position commands sent."""
        return self._command_count

    def get_last_command(self) -> float:
        """Get the last commanded position."""
        return self._last_command

    def get_position_error(self) -> float:
        """
        Get the difference between commanded and actual position.

        Returns:
            Position error (commanded - actual)
        """
        return self._last_command - self.get_position()


def create_motor_driver(odrv0, initial_offset: float = 0.0) -> MotorDriver:
    """Create a MotorDriver instance."""
    return MotorDriver(odrv0, initial_offset)
