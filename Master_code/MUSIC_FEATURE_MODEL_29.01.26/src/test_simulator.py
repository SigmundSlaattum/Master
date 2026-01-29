#!/usr/bin/env python3
"""
Simple test script for the floor platform simulator.
Run this to verify the simulator works before using it with the full system.
"""

from floor_simulator import FloorPlatformSimulator
import time
import math


def main():
    print("=" * 50)
    print("Floor Platform Simulator Test")
    print("=" * 50)
    print("\nThis will run a simple motion pattern to verify")
    print("the PyBullet simulation is working correctly.\n")

    # Create simulator with GUI enabled
    simulator = FloorPlatformSimulator(enable_gui=True)

    try:
        print("Running test pattern for 20 seconds...")
        print("You should see:")
        print("  - Bottom wooden plate (static)")
        print("  - 4 vertical aluminum struts at corners")
        print("  - Horizontal aluminum struts at top and bottom")
        print("  - Top wooden plate moving up/down and side-to-side")
        print("\nPress Ctrl+C to stop early.\n")

        duration = 20.0  # seconds
        start_time = time.time()

        # Test with two superimposed sinusoids (like the real system)
        frequency1 = 1.0  # 1 Hz
        frequency2 = 0.5  # 0.5 Hz (half speed)
        amplitude1 = 8.0
        amplitude2 = 3.0

        while (time.time() - start_time) < duration:
            current_time = time.time() - start_time

            # Generate composite sinusoidal position command
            # (mimics the real motor control pattern)
            pos1 = amplitude1 * math.sin(2 * math.pi * frequency1 * current_time)
            pos2 = amplitude2 * math.sin(2 * math.pi * frequency2 * current_time)
            position = pos1 + pos2

            # Update simulator
            simulator.update_position(position)
            simulator.step_simulation()

            # Print status every 2 seconds
            if int(current_time * 2) % 2 == 0 and (current_time % 1.0) < 0.02:
                print(f"Time: {current_time:.1f}s | Position: {position:+.2f} | "
                      f"Vertical: ~{position*0.01:.3f}m")

        print("\n" + "=" * 50)
        print("Test complete! Simulation is working correctly.")
        print("=" * 50)

    except KeyboardInterrupt:
        print("\n\nTest stopped by user.")
    finally:
        simulator.close()


if __name__ == "__main__":
    main()
