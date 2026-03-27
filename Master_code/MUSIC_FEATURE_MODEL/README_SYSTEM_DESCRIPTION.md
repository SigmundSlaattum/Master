# Music-Synchronized Motor Control System: Technical Description

This document provides a third-person description of the software system developed for the master thesis. The system synchronizes a motorized floor platform with music by extracting audio features offline and using them to generate pre-computed motor trajectories that are played back in real time.

---

## 1. System Overview

The system is a music-synchronized motor control platform that translates audio characteristics into physical motion. It operates in two distinct phases: an **offline preparation phase** where audio analysis and trajectory computation take place, and a **runtime phase** where the pre-computed trajectories are played back in synchronization with audio output.

The architecture follows an "offline-heavy, runtime-light" design principle. All computationally expensive operations (feature extraction, trajectory generation) are performed before playback begins, while the real-time control loop is kept minimal to ensure deterministic timing.

The software is implemented in Python and organized into the following modules:

| Module | Location | Responsibility |
|--------|----------|---------------|
| Offline Pipeline | `src/offline/` | Feature extraction, trajectory generation, song management |
| Core Playback | `src/core/` | Audio playback, trajectory lookup, motor control, orchestration |
| Calibration | `src/calibration/` | System latency measurement and compensation |
| Remote Control | `src/bluetooth_controller.py` | Bluetooth Low Energy remote for amplitude control |
| Data Recording | `src/data_recorder.py` | Runtime data capture and synchronization analysis |
| User Study | `src/user_study.py` | Experimental workflow management |
| Web Interface | `src/web/app.py` | Browser-based control panel |
| Motor Setup | `src/odrive_controller.py` | ODrive motor controller configuration |
| Configuration | `src/config.py` | Centralized system parameters |
| Entry Point | `src/main.py` | CLI interface for song selection and playback |

---

## 2. Offline Pipeline

### 2.1 Feature Extraction (`src/offline/feature_extractor.py`)

The feature extractor analyzes an audio file and produces a set of time-indexed features that describe the musical content. It uses the `librosa` library for all signal processing operations.

The extractor loads the audio file at its native sample rate and computes the following features:

**Global features:**
- **BPM (Beats Per Minute):** The global tempo is estimated using librosa's beat tracking algorithm, which identifies beat positions in the audio signal.
- **Beat times:** An array of timestamps (in seconds) marking each detected beat.

**Time-indexed features** (computed at approximately 100 ms intervals using a 1.0-second sliding analysis window):

- **RMS Energy:** The root-mean-square energy of each audio segment is computed using `librosa.feature.rms`. The raw RMS value is normalized to a 0-1 range by multiplying by 3.0 and capping at 1.0. This feature represents the loudness of the music at each point in time.

- **Spectral Complexity:** A composite metric calculated from six weighted spectral features:
  - Spectral Centroid (10% weight) -- represents the brightness of the sound
  - Spectral Centroid Variance (25% weight) -- captures variation in brightness
  - Spectral Bandwidth (25% weight) -- measures the spread of frequencies
  - Spectral Rolloff (15% weight) -- indicates the amount of high-frequency content
  - Zero Crossing Rate (10% weight) -- reflects percussiveness
  - Spectral Flux (15% weight) -- captures dynamic changes in the spectrum

  Each component is normalized to a 0-1 range using empirically determined frequency ranges (e.g., spectral centroid is mapped from the 500-4000 Hz range). The weighted sum produces a single complexity value between 0 and 1.

- **Local Tempo:** The instantaneous tempo at each timestamp is derived from inter-beat intervals (IBIs). The time difference between consecutive beats is converted to BPM, filtered to the 20-300 BPM range, smoothed with a 5-beat moving average, and interpolated to match the analysis timestamps.

All extracted features are stored in a `FeatureData` dataclass containing the global BPM, duration, sample rate, timestamp array, RMS array, complexity array, local tempo array, and beat times array.

### 2.2 Trajectory Generation (`src/offline/trajectory_generator.py`)

