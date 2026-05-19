"""
ODrive Controller Module

This module handles all ODrive setup, configuration, and communication.
Extracted from motor_control_music.py to provide a clean separation of concerns.
"""

import odrive
from odrive.enums import *
import time
import threading


class ODriveController:
    """
    Class to manage ODrive motor controller setup and operations.

    Attributes:
        odrv: ODrive device object
        axis: Motor axis (default: axis0)
    """

    def __init__(self, axis_number=0):
        """
        Initialize ODrive controller.

        Args:
            axis_number: Which axis to control (default: 0)
        """
        self.odrv = None
        self.axis_number = axis_number
        self.axis = None

    def find_odrive(self, timeout=30, allow_cancel=True, cancel_callback=None):
        """
        Search for and connect to ODrive.

        Args:
            timeout: Maximum time to search for ODrive in seconds
            allow_cancel: Whether to allow cancellation during search
            cancel_callback: Function that returns True if search should be cancelled

        Returns:
            bool: True if ODrive found, False otherwise
        """
        print("Looking for ODrive...")

        if allow_cancel and cancel_callback:
            # Search with cancellation support
            search_thread = threading.Thread(
                target=lambda: setattr(search_thread, 'result', odrive.find_any()),
                daemon=True
            )
            search_thread.result = None
            search_thread.start()

            start_time = time.time()
            while search_thread.is_alive():
                if cancel_callback():
                    print("ODrive search cancelled by user")
                    return False

                if time.time() - start_time > timeout:
                    print(f"ODrive search timeout after {timeout}s")
                    return False

                time.sleep(0.1)

            self.odrv = search_thread.result
        else:
            # Simple search without cancellation
            try:
                self.odrv = odrive.find_any(timeout=timeout)
            except Exception as e:
                print(f"Error finding ODrive: {e}")
                return False

        if self.odrv is None:
            print("ODrive not found")
            return False

        print("ODrive found")
        self.axis = getattr(self.odrv, f'axis{self.axis_number}')
        return True

    def start_closed_loop(self):
        """
        Start closed-loop control without calibration.
        Use this when ODrive has been previously calibrated.
        """
        if self.odrv is None or self.axis is None:
            raise RuntimeError("ODrive not connected. Call find_odrive() first.")

        print("Setting to closed-loop control mode...")
        self.axis.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
        print("Closed-loop control mode set")

    def set_position(self, position):
        """
        Set target position for the motor.

        Args:
            position: Target position in turns
        """
        if self.odrv is None or self.axis is None:
            raise RuntimeError("ODrive not connected. Call find_odrive() first.")

        self.axis.controller.input_pos = position

    def get_position(self):
        """
        Get current motor position.

        Returns:
            float: Current position estimate in turns
        """
        if self.odrv is None or self.axis is None:
            raise RuntimeError("ODrive not connected. Call find_odrive() first.")

        return self.axis.encoder.pos_estimate

    def get_velocity(self):
        """
        Get current motor velocity.

        Returns:
            float: Current velocity estimate in turns/s
        """
        if self.odrv is None or self.axis is None:
            raise RuntimeError("ODrive not connected. Call find_odrive() first.")

        return self.axis.encoder.vel_estimate

    def check_errors(self):
        """
        Check for axis errors.

        Returns:
            int: Error code (0 if no errors)
        """
        if self.odrv is None or self.axis is None:
            raise RuntimeError("ODrive not connected. Call find_odrive() first.")

        return self.axis.error

    def clear_errors(self):
        """Clear axis errors."""
        if self.odrv is None or self.axis is None:
            raise RuntimeError("ODrive not connected. Call find_odrive() first.")

        self.axis.error = 0

    def set_idle(self):
        """Set motor to idle state."""
        if self.odrv is None or self.axis is None:
            raise RuntimeError("ODrive not connected. Call find_odrive() first.")

        self.axis.requested_state = AXIS_STATE_IDLE
        print("Motor set to idle state")

    def get_bus_voltage(self):
        """
        Get DC bus voltage.

        Returns:
            float: Bus voltage in volts
        """
        if self.odrv is None:
            raise RuntimeError("ODrive not connected. Call find_odrive() first.")

        return self.odrv.vbus_voltage

    def get_motor_current(self):
        """
        Get motor current.

        Returns:
            float: Motor current in amps
        """
        if self.odrv is None or self.axis is None:
            raise RuntimeError("ODrive not connected. Call find_odrive() first.")

        return self.axis.motor.current_control.Iq_measured

    def disconnect(self):
        """Safely disconnect from ODrive."""
        if self.axis is not None:
            try:
                self.set_idle()
            except:
                pass

        self.odrv = None
        self.axis = None
        print("ODrive disconnected")


