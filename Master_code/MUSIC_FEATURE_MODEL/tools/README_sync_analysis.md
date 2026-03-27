# Synchronization Analysis — Technical Documentation

This document describes the full data pipeline from music feature extraction through motor control, data recording, peak-based synchronization measurement, and the statistical analysis performed by `sync_analysis.py`.

---

## 1. Offline Music Feature Extraction

Before any user study, each song is pre-processed by `feature_extractor.py` using librosa:

| Feature | Method | Range | Purpose |
|---------|--------|-------|---------|
| **BPM** | `librosa.beat.beat_track()` | Global scalar | Drives the oscillation frequency |
| **Beat times** | Inter-beat intervals | Seconds | Anchors timing |
| **RMS energy** | `librosa.feature.rms()`, normalized by 3.0, capped at 1.0 | 0–1 | Controls the master amplitude envelope |
| **Spectral complexity** | Weighted blend of 6 spectral features | 0–1 | Controls the balance between simple and complex motion |

### Complexity blend weights

| Feature | Weight |
|---------|--------|
| Spectral centroid | 10% |
| Centroid variance | 25% |
| Spectral bandwidth | 25% |
| Spectral rolloff | 15% |
| Zero crossing rate | 10% |
| Spectral flux | 15% |

---

## 2. Trajectory Generation (Dual Sinusoid)

The motor trajectory is a **sum of two sinusoids** whose amplitudes depend on the music features:

```
position(t) = initial_offset + master_amplitude × [A₁·sin(ω₁·t) + A₂·sin(ω₂·t)]
```

| Symbol | Definition |
|--------|------------|
| `master_amplitude` | `min(RMS(t) × 3.0, 1.0)` — envelope from loudness |
| `ω₁` | `2π × BPM / 60` — primary beat frequency |
| `ω₂` | `π × BPM / 60` — half-frequency harmonic |
| `A₁` | `max_amplitude × (1 − complexity(t) × 0.5)` — primary sinusoid amplitude |
| `A₂` | `max_amplitude × complexity(t)` — harmonic amplitude |
| `max_amplitude` | 7.5 motor turns (configurable) |
| `initial_offset` | Motor position at recording start (oscillation center) |

### Simple vs Complex conditions

| Aspect | Simple | Complex |
|--------|--------|---------|
| Active sinusoids | 1 (A₁ only) | 2 (A₁ + A₂) |
| A₁ | 7.5 turns | 7.5 × (1 − 0.5 × complexity) |
| A₂ | 0 | 7.5 × complexity |
| Complexity input | Forced to 0 | Tracks spectral features (0–1) |
| Motion character | Smooth, predictable single sine wave | Richer, musically expressive dual sine |

The trajectory is pre-computed at **10 ms resolution** and stored as `.npy` files (columns: timestamp, position, velocity).

### Velocity feedforward

An analytical derivative is computed alongside position:

```
velocity(t) = master_amplitude × [A₁·ω₁·cos(ω₁·t) + A₂·ω₂·cos(ω₂·t)]
```

This is sent to the motor controller to improve tracking accuracy.

### Amplitude attenuation

If the computed peak velocity exceeds the motor's RPM limit (5500 RPM default), both A₁ and A₂ are scaled down proportionally. This prevents overcurrent at high BPM.

---

## 3. Runtime: 60 Hz Control Loop

During playback, `playback_controller.py` runs a loop at **60 Hz** (every 16.67 ms):

1. Read current **audio timestamp** (master clock from sounddevice).
2. Read **user amplitude** from the Bluetooth remote (0.0–0.6, thread-safe).
3. Apply **latency compensation**: `lookup_time = audio_time + latency_offset` (~35 ms typical).
4. Look up trajectory position and velocity at `lookup_time`, scaled by `user_amplitude`.
5. Send position + velocity feedforward to the **ODrive motor controller**.
6. Record a data sample (see below).

### What "position" means

Position is measured in **motor shaft turns** (not degrees or radians). With a gear ratio of 15:1, the output shaft moves 1/15th of the motor turns. The motor oscillates around `initial_offset`, which is the shaft position at the moment recording begins.

### How user amplitude is applied

```
final_position = initial_offset + (trajectory_position × user_amplitude)
```

The user amplitude (0.0–0.6) linearly scales the oscillation magnitude. At 0.0 the motor holds still; at 0.6 the motion is at maximum.

---

## 4. Bluetooth Remote Control

The Arduino Nano 33 BLE transmits rotary encoder position via BLE at **20 Hz** (every 50 ms). The PC side converts encoder clicks to an amplitude value:

```
amplitude = 0.3 + (encoder_delta × 0.005)     clamped to [0.0, 0.6]
```

The button toggles between the current amplitude and 0.0 (pause/resume). Because BLE updates at 20 Hz but the control loop runs at 60 Hz, the same amplitude value is used for ~3 consecutive control iterations.

---

## 5. Data Recording

