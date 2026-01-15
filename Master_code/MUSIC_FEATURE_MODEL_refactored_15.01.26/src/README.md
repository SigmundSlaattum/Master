# Source Code Directory

This directory contains all the Python source code for the Music-Synchronized Motor Control project.

## Project Structure

```
src/
├── motor_control_music.py          # Main control script (entry point)
├── motor_controller.py              # Motor control loop logic
├── odrive_controller.py             # ODrive setup and communication
├── music_config.py                  # Music library management
├── music_analyzer.py                # Music feature extraction
├── visualization.py                 # Visualization management
├── audio_synthesizer.py             # Real-time audio synthesis
├── floor_simulator.py               # PyBullet simulation
├── delay_compensator.py             # Delay compensation utilities
├── motor_control_music_backup.py    # Backup of original implementation
├── motor_control_music_with_delay_comp.py  # Delay compensation example
└── test_simulator.py                # Simulator test script
```

## Running the Project

From the `src/` directory, run:

```bash
# Basic usage (hardware mode)
python motor_control_music.py

# Simulation mode
python motor_control_music.py -sim

# With plotting
python motor_control_music.py -sim -plot

# Select music genre
python motor_control_music.py -g metal -s 0

# Interactive song selection
python motor_control_music.py -i

# Reset and calibrate ODrive
python motor_control_music.py -r -c

# With audio synthesis
python motor_control_music.py -sim -a
```

## Module Overview

### Core Modules

- **motor_control_music.py**: Main entry point that coordinates all components
- **motor_controller.py**: Encapsulates control loop logic with music synchronization
- **odrive_controller.py**: Handles ODrive connection, configuration, and reset operations

### Music & Analysis

- **music_config.py**: Manages music library, song selection, and file paths
- **music_analyzer.py**: Extracts music features (BPM, RMS, complexity, beat phase)

### Visualization & Feedback

- **visualization.py**: Unified interface for PyBullet simulation and matplotlib plotting
- **audio_synthesizer.py**: Generates audio feedback based on motor position

### Utilities

- **floor_simulator.py**: PyBullet-based floor platform simulation
- **delay_compensator.py**: LSE-based delay compensation utilities

## Dependencies

The songs directory is located at `../../songs` (in the Master_code directory, two levels up from src/).

Directory structure:
```
Master_code/
├── songs/                    # Music files
└── MUSIC_FEATURE_MODEL/
    ├── src/                  # You are here
    └── ...
```

See the main project README for full dependency list and installation instructions.