def configure_odrive(odrv0):
    """
    Configure ODrive with specified motor settings (new implementation).

    Args:
        odrv0: ODrive device object
    """
    print("Configuring ODrive with load resistors...")

    odrv0.axis0.motor.config.pole_pairs = 7
    odrv0.axis0.motor.config.calibration_current = 30
    odrv0.axis0.motor.config.resistance_calib_max_voltage = 4
    odrv0.axis0.motor.config.motor_type = 1  # MOTOR_TYPE_HIGH_CURRENT
    odrv0.axis0.motor.config.current_lim = 80

    # Configure encoder (CUI AMT102-V)
    odrv0.axis0.encoder.config.mode = 0  # ENCODER_MODE_INCREMENTAL
    odrv0.axis0.encoder.config.cpr = 8192  # AMT102-V has 2048 PPR = 8192 CPR

    # Set controller mode
    odrv0.axis0.controller.config.control_mode = 3  # CONTROL_MODE_POSITION_CONTROL

    # Set calibration sequence
    odrv0.axis0.config.startup_encoder_offset_calibration = True
    odrv0.axis0.config.startup_motor_calibration = True  # Set to True first time only
    odrv0.axis0.motor.config.pre_calibrated = False
    odrv0.axis0.encoder.config.pre_calibrated = False
    odrv0.axis0.config.startup_closed_loop_control = False


    # Configure de-accelleration rate and velocity:
    # Hard overspeed roof at 6500 RPM (108.33 turns/s)
    # vel_limit × vel_limit_tolerance = overspeed trip threshold
    # 72.22 × 1.5 = 108.33 turns/s ≈ 6500 RPM
    odrv0.axis0.controller.config.vel_limit = 72.22
    odrv0.axis0.controller.config.vel_limit_tolerance = 1.5
    odrv0.axis0.trap_traj.config.accel_limit = 10  # i have tried 6 because of BUS OVERVOLTAGE
    odrv0.axis0.trap_traj.config.decel_limit = 10  # i have tried 6 because of BUS OVERVOLTAGE
    odrv0.axis0.controller.config.pos_gain = 50


    # ---- breake resistance and related parameters ----
    odrv0.config.brake_resistance = 2.0

    # Configure DC bus overvoltage protection
    odrv0.config.dc_bus_overvoltage_trip_level = 40

    # Enable overvoltage ramp (helps with regen braking)
    odrv0.config.enable_dc_bus_overvoltage_ramp = True
    odrv0.config.dc_bus_overvoltage_ramp_start = 36  # Start ramping down power
    odrv0.config.dc_bus_overvoltage_ramp_end = 38    # Full brake at this voltage

    # Allow some regenerative current
    odrv0.config.dc_max_positive_current = 20    # Increase from 10
    odrv0.config.dc_max_negative_current = -10   # Allow MORE regen current (was -3)

    # Spinout detection parameters
    odrv0.axis0.controller.config.spinout_electrical_power_threshold = 200
    odrv0.axis0.controller.config.spinout_mechanical_power_threshold = -200

    # ---- END break resistance and related parameters

    # Save configuration and wait for it to complete
    print("Saving configuration...")
    try:
        odrv0.save_configuration()
        print("Configuration saved successfully")
    except Exception as e:
        print(f"Save may have completed (got: {e})")

    # Wait for save to fully commit to flash
    time.sleep(2)

    # Verify startup calibration is set
    print(f"Verifying: startup_motor_calibration = {odrv0.axis0.config.startup_motor_calibration}")
    print(f"Verifying: startup_encoder_offset_calibration = {odrv0.axis0.config.startup_encoder_offset_calibration}")

    # Reboot to apply settings
    print("Rebooting ODrive...")
    odrv0.reboot()