The trajectory generator converts the extracted audio features into a pre-computed array of motor positions and velocities. The output is a NumPy array of shape (N, 3), where each row contains a timestamp, a motor position (in motor turns), and a motor velocity (in turns per second).

**Motion model:**

The system uses a dual-sinusoid motion model:

```
position(t) = master_amplitude * [A1 * sin(omega1 * t) + A2 * sin(omega2 * t)]
velocity(t) = master_amplitude * [A1 * omega1 * cos(omega1 * t) + A2 * omega2 * cos(omega2 * t)]
```

Where:
- `omega1 = 2 * pi * frequency` is the primary angular frequency
- `omega2 = pi * frequency` is a harmonic at half the primary frequency
- `frequency = BPM / 60 / frequency_divisor`
- `master_amplitude = min(RMS * 3.0, 1.0)` scales the motion according to the audio energy

**Amplitude distribution based on complexity:**

The complexity value determines how the total amplitude is distributed between the two sinusoidal components:

```
A1 = max_amplitude * (1.0 - complexity * 0.5)
A2 = max_amplitude * complexity
```

When the complexity is 0 (simple music), the motion is a pure single sinusoid at the beat frequency. When complexity is 1 (complex music), both the primary and harmonic sinusoids contribute equally, producing a more layered motion pattern.

**Pattern types:**

Two pattern types are supported:
- **Simple pattern:** Forces complexity to 0.0, resulting in a single sinusoidal oscillation.
- **Complex pattern:** Uses the actual complexity values from the audio analysis, distributing amplitude between both sinusoidal components.

**Tempo modes:**

Two tempo modes are supported:

- **Fixed tempo:** Uses the constant global BPM throughout the entire trajectory. The angular frequencies remain constant, and standard sinusoidal formulas are applied.

- **Dynamic tempo:** Uses the time-varying local tempo. Instead of a constant angular frequency, the system performs cumulative phase integration using the trapezoidal rule:

  ```
  phase(t) = integral from 0 to t of omega(tau) d_tau
  ```

  This approach ensures that the oscillation frequency smoothly tracks tempo changes in the music without phase discontinuities.

**Motor safety -- amplitude attenuation:**

At high tempos, the peak motor velocity of the sinusoidal motion may exceed the safe operating limits of the motor (a Turnigy SK8-6374 BLDC motor rated at 192 KV). The system computes the maximum safe amplitude as:

```
A_max = motor_velocity_max / (2 * pi * frequency)
```

If the configured maximum amplitude exceeds this value, an attenuation factor is applied to reduce the amplitude proportionally. The motor RPM limit is set conservatively to 5500 RPM, below the physical limit of approximately 6144 RPM at 32V.

**Output:**

For each song, four trajectory variants are generated:
1. `trajectory.npy` -- Complex pattern, fixed tempo
2. `trajectory_dynamic.npy` -- Complex pattern, dynamic tempo
3. `trajectory_simple.npy` -- Simple pattern, fixed tempo
4. `trajectory_simple_dynamic.npy` -- Simple pattern, dynamic tempo

The trajectories are stored at 10 ms resolution (100 Hz), resulting in approximately 100 samples per second.

### 2.3 Song Management (`src/offline/song_manager.py`)

The song manager maintains a library of prepared songs. Each song is stored in its own directory (e.g., `songs/song_001/`) containing the audio file (`audio.wav` at 44.1 kHz stereo), four trajectory variants, and a metadata file (`metadata.json`).

A central index file (`songs/index.json`) tracks all registered songs with their metadata: ID, name, artist, duration, BPM, directory path, original filename, and creation timestamp.

### 2.4 Song Preparation (`src/offline/prepare_song.py`)

The song preparation module orchestrates the full offline pipeline. When a new song is added to the system, the following steps are executed in sequence:

1. The audio file is converted to WAV format (44.1 kHz, stereo) if it is not already in that format.
2. Audio features are extracted using the feature extractor.
3. Four trajectory variants are generated (simple/complex crossed with fixed/dynamic tempo).
4. The song is registered in the song library index.
5. Metadata including feature statistics is saved.

