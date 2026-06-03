# Music-Synchronized Motor Control

A Python system that drives a motorized floor platform in synchronization with music. Audio features (tempo, loudness, spectral complexity) are extracted offline and converted into pre-computed motor trajectories. At runtime, the audio file plays through a soundcard while the motor follows the matching trajectory, with the soundcard's sample clock used as the master time reference.

For a full technical description of the design, see [`README_SYSTEM_DESCRIPTION.md`](../README_SYSTEM_DESCRIPTION.md). For diagrams, see [`README_DIAGRAMS.md`](../README_DIAGRAMS.md).

---

## What the system does

The system separates work into two phases:

1. **Offline preparation** — given an audio file, extract features (BPM, RMS, complexity, local tempo) and bake four motor trajectory variants (simple/complex × fixed/dynamic tempo) into `.npy` files alongside a normalized `audio.wav`.

2. **Runtime playback** — load a prepared song, start audio playback through `sounddevice`, and run a 60 Hz control loop that queries the trajectory at the current audio sample position, applies the user-controlled amplitude and latency look-ahead, and sends position + velocity commands to an ODrive motor controller.

Motor commands follow a dual-sinusoid model:

```
x(t) = p₀ + A_user · A_master(t) · [ A₁ · sin(2π f τ) + A₂ · sin(π f τ) ],   τ = t + Δt

where  A₁ = A_max (1 − 0.5 c),   A₂ = A_max c,   c ∈ [0, 1]
```

with `A_master(t)` driven by RMS loudness, `c` driven by spectral complexity, `f = BPM / 60`, `A_user` set by the live amplitude slider, and `Δt` the calibrated latency look-ahead.

---

## Project layout

```
MUSIC_FEATURE_MODEL/
├── src/
│   ├── main.py                    # CLI entry point (terminal playback)
│   ├── config.py                  # Centralized system parameters
│   ├── data_recorder.py           # Runtime data capture
│   ├── bluetooth_controller.py    # BLE remote (Arduino Nano 33 BLE)
│   ├── odrive_controller.py       # ODrive setup & calibration
│   ├── user_study.py              # Within-subjects study workflow
│   ├── core/                      # Runtime playback pipeline
│   │   ├── audio_player.py        #   Soundcard-driven master clock
│   │   ├── trajectory_player.py   #   O(1) trajectory lookup
│   │   ├── motor_driver.py        #   ODrive command interface
│   │   └── playback_controller.py #   60 Hz control loop
│   ├── offline/                   # Offline preparation pipeline
│   │   ├── prepare_song.py        #   End-to-end song preparation
│   │   ├── feature_extractor.py   #   BPM, RMS, complexity, local tempo
│   │   ├── trajectory_generator.py#   Dual-sinusoid trajectory baking
│   │   ├── song_manager.py        #   Song library / index management
│   │   └── regenerate_trajectory.py # Rebake with new BPM/options
│   ├── calibration/               # Latency calibration utilities
│   ├── web/                       # Flask + SocketIO control panel
│   └── songs/ (or ../songs/)      # Prepared song library
├── tools/
│   ├── sync_analysis.py           # Post-hoc beat / tracking analysis
│   └── ...                        # Misc analysis & plotting tools
├── setup/
│   └── requirements.txt           # Python dependencies
├── config/                        # Runtime config (latency.json, etc.)
├── docs/, images/                 # Supplementary documentation
├── README_SYSTEM_DESCRIPTION.md   # Full technical description
└── README_DIAGRAMS.md             # Diagram reference
```

---

## Installation

### System dependencies

- **Python 3.10+** (recommended)
- **ffmpeg** — required by `prepare_song.py` to normalize audio to 44.1 kHz WAV
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
- **PortAudio** (usually pulled in by `sounddevice`; on Linux: `sudo apt install libportaudio2`)
- **ODrive firmware** on the motor controller, accessible over USB

### Python environment

```bash
# Optional: create a clean environment
conda create -n music-motor python=3.10
conda activate music-motor

# Install Python packages
pip install -r setup/requirements.txt
```

### Bluetooth remote (optional)

The Arduino code lives in `src/arduino_code_power_optimized/`. To enable BLE on Linux:

```bash
bash setup/install_bluetooth.sh
```

