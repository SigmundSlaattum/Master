# Diagram Reference: Data Flow and Sequence of Operations

This document provides structured text descriptions for creating diagrams of the system architecture, data flow, and sequence of operations. Each section is formatted to map directly to a specific diagram.

---

## Diagram 1: High-Level System Architecture

**Type:** Block diagram

**Blocks:**

1. **Offline Pipeline** (dashed border, contains sub-blocks)
   - Feature Extractor
   - Trajectory Generator
   - Song Manager

2. **Runtime System** (solid border, contains sub-blocks)
   - Audio Player (Master Clock)
   - Trajectory Player
   - Motor Driver
   - Playback Controller (orchestrator)

3. **User Interfaces** (solid border, contains sub-blocks)
   - Bluetooth Remote (BLE)
   - Web Interface (Flask + SocketIO)

4. **Hardware** (solid border, contains sub-blocks)
   - ODrive Motor Controller
   - BLDC Motor + Encoder
   - Audio Output Device
   - Arduino Nano 33 BLE + Rotary Encoder

5. **Data Storage**
   - Song Library (songs/)
   - Configuration (config/)

**Connections:**

- Offline Pipeline --> Song Library: "Stores trajectories + metadata"
- Song Library --> Runtime System: "Loads audio + trajectory"
- Audio Player --> Playback Controller: "current_time_seconds (master clock)"
- Playback Controller --> Trajectory Player: "timestamp + latency_offset"
- Trajectory Player --> Playback Controller: "position, velocity"
- Playback Controller --> Motor Driver: "set_position_with_velocity()"
- Motor Driver --> ODrive Motor Controller: "USB: input_pos, input_vel"
- Audio Player --> Audio Output Device: "PCM audio stream"
- Bluetooth Remote --> Playback Controller: "user_amplitude"
- Web Interface --> Playback Controller: "controls (play/stop/amplitude)"
- Configuration --> Playback Controller: "latency_offset"

---

## Diagram 2: Offline Song Preparation Pipeline

**Type:** Flow chart (top to bottom)

**Steps:**

```
[Audio File (any format)]
       |
       v
[1. Convert to WAV]
  Format: 44.1 kHz, stereo, 16-bit
       |
       v
[2. Feature Extraction]  <-- librosa
  |-- BPM detection (beat tracking)
  |-- Beat times (array of timestamps)
  |-- RMS energy (100ms frames, 1.0s window)
  |-- Spectral complexity (6 weighted features)
  |-- Local tempo (from inter-beat intervals)
       |
       v
  Output: FeatureData dataclass
       |
       v
[3. Trajectory Generation] (runs 4 times)
  |
  |--> [3a. Complex + Fixed tempo]  --> trajectory.npy
  |--> [3b. Complex + Dynamic tempo] --> trajectory_dynamic.npy
  |--> [3c. Simple + Fixed tempo]   --> trajectory_simple.npy
  |--> [3d. Simple + Dynamic tempo] --> trajectory_simple_dynamic.npy
       |
       v
  Output per variant: numpy array (N, 3)
    Column 0: timestamp (seconds)
    Column 1: position (motor turns)
    Column 2: velocity (turns/second)
       |
       v
[4. Register in Song Library]
  |-- Create song directory (songs/song_XXX/)
  |-- Save audio.wav
  |-- Save 4 trajectory .npy files
  |-- Save metadata.json
  |-- Update songs/index.json
```

---

## Diagram 3: Feature Extraction Detail

**Type:** Flow chart with data annotations

```
[Audio file (WAV)]
       |
       v
[librosa.load()] --> y (waveform), sr (sample rate)
       |
       +---> [Beat Tracking]
       |       librosa.beat.beat_track()
       |       Output: global BPM (float), beat_frames
       |         |
       |         v
       |       librosa.frames_to_time()
       |       Output: beat_times (array of seconds)
       |
       +---> [Frame-by-Frame Analysis]
       |       For each 100ms frame with 1.0s sliding window:
       |         |
       |         +---> [RMS Energy]
       |         |       librosa.feature.rms()
       |         |       Normalize: min(value * 3.0, 1.0)
       |         |       Output: rms [0-1]
       |         |
       |         +---> [Spectral Complexity]
       |                 6 features, weighted sum:
       |                 - Spectral Centroid      (10%)
       |                 - Centroid Variance       (25%)
       |                 - Spectral Bandwidth      (25%)
       |                 - Spectral Rolloff        (15%)
       |                 - Zero Crossing Rate      (10%)
       |                 - Spectral Flux           (15%)
       |                 Each normalized to [0-1]
       |                 Output: complexity [0-1]
       |
       +---> [Local Tempo Extraction]
               Input: beat_times
               1. Compute inter-beat intervals (IBI)
               2. Convert to instantaneous BPM: 60 / IBI
               3. Filter: keep 20-300 BPM range
               4. Smooth: 5-beat moving average
               5. Interpolate to analysis timestamps
               Output: local_tempo (BPM at each frame)
```