An optional BPM override allows the user to specify a different tempo than the one detected automatically. When a BPM override is applied, the local tempo values are scaled proportionally to maintain the relative tempo variations while changing the baseline.

---

## 3. Runtime System

### 3.1 Audio Player (`src/core/audio_player.py`)

The audio player is responsible for audio output and serves as the **master clock** for the entire synchronization system. It uses the `sounddevice` library to create a callback-based output stream.

The audio file is loaded entirely into memory as a float32 NumPy array normalized to the range [-1.0, 1.0]. If the source is mono, it is duplicated to stereo. Playback is driven by a callback function invoked by the audio driver at regular intervals (block size of 1024 samples by default).

The critical property of the audio player is its `current_time_seconds` attribute, which computes the current playback position by dividing the sample index by the sample rate. This property is thread-safe (protected by a lock) and is read by the motor control loop running in a separate thread. Since the sample index is updated atomically within the audio callback, this provides sample-accurate timing information.

### 3.2 Trajectory Player (`src/core/trajectory_player.py`)

The trajectory player provides efficient lookup of pre-computed motor positions and velocities. It is designed to operate in the real-time control loop with minimal CPU overhead.

The trajectory is loaded from a `.npy` file at initialization. The player supports both legacy format (N, 2) with only timestamps and positions, and the current format (N, 3) with timestamps, positions, and velocities.

**Lookup mechanism:**

Since the trajectory is sampled at uniform time intervals (10 ms), the player uses an O(1) index calculation instead of binary search:

```
index = floor(timestamp / time_step)
```

Once the index is determined, linear interpolation is applied between adjacent samples:

```
alpha = (t - t0) / (t1 - t0)
position = p0 + alpha * (p1 - p0)
velocity = v0 + alpha * (v1 - v0)
```

The looked-up position is then scaled by the user amplitude and offset to the motor's initial position:

```
final_position = initial_offset + base_position * user_amplitude
final_velocity = base_velocity * user_amplitude
```

### 3.3 Motor Driver (`src/core/motor_driver.py`)

The motor driver is a thin interface layer to the ODrive motor controller. It provides two methods for sending motor commands:

- **Position-only mode:** Sets the target position via `odrv0.axis0.controller.input_pos`.
- **Position with velocity feedforward:** Sets both the target velocity (`input_vel`) and target position (`input_pos`). The velocity feedforward improves tracking accuracy by informing the controller of the expected velocity, which reduces phase lag during fast direction changes.

The driver also reads the current motor position from the encoder (`odrv0.axis0.encoder.pos_estimate`) for error monitoring and tracks command counts and last-commanded values for diagnostics.

### 3.4 Playback Controller (`src/core/playback_controller.py`)

The playback controller is the main orchestrator that coordinates audio playback, trajectory lookup, and motor control. It runs a dedicated control thread at 60 Hz (configurable).

**Control loop operation:**

On each iteration (approximately every 16.7 ms), the control loop performs the following steps:

1. **Read the master clock:** The current playback time is obtained from the audio player's sample-accurate timestamp.
2. **Read user parameters:** The user amplitude (from the Bluetooth remote or web interface) and latency offset are read in a thread-safe manner.
3. **Look up the trajectory:** The effective timestamp (current time plus latency offset) is used to look up the pre-computed position and velocity from the trajectory player.
4. **Send the motor command:** The target position and velocity (if feedforward is enabled) are sent to the motor driver.
5. **Record diagnostics:** Loop timing and position error are recorded for statistics.
6. **Timing regulation:** The loop sleeps until the next scheduled iteration to maintain the target rate.

The control loop is designed to complete each iteration in under 1 ms, providing approximately 60x headroom relative to the 16.7 ms period.

**Thread safety:**

User-controllable parameters (amplitude, latency offset, feedforward enable) are each protected by individual locks. This allows the Bluetooth controller, web interface, or other threads to update these values without interfering with the control loop.

---

## 4. Latency Calibration (`src/calibration/calibrator.py`)

Audio-motor synchronization requires compensating for the total system latency, which includes audio device output latency, USB communication delay, and motor mechanical response time.

The calibration process consists of two phases:

**Automated measurement:**
1. **Motor latency** is measured by sending a step position command and timing how long it takes for the encoder to detect movement. This is repeated 10 times, and the results are averaged.
2. **Audio latency** is queried from the audio device driver using the `sounddevice` library.
3. The total latency is computed as the sum of motor and audio latency (typically around 35-40 ms).

**Interactive fine-tuning:**
After automated measurement, the user can listen to a test song while observing the motor. The user reports whether the motor appears to move early, late, or in sync with the beat. Based on this feedback, the latency offset is adjusted iteratively with decreasing step sizes (starting at 10 ms, reducing by 30% per iteration, with a minimum of 2 ms).

The calibrated offset is saved to `config/latency.json` and loaded automatically for subsequent playback sessions. The playback controller uses this offset as a look-ahead parameter: the trajectory is evaluated at `current_time + latency_offset` to compensate for the delay between command issuance and physical movement.

---

## 5. Bluetooth Remote Control (`src/bluetooth_controller.py`)

The system includes a wireless remote control built from an Arduino Nano 33 BLE with a rotary encoder and push button. Communication uses Bluetooth Low Energy (BLE) with a custom GATT service.

**Communication protocol:**

The Arduino sends UTF-8 encoded messages via BLE notifications:
- `"Pos: <integer>"` -- Reports the absolute encoder position (0-65535).
- `"SWITCH PRESSED"` -- Reports a button press event.
- `"Battery: <float>V"` -- Reports the current battery voltage.
- `"BATTERY LOW: <float>V"` -- Reports a low-battery warning.

**Amplitude control:**

The user amplitude is computed from the encoder change relative to an initial baseline:

```
user_amplitude = clamp(0.3 + delta * step_size, 0.0, max_amplitude)
```

Where `delta` is the encoder position change (optionally direction-reversed), `step_size` is 0.005 per encoder click, and `max_amplitude` is 0.6. The initial default amplitude is 0.3.

The button toggles the motion on and off: pressing it saves the current amplitude and sets it to 0.0; pressing again restores the saved amplitude.

**Connection management:**

The BLE connection runs in a dedicated background thread with an asyncio event loop. Auto-reconnection is supported: if the connection is lost, the system retries at configurable intervals (default 5 seconds).

---

## 6. Data Recording and Analysis (`src/data_recorder.py`)

The data recorder captures time-series data during playback for post-hoc analysis. It records five streams at the control loop rate:

- Timestamps (relative to recording start)
- User amplitude values (from the remote control)
- Original positions (trajectory values before user amplitude scaling)
- Final positions (the actual commands sent to the motor)
- Actual positions (encoder feedback from the motor)

Data is stored in bounded deques (default 10,000 samples) to prevent unbounded memory growth.

**Analysis capabilities:**

The recorder provides several analysis and visualization functions:

- **Statistics:** Min, max, mean, and standard deviation for each data stream, plus position error RMS.
- **Separate plots:** Three-subplot figures showing user amplitude, original positions, and final positions over time.
- **Combined plots:** Overlay of all data streams on a single plot with dual y-axes.
- **Synchronization analysis:** Compares the actual motor position against a music-derived reference sinusoid at the beat frequency. The analysis computes:
  - Phase lag (via cross-correlation)
  - Correlation coefficient (shape similarity)
  - Mean peak timing offset (per-beat accuracy)
  - Peak offset standard deviation (consistency)

Data can be exported to CSV files for further processing.

---

## 7. User Study Framework (`src/user_study.py`)

The user study module manages a within-subjects experimental design for evaluating the effect of different motion patterns on the user experience.

**Study design:**

Each study session consists of 3 songs, each played with 3 different motion patterns:
- **NONE:** No motion (amplitude set to 0.0)
- **SIMPLE:** Single-sinusoid oscillation at the beat frequency
- **COMPLEX:** Dual-sinusoid oscillation with complexity-driven amplitude distribution

This produces 9 trials per participant (3 songs x 3 patterns). Both the song order and the pattern order within each song are randomized independently.

**Trial management:**

