import odrive
from odrive.enums import *
import time

def configure_odrive(odrv0):
    """Configure ODrive with specified motor settings."""
    print("Configuring ODrive with provided settings...")

    
    # Check voltage before proceeding
    print(f"VBUS Voltage: {odrv0.vbus_voltage}V")
    if odrv0.vbus_voltage < 12:
        print(f"ERROR: Voltage too low! {odrv0.vbus_voltage}V detected. Need 12V+")
        return False

    odrv0.axis0.motor.config.current_lim = 100
    odrv0.axis0.controller.config.vel_limit = 10
    odrv0.axis0.motor.config.torque_constant = 8.27 / 90
    odrv0.axis0.motor.config.motor_type = MOTOR_TYPE_HIGH_CURRENT  # Changed from PMSM_CURRENT_CONTROL
    odrv0.axis0.encoder.config.cpr = 8192
    odrv0.axis0.motor.config.calibration_current = 50  # Reduced from 20A
    odrv0.axis0.encoder.config.use_index = False  # Disable index until basic setup works
    odrv0.axis0.motor.config.pole_pairs = 7
    odrv0.config.dc_max_negative_current = -2

    # Encoder configuration for absolute SPI
    odrv0.axis0.encoder.config.mode = ENCODER_MODE_INCREMENTAL  # or ENCODER_MODE_SPI_ABS_CUI
    odrv0.axis0.encoder.config.abs_spi_cs_gpio_pin = 1  # Typically GPIO1 for SPI CS

    # PID settings
    odrv0.axis0.controller.config.pos_gain = 20  # Reduced from 200 for stability
    odrv0.axis0.controller.config.vel_gain = 0.16  # Reduced from 0.8
    odrv0.axis0.controller.config.vel_integrator_gain = 0.1

    odrv0.axis0.controller.config.input_mode = INPUT_MODE_POS_FILTER
    odrv0.axis0.controller.config.control_mode = CONTROL_MODE_POSITION_CONTROL
    
    return True

def run_motor_calibration_only(odrv0):
    """Run motor calibration without encoder first."""
    print("Starting motor calibration only...")
    
    # First try just motor calibration
    odrv0.axis0.requested_state = AXIS_STATE_MOTOR_CALIBRATION
    
    # Wait for motor calibration to complete
    timeout = 15
    start_time = time.time()
    while odrv0.axis0.current_state != AXIS_STATE_IDLE:
        if time.time() - start_time > timeout:
            print("Motor calibration timeout!")
            return False
        time.sleep(0.5)
        print(f"Motor calibrating... State: {odrv0.axis0.current_state}")
    
    # Check for motor errors
    if odrv0.axis0.motor.error != 0:
        print(f"Motor calibration failed: {odrv0.axis0.motor.error}")
        return False
    
    print("Motor calibration successful!")
    return True

def check_encoder_connection(odrv0):
    """Check if encoder is communicating properly."""
    print("Checking encoder connection...")
    
    try:
        # Try to read encoder position
        pos = odrv0.axis0.encoder.pos_estimate
        print(f"Encoder position: {pos}")
        return True
    except Exception as e:
        print(f"Encoder read failed: {e}")
        return False

def main():
    try:
        # Find ODrive
        print("Searching for ODrive...")
        odrv0 = odrive.find_any()
        print(f"Found ODrive with serial number: {odrv0.serial_number}")
        
        # Clear any existing errors
        print("Clearing existing errors...")
        odrv0.clear_errors()
        time.sleep(1)
        
        # Check voltage first
        print(f"VBUS Voltage: {odrv0.vbus_voltage}V")
        if odrv0.vbus_voltage < 12:
            print("ERROR: DC Bus Under-Voltage! Please check power supply.")
            print("Required: 12-56V DC, Currently detected: {odrv0.vbus_voltage}V")
            return
        
        # Configure ODrive
        if not configure_odrive(odrv0):
            return
        
        # Save configuration
        print("Saving configuration...")
        try:
            odrv0.save_configuration()
            print("Configuration saved successfully")
            time.sleep(2)
        except Exception as e:
            print(f"Note: {e}")
        
        # Step 1: Motor calibration only
        if not run_motor_calibration_only(odrv0):
            return
        
        # Step 2: Check encoder connection
        if not check_encoder_connection(odrv0):
            print("Encoder not communicating. Checking configuration...")
            print("Make sure:")
            print("1. Encoder is properly wired (SPI lines)")
            print("2. Correct GPIO pin for CS is configured")
            print("3. Encoder power is connected")
            return
        
        # Step 3: Try encoder offset calibration
        print("Starting encoder offset calibration...")
        odrv0.axis0.requested_state = AXIS_STATE_ENCODER_OFFSET_CALIBRATION
        
        timeout = 10
        start_time = time.time()
        while odrv0.axis0.current_state != AXIS_STATE_IDLE:
            if time.time() - start_time > timeout:
                print("Encoder calibration timeout!")
                break
            time.sleep(0.5)
            print(f"Encoder calibrating... State: {odrv0.axis0.current_state}")
        
        if odrv0.axis0.encoder.error != 0:
            print(f"Encoder calibration error: {odrv0.axis0.encoder.error}")
            print("Trying to continue without full encoder calibration...")
        
        # Step 4: Try closed loop control
        print("Setting to closed-loop control...")
        odrv0.axis0.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
        time.sleep(1)
        
        if odrv0.axis0.current_state == AXIS_STATE_CLOSED_LOOP_CONTROL:
            print("Successfully entered closed-loop control!")
            
            # Try a small movement
            print("Testing small movement...")
            current_pos = odrv0.axis0.encoder.pos_estimate
            odrv0.axis0.controller.input_pos = current_pos + 1000  # Small movement
            time.sleep(2)
            
            # Return to original position
            odrv0.axis0.controller.input_pos = current_pos
            time.sleep(1)
            
            print("Movement test completed!")
        else:
            print(f"Failed to enter closed-loop. State: {odrv0.axis0.current_state}")
        
        # Return to idle
        odrv0.axis0.requested_state = AXIS_STATE_IDLE
        print("Done!")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()