---

## Diagram 4: Trajectory Generation -- Motion Model

**Type:** Block diagram with mathematical annotations

```
INPUTS:
  - RMS(t): Audio energy at time t [0-1]
  - Complexity(t): Spectral complexity at time t [0-1]
  - BPM: Global beats per minute (fixed mode) or local_tempo(t) (dynamic mode)
  - frequency_divisor: Divisor for oscillation frequency (default 1.0)

COMPUTATION:

  [1. Frequency Calculation]
      frequency = BPM / 60 / frequency_divisor    (Hz)
      omega1 = 2 * pi * frequency                 (primary, rad/s)
      omega2 = pi * frequency                     (harmonic, rad/s)

  [2. Master Amplitude]
      master_amplitude = min(RMS(t) * 3.0, 1.0)   [0-1]

  [3. Amplitude Distribution]
      If pattern = "simple":
          complexity = 0
      A1 = max_amplitude * (1.0 - complexity * 0.5)   (primary)
      A2 = max_amplitude * complexity                   (harmonic)

  [4. Safety Attenuation]
      A_max = motor_vel_max / omega1
      If A_max < max_amplitude:
          attenuation = A_max / max_amplitude
          A1 = A1 * attenuation
          A2 = A2 * attenuation

  [5. Position and Velocity]
      FIXED TEMPO:
          position(t) = master_amp * [A1*sin(omega1*t) + A2*sin(omega2*t)]
          velocity(t) = master_amp * [A1*omega1*cos(omega1*t) + A2*omega2*cos(omega2*t)]

      DYNAMIC TEMPO:
          phase1(t) = integral_0^t omega1(tau) d_tau     (trapezoidal integration)
          phase2(t) = integral_0^t omega2(tau) d_tau
          position(t) = master_amp * [A1*sin(phase1(t)) + A2*sin(phase2(t))]
          velocity(t) = master_amp * [A1*omega1(t)*cos(phase1(t)) + A2*omega2(t)*cos(phase2(t))]

OUTPUT:
  Trajectory array: (N, 3) = [timestamp, position, velocity]
  Resolution: 10 ms (100 samples/second)
```

---

## Diagram 5: Runtime Control Loop (60 Hz)

**Type:** Sequence diagram (time flows top to bottom)

**Actors:**
- Audio Player (Thread 1 -- audio callback)
- Playback Controller (Thread 2 -- control loop)
- Trajectory Player (called by Thread 2)
- Motor Driver (called by Thread 2)
- ODrive Hardware
- Bluetooth Controller (Thread 3 -- BLE async loop)

**Sequence (one iteration of the control loop):**

```
Audio Callback Thread               Control Loop Thread (60 Hz)             BLE Thread
       |                                     |                                  |
       | [audio driver invokes callback]     |                                  |
       | outdata[:] = audio_data[start:end]  |                                  |
       | _sample_index = end                 |                                  |
       |                                     |                                  |
       |                  1. Read master clock|                                  |
       |<----- current_time_seconds ---------|                                  |
       |  (thread-safe: lock + sample_index / sample_rate)                      |
       |                                     |                                  |
       |                  2. Read user params |                                  |
       |                                     |<-- user_amplitude (lock) --------|
       |                                     |    (from encoder rotation)        |
       |                                     |                                  |
       |                  3. Compute effective time                              |
       |                     t_eff = current_time + latency_offset              |
       |                                     |                                  |
       |                  4. Trajectory lookup|                                  |
       |                     [Trajectory Player]                                |
       |                     index = floor(t_eff / time_step)                   |
       |                     interpolate position + velocity                    |
       |                     apply user_amplitude + initial_offset              |
       |                     return (target_pos, target_vel)                    |
       |                                     |                                  |
       |                  5. Send motor command                                 |
       |                     [Motor Driver]                                     |
       |                     odrv0.axis0.controller.input_vel = target_vel      |
       |                     odrv0.axis0.controller.input_pos = target_pos      |
       |                                     |                                  |
       |                  6. Read encoder feedback                              |
       |                     actual_pos = odrv0.axis0.encoder.pos_estimate      |
       |                                     |                                  |
       |                  7. Record diagnostics                                 |
       |                     loop_time, position_error                          |
       |                                     |                                  |
       |                  8. Sleep until next period                            |
       |                     next_time += 1/60                                  |
       |                     sleep(next_time - now)                             |
       |                                     |                                  |
```