The study manager provides methods to:
- Set up a new study with selected songs and their configurations (library source, tempo mode)
- Retrieve the current trial (song, pattern, trial number)
- Advance to the next trial after completion
- Track progress and generate summaries
- Determine the appropriate trajectory file and amplitude for each trial

The study module does not interact directly with playback or motor control; instead, it provides configuration information that the web interface uses to set up each trial.

**Data collection:**

When data recording is enabled for a study, the system automatically records motor and control data during each trial and saves the results upon trial completion. All output files are stored in a study-specific folder under `src/user_study_data/<folder_name>/`, where `<folder_name>` is specified by the user at study setup.

For each completed trial, the following files are generated in a background thread to avoid blocking the control loop:

1. **Raw data CSV** (`<SongName>__<pattern>__data.csv`): Contains the full time-series recording with columns for time, user amplitude, original position, final position, and actual position.

2. **Separate plot** (`<SongName>__<pattern>__plot_separate.png`): A three-subplot figure showing user amplitude, original trajectory position, and final motor position as individual time-series plots.

3. **Combined plot** (`<SongName>__<pattern>__plot_combined.png`): An overlay visualization with all data streams on a single plot using dual y-axes for position and amplitude.

4. **Synchronization plot** (`<SongName>_<pattern>_synchronization.png`): A two-panel figure comparing the actual motor position against a reference sinusoid derived from the song's BPM. The upper panel overlays the music beat sinusoid with the centered motor position and displays synchronization metrics (BPM, phase lag, correlation coefficient, mean peak offset, and peak offset standard deviation). The lower panel shows per-beat timing offsets over time with mean and standard deviation bands.

5. **Synchronization CSV** (`<SongName>_<pattern>_synchronization.csv`): Contains metadata headers with synchronization metrics (BPM, music frequency, phase lag, correlation, mean peak offset, peak offset standard deviation, number of peaks), followed by per-peak timing offset data and the full time-series of the music reference sinusoid alongside the centered actual motor position.

When the study is completed (all 9 trials finished), a **trial list summary** (`trial_list.txt`) is saved to the same output directory. This file documents the order in which trials were presented, listing the trial number, song name, pattern type, library source, and tempo mode for each trial.

---

## 8. Web Interface (`src/web/app.py`)

The web interface is built with Flask and Flask-SocketIO, providing a browser-based control panel for the system. It exposes REST API endpoints for playback control and WebSocket events for real-time status updates.

**Key features:**
- Song selection from both the standard and legacy libraries
- Playback controls (play, stop, pause/resume)
- Bluetooth remote connection management
- Real-time display of user amplitude, motor position, and loop timing
- Data recording with CSV and plot export
- User study workflow with guided trial progression
- Live battery voltage monitoring for the remote control

---

## 9. Motor Configuration (`src/odrive_controller.py`)

The ODrive controller module handles the configuration and setup of the brushless DC motor. The motor is a Turnigy SK8-6374 (192 KV) with a CUI AMT102-V incremental encoder (8192 counts per revolution).

**Key configuration parameters:**
- Control mode: Position control with velocity feedforward
- Current limit: 80 A
- Velocity limit: 50 turns/second
- Position gain: 50
- Acceleration/deceleration limit: 10 turns/second^2
- Brake resistance: 2.0 ohm (for regenerative braking)
- Gear ratio: 15:1 (motor turns to output turns)

The module provides functions for motor calibration (phase resistance, inductance, encoder offset), arming (transitioning to closed-loop control), error detection and clearing, and soft/hard reset operations.

---

## 10. Global Configuration (`src/config.py`)

The configuration module defines system-wide parameters organized into three dataclasses:

- **MotorConfig:** Gear ratio (15.0), maximum amplitude (7.5 motor turns), control loop rate (60 Hz), and motor velocity limits (5500 RPM conservative maximum).
- **AudioConfig:** Sample rate (44,100 Hz) and audio buffer block size (1024 samples).
- **TrajectoryConfig:** Trajectory time resolution (10 ms).

The module also defines project directory paths (songs, configuration, legacy) and ensures required directories exist at import time.
