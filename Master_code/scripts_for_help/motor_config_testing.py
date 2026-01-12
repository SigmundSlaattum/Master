import odrive 
from odrive.enums import*
import time
import math


# Arm motor
print("Finding an ODrive...")
odrv0 = odrive.find_any()
print(f"Found ODrive with serial number: {odrv0.serial_number}")
odrv0.axis0.requested_state = 8  # CLOSED_LOOP_CONTROL
time.sleep(1)

# Sinusoidal motion parameters
amplitude = 11  # revolutions (adjust to your needs)
frequency = 1   # Hz (adjust based on your audio BPM)

start_time = time.time()
last_time = start_time
start_position = odrv0.axis0.encoder.pos_estimate
try:
    while True:
        current_time = time.time()
        dt = current_time - last_time
        
        # Only update if enough time has passed (target 200-500 Hz)
        if dt >= 0.002:  # 500 Hz update rate
            t = current_time - start_time
            position = start_position + amplitude * math.sin(2 * math.pi * frequency * t)
            odrv0.axis0.controller.input_pos = position
            last_time = current_time
except KeyboardInterrupt:
    odrv0.axis0.requested_state = 1  # IDLE