---

## Diagram 6: Latency Compensation Model

**Type:** Timeline / signal flow diagram

```
TIME -->

Event A: Audio sample reaches speaker at time T_audio

Event B: Motor command sent at time T_command

Event C: Motor physically moves at time T_movement

WITHOUT COMPENSATION:
  Audio plays at T
  Motor command sent at T
  Motor moves at T + latency_total
  Result: Motor is LATE by latency_total

  |------- latency_total --------|
  |-- audio_latency --|-- motor_latency --|

  Typical values:
    Audio latency: ~18 ms (device buffer)
    Motor latency: ~19 ms (command -> movement)
    Total: ~37 ms

WITH COMPENSATION (look-ahead):
  Audio plays at T
  Motor command sent for T + latency_offset (look-ahead)
  Motor moves at T + latency_offset + latency_total
  If latency_offset = -latency_total: Motor moves at T
  Result: Motor is IN SYNC

  t_effective = current_audio_time + latency_offset

CALIBRATION PROCESS:
  1. Automated: Measure motor_latency (10 step tests) + query audio_latency
  2. Interactive: Play song, user feedback (early/late/good)
  3. Binary search adjustment (start 10ms, reduce by 30% per step, min 2ms)
  4. Save to config/latency.json
```

---

## Diagram 7: Bluetooth Remote Control Data Flow

**Type:** Sequence diagram

```
[Arduino Nano 33 BLE]          [BluetoothController]         [PlaybackController]
  Rotary Encoder                  (Python, BLE thread)          (Control loop)
  Push Button                          |                             |
       |                               |                             |
       | BLE Notify: "Pos: 32750"      |                             |
       |------------------------------>|                             |
       |                               | Parse encoder value         |
       |                               | delta = value - initial     |
       |                               | amplitude = 0.3 + delta*0.005
       |                               | clamp(0.0, 0.6)            |
       |                               |                             |
       |                               | callback: on_amplitude_change(amp)
       |                               |---------------------------->|
       |                               |                             | set_user_amplitude(amp)
       |                               |                             | (lock-protected)
       |                               |                             |
       | BLE Notify: "SWITCH PRESSED"  |                             |
       |------------------------------>|                             |
       |                               | Toggle: save/restore       |
       |                               |   amplitude (0 <-> saved)  |
       |                               | callback: on_switch_press() |
       |                               | callback: on_amplitude_change(amp)
       |                               |---------------------------->|
       |                               |                             |
       | BLE Notify: "Battery: 8.2V"   |                             |
       |------------------------------>|                             |
       |                               | Update battery_voltage     |
       |                               | Check low battery (<7V)    |
       |                               | callback: on_battery_update()|
       |                               |                             |
```

---

## Diagram 8: User Study Experimental Design

**Type:** Flow chart / matrix diagram

```
STUDY SETUP:
  User selects 3 songs, each with:
    - Song ID
    - Library source (standard / legacy)
    - Tempo mode (fixed / dynamic)

RANDOMIZATION:
  Song order:    [Song_A, Song_B, Song_C] --> shuffled --> e.g. [Song_B, Song_A, Song_C]
  Pattern order: Per song, independently shuffled:
    Song_A patterns: [COMPLEX, NONE, SIMPLE]     (example)
    Song_B patterns: [SIMPLE, COMPLEX, NONE]     (example)
    Song_C patterns: [NONE, SIMPLE, COMPLEX]     (example)

TRIAL EXECUTION (9 trials total):

  Trial 1: Song_B + SIMPLE
    trajectory: trajectory_simple.npy (or _dynamic variant)
    amplitude: 0.5
  Trial 2: Song_B + COMPLEX
    trajectory: trajectory.npy (or _dynamic variant)
    amplitude: 0.5
  Trial 3: Song_B + NONE
    trajectory: trajectory.npy (amplitude = 0.0, no motion)
    amplitude: 0.0
  --- Song_B complete ---

  Trial 4: Song_A + COMPLEX
  Trial 5: Song_A + NONE
  Trial 6: Song_A + SIMPLE
  --- Song_A complete ---

  Trial 7: Song_C + NONE
  Trial 8: Song_C + SIMPLE
  Trial 9: Song_C + COMPLEX
  --- Song_C complete ---
  --- Study complete ---

PATTERN DEFINITIONS:
  NONE:    No motion. Trajectory loaded but amplitude = 0.0
  SIMPLE:  Single sinusoid. Uses trajectory_simple[_dynamic].npy
           Complexity forced to 0, only primary frequency active
  COMPLEX: Dual sinusoid. Uses trajectory[_dynamic].npy
           Both primary and harmonic frequencies, driven by audio complexity

DATA COLLECTION PER TRIAL:
  - Motor position time series (recorded via DataRecorder)
  - User amplitude time series
  - Synchronization metrics (phase lag, correlation, peak offsets)
  - CSV export + visualization plots
```

