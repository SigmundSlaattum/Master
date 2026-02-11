# MUSIC_FEATURE_MODEL: Complete System Architecture Documentation

## Executive Summary

The MUSIC_FEATURE_MODEL is a real-time music-synchronized motor control system. It consists of:
- **Offline pipeline**: Feature extraction → Trajectory generation → Pre-computation
- **Runtime system**: Audio playback → Trajectory lookup → Motor control at 60Hz
- **Real-time control**: Velocity feedforward, latency compensation, user amplitude modulation
- **Remote interface**: Bluetooth encoder control, Web UI with user study capabilities

---

## 1. FEATURE EXTRACTION PIPELINE

### 1.1 Overview

All feature extraction happens **offline** during song preparation, not during playback. This keeps the real-time control loop CPU-light.

**Location**: `src/offline/feature_extractor.py`

### 1.2 Feature Data Structure

```python
@dataclass
class FeatureData:
    bpm: float                    # Global beats per minute
    duration: float               # Total duration in seconds
    sample_rate: int              # Sample rate (44100 Hz)

    timestamps: np.ndarray        # Shape (num_frames,) - time in seconds (~100ms intervals)
    rms: np.ndarray               # Shape (num_frames,) - RMS energy [0-1]
    complexity: np.ndarray        # Shape (num_frames,) - spectral complexity [0-1]
    local_tempo: np.ndarray       # Shape (num_frames,) - local BPM at each timestamp

    beat_times: np.ndarray        # Shape (num_beats,) - beat positions in seconds
```

### 1.3 Feature Extraction Details

#### BPM Detection
```python
tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=512)
beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=512)
```
- Uses librosa's beat tracking algorithm
- Returns global BPM and per-beat timestamps

#### Frame-Level Features
- **Resolution**: 0.1s (100ms) intervals
- **Window**: 1.0s sliding window centered on each timestamp
- **RMS calculation**: `rms_values[i] = min(rms_mean * 3.0, 1.0)` normalized to [0-1]

#### Complexity Metric

Six weighted spectral features combined:

| Feature | Weight | Normalization | Meaning |
|---------|--------|---------------|---------|
| Spectral Centroid | 0.10 | (centroid - 500Hz) / 3500Hz | Brightness |
| Centroid Variance | 0.25 | std / 500Hz | Brightness variation |
| Spectral Bandwidth | 0.25 | (bandwidth - 1000Hz) / 4000Hz | Frequency spread |
| Spectral Rolloff | 0.15 | (rolloff - 2000Hz) / 6000Hz | High frequency content |
| Zero Crossing Rate | 0.10 | zcr × 20 | Percussiveness |
| Spectral Flux | 0.15 | flux / 1000 | Dynamics |

**Formula**:
```
complexity = Σ(weight_i × clip(normalized_feature_i, 0, 1))
```

All features normalized to [0, 1] before weighting.

#### Local Tempo Extraction

Uses inter-beat intervals (IBI) to compute instantaneous BPM:

1. Calculate time between consecutive beats: `ibis = np.diff(beat_times)`
2. Convert to BPM: `local_bpms = 60.0 / ibis`
3. Filter unrealistic values (outside 20-300 BPM range)
4. Smooth with 5-beat moving average window
5. Interpolate to feature timestamps using linear interpolation

---

## 2. MOTION GENERATION

### 2.1 Overview

**Location**: `src/offline/trajectory_generator.py`

The trajectory generator converts audio features into pre-computed motor commands. Trajectories are stored as numpy arrays and played back during runtime.

### 2.2 Dual-Sinusoid Motion Model

The motion is generated using a **dual-sinusoid formula**:

```
position(t) = master_amplitude × [A₁·sin(ω₁·t) + A₂·sin(ω₂·t)]
velocity(t) = master_amplitude × [A₁·ω₁·cos(ω₁·t) + A₂·ω₂·cos(ω₂·t)]
```

Where:
- **ω₁ = 2π·frequency** (primary angular frequency)
- **ω₂ = π·frequency** (harmonic at half frequency)
- **frequency = BPM / 60** (Hz)
- **frequency_divisor** allows halving: `frequency = BPM / (60 × divisor)`

### 2.3 Amplitude Distribution Based on Complexity