def arm(odrv0):
    """
    Arm ODrive without calibration.

    Args:
        odrv0: ODrive device object
    """
    odrv0.axis0.requested_state = 8
    print("Closed-loop control mode set")


def print_errors(odrv0):
    """
    Print all current errors on the ODrive.

    Args:
        odrv0: ODrive device object
    """
    print("\n" + "="*60)
    print("CURRENT ERROR STATUS")
    print("="*60)

    # Axis errors
    try:
        axis_err = odrv0.axis0.error
        print(f"Axis 0 error: {axis_err} ({hex(axis_err)})")
        if axis_err == 0:
            print("  ✓ No axis errors")
    except AttributeError:
        print("Axis 0 error: Unable to read")

    try:
        motor_err = odrv0.axis0.motor.error
        print(f"Motor error: {motor_err} ({hex(motor_err)})")
        if motor_err == 0:
            print("  ✓ No motor errors")
    except AttributeError:
        print("Motor error: Unable to read")

    try:
        ctrl_err = odrv0.axis0.controller.error
        print(f"Controller error: {ctrl_err} ({hex(ctrl_err)})")
        if ctrl_err == 0:
            print("  ✓ No controller errors")
    except AttributeError:
        print("Controller error: Unable to read")

    try:
        enc_err = odrv0.axis0.encoder.error
        print(f"Encoder error: {enc_err} ({hex(enc_err)})")
        if enc_err == 0:
            print("  ✓ No encoder errors")
    except AttributeError:
        print("Encoder error: Unable to read")

    # Current state
    try:
        state = odrv0.axis0.current_state
        print(f"\nCurrent axis state: {state}")
        # Decode state name
        state_names = {
            0: "UNDEFINED",
            1: "IDLE",
            2: "STARTUP_SEQUENCE",
            3: "FULL_CALIBRATION_SEQUENCE",
            4: "MOTOR_CALIBRATION",
            6: "ENCODER_INDEX_SEARCH",
            7: "ENCODER_OFFSET_CALIBRATION",
            8: "CLOSED_LOOP_CONTROL",
            9: "LOCKIN_SPIN",
            10: "ENCODER_DIR_FIND",
            11: "HOMING",
        }
        if state in state_names:
            print(f"  State name: {state_names[state]}")
    except AttributeError:
        print("\nCurrent axis state: Unable to read")

    try:
        armed = odrv0.axis0.motor.armed_state
        print(f"Motor armed state: {armed}")
    except AttributeError:
        print("Motor armed state: Unable to read")

    print("="*60 + "\n")


def clear_errors(odrv0):
    """
    Clear all errors on the ODrive.

    Args:
        odrv0: ODrive device object
    """
    print("Clearing all errors...")

    try:
        # First set axis to idle
        odrv0.axis0.requested_state = AXIS_STATE_IDLE
        time.sleep(0.5)

        # Then try to clear errors if the method exists
        if hasattr(odrv0.axis0, 'clear_errors'):
            odrv0.axis0.clear_errors()

    except Exception as e:
        print(f"Warning during error clearing: {e}")

    time.sleep(0.5)

    print("✓ Errors cleared (set to IDLE)")


def soft_reset(odrv0):
    """
    Perform a soft reset (clear errors and return to idle).

    Args:
        odrv0: ODrive device object
    """
    print("\n" + "="*60)
    print("PERFORMING SOFT RESET")
    print("="*60)

    clear_errors(odrv0)
    print_errors(odrv0)

    print("✓ Soft reset complete")