---

## Diagram 9: Thread Architecture

**Type:** Block diagram showing concurrent threads

```
+--------------------------------------------------+
|                MAIN THREAD                        |
|  - CLI interface (main.py)                        |
|  - Song selection                                 |
|  - Setup and teardown                             |
+--------------------------------------------------+
         |              |               |
         v              v               v
+----------------+ +------------------+ +-------------------+
| AUDIO THREAD   | | CONTROL THREAD   | | BLE THREAD        |
| (sounddevice)  | | (60 Hz loop)     | | (asyncio loop)    |
|                | |                  | |                   |
| - Callback-    | | - Read audio     | | - BLE scan        |
|   based stream | |   clock          | | - BLE connect     |
| - Fills output | | - Lookup         | | - Notification    |
|   buffer       | |   trajectory     | |   handler         |
| - Updates      | | - Send motor     | | - Auto-reconnect  |
|   sample_index | |   commands       | |                   |
|                | | - Record data    | | Writes to:        |
| Provides:      | |                  | |  user_amplitude   |
|  master clock  | | Reads from:      | |  (lock-protected) |
|  (sample count)| |  audio timestamp | |                   |
+----------------+ |  user_amplitude  | +-------------------+
                   |  latency_offset  |
                   |                  |
                   | Writes to:       |
                   |  motor commands  |
                   |  (via USB)       |
                   +------------------+

SHARED STATE (lock-protected):
  - _sample_index:    Written by Audio Thread,    Read by Control Thread
  - _user_amplitude:  Written by BLE Thread,      Read by Control Thread
  - _latency_offset:  Written by Web/Main Thread, Read by Control Thread
  - _feedforward_enabled: Written by Web Thread,  Read by Control Thread

Optional additional threads:
  +-------------------+
  | WEB SERVER THREAD  |
  | (Flask-SocketIO)   |
  | - HTTP endpoints   |
  | - WebSocket events |
  | - Reads/writes     |
  |   shared state     |
  +-------------------+
```

---

## Diagram 10: Complete Data Flow (End-to-End)

**Type:** Data flow diagram (DFD)

```
                        OFFLINE PHASE
                        =============

  [Audio File] --(raw audio)--> [Feature Extractor]
                                       |
                               (FeatureData: BPM, beats,
                                RMS, complexity, local_tempo)
                                       |
                                       v
                               [Trajectory Generator]
                                       |
                               (4 trajectory .npy files:
                                each is N x 3 array of
                                [time, position, velocity])
                                       |
                                       v
                                [Song Manager]
                                       |
                               (songs/song_XXX/
                                audio.wav, trajectory*.npy,
                                metadata.json, index.json)
                                       |
                                       v
                               [Song Library on Disk]


                        RUNTIME PHASE
                        =============

  [Song Library] --audio.wav--> [Audio Player]
                                    |
                                (PCM samples) --> [Speaker]
                                    |
                            (current_time_seconds)
                                    |
                                    v
  [Song Library] --trajectory.npy--> [Trajectory Player]
                                          |
                                    (position, velocity
                                     at t + latency_offset)
                                          |
                                          v
  [config/latency.json] --offset--> [Playback Controller] <--user_amplitude-- [BLE Remote]
                                          |
                                    (input_pos, input_vel)
                                          |
                                          v
                                    [Motor Driver]
                                          |
                                    (USB commands)
                                          |
                                          v
                                    [ODrive Controller]
                                          |
                                    (PWM signals)
                                          |
                                          v
                                    [BLDC Motor]
                                          |
                                    (physical rotation)
                                          |
                                          v
                                    [Encoder] --feedback--> [Motor Driver]
                                                              |
                                                        (position_error)
                                                              |
                                                              v
                                                        [Data Recorder]
                                                              |
                                                        (CSV, plots,
                                                         sync analysis)
```

---

## Diagram 11: Song Library File Structure

**Type:** Tree diagram