The **amplitude distribution** between the two sinusoids is controlled by the music's **complexity** value:

```python
amplitude1 = max_amplitude × (1.0 - complexity × 0.5)  # Primary sinusoid
amplitude2 = max_amplitude × complexity                 # Harmonic sinusoid
```

**Interpretation**:
- **Low complexity (0.0)**: Only primary sinusoid active → simple, regular motion
- **High complexity (1.0)**: Equal mix of both sinusoids → more complex, layered motion

### 2.4 Pattern Types

| Pattern Type | Complexity Value | Result |
|--------------|------------------|--------|
| `'complex'` | From feature extraction | Both sinusoids active, complexity modulates distribution |
| `'simple'` | Forced to 0.0 | Only primary sinusoid active |
| `'none'` | N/A | No motion (motor stays still) |

### 2.5 Fixed Tempo Trajectory Generation

For constant BPM trajectories:

```python
base_frequency = bpm / 60.0
frequency = base_frequency / frequency_divisor

omega1 = 2π × frequency
omega2 = 2π × (frequency / 2)

for each timestamp t:
    rms = interpolate(t, feature_timestamps, rms_array)
    complexity = interpolate(t, feature_timestamps, complexity_array)

    master_amplitude = min(rms × 3.0, 1.0)  # Scale by RMS energy
    amplitude1, amplitude2 = calculate_amplitudes(complexity)

    position = initial_offset + (amplitude1×sin(omega1×t) + amplitude2×sin(omega2×t)) × master_amplitude
    velocity = (amplitude1×omega1×cos(omega1×t) + amplitude2×omega2×cos(omega2×t)) × master_amplitude
```

**Output**: Array of shape (N, 3) = [time, position, velocity]

### 2.6 Dynamic Tempo Trajectory Generation

For songs with varying tempo, uses **cumulative phase integration** to track tempo changes smoothly:

```
Phase(t) = ∫₀ᵗ ω(τ) dτ
position(t) = A₁·sin(φ₁(t)) + A₂·sin(φ₂(t))
velocity(t) = A₁·ω₁(t)·cos(φ₁(t)) + A₂·ω₂(t)·cos(φ₂(t))
```

**Integration method** (trapezoidal rule):
```python
omega1_array = 2π × effective_tempo / 60  # Time-varying angular frequency
omega2_array = omega1_array / 2

for i in range(1, num_samples):
    dt = timestamps[i] - timestamps[i-1]
    phase1[i] = phase1[i-1] + (omega1_array[i-1] + omega1_array[i]) / 2 × dt
    phase2[i] = phase2[i-1] + (omega2_array[i-1] + omega2_array[i]) / 2 × dt
```

**Key advantages**:
- Smooth phase tracking even with tempo changes
- No discontinuities or phase jumps
- Accurate velocity feedforward at variable tempos

### 2.7 Trajectory Configuration

```python
@dataclass
class TrajectoryConfig:
    max_amplitude: float = 7.5         # Maximum motor turns at shaft
    gear_ratio: float = 15.0           # Motor turns : output turns
    initial_offset: float = 0.0        # Center position
    resolution_ms: float = 10.0        # Time step (10ms = 100Hz sample rate)
    pattern_type: str = 'complex'      # 'simple' or 'complex'
    frequency_divisor: float = 1.0     # 2.0 = half frequency
```

### 2.8 Song Preparation Pipeline

**Location**: `src/offline/prepare_song.py`

Song preparation generates **4 trajectory variants** per song:

| Filename | Tempo Mode | Pattern |
|----------|------------|---------|
| `trajectory.npy` | Fixed | Complex |
| `trajectory_dynamic.npy` | Dynamic | Complex |
| `trajectory_simple.npy` | Fixed | Simple |
| `trajectory_simple_dynamic.npy` | Dynamic | Simple |

**BPM Scaling** (for manual BPM override):
```python
if bpm_override is not None:
    scale_factor = bpm_override / features.bpm
    features.local_tempo = features.local_tempo × scale_factor
```

This allows manual BPM adjustment while maintaining dynamic tempo proportions.

---

## 3. SYNCHRONIZATION MECHANISM

### 3.1 Master Clock: Audio Playback

**Location**: `src/core/audio_player.py`

**Synchronization principle**: Audio playback is the **master clock**. All motor motion is driven by the current audio playback time.