def hard_reset(odrv0, confirm=True):
    """
    Perform a hard reset (reboot the ODrive).

    Args:
        odrv0: ODrive device object
        confirm: Whether to ask for user confirmation (default: True)

    Returns:
        bool: True if reset was performed, False if cancelled
    """
    print("\n" + "="*60)
    print("PERFORMING HARD RESET (REBOOT)")
    print("="*60)
    print("\nWARNING: This will reboot the ODrive!")
    print("You will need to reconnect after the reboot.")

    if confirm:
        response = input("\nContinue? (yes/no): ")
        if response.lower() != 'yes':
            print("Hard reset cancelled")
            return False

    print("\nRebooting ODrive...")
    try:
        odrv0.reboot()
        print("✓ Reboot command sent")
        print("\nWait ~5 seconds, then reconnect using 'odrive.find_any()'")
        return True
    except Exception as e:
        print(f"Reboot initiated (connection lost as expected): {e}")
        return True


def test_calibration(odrv0):
    """
    Test if the ODrive can enter calibration mode.

    Args:
        odrv0: ODrive device object

    Returns:
        bool: True if calibration succeeded, False otherwise
    """
    print("\n" + "="*60)
    print("TESTING CALIBRATION SEQUENCE")
    print("="*60)

    # First clear any errors
    print("\n1. Clearing errors...")
    odrv0.axis0.requested_state = AXIS_STATE_IDLE
    time.sleep(0.5)

    # Try to clear errors if the method exists
    if hasattr(odrv0.axis0, 'clear_errors'):
        odrv0.axis0.clear_errors()

    print_errors(odrv0)

    if odrv0.axis0.error != 0 or odrv0.axis0.motor.error != 0:
        print("⚠ Cannot start calibration - errors present!")
        print("Try clearing errors first")
        return False

    print("\n2. Starting motor calibration...")
    odrv0.axis0.requested_state = AXIS_STATE_MOTOR_CALIBRATION

    print("Waiting for motor calibration to complete...")
    timeout = 20  # 20 second timeout
    start_time = time.time()

    while odrv0.axis0.current_state != AXIS_STATE_IDLE:
        if time.time() - start_time > timeout:
            print("✗ Calibration timeout!")
            print_errors(odrv0)
            return False

        if odrv0.axis0.error != 0:
            print("✗ Calibration failed with errors!")
            print_errors(odrv0)
            return False

        print(f"  State: {odrv0.axis0.current_state} (waiting for IDLE)", end='\r')
        time.sleep(0.2)

    print("\n✓ Motor calibration completed successfully!")

    # Check if motor should have beeped
    if odrv0.axis0.motor.error == 0:
        print("\n✓ No motor errors - motor should have made a beep during calibration")

    print_errors(odrv0)
    return True


def show_motor_status(odrv0):
    """
    Show detailed motor and configuration status.

    Args:
        odrv0: ODrive device object
    """
    print("\n" + "="*60)
    print("MOTOR CONFIGURATION STATUS")
    print("="*60)

    print("\nMotor Configuration:")
    print(f"  Motor type: {odrv0.axis0.motor.config.motor_type}")
    print(f"  Pole pairs: {odrv0.axis0.motor.config.pole_pairs}")
    print(f"  Current limit: {odrv0.axis0.motor.config.current_lim} A")
    print(f"  Calibration current: {odrv0.axis0.motor.config.calibration_current} A")
    print(f"  Torque constant: {odrv0.axis0.motor.config.torque_constant}")
    print(f"  Phase resistance: {odrv0.axis0.motor.phase_resistance} Ω")
    print(f"  Phase inductance: {odrv0.axis0.motor.phase_inductance} H")

    print("\nEncoder Configuration:")
    print(f"  CPR: {odrv0.axis0.encoder.config.cpr}")
    print(f"  Use index: {odrv0.axis0.encoder.config.use_index}")

    print("\nController Configuration:")
    print(f"  Control mode: {odrv0.axis0.controller.config.control_mode}")
    print(f"  Input mode: {odrv0.axis0.controller.config.input_mode}")
    print(f"  Vel limit: {odrv0.axis0.controller.config.vel_limit}")
    print(f"  Pos gain: {odrv0.axis0.controller.config.pos_gain}")
    print(f"  Vel gain: {odrv0.axis0.controller.config.vel_gain}")

    print("\nSystem Configuration:")
    print(f"  DC bus voltage: {odrv0.vbus_voltage} V")
    print(f"  DC max negative current: {odrv0.config.dc_max_negative_current} A")

    print_errors(odrv0)