---

## Quick start

### 1. Prepare a song

Add an MP3 (or WAV/FLAC/etc.) to the system. This converts the audio to 44.1 kHz WAV, extracts features, and bakes four trajectory variants.

```bash
# Interactive mode
python src/offline/prepare_song.py

# Direct mode
python src/offline/prepare_song.py path/to/song.mp3 --name "Song Title" --artist "Artist"

# With manual BPM override (when librosa misdetects)
python src/offline/prepare_song.py song.mp3 --name "Title" --artist "Artist" --bpm 128
```

Prepared songs are stored under `src/songs/<song_id>/` and indexed in `songs/index.json`.

### 2. Calibrate latency (once per setup)

```bash
python src/main.py --calibrate
```

This measures motor response time, queries the audio device latency, and offers interactive fine-tuning. The result is saved to `config/latency.json`.

### 3. Play a song

**Terminal mode** (`src/main.py`):

```bash
# List available songs
python src/main.py --list

# Play by name or ID
python src/main.py --song "Song Title"
python src/main.py -s 001

# Override latency (in milliseconds)
python src/main.py -s 001 --latency 35

# Interactive song selection (no arguments)
python src/main.py
```

**Web interface** (`src/web/app.py`) — recommended for live control:

```bash
python src/web/app.py
```

Open `http://localhost:5000` in a browser. The page provides song selection, play/pause/stop, real-time amplitude and latency sliders, Bluetooth remote pairing, live status display, data recording, and the user-study workflow.

---

## Working with prepared songs

### Regenerate a trajectory with new settings

If you change the gear ratio, motor RPM limit, or want to re-bake with a different BPM without redoing feature extraction:

```bash
python src/offline/regenerate_trajectory.py <song_id> [--bpm 120] [--amplitude 7.5]
```

### Analyze recorded data

After a user-study session, run the analysis tool to produce per-participant and aggregated plots/tables comparing motor tracking and beat alignment across patterns:

```bash
python tools/sync_analysis.py --all
```

See [`tools/README_sync_analysis.md`](../tools/README_sync_analysis.md) for the full set of flags.

---

## Hardware

The runtime expects:

- **ODrive v3.6** motor controller (USB connection)
- **Turnigy SK8-6374 BLDC motor** (192 KV) with **CUI AMT102-V** encoder (8192 CPR), 15:1 reduction
- **24–32 V DC** supply with brake-resistor (2 Ω)
- Optional: **Arduino Nano 33 BLE** with rotary encoder + button for the wireless amplitude remote
- **Audio output device** (line-out, USB DAC, or Bluetooth speaker — Bluetooth adds ~100–250 ms latency, compensated by the latency slider)

Motor parameters are defined in `src/config.py` and `src/odrive_controller.py`.

---

## Configuration

System-wide defaults are in `src/config.py`:

- Control loop rate: **60 Hz**
- Trajectory resolution: **10 ms** (100 Hz)
- Audio sample rate: **44 100 Hz**
- Audio buffer: **1024 samples**
- Motor max amplitude: **7.5 turns**
- Motor RPM limit (safety): **5 500 RPM**
- Gear ratio: **15:1**

Per-song latency offsets (and pattern-specific overrides for the user study) are persisted to each song's `metadata.json`. The global default is stored in `config/latency.json`.

---

## Master clock — why soundcard-driven

`src/core/audio_player.py` opens a `sounddevice.OutputStream` whose callback is invoked by a high-priority OS thread driven by the soundcard hardware clock. Each callback advances an integer `sample_index`. The control loop reads

```
t_audio = sample_index / sample_rate
```

once per iteration and queries the trajectory at `t_audio + Δt`. Because the trajectory time axis and the audio sample axis share one clock, there is no drift between music and motion — regardless of OS scheduling jitter, audio underruns, or wall-clock drift.

---

## See also

- [`README_SYSTEM_DESCRIPTION.md`](../README_SYSTEM_DESCRIPTION.md) — complete module-by-module technical description
- [`README_DIAGRAMS.md`](../README_DIAGRAMS.md) — architecture, data-flow, and sequence diagrams
- [`tools/README_sync_analysis.md`](../tools/README_sync_analysis.md) — analysis tooling reference