**Key Properties**:
- **Sample-accurate tracking**: Uses sample count from audio callback
- **Thread-safe access**: Locked access to `_sample_index`

```python
@property
def current_time_seconds(self) -> float:
    """Thread-safe access to current playback position"""
    with self._lock:
        return self._sample_index / self.sample_rate
```

### 3.2 Real-Time Control Loop

**Location**: `src/core/playback_controller.py`

**Architecture**: Separate thread running at 60Hz (default)

```python
def _control_loop(self):
    """Main control loop at 60Hz"""
    next_time = time.perf_counter()

    while self._running:
        # Get current audio time (master clock)
        current_time = self.audio_player.current_time_seconds

        # Get user amplitude (Bluetooth remote)
        user_amp = self._user_amplitude

        # Get latency offset
        latency_off = self.latency_offset

        # Lookup trajectory position and velocity
        target_pos, target_vel = self.trajectory_player.get_position_and_velocity(
            timestamp=current_time,
            user_amplitude=user_amp,
            initial_offset=self._initial_offset,
            latency_offset=latency_off
        )

        # Send to motor
        self.motor_driver.set_position_with_velocity(target_pos, target_vel)

        # Maintain 60Hz timing
        next_time += self.control_period
        sleep_time = next_time - time.perf_counter()
        if sleep_time > 0:
            time.sleep(sleep_time)
```

**Timing**:
- Loop Frequency: 60Hz
- Control Period: 16.67ms
- Target Duration per Loop: <1ms (CPU-light)

### 3.3 Latency Compensation

**Principle**: "Look ahead" in the trajectory to compensate for total system latency.

```python
t_effective = current_audio_time + latency_offset_s
position = trajectory_player.get_position(t_effective)
```

**Total Latency Sources**:

| Source | Typical Range |
|--------|---------------|
| Audio device output latency | 10-20ms |
| USB/communication latency | 5-10ms |
| Motor mechanical response | 10-20ms |
| **Total typical** | **~35ms** |

**Storage**: `config/latency.json`

### 3.4 Trajectory Lookup (Hot Path)

**Location**: `src/core/trajectory_player.py`

**Design**: O(1) lookup time using uniform time stepping

```python
def get_position(self, timestamp: float, latency_offset: float = 0.0) -> float:
    """O(1) trajectory lookup with linear interpolation"""

    t = timestamp + latency_offset

    # O(1) index calculation using known time_step
    index_float = t / self.time_step
    index = int(index_float)

    # Linear interpolation between adjacent samples
    alpha = (t - t0) / (t1 - t0)
    return p0 + alpha × (p1 - p0)
```

**Pre-computed Time Step**: `time_step = timestamps[1] - timestamps[0]`
- Avoids binary search O(log N) overhead
- Perfect for uniform trajectory sampling

---

## 4. MOTOR CONTROL

### 4.1 ODrive Hardware Interface

**Location**: `src/core/motor_driver.py`

```python
class MotorDriver:
    def set_position(self, position: float) -> None:
        """Set motor position (called at 60Hz)"""
        self.odrv0.axis0.controller.input_pos = position

    def set_position_with_velocity(self, position: float, velocity: float) -> None:
        """Set position with velocity feedforward"""
        self.odrv0.axis0.controller.input_vel = velocity  # First
        self.odrv0.axis0.controller.input_pos = position  # Then position
```

**Important**: Velocity must be set BEFORE position for proper feedforward.

### 4.2 Motor Configuration

| Parameter | Value | Description |
|-----------|-------|-------------|
| gear_ratio | 15.0 | Motor turns : output turns |
| max_amplitude | 7.5 | Maximum motor amplitude in turns |
| control_rate_hz | 60.0 | Control loop rate |

**Physical Motion**:
- Trajectories computed at motor shaft (input side)
- Max amplitude: 7.5 motor turns ≈ ±0.5 output turns (with 15:1 gear ratio)

### 4.3 Control Modes

**Position-Only Mode**:
```python
self.odrv0.axis0.controller.input_pos = target_pos
```

**Position + Velocity Feedforward Mode**:
```python
self.odrv0.axis0.controller.input_vel = target_vel  # Feedforward term
self.odrv0.axis0.controller.input_pos = target_pos  # Position reference
```