`data_recorder.py` records one sample per control loop iteration (60 Hz). Each sample contains:

| Column | Description |
|--------|-------------|
| `Time (s)` | Elapsed time since recording start |
| `User Amplitude` | Current remote control value (0.0–0.6) |
| `Original Position` | Trajectory position before user amplitude scaling |
| `Final Position` | Position sent to motor: `initial_offset + original × user_amplitude` |
| `Actual Position` | Encoder feedback from ODrive (what the motor actually did) |

---

## 6. Synchronization Analysis (Peak Matching)

At the end of each trial, `data_recorder.plot_synchronization()` generates the synchronization CSV that `sync_analysis.py` consumes. This is where the **timing offset** between music and motor is computed.

### Step 1 — Reconstruct the music reference signal

A pure sinusoid is generated from the extracted BPM:

```
music_signal(t) = amplitude × sin(2π × BPM/60 × t)
```

This represents where the motor *should* peak if perfectly synchronised to the beat.

### Step 2 — Detect peaks

Using `scipy.signal.find_peaks()` with `height = 0.5 × signal_amplitude`:

- **Music peaks**: local maxima of the reference sinusoid → expected peak times.
- **Motor peaks**: local maxima of `actual_position − initial_offset` → observed peak times.

### Step 3 — Compute timing offsets

For each music peak at time `t_music`:

```
t_motor = time of nearest motor peak (by argmin of |t_motor − t_music|)
offset_ms = (t_motor − t_music) × 1000
```

- **Positive offset** → motor peaked *after* the music (late).
- **Negative offset** → motor peaked *before* the music (early).

### The half-period artifact

Because the motor oscillates continuously, the "nearest" motor peak can be off by N half-periods. For example, at 178 BPM the half-period is ~168 ms. A motor peak that is only 3 ms late might be matched to a music peak one full cycle away, producing an offset of ~168 ms or ~336 ms. The true timing error (3 ms) is masked.

### Synchronization CSV format

```
# Music-Motor Synchronization Data
# Song: song_name
# Pattern: simple/complex
# BPM: 178.2
# Phase Lag: 45.23 ms
# Correlation: 0.8642
# Mean Peak Offset: 35.12 ms
# Peak Offset Std: 18.45 ms
# Number of Peaks: 42

Peak Time (s),Timing Offset (ms)
0.500,35.2
1.000,32.1
...

Time (s),Music Sinusoid,Actual Position (centered)
0.0,0.0,0.0
...
```

`sync_analysis.py` reads only the **peak rows** (2-column numeric lines before the time-series section) and the `# BPM:` header.

---

## 7. sync_analysis.py — Corrections and Statistics

### 7.1 Half-period correction (`correct_offsets`)

Wraps every offset to the range `[−hp/2, +hp/2]` where `hp = 60000 / BPM / 2`:

```
corrected = ((offset + hp/2)  mod  hp) − hp/2
```

**Why this works:** Adding `hp/2` shifts the range so that 0 maps to `hp/2`. The modulo operation removes all complete half-period multiples. Subtracting `hp/2` re-centers around zero. The result is the smallest timing error within one half-cycle.

| BPM | Half-period (ms) | Correction range |
|-----|-------------------|------------------|
| 120 | 250.0 | ±125.0 ms |
| 150 | 200.0 | ±100.0 ms |
| 178 | 168.5 | ±84.3 ms |

**Effect:** Mean offsets typically drop from ~170 ms to ~2–5 ms after correction.

### 7.2 Absolute offsets

After correction, all offsets are converted to absolute values. The sign (early/late) is discarded because the analysis focuses on *accuracy* (how close to zero), not *direction*.

### 7.3 Outlier filtering (`filter_outliers`)

```
threshold = mean(|offsets|) + N × std(|offsets|)
```

Default `N = 2.0`. Any absolute offset exceeding this threshold is removed. This discards anomalous peaks from dropped frames, false detections, or extreme desynchronization. The threshold is computed independently per condition.

### 7.4 Descriptive statistics

All computed on the **filtered absolute offsets**:

| Statistic | Formula | Interpretation |
|-----------|---------|----------------|
| Mean | `Σ|x| / n` | Average timing error — primary quality metric |
| Median | 50th percentile | Typical peak error, robust to remaining outliers |
| Std | `√(Σ(|x|−mean)² / n)` | Consistency of timing — lower = more stable |
| Min / Max | Extremes of filtered set | Best / worst individual peak alignment |

### 7.5 Comparison metrics

**Absolute difference:**
```
diff = |mean₁ − mean₂|
```

**Percentage difference (relative to better condition):**
```
pct = diff / min(mean₁, mean₂) × 100
```

This expresses how much worse the inferior condition is, relative to the better one. For example, if Simple = 2.08 ms and Complex = 2.44 ms:
- diff = 0.36 ms
- pct = 0.36 / 2.08 × 100 = 17.3%
- Interpretation: Complex is 17.3% worse than Simple.