```
MUSIC_FEATURE_MODEL/
|
+-- songs/
|   +-- index.json                          # Song registry (all songs listed)
|   |
|   +-- song_001/
|   |   +-- audio.wav                       # 44.1 kHz stereo audio
|   |   +-- trajectory.npy                  # Complex pattern, fixed tempo
|   |   +-- trajectory_dynamic.npy          # Complex pattern, dynamic tempo
|   |   +-- trajectory_simple.npy           # Simple pattern, fixed tempo
|   |   +-- trajectory_simple_dynamic.npy   # Simple pattern, dynamic tempo
|   |   +-- metadata.json                   # Song metadata + feature statistics
|   |
|   +-- song_002/
|   |   +-- (same structure)
|   |
|   +-- ...
|
+-- config/
|   +-- latency.json                        # Calibrated latency offsets
|
+-- src/
    +-- main.py                             # CLI entry point
    +-- config.py                           # Global configuration
    +-- bluetooth_controller.py             # BLE remote control
    +-- odrive_controller.py                # Motor setup
    +-- data_recorder.py                    # Data recording + analysis
    +-- user_study.py                       # Experiment management
    |
    +-- core/                               # Real-time playback
    |   +-- audio_player.py                 # Master clock (audio)
    |   +-- trajectory_player.py            # O(1) trajectory lookup
    |   +-- motor_driver.py                 # ODrive command interface
    |   +-- playback_controller.py          # Main orchestrator
    |
    +-- offline/                            # Pre-computation
    |   +-- feature_extractor.py            # Audio analysis (librosa)
    |   +-- trajectory_generator.py         # Motion generation
    |   +-- song_manager.py                 # Song library management
    |   +-- prepare_song.py                 # Song preparation CLI
    |   +-- regenerate_trajectory.py        # Batch regeneration
    |
    +-- calibration/
    |   +-- calibrator.py                   # Latency measurement
    |
    +-- web/
        +-- app.py                          # Flask web interface
```

---

## Diagram 12: Amplitude Distribution by Complexity (for motion model explanation)

**Type:** Chart / visual explanation

```
Complexity = 0.0 (Simple music)          Complexity = 1.0 (Complex music)
================================         ================================

A1 = max_amp * (1.0 - 0*0.5)            A1 = max_amp * (1.0 - 1*0.5)
   = max_amp * 1.0                          = max_amp * 0.5
   = 7.5 turns (100%)                       = 3.75 turns (50%)

A2 = max_amp * 0.0                       A2 = max_amp * 1.0
   = 0.0 turns (0%)                         = 7.5 turns (100%)

Motion: Pure single sinusoid             Motion: Both sinusoids active
  pos(t) = A1*sin(omega*t)                pos(t) = A1*sin(omega*t)
                                                  + A2*sin(omega/2*t)

   ^                                        ^
   |  /\    /\    /\                        |  /\  /\      /\
   | /  \  /  \  /  \                       | /  \/  \    /
   |/    \/    \/    \                      |/        \  /
   +-------------------->                   +-------------------->
   |                  t                     |                    t
                                            More layered, complex shape


Complexity = 0.5 (Moderate)
================================
A1 = max_amp * 0.75 = 5.625 turns
A2 = max_amp * 0.50 = 3.75 turns

Motion: Primary dominant, harmonic present
```

---

## Diagram 13: Latency Calibration Process

**Type:** Flow chart

```
[Start Calibration]
       |
       v
[Arm Motor (closed-loop control)]
       |
       v
[Measure Motor Latency]
  Repeat 10 times:
    1. Record current position
    2. Send step command (+0.5 turns)
    3. Start timer
    4. Poll encoder until movement > threshold
    5. Record latency
    6. Return to start position
  Average all measurements
       |
       v
  motor_latency_ms (e.g., 19 ms)
       |
       v
[Query Audio Latency]
  sounddevice.query_devices() -->
  default_low_output_latency
       |
       v
  audio_latency_ms (e.g., 18 ms)
       |
       v
[Calculate Total]
  total = motor_latency + audio_latency
  (e.g., 37 ms)
       |
       v
[Interactive Fine-Tuning?] --No--> [Save & Done]
       |
      Yes
       |
       v
[Play 15-second test clip with current offset]
       |
       v
[User Feedback]
  |-- "Early" --> offset -= adjustment; adjustment *= 0.7 (min 2ms) --> [Replay]
  |-- "Late"  --> offset += adjustment; adjustment *= 0.7 (min 2ms) --> [Replay]
  |-- "Good"  --> [Save & Done]
  |-- "Replay"--> [Replay with same offset]
  |-- "Quit"  --> [Save & Done]
       |
       v
[Save to config/latency.json]
  {
    motor_latency_ms: 19.07,
    audio_latency_ms: 18.71,
    total_latency_ms: 37.78,
    fine_tune_offset_ms: -27.78,
    final_offset_ms: 10.0
  }
```