**Feedforward Benefits**:
- Reduces tracking error during direction changes
- Allows controller to anticipate motion
- Especially useful for complex dual-sinusoid patterns

### 4.4 Encoder Feedback

```python
def get_position(self) -> float:
    return self.odrv0.axis0.encoder.pos_estimate

def get_velocity(self) -> float:
    return self.odrv0.axis0.encoder.vel_estimate
```

**Used for**:
- Initial offset determination
- Position error tracking
- Feedback to data recorder for synchronization analysis

---

## 5. REMOTE CONTROL (BLUETOOTH)

### 5.1 Hardware

**Device**: Arduino Nano 33 BLE with rotary encoder

**BLE Configuration**:
```python
SERVICE_UUID = "19B10000-E8F2-537E-4F6C-D104768A1214"
CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"
DEVICE_NAMES = ["Nano_Encoder", "Arduino"]
```

**Location**: `src/bluetooth_controller.py`

### 5.2 Amplitude Control via Encoder

```python
def _notification_handler(self, sender, data: bytearray):
    message = data.decode('utf-8').strip()

    if message.startswith("Pos: "):
        encoder_value = int(message.split(": ")[1])

        # Calculate delta from baseline
        delta = encoder_value - self.initial_encoder_value

        # Apply direction reversal if enabled
        if self.encoder_direction_reversed:
            delta = -delta

        # Calculate new amplitude (each click = encoder_step_size)
        self.user_amplitude = clamp(0.3 + delta × encoder_step_size, 0.0, max_amplitude)
```

**Configuration**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| encoder_step_size | 0.005 | Amplitude change per encoder click |
| encoder_direction_reversed | True | Invert encoder direction |
| max_amplitude | 2.0 | Maximum amplitude limit |
| default_amplitude | 0.3 | Starting amplitude (30% of base trajectory) |

### 5.3 Button Toggle Behavior

```
Initial state:  user_amplitude = 0.3
Button press:   user_amplitude = 0.0 (pause motion)
Button press:   user_amplitude = 0.3 (resume motion)
```

The system saves amplitude before stopping and restores it on resume.

### 5.4 Message Types

| Message Format | Description |
|----------------|-------------|
| `"Pos: <value>"` | Encoder position update |
| `"SWITCH PRESSED"` | Button toggle |
| `"Battery: <voltage>V"` | Battery voltage |
| `"BATTERY LOW: <voltage>V"` | Low battery warning |

---

## 6. WEB INTERFACE & USER STUDY

### 6.1 Overview

**Location**: `src/web/app.py`

**Framework**: Flask + Flask-SocketIO for real-time updates

### 6.2 Key API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/songs` | GET | List available songs |
| `/api/play` | POST | Start playback |
| `/api/stop` | POST | Stop playback |
| `/api/amplitude` | POST | Set user amplitude |
| `/api/latency` | GET/POST | Get/set latency compensation |
| `/api/feedforward` | POST | Enable/disable velocity feedforward |
| `/api/user_study/*` | Various | User study management |

### 6.3 Song Variant Selection

Based on pattern type and tempo mode:

| Pattern | Tempo | Trajectory File |
|---------|-------|-----------------|
| complex | fixed | `trajectory.npy` |
| complex | dynamic | `trajectory_dynamic.npy` |
| simple | fixed | `trajectory_simple.npy` |
| simple | dynamic | `trajectory_simple_dynamic.npy` |

### 6.4 User Study Framework

**Structure**: 3 songs × 3 patterns = 9 trials

**Pattern Types**:
- `'complex'` - Dual-sinusoid motion modulated by complexity
- `'simple'` - Simple sinusoidal motion (complexity forced to 0)
- `'none'` - No motion (motor stays still)

**Trial Flow**:
1. Setup study with song configurations
2. For each trial: play song with assigned pattern
3. Record motor data throughout playback
4. Export synchronization analysis at trial end

### 6.5 Data Recording

**Location**: `src/data_recorder.py`

**Recorded at 60Hz**:

| Field | Description |
|-------|-------------|
| timestamp | Elapsed time from start (seconds) |
| user_amplitude | Remote control amplitude value |
| original_position | Trajectory output before amplitude scaling |
| final_position | Position sent to motor |
| actual_position | Encoder feedback |

