#!/usr/bin/env python3
"""
ODrive Reset Script

This script helps reset the ODrive when it gets stuck or won't calibrate properly.
It provides various reset options to recover from different error states.
"""

import odrive
from odrive.enums import *
import time
import argparse

def print_errors(odrv0):
    """Print all current errors on the ODrive."""
    print("\n" + "="*60)
    print("CURRENT ERROR STATUS")
    print("="*60)

    # Axis errors (in ODrive 0.6.x, errors are primarily on axis level)
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
        # Try to decode state name
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
    """Clear all errors on the ODrive."""
    print("Clearing all errors...")

    # In ODrive 0.6.x, errors are cleared by setting to IDLE state
    # There is no global clear_errors() method
    try:
        # First set axis to idle
        odrv0.axis0.requested_state = AXIS_STATE_IDLE
        time.sleep(0.5)

        # Then try to clear errors if the method exists
        # Some firmware versions have this method on the axis
        if hasattr(odrv0.axis0, 'clear_errors'):
            odrv0.axis0.clear_errors()

    except Exception as e:
        print(f"Warning during error clearing: {e}")

    time.sleep(0.5)

    print("✓ Errors cleared (set to IDLE)")
    print_errors(odrv0)

def soft_reset(odrv0):
    """Perform a soft reset (clear errors and return to idle)."""
    print("\n" + "="*60)
    print("PERFORMING SOFT RESET")
    print("="*60)

    clear_errors(odrv0)

    print("✓ Soft reset complete")

def hard_reset(odrv0):
    """Perform a hard reset (reboot the ODrive)."""
    print("\n" + "="*60)
    print("PERFORMING HARD RESET (REBOOT)")
    print("="*60)
    print("\nWARNING: This will reboot the ODrive!")
    print("You will need to reconnect after the reboot.")

    response = input("\nContinue? (yes/no): ")
    if response.lower() != 'yes':
        print("Hard reset cancelled")
        return

    print("\nRebooting ODrive...")
    try:
        odrv0.reboot()
        print("✓ Reboot command sent")
        print("\nWait ~5 seconds, then reconnect using 'odrive.find_any()'")
    except Exception as e:
        print(f"Reboot initiated (connection lost as expected): {e}")

def erase_configuration(odrv0):
    """Erase configuration and reboot (factory reset)."""
    print("\n" + "="*60)
    print("ERASE CONFIGURATION (FACTORY RESET)")
    print("="*60)
    print("\nWARNING: This will erase ALL configuration!")
    print("You will need to reconfigure the ODrive from scratch.")

    response = input("\nAre you SURE? Type 'ERASE' to confirm: ")
    if response != 'ERASE':
        print("Erase cancelled")
        return

    print("\nErasing configuration and rebooting...")
    try:
        odrv0.erase_configuration()
        print("✓ Configuration erased, ODrive rebooting")
        print("\nWait ~5 seconds, then reconnect and reconfigure")
    except Exception as e:
        print(f"Erase initiated (connection lost as expected): {e}")

def test_calibration(odrv0):
    """Test if the ODrive can enter calibration mode."""
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
        print("Try clearing errors first (option 2)")
        return

    print("\n2. Starting motor calibration...")
    odrv0.axis0.requested_state = AXIS_STATE_MOTOR_CALIBRATION

    print("Waiting for motor calibration to complete...")
    timeout = 20  # 20 second timeout
    start_time = time.time()

    while odrv0.axis0.current_state != AXIS_STATE_IDLE:
        if time.time() - start_time > timeout:
            print("✗ Calibration timeout!")
            print_errors(odrv0)
            return

        if odrv0.axis0.error != 0:
            print("✗ Calibration failed with errors!")
            print_errors(odrv0)
            return

        print(f"  State: {odrv0.axis0.current_state} (waiting for IDLE)", end='\r')
        time.sleep(0.2)

    print("\n✓ Motor calibration completed successfully!")

    # Check if motor should have beeped
    if odrv0.axis0.motor.error == 0:
        print("\n✓ No motor errors - motor should have made a beep during calibration")

    print_errors(odrv0)

def show_motor_status(odrv0):
    """Show detailed motor and configuration status."""
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

def main():
    parser = argparse.ArgumentParser(description="ODrive Reset and Diagnostic Tool")
    parser.add_argument('-a', '--auto-clear', action='store_true',
                       help="Automatically clear errors on startup")
    parser.add_argument('-t', '--test', action='store_true',
                       help="Test calibration sequence")

    args = parser.parse_args()

    print("="*60)
    print("ODrive Reset & Diagnostic Tool")
    print("="*60)

    print("\nSearching for ODrive...")
    try:
        odrv0 = odrive.find_any()
        print(f"✓ ODrive found: {odrv0.serial_number}")
    except Exception as e:
        print(f"✗ Failed to find ODrive: {e}")
        print("\nTroubleshooting:")
        print("  1. Check USB connection")
        print("  2. Check ODrive is powered")
        print("  3. Try different USB port")
        print("  4. Check if ODrive LED is on")
        return

    # Auto-clear if requested
    if args.auto_clear:
        clear_errors(odrv0)

    # Auto-test if requested
    if args.test:
        test_calibration(odrv0)
        return

    # Show initial status
    print_errors(odrv0)

    # Interactive menu
    while True:
        print("\n" + "="*60)
        print("RESET OPTIONS")
        print("="*60)
        print("1. Show current errors")
        print("2. Clear errors (soft reset)")
        print("3. Test calibration sequence")
        print("4. Show motor configuration")
        print("5. Hard reset (reboot ODrive)")
        print("6. Erase configuration (factory reset)")
        print("0. Exit")
        print()

        choice = input("Select option (0-6): ").strip()

        if choice == "0":
            break
        elif choice == "1":
            print_errors(odrv0)
        elif choice == "2":
            soft_reset(odrv0)
        elif choice == "3":
            test_calibration(odrv0)
        elif choice == "4":
            show_motor_status(odrv0)
        elif choice == "5":
            hard_reset(odrv0)
            break  # Exit after reboot
        elif choice == "6":
            erase_configuration(odrv0)
            break  # Exit after erase
        else:
            print("Invalid choice")

    print("\n" + "="*60)
    print("Done!")
    print("="*60)

if __name__ == "__main__":
    main()