### 7.6 Accuracy thresholds

For each threshold `T ∈ {1, 2, 5, 10}` ms:

```
percentage = (count of |offset| ≤ T) / (total filtered peaks) × 100
```

These answer: "What fraction of peaks were synchronised within T milliseconds?"

| Threshold | Interpretation |
|-----------|----------------|
| ≤ 1 ms | Near-perfect synchronization |
| ≤ 2 ms | Within one frame at 500 fps |
| ≤ 5 ms | Perceptually synchronous for most listeners |
| ≤ 10 ms | Acceptable; barely noticeable timing lag |

---

## 8. Plot Types

### Histogram (side-by-side)
- **Data:** Filtered absolute offsets per condition.
- **Shows:** Distribution shape, skewness, central tendency.
- **Annotations:** Dashed lines at mean (black) and median (gray).

### Time series (scatter)
- **Data:** Signed corrected offsets vs. peak time (unfiltered).
- **Shows:** Temporal trends — does sync improve, degrade, or drift over time?
- **Y-axis:** Capped at 95th percentile × 1.3 to prevent extreme outliers from compressing the scale.

### ECDF (empirical cumulative distribution)
- **Data:** Filtered absolute offsets.
- **Shows:** For any threshold on the x-axis, read the y-axis to see what fraction of peaks fall within that threshold.
- **Reference line:** 5 ms vertical marker.

### Box plot with jittered strip
- **Data:** Filtered absolute offsets.
- **Shows:** Median, interquartile range, whiskers; overlaid individual data points reveal density.
- **Y-axis:** Capped at 95th percentile.

### Rolling mean
- **Data:** Absolute offsets (unfiltered), smoothed with a 20-peak rolling window.
- **Shows:** Long-term synchronization trends, learning/fatigue effects.
- **Y-axis:** Capped at 95th percentile.

---

## 9. Y-axis Capping (`_ylim_from_percentile`)

```python
combined = concatenate(|array₁|, |array₂|)
ylim = percentile(combined, 95) × 1.3
```

Used in time series, box plot, and rolling mean. Prevents a few extreme values from compressing the visual range of the bulk data.

---

## 10. Output Structure

```
user_study_data/
  Participant_X/
    plots_during_user_study/          ← raw sync CSVs from data_recorder
      Song_Name_simple_synchronization.csv
      Song_Name_complex_synchronization.csv
    plots_post_user_study/
      Song_Name/                      ← output from sync_analysis.py
        sync_analysis_histogram.png
        sync_analysis_timeseries.png
        sync_analysis_ecdf.png
        sync_analysis_boxplot.png
        sync_analysis_rolling.png
        sync_analysis_report.md
        sync_analysis_report.tex
```

---

## 11. Complete Data Flow

```
Audio file (.wav/.mp3)
        │
        ▼
[OFFLINE] Feature Extraction (librosa)
        ├── BPM, beat times
        ├── RMS energy curve (0–1)
        └── Spectral complexity curve (0–1)
        │
        ▼
[OFFLINE] Trajectory Generation
        ├── position(t) = offset + master_amp × [A₁·sin(ω₁t) + A₂·sin(ω₂t)]
        ├── velocity(t) = analytical derivative (feedforward)
        └── Amplitude attenuation if velocity exceeds motor limit
        │
        ▼
trajectory.npy / trajectory_simple.npy  (10 ms resolution)
        │
        ▼
[RUNTIME] 60 Hz Control Loop
        ├── Audio time (master clock)
        ├── User amplitude from BLE remote (20 Hz, 0.0–0.6)
        ├── Latency compensation (~35 ms lookahead)
        ├── Trajectory lookup → position + velocity
        ├── ODrive motor command (position + velocity feedforward)
        └── Record sample: [time, user_amp, orig_pos, final_pos, actual_pos]
        │
        ▼
[POST-TRIAL] data_recorder.plot_synchronization()
        ├── Reconstruct music sinusoid: sin(2π × BPM/60 × t)
        ├── Detect music peaks (scipy find_peaks, height > 0.5 × amplitude)
        ├── Detect motor peaks (find_peaks on actual_position − offset)
        ├── For each music peak → nearest motor peak → offset (ms)
        └── Export: synchronization CSV with peak times + offsets
        │
        ▼
[ANALYSIS] sync_analysis.py
        ├── Parse CSV → (peak_time_s, timing_offset_ms) + BPM
        ├── Half-period correction: ((x + hp/2) mod hp) − hp/2
        ├── Absolute values → outlier filter (mean + 2σ)
        ├── Descriptive statistics (mean, median, std, min, max)
        ├── Accuracy thresholds (≤ 1, 2, 5, 10 ms)
        ├── Comparison: diff, %-diff relative to better condition
        ├── 5 plot types (histogram, timeseries, ECDF, boxplot, rolling)
        └── Reports (.md + .tex)
```