**Export Formats**:
- **CSV**: Raw time-series data
- **PNG**: Visualization plots
- **Synchronization analysis**: Peak timing offset between music and motor

---

## 7. DATA FLOW DIAGRAMS

### 7.1 Offline Preparation Pipeline

```
Audio File (.mp3, .wav, etc.)
         │
         ▼
┌─────────────────────────────┐
│   ffmpeg conversion         │
│   → 44.1kHz stereo WAV      │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│   Feature Extractor         │
│   ├── BPM detection         │
│   ├── Beat timestamps       │
│   ├── RMS energy            │
│   ├── Spectral complexity   │
│   └── Local tempo           │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│   Trajectory Generator      │
│   × 4 variants:             │
│   ├── Fixed + Complex       │
│   ├── Dynamic + Complex     │
│   ├── Fixed + Simple        │
│   └── Dynamic + Simple      │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│   Song Directory            │
│   ├── audio.wav             │
│   ├── trajectory.npy        │
│   ├── trajectory_dynamic.npy│
│   ├── trajectory_simple.npy │
│   ├── trajectory_simple_... │
│   └── metadata.json         │
└─────────────────────────────┘
```

### 7.2 Runtime Playback Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    Control Loop (60Hz)                       │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Audio Player │───▶│ Trajectory   │───▶│ Motor Driver │  │
│  │(Master Clock)│    │ Player       │    │ (ODrive)     │  │
│  │              │    │ (O(1) lookup)│    │              │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                   ▲                    │          │
│         │                   │                    ▼          │
│         │            ┌──────────────┐    ┌──────────────┐  │
│         │            │ User         │    │ Encoder      │  │
│         │            │ Amplitude    │    │ Feedback     │  │
│         │            │ (Bluetooth)  │    │              │  │
│         │            └──────────────┘    └──────────────┘  │
│         │                                        │          │
│         ▼                                        ▼          │
│  ┌──────────────┐                        ┌──────────────┐  │
│  │ current_time │                        │ Data         │  │
│  │ (seconds)    │                        │ Recorder     │  │
│  └──────────────┘                        └──────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Synchronization Analysis

```
┌─────────────────────────────────────────────────────────────┐
│              Synchronization Analysis                        │
│                                                             │
│  Music Reference              Motor Feedback                │
│  ┌──────────────┐            ┌──────────────┐              │
│  │ BPM-derived  │            │ Encoder      │              │
│  │ sinusoid     │            │ position     │              │
│  └──────────────┘            └──────────────┘              │
│         │                           │                       │
│         ▼                           ▼                       │
│  ┌─────────────────────────────────────────┐               │
│  │           Peak Detection                 │               │
│  │    (scipy.signal.find_peaks)            │               │
│  └─────────────────────────────────────────┘               │
│         │                           │                       │
│         ▼                           ▼                       │
│  ┌──────────────┐            ┌──────────────┐              │
│  │ Music peak   │            │ Motor peak   │              │
│  │ timestamps   │            │ timestamps   │              │
│  └──────────────┘            └──────────────┘              │
│         │                           │                       │
│         └───────────┬───────────────┘                       │
│                     ▼                                       │
│         ┌──────────────────────┐                           │
│         │ For each music peak: │                           │
│         │ Find nearest motor   │                           │
│         │ peak, calculate      │                           │
│         │ timing offset (ms)   │                           │
│         └──────────────────────┘                           │
│                     │                                       │
│                     ▼                                       │
│         ┌──────────────────────┐                           │
│         │ Output:              │                           │
│         │ • Mean offset (ms)   │                           │
│         │ • Std deviation (ms) │                           │
│         │ • Per-peak offsets   │                           │
│         └──────────────────────┘                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. KEY ALGORITHMS

### 8.1 Dual-Sinusoid Position Formula

**Fixed tempo**:
```
position(t) = A₁·sin(2π·f·t) + A₂·sin(π·f·t)

where:
  f = BPM / 60                              (Hz)
  A₁ = max_amplitude × (1.0 - complexity × 0.5)
  A₂ = max_amplitude × complexity
```

**Dynamic tempo** (phase integration):
```
position(t) = A₁·sin(φ₁(t)) + A₂·sin(φ₂(t))

where:
  φ₁(t) = ∫₀ᵗ 2π·local_tempo(τ)/60 dτ
  φ₂(t) = ∫₀ᵗ π·local_tempo(τ)/60 dτ
```

### 8.2 Complexity Calculation

```
complexity = (
    0.10 × clip((centroid - 500) / 3500, 0, 1) +
    0.25 × clip(centroid_std / 500, 0, 1) +
    0.25 × clip((bandwidth - 1000) / 4000, 0, 1) +
    0.15 × clip((rolloff - 2000) / 6000, 0, 1) +
    0.10 × clip(zcr × 20, 0, 1) +
    0.15 × clip(flux / 1000, 0, 1)
)
```

### 8.3 Local Tempo Extraction

```python
ibis = diff(beat_times)                    # Inter-beat intervals
local_bpms = 60.0 / ibis                   # Convert to BPM
valid = filter(20 <= local_bpms <= 300)    # Remove outliers
smoothed = moving_average(valid, window=5) # 5-beat smoothing
local_tempo = interpolate(timestamps, valid_times, smoothed)
```

### 8.4 O(1) Trajectory Lookup

```python
# Given: trajectory array (N, 3) with uniform time_step
# Find position at arbitrary time t

index_float = t / time_step
index = int(index_float)
alpha = index_float - index

position = positions[index] + alpha × (positions[index+1] - positions[index])
velocity = velocities[index] + alpha × (velocities[index+1] - velocities[index])
```

### 8.5 Peak Timing Offset Calculation

```python
# For each music peak, find nearest motor peak
for music_peak_time in music_peak_times:
    time_diffs = motor_peak_times - music_peak_time
    nearest_idx = argmin(abs(time_diffs))
    offset_ms = time_diffs[nearest_idx] × 1000

    # Positive offset = motor is late
    # Negative offset = motor is early
```

---

## 9. PERFORMANCE CHARACTERISTICS

### 9.1 Trajectory Lookup Performance

| Operation | Time |
|-----------|------|
| Single position lookup | ~2-3 μs |
| Position + velocity lookup | ~3-4 μs |
| Loop time budget (60Hz) | 16.67 ms |
| Available margin | >99% |

### 9.2 Memory Usage

| Data Type | Size |
|-----------|------|
| Audio (per minute) | ~10 MB (44.1kHz × 16-bit stereo) |
| Trajectory (per second) | ~2.4 KB (100 samples × 3 columns × 8 bytes) |
| 3-minute song trajectory | ~7.2 KB |
| Feature data (per song) | ~50 KB |

### 9.3 Control Loop Timing

| Component | Duration |
|-----------|----------|
| Control period | 16.67 ms |
| Trajectory lookup | ~3 μs |
| Motor command | ~1 ms |
| Available margin | >15 ms |

---

## 10. SYSTEM CONSTRAINTS & LIMITS

### 10.1 Audio Constraints

| Constraint | Value |
|------------|-------|
| Sample rate | Fixed at 44.1 kHz |
| Channels | Stereo (converted to mono for analysis) |
| Format | WAV after conversion |
| Max duration | No hard limit (tested up to 10+ minutes) |

### 10.2 Motor Constraints

| Constraint | Value |
|------------|-------|
| Max amplitude | 7.5 motor turns |
| Control rate | 60 Hz nominal (configurable 30-100 Hz) |
| Position range | -7.5 to +7.5 turns |
| Position accuracy | ±0.01 turns (encoder dependent) |

### 10.3 Trajectory Constraints

| Constraint | Value |
|------------|-------|
| Time resolution | 10 ms minimum |
| Max samples | ~100,000 (10,000 seconds at 10 ms) |
| Position range | [-7.5, +7.5] turns |
| Velocity range | [-100, +100] turns/sec |

### 10.4 Latency Constraints

| Constraint | Value |
|------------|-------|
| Compensation range | 0-200 ms |
| Typical compensation | 20-50 ms |
| Accuracy | ±1 ms |

---

## 11. CONFIGURATION PARAMETERS

### 11.1 Core System Configuration

```python
MOTOR_CONFIG = MotorConfig(
    gear_ratio = 15.0           # Motor:output ratio
    max_amplitude = 7.5         # Motor turns
    control_rate_hz = 60.0      # Control frequency
)

AUDIO_CONFIG = AudioConfig(
    sample_rate = 44100         # Hz
    blocksize = 1024            # Audio buffer
)

TRAJECTORY_CONFIG = TrajectoryConfig(
    resolution_ms = 10.0        # 100 Hz sample rate
)
```

### 11.2 Song Preparation Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| max_amplitude | 7.5 | Motor turns |
| gear_ratio | 15.0 | Motor:output ratio |
| resolution_ms | 10.0 | Trajectory time step |
| half_freq_simple | False | Halve frequency for simple pattern |
| half_freq_complex | False | Halve frequency for complex pattern |

### 11.3 Bluetooth Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| encoder_step_size | 0.005 | Amplitude change per click |
| encoder_direction_reversed | True | Invert encoder direction |
| max_amplitude | 2.0 | Maximum remote amplitude |

### 11.4 Latency Configuration

```json
{
    "latency_offset_ms": 35.0,
    "pattern_latencies": {
        "simple": 35.0,
        "complex": 40.0,
        "none": 0.0
    }
}
```

---

## 12. DEPENDENCIES

### 12.1 Python Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| librosa | 0.10+ | Audio analysis, beat tracking |
| numpy | - | Numerical computing |
| scipy | - | Signal processing (find_peaks) |
| sounddevice | - | Audio playback (sample-accurate) |
| flask | - | Web framework |
| flask-socketio | - | Real-time WebSocket |
| bleak | - | Bluetooth Low Energy |
| odrive | - | ODrive motor API |
| matplotlib | - | Plotting (Agg backend) |

### 12.2 External Tools

| Tool | Purpose |
|------|---------|
| ffmpeg | Audio format conversion |

---

## 13. REFERENCE ARCHITECTURE DIAGRAM

```
┌─────────────────────────────────────────────────────────────────┐
│                    MUSIC_FEATURE_MODEL SYSTEM                    │
└─────────────────────────────────────────────────────────────────┘

                         OFFLINE PHASE
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Audio File   │───▶│ Feature      │───▶│ Trajectory   │
│ (.mp3, .wav) │    │ Extractor    │    │ Generator    │
└──────────────┘    └──────────────┘    └──────────────┘
                                               │
                    ┌──────────────────────────┘
                    ▼
            ┌──────────────┐
            │ Song Library │
            │ (4 variants  │
            │  per song)   │
            └──────────────┘
                    │
════════════════════╪═════════════════════════════════════════════
                    │
                    ▼            RUNTIME PHASE
┌─────────────────────────────────────────────────────────────────┐
│                   Playback Controller (60 Hz)                    │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Audio Player │─▶│ Trajectory   │─▶│ Motor Driver │          │
│  │(Master Clock)│  │ Player       │  │ (ODrive)     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                           ▲                                      │
│                           │                                      │
│                    ┌──────────────┐                             │
│                    │ Latency      │                             │
│                    │ Compensation │                             │
│                    └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
         │                                            │
         ▼                                            ▼
┌──────────────────┐                      ┌──────────────────┐
│ Web UI           │                      │ Bluetooth Remote │
│ (Flask/SocketIO) │                      │ (Arduino Nano)   │
├──────────────────┤                      ├──────────────────┤
│ • Song selection │                      │ • Amplitude ctrl │
│ • Playback ctrl  │                      │ • On/off toggle  │
│ • User study     │                      │ • Battery status │
│ • Data recording │                      │                  │
└──────────────────┘                      └──────────────────┘
```

---

## 14. SUMMARY

The MUSIC_FEATURE_MODEL is a real-time music-synchronized motor control system with:

| Aspect | Implementation |
|--------|----------------|
| **Offline intelligence** | Comprehensive feature extraction and trajectory pre-computation |
| **Real-time efficiency** | O(1) trajectory lookup, <1ms control loop overhead |
| **Musical modeling** | Dual-sinusoid patterns with complexity-based amplitude distribution |
| **Flexible control** | Multiple motion patterns, dynamic tempo support |
| **User interaction** | Bluetooth remote, web interface, user study framework |
| **Data capture** | Detailed recording and synchronization analysis |

The architecture cleanly separates offline preparation (complex computations) from runtime (minimal overhead), achieving both sophistication and real-time performance.
