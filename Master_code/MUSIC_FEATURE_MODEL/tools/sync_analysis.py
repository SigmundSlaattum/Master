6#!/usr/bin/env python3
"""
Analyze and compare music-motor synchronization data.

Uses pre-computed trajectory files from songs/ as the music reference
(capturing tempo changes, RMS modulation, complexity) instead of a
simple BPM-derived sinusoid.  Actual motor position is read from the
synchronization CSV exported by data_recorder.

Usage:
    python sync_analysis.py
"""

import argparse
import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

# ── Base directories (hardcoded) ──────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DATA_DIR = os.path.join(SCRIPT_DIR, "..", "src", "user_study_data")
SONGS_DIR = os.path.join(SCRIPT_DIR, "..", "songs")

# ── Consistent colors for both conditions ─────────────────────────────────
COLOR1 = "#1f77b4"  # blue
COLOR2 = "#e05252"  # red

# ── Display names for songs (used in plot titles) ─────────────────────────
SONG_DISPLAY_NAMES = {
    "so easy": "EDM",
    "lacrimosa": "Classical",
    "is there anybody out there": "Metal",
}


def _display_song(song: str) -> str:
    """Map a song name to its display name for plot titles."""
    return SONG_DISPLAY_NAMES.get(song.lower().strip(), song)


# ── Song index lookup ─────────────────────────────────────────────────────
def _load_song_index() -> list[dict]:
    """Load songs/index.json and return the list of song entries."""
    idx_path = os.path.join(SONGS_DIR, "index.json")
    with open(idx_path, "r") as f:
        return json.load(f)["songs"]


def _find_song_entry(song_name: str) -> dict | None:
    """Find a song entry in index.json by fuzzy-matching the song name."""
    entries = _load_song_index()
    name_lower = song_name.lower().strip()
    for entry in entries:
        if entry["name"].lower() == name_lower:
            return entry
    # Fallback: substring match
    for entry in entries:
        if entry["name"].lower() in name_lower or name_lower in entry["name"].lower():
            return entry
    return None


def _load_trajectory(song_entry: dict, condition: str) -> np.ndarray:
    """Load the trajectory .npy for a song + condition.

    Returns array of shape (N, 3): [time_s, position, velocity].
    Uses the dynamic-tempo variant to capture local tempo changes.
    """
    song_dir = os.path.join(SONGS_DIR, song_entry["path"])
    cond = condition.lower()
    if cond == "simple":
        filename = "trajectory_simple_dynamic.npy"
        fallback = "trajectory_simple.npy"
    else:  # complex (or none, etc.)
        filename = "trajectory_dynamic.npy"
        fallback = "trajectory.npy"

    path = os.path.join(song_dir, filename)
    if not os.path.isfile(path):
        path = os.path.join(song_dir, fallback)
    if not os.path.isfile(path):
        print(f"Error: trajectory not found: {path}")
        sys.exit(1)

    traj = np.load(path)
    print(f"  Loaded trajectory: {os.path.basename(path)} "
          f"({traj.shape[0]} samples, {traj[-1,0]:.1f}s)")
    return traj


# ── CSV parsing (full time series) ───────────────────────────────────────
def parse_sync_csv_timeseries(filepath: str) -> tuple[np.ndarray, np.ndarray, float]:
    """Parse a synchronization CSV and extract the full time-series section.

    Returns (times, actual_position_centered, bpm).
    """
    bpm = None
    times = []
    actual_pos = []
    in_timeseries = False

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# BPM:"):
                bpm = float(line.split(":")[1].strip())
                continue
            if line.startswith("Time (s),Music Sinusoid,Actual Position"):
                in_timeseries = True
                continue
            if not in_timeseries:
                continue
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) != 3:
                continue
            try:
                times.append(float(parts[0]))
                actual_pos.append(float(parts[2]))  # Actual Position (centered)
            except ValueError:
                continue

    return np.array(times), np.array(actual_pos), bpm


# ── Peak-based synchronization using trajectory reference ─────────────────
def compute_peak_offsets(traj: np.ndarray,
                         times: np.ndarray,
                         actual_pos: np.ndarray) -> pd.DataFrame:
    """Detect peaks in trajectory and actual motor data, compute timing offsets.

    Args:
        traj: Trajectory array (N, 3) — [time, position, velocity]
        times: Recorded timestamps from CSV
        actual_pos: Actual motor position (centered) from CSV

    Returns:
        DataFrame with columns [peak_time_s, timing_offset_ms]
    """
    # Interpolate trajectory position at the recorded timestamps
    traj_at_times = np.interp(times, traj[:, 0], traj[:, 1])

    # Detect peaks in the trajectory reference
    traj_amplitude = (traj_at_times.max() - traj_at_times.min()) / 2
    if traj_amplitude < 0.01:
        traj_amplitude = 1.0
    traj_peaks, _ = find_peaks(traj_at_times, height=0.3 * traj_amplitude)

    # Detect peaks in the actual motor position
    motor_amplitude = (actual_pos.max() - actual_pos.min()) / 2
    if motor_amplitude < 0.01:
        motor_amplitude = 1.0
    motor_peaks, _ = find_peaks(actual_pos, height=0.3 * motor_amplitude)

    if len(motor_peaks) == 0:
        print("  Warning: no motor peaks detected.")
        return pd.DataFrame(columns=["peak_time_s", "timing_offset_ms"])

    # For each trajectory peak, find nearest motor peak → timing offset
    motor_peak_times = times[motor_peaks]
    rows = []
    for traj_idx in traj_peaks:
        traj_peak_time = times[traj_idx]
        time_diffs = motor_peak_times - traj_peak_time
        nearest = np.argmin(np.abs(time_diffs))
        offset_ms = time_diffs[nearest] * 1000  # positive = motor late
        rows.append((traj_peak_time, offset_ms))

    print(f"  Trajectory peaks: {len(traj_peaks)}, "
          f"Motor peaks: {len(motor_peaks)}, "
          f"Offsets computed: {len(rows)}")

    return pd.DataFrame(rows, columns=["peak_time_s", "timing_offset_ms"])


# ── Half-period correction ────────────────────────────────────────────────
def correct_offsets(df: pd.DataFrame, bpm: float) -> pd.DataFrame:
    """Wrap offsets modulo half-period to fix peak-matching artifacts."""
    half_period_ms = 60_000 / bpm / 2
    offsets = df["timing_offset_ms"].values.copy()
    corrected = ((offsets + half_period_ms / 2) % half_period_ms) - half_period_ms / 2
    df = df.copy()
    df["timing_offset_ms"] = corrected
    return df


# ── Interactive selection helpers ─────────────────────────────────────────
def _ask_number(prompt_text: str, max_val: int) -> int:
    """Prompt until the user enters a valid integer in [1, max_val]."""
    while True:
        try:
            choice = int(input(prompt_text))
        except (ValueError, EOFError):
            print("  Please enter a valid number.")
            continue
        if 1 <= choice <= max_val:
            return choice
        print(f"  Number must be between 1 and {max_val}.")


def select_participant() -> str:
    """List participant folders and let the user pick one. Returns full path."""
    base = os.path.abspath(BASE_DATA_DIR)
    if not os.path.isdir(base):
        print(f"Error: data directory not found: {base}")
        sys.exit(1)

    participants = sorted(
        d for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d))
    )
    if not participants:
        print(f"Error: no participant folders in {base}")
        sys.exit(1)

    print("\nAvailable participants:")
    for i, name in enumerate(participants, 1):
        print(f"  [{i}] {name}")

    choice = _ask_number("\nSelect participant: ", len(participants))
    folder = os.path.join(base, participants[choice - 1])
    print(f"  → {participants[choice - 1]}")
    return folder


def select_files(folder: str) -> tuple[str, str]:
    """List CSVs in folder (or plots_during_user_study/) and let the user pick two."""
    data_dir = os.path.join(folder, "plots_during_user_study")
    if not os.path.isdir(data_dir):
        data_dir = folder  # fallback to flat layout

    csvs = sorted(f for f in os.listdir(data_dir)
                   if f.endswith("_synchronization.csv"))
    if len(csvs) < 2:
        print(f"Error: need at least 2 CSV files in {data_dir}, found {len(csvs)}.")
        sys.exit(1)

    print("\nAvailable CSV files:")
    for i, name in enumerate(csvs, 1):
        print(f"  [{i}] {name}")

    file1_idx = _ask_number("\nEnter number for file 1: ", len(csvs))
    file2_idx = _ask_number("Enter number for file 2: ", len(csvs))
    return (os.path.join(data_dir, csvs[file1_idx - 1]),
            os.path.join(data_dir, csvs[file2_idx - 1]))


def label_from_filename(filepath: str) -> str:
    """Extract condition label (e.g. 'Simple', 'Complex', 'None') from filename."""
    name = os.path.basename(filepath).replace("_synchronization.csv", "")
    for condition in ("simple", "complex", "none"):
        if f"_{condition}" in name.lower():
            return condition.capitalize()
    return name


def song_from_filename(filepath: str) -> str:
    """Extract song name from filename, e.g. 'Is There Anybody Out There'."""
    name = os.path.basename(filepath).replace("_synchronization.csv", "")
    for condition in ("_simple", "_complex", "_none"):
        idx = name.lower().find(condition)
        if idx != -1:
            return name[:idx].replace("_", " ")
    return name.replace("_", " ")


# ── Outlier filtering ────────────────────────────────────────────────────
def filter_outliers(abs_offsets: np.ndarray, n_std: float):
    """Return (filtered array, threshold) after removing values > mean + n_std*std."""
    threshold = abs_offsets.mean() + n_std * abs_offsets.std()
    filtered = abs_offsets[abs_offsets <= threshold]
    return filtered, threshold


# ── Statistics ───────────────────────────────────────────────────────────
def print_stats(label, abs_raw, abs_filt, threshold):
    print(f"\n{'─' * 50}")
    print(f"  {label}")
    print(f"{'─' * 50}")
    print(f"  Total peaks:       {len(abs_raw)}")
    print(f"  Outlier threshold: {threshold:.2f} ms")
    print(f"  Peaks retained:    {len(abs_filt)}  "
          f"({len(abs_raw) - len(abs_filt)} removed)")
    print(f"  Mean abs offset:   {abs_filt.mean():.2f} ms")
    print(f"  Median abs offset: {np.median(abs_filt):.2f} ms")
    print(f"  Std abs offset:    {abs_filt.std():.2f} ms")


def print_comparison(label1, mean1, label2, mean2):
    diff = abs(mean1 - mean2)
    better_label = label1 if mean1 < mean2 else label2
    worse_label = label2 if mean1 < mean2 else label1
    better_mean = min(mean1, mean2)
    pct = (diff / better_mean * 100) if better_mean > 0 else float("inf")
    print(f"\n{'═' * 50}")
    print("  Comparison")
    print(f"{'═' * 50}")
    print(f"  Difference in mean offset: {diff:.2f} ms")
    print(f"  Percentage difference:     {pct:.1f}% (relative to {better_label})")
    print(f"  → {better_label} is more synchronised than {worse_label} "
          f"by {diff:.2f} ms on average.\n")


# ── Y-axis limiting helper ───────────────────────────────────────────────
def _ylim_from_percentile(*arrays, percentile=95, margin=1.3):
    """Compute a y-limit from the Nth percentile of combined data, with margin."""
    combined = np.concatenate([np.abs(a) for a in arrays])
    return np.percentile(combined, percentile) * margin


# ── Plot functions ───────────────────────────────────────────────────────
def plot_histogram(af1, af2, label1, label2, song, out_path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, data, label, color in zip(
        axes, [af1, af2], [label1, label2], [COLOR1, COLOR2]
    ):
        ax.hist(data, bins=30, color=color, alpha=0.7, edgecolor="white")
        ax.axvline(data.mean(), color="black", linestyle="--", linewidth=1.2,
                   label=f"Mean = {data.mean():.1f} ms")
        ax.axvline(np.median(data), color="gray", linestyle="--", linewidth=1.2,
                   label=f"Median = {np.median(data):.1f} ms")
        ax.set_title(label)
        ax.set_xlabel("Absolute Timing Offset (ms)")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("Count")
    fig.suptitle(f"{_display_song(song)} — Distribution of Absolute Timing Offsets (filtered)",
                 fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_timeseries(df1, df2, label1, label2, song, out_path):
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.scatter(df1["peak_time_s"], df1["timing_offset_ms"],
               s=18, alpha=0.6, color=COLOR1, label=label1)
    ax.scatter(df2["peak_time_s"], df2["timing_offset_ms"],
               s=18, alpha=0.6, color=COLOR2, label=label2)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="-")
    ylim = _ylim_from_percentile(df1["timing_offset_ms"].values,
                                  df2["timing_offset_ms"].values)
    ax.set_ylim(-ylim, ylim)
    ax.set_xlabel("Peak Time (s)")
    ax.set_ylabel("Timing Offset (ms)")
    ax.set_title(f"{_display_song(song)} — Signed Timing Offset vs. Peak Time")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_ecdf(af1, af2, label1, label2, song, out_path):
    fig, ax = plt.subplots(figsize=(8, 5))
    for data, label, color in [(af1, label1, COLOR1), (af2, label2, COLOR2)]:
        sorted_d = np.sort(data)
        cdf = np.arange(1, len(sorted_d) + 1) / len(sorted_d)
        ax.step(sorted_d, cdf, where="post", color=color, linewidth=1.5, label=label)
    ax.axvline(5, color="gray", linestyle="--", linewidth=1, label="5 ms reference")
    ax.set_xlabel("Absolute Timing Offset (ms)")
    ax.set_ylabel("Proportion of Peaks")
    ax.set_title(f"{_display_song(song)} — Proportion of Peaks Within X ms of Perfect Sync (ECDF)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_boxplot(af1, af2, label1, label2, song, out_path):
    fig, ax = plt.subplots(figsize=(7, 5))
    bp = ax.boxplot([af1, af2], labels=[label1, label2], widths=0.5,
                    patch_artist=True, showfliers=False)
    for patch, color in zip(bp["boxes"], [COLOR1, COLOR2]):
        patch.set_facecolor(color)
        patch.set_alpha(0.4)
    # jittered strip
    rng = np.random.default_rng(42)
    for i, (data, color) in enumerate([(af1, COLOR1), (af2, COLOR2)], 1):
        jitter = rng.uniform(-0.12, 0.12, size=len(data))
        ax.scatter(np.full(len(data), i) + jitter, data,
                   s=12, alpha=0.35, color=color, zorder=3)
    ax.set_ylabel("Absolute Timing Offset (ms)")
    ax.set_ylim(0, _ylim_from_percentile(af1, af2))
    ax.set_title(f"{_display_song(song)} — Box Plot of Absolute Timing Offsets (filtered)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def _plot_sync_ax(ax, df_offsets, color, show_legend=True):
    """Plot peak timing offsets on a given axis.

    Args:
        ax: Matplotlib axis
        df_offsets: DataFrame with [peak_time_s, timing_offset_ms]
        label: Label for this series
        color: Line/fill color
        show_legend: Whether to show the legend
    """
    if df_offsets.empty:
        ax.text(0.5, 0.5, 'No peaks detected', transform=ax.transAxes,
                ha='center', va='center', fontsize=12)
        return

    peak_times = df_offsets["peak_time_s"].values
    peak_offsets = df_offsets["timing_offset_ms"].values
    mean_off = peak_offsets.mean()
    std_off = peak_offsets.std()

    ax.plot(peak_times, peak_offsets, 'o-', color=color, linewidth=1.0,
            markersize=3, alpha=0.7, label='Peak Timing Offset')
    ax.axhline(0, color='black', linewidth=1, alpha=0.5, label='Perfect sync')
    ax.axhline(mean_off, color=color, linestyle='--', linewidth=1.5,
               alpha=0.7, label=f'Mean ({mean_off:+.1f} ms)')
    ax.fill_between(peak_times, mean_off - std_off, mean_off + std_off,
                     alpha=0.15, color=color,
                     label=f'±1 Std ({std_off:.1f} ms)')
    ylim = _ylim_from_percentile(peak_offsets)
    ax.set_ylim(-ylim, ylim)
    ax.set_ylabel('Timing Offset (ms)')
    ax.grid(True, alpha=0.3)
    if show_legend:
        ax.legend(loc='upper right', fontsize=8)


def plot_sync_waveform(df_offsets, label, song, bpm, out_path):
    """Plot peak timing offsets for a single condition.

    Args:
        df_offsets: DataFrame with [peak_time_s, timing_offset_ms] (corrected)
        label: Condition label (e.g. 'Simple', 'Complex')
        song: Song name
        bpm: Song BPM
        out_path: Output file path
    """
    fig, ax = plt.subplots(figsize=(12, 4))
    fig.suptitle(f"{_display_song(song)} — {label} (BPM: {bpm:.0f})", fontsize=13, fontweight='bold')

    _plot_sync_ax(ax, df_offsets, COLOR1)
    ax.set_xlabel('Time (seconds)')
    ax.set_title('Peak Synchronization (Positive = Motor Late, Negative = Motor Early)',
                 fontsize=10)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_sync_collection(song: str, bpm: float, condition: str,
                         participant_data: list[tuple[str, pd.DataFrame]],
                         out_path: str):
    """Plot peak timing offsets for one song+condition across all participants.

    Args:
        song: Song name
        bpm: Song BPM
        condition: Condition label (e.g. 'Simple', 'Complex')
        participant_data: List of (participant_name, df_offsets) tuples
        out_path: Output file path
    """
    n = len(participant_data)
    if n == 0:
        return

    fig, axes = plt.subplots(n, 1, figsize=(12, 3 * n), sharex=True)
    if n == 1:
        axes = [axes]

    fig.suptitle(f"{_display_song(song)} — {condition} — All Participants (BPM: {bpm:.0f})",
                 fontsize=14, fontweight='bold')

    colors = plt.cm.tab10.colors
    for i, (pname, df_offsets) in enumerate(participant_data):
        ax = axes[i]
        color = colors[i % len(colors)]
        _plot_sync_ax(ax, df_offsets, color, show_legend=True)
        ax.set_ylabel(f'{pname}\nOffset (ms)', fontsize=9)

    axes[-1].set_xlabel('Time (seconds)')
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_rolling(df1, df2, label1, label2, song, window, out_path):
    fig, ax = plt.subplots(figsize=(12, 5))
    for df, label, color in [(df1, label1, COLOR1), (df2, label2, COLOR2)]:
        abs_off = df["timing_offset_ms"].abs()
        rolling = abs_off.rolling(window=window, min_periods=1).mean()
        ax.plot(df["peak_time_s"], rolling, color=color, linewidth=1.5, label=label)
    ylim = _ylim_from_percentile(df1["timing_offset_ms"].values,
                                  df2["timing_offset_ms"].values)
    ax.set_ylim(0, ylim)
    ax.set_xlabel("Peak Time (s)")
    ax.set_ylabel("Rolling Mean Absolute Offset (ms)")
    ax.set_title(f"{_display_song(song)} — Rolling Mean (window={window}) of Absolute Offset")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ── Beat alignment analysis ──────────────────────────────────────────────
def _extract_beat_times(song_entry: dict) -> np.ndarray:
    """Extract beat times from the song's audio file using librosa."""
    import librosa

    song_dir = os.path.join(SONGS_DIR, song_entry["path"])
    audio_path = os.path.join(song_dir, "audio.wav")
    if not os.path.isfile(audio_path):
        print(f"  Error: audio file not found: {audio_path}")
        return np.array([])

    print(f"  Loading audio for beat detection: {os.path.basename(audio_path)}")
    y, sr = librosa.load(audio_path, sr=44100, mono=True)
    _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    print(f"  Detected {len(beat_times)} beats")
    return beat_times


def compute_beat_peak_offsets(beat_times: np.ndarray,
                               times: np.ndarray,
                               actual_pos: np.ndarray,
                               bpm: float) -> pd.DataFrame:
    """For each beat, find the nearest motor peak and compute the timing offset.

    This measures how well motor end-stops (peaks/reversals) align with
    musical beats, rather than with trajectory peaks.

    Only considers end-stops within half a beat period of each beat to avoid
    matching to distant, unrelated end-stops.

    Args:
        beat_times: Array of beat positions in seconds
        times: Recorded timestamps from CSV
        actual_pos: Actual motor position (centered) from CSV
        bpm: Song BPM (used to compute max matching window)

    Returns:
        Tuple of (DataFrame with columns [beat_time_s, timing_offset_ms],
                  beats_matched: int, beats_skipped: int)
    """
    # Detect peaks (end-stops) in the actual motor position
    motor_amplitude = (actual_pos.max() - actual_pos.min()) / 2
    if motor_amplitude < 0.01:
        print("  Warning: motor amplitude too small for peak detection.")
        return pd.DataFrame(columns=["beat_time_s", "timing_offset_ms"]), 0, 0

    # Detect both positive and negative peaks (both end-stops)
    pos_peaks, _ = find_peaks(actual_pos, height=0.3 * motor_amplitude)
    neg_peaks, _ = find_peaks(-actual_pos, height=0.3 * motor_amplitude)
    all_peak_indices = np.sort(np.concatenate([pos_peaks, neg_peaks]))

    if len(all_peak_indices) == 0:
        print("  Warning: no motor peaks detected.")
        return pd.DataFrame(columns=["beat_time_s", "timing_offset_ms"]), 0, 0

    motor_peak_times = times[all_peak_indices]

    # Maximum search window: half a beat period
    max_offset_s = 60.0 / bpm / 2.0

    # For each beat, find nearest motor end-stop within the window
    rows = []
    skipped = 0
    for bt in beat_times:
        # Only consider beats within the recorded time range
        if bt < times[0] or bt > times[-1]:
            continue
        time_diffs = motor_peak_times - bt
        abs_diffs = np.abs(time_diffs)
        # Only consider end-stops within half a beat period
        within_window = abs_diffs <= max_offset_s
        if not np.any(within_window):
            skipped += 1
            continue
        # Find nearest within the window
        masked_abs = np.where(within_window, abs_diffs, np.inf)
        nearest = np.argmin(masked_abs)
        offset_ms = time_diffs[nearest] * 1000  # positive = peak after beat
        rows.append((bt, offset_ms))

    matched = len(rows)
    print(f"  Beats matched: {matched}, Beats skipped: {skipped}, "
          f"Motor end-stops: {len(all_peak_indices)}")
    return pd.DataFrame(rows, columns=["beat_time_s", "timing_offset_ms"]), matched, skipped


def plot_beat_alignment(df_offsets, label, song, bpm, out_path):
    """Plot beat-to-peak timing offsets for a single condition."""
    fig, ax = plt.subplots(figsize=(12, 4))
    fig.suptitle(f"{_display_song(song)} — {label} — Beat vs End-Stop Alignment (BPM: {bpm:.0f})",
                 fontsize=12, fontweight='bold')

    if df_offsets.empty:
        ax.text(0.5, 0.5, 'No data', transform=ax.transAxes,
                ha='center', va='center', fontsize=12)
    else:
        beat_times = df_offsets["beat_time_s"].values
        offsets = df_offsets["timing_offset_ms"].values
        mean_off = offsets.mean()
        std_off = offsets.std()

        ax.plot(beat_times, offsets, 'o-', color=COLOR1, linewidth=1.0,
                markersize=3, alpha=0.7, label='Beat-to-Peak Offset')
        ax.axhline(0, color='black', linewidth=1, alpha=0.5,
                   label='Perfect alignment (peak on beat)')
        ax.axhline(mean_off, color=COLOR1, linestyle='--', linewidth=1.5,
                   alpha=0.7, label=f'Mean ({mean_off:+.1f} ms)')
        ax.fill_between(beat_times, mean_off - std_off, mean_off + std_off,
                         alpha=0.15, color=COLOR1,
                         label=f'±1 Std ({std_off:.1f} ms)')
        ylim = _ylim_from_percentile(offsets)
        ax.set_ylim(-ylim, ylim)

    ax.set_xlabel('Time (seconds)')
    ax.set_ylabel('Timing Offset (ms)')
    ax.set_title('Positive = end-stop after beat, Negative = end-stop before beat',
                 fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper right', fontsize=8)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_beat_alignment_collection(song: str, bpm: float, condition: str,
                                    participant_data: list[tuple[str, pd.DataFrame]],
                                    out_path: str):
    """Plot beat alignment for one song+condition across all participants."""
    n = len(participant_data)
    if n == 0:
        return

    fig, axes = plt.subplots(n, 1, figsize=(12, 3 * n), sharex=True)
    if n == 1:
        axes = [axes]

    fig.suptitle(f"{_display_song(song)} — {condition} — Beat vs End-Stop — All Participants (BPM: {bpm:.0f})",
                 fontsize=13, fontweight='bold')

    colors = plt.cm.tab10.colors
    for i, (pname, df_offsets) in enumerate(participant_data):
        ax = axes[i]
        color = colors[i % len(colors)]
        if not df_offsets.empty:
            bt = df_offsets["beat_time_s"].values
            off = df_offsets["timing_offset_ms"].values
            mean_off = off.mean()
            std_off = off.std()
            ax.plot(bt, off, 'o-', color=color, linewidth=1.0, markersize=3, alpha=0.7,
                    label='Beat-to-Peak Offset')
            ax.axhline(0, color='black', linewidth=1, alpha=0.5, label='Perfect alignment')
            ax.axhline(mean_off, color=color, linestyle='--', linewidth=1.5, alpha=0.7,
                       label=f'Mean ({mean_off:+.1f} ms)')
            ax.fill_between(bt, mean_off - std_off, mean_off + std_off,
                             alpha=0.15, color=color,
                             label=f'±1 Std ({std_off:.1f} ms)')
            ylim = _ylim_from_percentile(off)
            ax.set_ylim(-ylim, ylim)
        ax.set_ylabel(f'{pname}\nOffset (ms)', fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right', fontsize=8)

    axes[-1].set_xlabel('Time (seconds)')
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def _write_beat_alignment_table(rows: list[dict], out_dir: str):
    """Write beat alignment summary tables (LaTeX + Markdown)."""

    def _signed(v):
        return f"+{v:.2f}" if v >= 0 else f"{v:.2f}"

    # ── Markdown ──
    md_lines = [
        "# Beat Alignment Summary — Simple vs Complex",
        "",
        "Mean signed offset (ms) from beat to nearest motor end-stop.",
        "Closer to zero = end-stops land on the beat.",
        "",
        "| P | Song | Simple (ms) | Complex (ms) | |Simple| | |Complex| | S match | C match | Better |",
        "|---|------|------------:|-------------:|--------:|---------:|--------:|--------:|--------|",
    ]

    for row in rows:
        md_lines.append(
            f"| {row['participant']} | {row['song']} | "
            f"{_signed(row['simple_offset'])} | {_signed(row['complex_offset'])} | "
            f"{row['simple_abs']:.2f} | {row['complex_abs']:.2f} | "
            f"{row['simple_match']} | {row['complex_match']} | "
            f"**{row['better']}** |"
        )

    simple_wins = sum(1 for r in rows if r["better"] == "simple")
    complex_wins = sum(1 for r in rows if r["better"] == "complex")
    ties = sum(1 for r in rows if r["better"] == "tie")
    avg_s_abs = np.mean([r["simple_abs"] for r in rows])
    avg_c_abs = np.mean([r["complex_abs"] for r in rows])

    md_lines.extend([
        f"| **Avg** | | | | **{avg_s_abs:.2f}** | **{avg_c_abs:.2f}** | "
        f"**{simple_wins}S / {complex_wins}C / {ties}T** |",
        "",
    ])

    md_path = os.path.join(out_dir, "beat_alignment_summary.md")
    with open(md_path, "w") as f:
        f.write("\n".join(md_lines))
    print(f"  Saved: {md_path}")

    # ── LaTeX ──
    tex_lines = [
        r"% Beat alignment summary — motor end-stops vs musical beats",
        r"",
        r"\begin{table}[ht]",
        r"\centering",
        r"\small",
        r"\begin{tabular}{l l rr rr cc r}",
        r"\toprule",
        r"\textbf{P} & \textbf{Song} &",
        r"\textbf{Simple (ms)} & \textbf{Complex (ms)} &",
        r"\textbf{|Simple|} & \textbf{|Complex|} &",
        r"\textbf{S match} & \textbf{C match} & \textbf{Better} \\",
        r"\midrule",
    ]

    prev_p = None
    for row in rows:
        if prev_p is not None and row["participant"] != prev_p:
            tex_lines.append(r"\addlinespace[4pt]")
        prev_p = row["participant"]

        s_sign = f"$+{row['simple_offset']:.2f}$" if row['simple_offset'] >= 0 else f"${row['simple_offset']:.2f}$"
        c_sign = f"$+{row['complex_offset']:.2f}$" if row['complex_offset'] >= 0 else f"${row['complex_offset']:.2f}$"

        tex_lines.append(
            f"{row['participant']} & {row['song']} & "
            f"{s_sign} & {c_sign} & "
            f"${row['simple_abs']:.2f}$ & ${row['complex_abs']:.2f}$ & "
            f"{row['simple_match']} & {row['complex_match']} & "
            f"\\textbf{{{row['better']}}} \\\\"
        )

    tex_lines.extend([
        r"\midrule",
        f"\\multicolumn{{2}}{{l}}{{\\textbf{{Average}}}} & & & "
        f"$\\mathbf{{{avg_s_abs:.2f}}}$ & $\\mathbf{{{avg_c_abs:.2f}}}$ & "
        f"& & \\textbf{{{simple_wins}S / {complex_wins}C / {ties}T}} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Mean timing offset (ms) from musical beat to nearest motor "
        r"end-stop (peak/reversal), per participant and song. "
        r"S/C match shows beats matched out of total beats in the recording window "
        r"(beats without a nearby end-stop within half a beat period are excluded). "
        r"Closer to zero = better perceptual alignment.}",
        r"\label{tab:beat_alignment}",
        r"\end{table}",
        "",
    ])

    tex_path = os.path.join(out_dir, "beat_alignment_summary.tex")
    with open(tex_path, "w") as f:
        f.write("\n".join(tex_lines))
    print(f"  Saved: {tex_path}")


def run_beat_alignment_analysis(outlier_std: float):
    """Run beat alignment analysis across all participants.

    For each song+condition, compares motor end-stop timing to musical beats
    rather than trajectory peaks. This tests whether the platform's physical
    reversals align with the perceived beat.
    """
    base = os.path.abspath(BASE_DATA_DIR)
    if not os.path.isdir(base):
        print(f"Error: data directory not found: {base}")
        sys.exit(1)

    participants = sorted(
        d for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d))
    )

    # Cache beat times per song (expensive to extract)
    beat_cache: dict[str, np.ndarray] = {}

    # Collect data for summary table
    table_rows = []

    # Collect data for collection plots: {(song, condition, bpm): [(participant, df)]}
    collection_data: dict[tuple[str, str, float], list[tuple[str, pd.DataFrame]]] = {}

    for participant_name in participants:
        folder = os.path.join(base, participant_name)
        data_dir = os.path.join(folder, "plots_during_user_study")
        if not os.path.isdir(data_dir):
            continue

        print(f"\n{'╔' + '═' * 58 + '╗'}")
        print(f"  Participant: {participant_name}")
        print(f"{'╚' + '═' * 58 + '╝'}")

        csvs = sorted(f for f in os.listdir(data_dir)
                       if f.endswith("_synchronization.csv")
                       and "_none_" not in f.lower())

        # Group by song
        songs: dict[str, dict[str, str]] = {}
        for csv_name in csvs:
            full_path = os.path.join(data_dir, csv_name)
            song = song_from_filename(full_path)
            condition = label_from_filename(full_path).lower()
            songs.setdefault(song, {})[condition] = full_path

        per_song_offsets = {}

        for song, conditions in sorted(songs.items()):
            song_entry = _find_song_entry(song)
            if song_entry is None:
                continue
            bpm = song_entry["bpm"]

            # Get beat times (cached)
            if song not in beat_cache:
                beat_cache[song] = _extract_beat_times(song_entry)
            beat_times = beat_cache[song]
            if len(beat_times) == 0:
                continue

            for cond in ("simple", "complex"):
                if cond not in conditions:
                    continue

                path = conditions[cond]
                print(f"\n  [{song} — {cond}]")
                times, actual, _ = parse_sync_csv_timeseries(path)
                if len(times) == 0:
                    continue

                df, matched, skipped = compute_beat_peak_offsets(beat_times, times, actual, bpm)
                if df.empty:
                    continue

                # Outlier removal (no half-period correction — raw offsets)
                signed = df["timing_offset_ms"].values
                abs_vals = np.abs(signed)
                threshold = abs_vals.mean() + outlier_std * abs_vals.std()
                df = df[abs_vals <= threshold]

                per_song_offsets[(song, cond)] = df
                per_song_offsets[(song, cond, "matched")] = matched
                per_song_offsets[(song, cond, "skipped")] = skipped

                # Per-participant sync plot
                sync_dir = os.path.join(folder, "plots_post")
                os.makedirs(sync_dir, exist_ok=True)
                song_slug = song.replace(" ", "_")
                plot_beat_alignment(df, cond.capitalize(), song, bpm,
                                    os.path.join(sync_dir,
                                                 f"{song_slug}_beat_alignment_{cond}.png"))

                # Collect for collection plots
                p_short = participant_name.replace("Participant_", "P")
                key = (song, cond.capitalize(), bpm)
                collection_data.setdefault(key, []).append((p_short, df))

        # Build table rows for this participant
        p_short = participant_name.replace("Participant_", "P")
        for song_entry_item in _load_song_index():
            song = song_entry_item["name"]
            s_key = (song, "simple")
            c_key = (song, "complex")
            if s_key in per_song_offsets and c_key in per_song_offsets:
                s_mean = float(per_song_offsets[s_key]["timing_offset_ms"].mean())
                c_mean = float(per_song_offsets[c_key]["timing_offset_ms"].mean())
                s_abs = abs(s_mean)
                c_abs = abs(c_mean)
                s_matched = per_song_offsets.get((song, "simple", "matched"), 0)
                s_skipped = per_song_offsets.get((song, "simple", "skipped"), 0)
                c_matched = per_song_offsets.get((song, "complex", "matched"), 0)
                c_skipped = per_song_offsets.get((song, "complex", "skipped"), 0)
                s_total = s_matched + s_skipped
                c_total = c_matched + c_skipped
                if abs(s_abs - c_abs) < 0.005:
                    better = "tie"
                elif s_abs < c_abs:
                    better = "simple"
                else:
                    better = "complex"
                table_rows.append({
                    "participant": p_short, "song": _display_song(song),
                    "simple_offset": round(s_mean, 2),
                    "complex_offset": round(c_mean, 2),
                    "simple_abs": round(s_abs, 2),
                    "complex_abs": round(c_abs, 2),
                    "simple_match": f"{s_matched}/{s_total}",
                    "complex_match": f"{c_matched}/{c_total}",
                    "better": better,
                })

    # ── Collection plots ──────────────────────────────────────────────
    if collection_data:
        print("\nGenerating beat alignment collection plots …")
        collection_dir = os.path.join(base, "collection_plots")
        os.makedirs(collection_dir, exist_ok=True)

        for (song, condition, bpm), pdata in sorted(collection_data.items()):
            song_slug = song.replace(" ", "_")
            out_path = os.path.join(
                collection_dir,
                f"{song_slug}_beat_alignment_{condition.lower()}_all_participants.png")
            plot_beat_alignment_collection(song, bpm, condition, pdata, out_path)

    # ── Summary table ─────────────────────────────────────────────────
    if table_rows:
        out_dir = os.path.join(base, "summary_tables")
        os.makedirs(out_dir, exist_ok=True)
        _write_beat_alignment_table(table_rows, out_dir)

    print(f"\n{'═' * 60}")
    print(f"  Beat alignment analysis complete.")
    print(f"{'═' * 60}")


# ── Beat waveform plot (motor position + beats + end-stops) ──────────────
def plot_beat_waveform(times: np.ndarray, actual_pos: np.ndarray,
                       beat_times: np.ndarray, label: str, song: str,
                       bpm: float, out_path: str):
    """Plot motor waveform with beat markers and end-stop markers.

    Shows:
    - Motor position waveform (continuous line)
    - Thin vertical lines at each beat time
    - Markers at each motor end-stop (both positive and negative peaks)

    Args:
        times: Recorded timestamps from CSV
        actual_pos: Actual motor position (centered) from CSV
        beat_times: Array of beat positions in seconds
        label: Condition label (e.g. 'Simple', 'Complex')
        song: Song name
        bpm: Song BPM
        out_path: Output file path
    """
    fig, ax = plt.subplots(figsize=(16, 5))
    fig.suptitle(f"{_display_song(song)} — {label} — Motor Waveform with Beats & End-Stops (BPM: {bpm:.0f})",
                 fontsize=12, fontweight='bold')

    # Motor position waveform
    ax.plot(times, actual_pos, color=COLOR2, linewidth=0.8, alpha=0.8,
            label='Motor Position')

    # Beat markers — visible vertical lines with top ticks
    beats_in_range = beat_times[(beat_times >= times[0]) & (beat_times <= times[-1])]
    y_min = actual_pos.min() * 1.15
    y_max = actual_pos.max() * 1.15
    for i, bt in enumerate(beats_in_range):
        ax.vlines(bt, y_min, y_max, color='#7b2d8e', linewidth=0.5, alpha=0.35,
                  label='Beat' if i == 0 else None)
    # Beat tick marks at top edge for clarity
    ax.scatter(beats_in_range, np.full(len(beats_in_range), y_max),
               color='#7b2d8e', s=12, marker='|', linewidths=1.5, zorder=4,
               alpha=0.7)

    # Detect all end-stops (positive and negative peaks)
    motor_amplitude = (actual_pos.max() - actual_pos.min()) / 2
    if motor_amplitude > 0.01:
        pos_peaks, _ = find_peaks(actual_pos, height=0.3 * motor_amplitude)
        neg_peaks, _ = find_peaks(-actual_pos, height=0.3 * motor_amplitude)

        # Plot positive end-stops (top reversals)
        if len(pos_peaks) > 0:
            ax.scatter(times[pos_peaks], actual_pos[pos_peaks],
                       color=COLOR1, s=20, zorder=5, marker='v',
                       label=f'End-stops ({len(pos_peaks) + len(neg_peaks)} total)')

        # Plot negative end-stops (bottom reversals)
        if len(neg_peaks) > 0:
            ax.scatter(times[neg_peaks], actual_pos[neg_peaks],
                       color=COLOR1, s=20, zorder=5, marker='^')

    ax.set_xlabel('Time (seconds)')
    ax.set_ylabel('Position (turns, centered)')
    ax.axhline(0, color='black', linewidth=0.5, alpha=0.3)
    ax.grid(True, alpha=0.2)
    ax.legend(loc='upper right', fontsize=9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def run_beat_vs_track_plot(participant: str = "Participant_1",
                            song: str = "Is There Anybody Out There",
                            condition: str = "complex",
                            time_start: float = 0.0,
                            time_end: float = 10.0):
    """Generate a side-by-side comparison plot illustrating the conceptual
    difference between beat alignment and motor tracking synchronization.

    Top panel: motor position waveform with beat markers (purple lines) and
               end-stop markers (blue triangles) — beat alignment view
    Bottom panel: per-peak timing offset scatter (motor peaks vs trajectory
                  peaks) — motor tracking view

    Both panels share the x-axis (time). Window is zoomed to time_start..time_end
    to make the conceptual difference visible.
    """
    base = os.path.abspath(BASE_DATA_DIR)
    folder = os.path.join(base, participant)
    data_dir = os.path.join(folder, "plots_during_user_study")
    if not os.path.isdir(data_dir):
        print(f"Error: data directory not found: {data_dir}")
        sys.exit(1)

    # Find the matching CSV
    song_slug = song.replace(" ", "_")
    csv_name = f"{song_slug}_{condition}_synchronization.csv"
    csv_path = os.path.join(data_dir, csv_name)
    if not os.path.isfile(csv_path):
        print(f"Error: CSV not found: {csv_path}")
        sys.exit(1)

    # Look up song metadata
    song_entry = _find_song_entry(song)
    if song_entry is None:
        print(f"Error: song '{song}' not found in index.json")
        sys.exit(1)
    bpm = song_entry["bpm"]

    # Parse motor position
    times, actual, _ = parse_sync_csv_timeseries(csv_path)
    if len(times) == 0:
        print(f"Error: no time-series data in {csv_path}")
        sys.exit(1)

    # Load trajectory for motor tracking analysis
    traj = _load_trajectory(song_entry, condition.capitalize())

    # Extract beat times for beat alignment analysis
    beat_times = _extract_beat_times(song_entry)

    # Compute trajectory peak offsets
    df_track = compute_peak_offsets(traj, times, actual)
    df_track = correct_offsets(df_track, bpm)

    # Build the figure ────────────────────────────────────────────────
    # Top: motor tracking, Bottom: beat alignment
    fig, (ax_track, ax_beat) = plt.subplots(2, 1, figsize=(13, 7), sharex=True,
                                              gridspec_kw={'height_ratios': [2, 3]})
    fig.suptitle(f"Two views of synchronization — {_display_song(song)} / "
                 f"{condition.capitalize()} / {participant.replace('Participant_', 'P')} "
                 f"(BPM: {bpm:.0f})",
                 fontsize=14, fontweight='bold')

    # ── Top panel: Motor tracking view ─────────────────────────────────
    if not df_track.empty:
        peak_times = df_track["peak_time_s"].values
        peak_offsets = df_track["timing_offset_ms"].values
        win_mask = (peak_times >= time_start) & (peak_times <= time_end)
        pt_z = peak_times[win_mask]
        po_z = peak_offsets[win_mask]

        ax_track.scatter(pt_z, po_z, s=40, color=COLOR1, alpha=0.7,
                         edgecolor='white', linewidth=0.5,
                         label='Per-peak offset')
        if len(pt_z) > 1:
            order = np.argsort(pt_z)
            ax_track.plot(pt_z[order], po_z[order], color=COLOR1,
                          linewidth=0.8, alpha=0.4)

        ax_track.axhline(0, color='black', linewidth=1, alpha=0.5,
                         label='Perfect tracking')
        if len(po_z) > 0:
            mean_off = po_z.mean()
            ax_track.axhline(mean_off, color=COLOR2, linestyle='--',
                             linewidth=1.2, alpha=0.6,
                             label=f'Mean ({mean_off:+.1f} ms)')
            ylim = max(20, np.percentile(np.abs(po_z), 95) * 1.3) if len(po_z) > 0 else 20
            ax_track.set_ylim(-ylim, ylim)

    ax_track.set_ylabel('Timing Offset (ms)')
    ax_track.set_title(
        'Motor Tracking — How well did each motor peak match its trajectory peak?',
        fontsize=11, color='#475569')
    ax_track.grid(True, alpha=0.2)
    ax_track.legend(loc='upper right', fontsize=9)

    # ── Bottom panel: Beat alignment view ─────────────────────────────
    mask = (times >= time_start) & (times <= time_end)
    times_z = times[mask]
    actual_z = actual[mask]

    ax_beat.plot(times_z, actual_z, color=COLOR2, linewidth=1.0, alpha=0.85,
                 label='Motor Position')

    # Beat markers (purple lines)
    beats_in_window = beat_times[(beat_times >= time_start) & (beat_times <= time_end)]
    if len(actual_z) > 0:
        y_min = actual_z.min() * 1.15
        y_max = actual_z.max() * 1.15
    else:
        y_min, y_max = -1, 1
    for i, bt in enumerate(beats_in_window):
        ax_beat.vlines(bt, y_min, y_max, color='#7b2d8e', linewidth=0.5, alpha=0.55,
                       label='Beat' if i == 0 else None)
    ax_beat.scatter(beats_in_window, np.full(len(beats_in_window), y_max),
                    color='#7b2d8e', s=14, marker='|', linewidths=1.5,
                    zorder=4, alpha=0.8)

    # End-stop markers (blue triangles)
    motor_amplitude = (actual.max() - actual.min()) / 2
    if motor_amplitude > 0.01:
        pos_peaks, _ = find_peaks(actual, height=0.3 * motor_amplitude)
        neg_peaks, _ = find_peaks(-actual, height=0.3 * motor_amplitude)
        pos_in = pos_peaks[(times[pos_peaks] >= time_start) & (times[pos_peaks] <= time_end)]
        neg_in = neg_peaks[(times[neg_peaks] >= time_start) & (times[neg_peaks] <= time_end)]
        total_endstops = len(pos_in) + len(neg_in)
        if len(pos_in) > 0:
            ax_beat.scatter(times[pos_in], actual[pos_in],
                            color=COLOR1, s=28, zorder=5, marker='v',
                            label=f'End-stops ({total_endstops} in window)')
        if len(neg_in) > 0:
            ax_beat.scatter(times[neg_in], actual[neg_in],
                            color=COLOR1, s=28, zorder=5, marker='^')

    ax_beat.axhline(0, color='black', linewidth=0.5, alpha=0.3)
    ax_beat.set_ylabel('Motor Position\n(turns, centered)')
    ax_beat.set_title(
        'Beat Alignment — Do the platform reversals (▼▲) land on the beats (purple lines)?',
        fontsize=11, color='#475569')
    ax_beat.grid(True, alpha=0.2)
    ax_beat.legend(loc='upper right', fontsize=9)

    # ── X-axis in seconds, major ticks every 1 second ─────────────────
    ax_track.set_xlim(time_start, time_end)
    from matplotlib.ticker import MultipleLocator
    ax_beat.xaxis.set_major_locator(MultipleLocator(1))
    ax_beat.set_xlabel('Time (seconds)')

    fig.tight_layout()

    # Save
    out_dir = os.path.join(base, "comparison_plots")
    os.makedirs(out_dir, exist_ok=True)
    p_short = participant.replace("Participant_", "P")
    out_path = os.path.join(
        out_dir,
        f"{p_short}_{song_slug}_{condition}_beat_vs_track_{int(time_start)}-{int(time_end)}s.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")

    print(f"\n{'═' * 60}")
    print(f"  Comparison plot complete.")
    print(f"{'═' * 60}")


def run_beat_waveform_plots():
    """Generate beat waveform plots for all participants and songs.

    Also generates collection plots (all participants per song+condition).
    """
    base = os.path.abspath(BASE_DATA_DIR)
    if not os.path.isdir(base):
        print(f"Error: data directory not found: {base}")
        sys.exit(1)

    participants = sorted(
        d for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d))
    )

    # Cache beat times per song
    beat_cache: dict[str, np.ndarray] = {}

    for participant_name in participants:
        folder = os.path.join(base, participant_name)
        data_dir = os.path.join(folder, "plots_during_user_study")
        if not os.path.isdir(data_dir):
            continue

        print(f"\n{'╔' + '═' * 58 + '╗'}")
        print(f"  Participant: {participant_name}")
        print(f"{'╚' + '═' * 58 + '╝'}")

        csvs = sorted(f for f in os.listdir(data_dir)
                       if f.endswith("_synchronization.csv")
                       and "_none_" not in f.lower())

        # Group by song
        songs: dict[str, dict[str, str]] = {}
        for csv_name in csvs:
            full_path = os.path.join(data_dir, csv_name)
            song = song_from_filename(full_path)
            condition = label_from_filename(full_path).lower()
            songs.setdefault(song, {})[condition] = full_path

        for song, conditions in sorted(songs.items()):
            song_entry = _find_song_entry(song)
            if song_entry is None:
                continue
            bpm = song_entry["bpm"]

            # Get beat times (cached)
            if song not in beat_cache:
                beat_cache[song] = _extract_beat_times(song_entry)
            beat_times = beat_cache[song]
            if len(beat_times) == 0:
                continue

            for cond in ("simple", "complex"):
                if cond not in conditions:
                    continue

                path = conditions[cond]
                print(f"\n  [{song} — {cond}]")
                times, actual, _ = parse_sync_csv_timeseries(path)
                if len(times) == 0:
                    continue

                sync_dir = os.path.join(folder, "plots_post")
                os.makedirs(sync_dir, exist_ok=True)
                song_slug = song.replace(" ", "_")
                plot_beat_waveform(times, actual, beat_times,
                                   cond.capitalize(), song, bpm,
                                   os.path.join(sync_dir,
                                                f"{song_slug}_beat_waveform_{cond}.png"))

    print(f"\n{'═' * 60}")
    print(f"  Beat waveform plots complete.")
    print(f"{'═' * 60}")


# ── Markdown report ──────────────────────────────────────────────────────
def write_report(out_path, song, participant,
                 label1, abs1_raw, abs1_filt, thresh1,
                 label2, abs2_raw, abs2_filt, thresh2):
    """Write a comparative markdown report."""
    mean1, mean2 = abs1_filt.mean(), abs2_filt.mean()
    med1, med2 = np.median(abs1_filt), np.median(abs2_filt)
    std1, std2 = abs1_filt.std(), abs2_filt.std()
    diff = abs(mean1 - mean2)
    better = label1 if mean1 < mean2 else label2
    worse = label2 if mean1 < mean2 else label1
    better_mean = min(mean1, mean2)
    pct = (diff / better_mean * 100) if better_mean > 0 else float("inf")

    # Proportion within thresholds
    def within(data, ms):
        return (data <= ms).sum() / len(data) * 100

    lines = [
        f"# Synchronization Report — {song}",
        f"",
        f"**Participant:** {participant}  ",
        f"**Music reference:** pre-computed trajectory (dynamic tempo)  ",
        f"**Outlier threshold:** mean + N×std (per condition)",
        f"",
        f"## Per-Condition Statistics",
        f"",
        f"| Metric | {label1} | {label2} |",
        f"|--------|-------:|-------:|",
        f"| Total peaks | {len(abs1_raw)} | {len(abs2_raw)} |",
        f"| Outlier threshold (ms) | {thresh1:.1f} | {thresh2:.1f} |",
        f"| Peaks retained | {len(abs1_filt)} | {len(abs2_filt)} |",
        f"| **Mean abs offset (ms)** | **{mean1:.2f}** | **{mean2:.2f}** |",
        f"| Median abs offset (ms) | {med1:.2f} | {med2:.2f} |",
        f"| Std abs offset (ms) | {std1:.2f} | {std2:.2f} |",
        f"| Min abs offset (ms) | {abs1_filt.min():.2f} | {abs2_filt.min():.2f} |",
        f"| Max abs offset (ms) | {abs1_filt.max():.2f} | {abs2_filt.max():.2f} |",
        f"",
        f"## Accuracy Thresholds",
        f"",
        f"| Within threshold | {label1} | {label2} |",
        f"|-----------------|-------:|-------:|",
        f"| ≤ 1 ms | {within(abs1_filt, 1):.1f}% | {within(abs2_filt, 1):.1f}% |",
        f"| ≤ 2 ms | {within(abs1_filt, 2):.1f}% | {within(abs2_filt, 2):.1f}% |",
        f"| ≤ 5 ms | {within(abs1_filt, 5):.1f}% | {within(abs2_filt, 5):.1f}% |",
        f"| ≤ 10 ms | {within(abs1_filt, 10):.1f}% | {within(abs2_filt, 10):.1f}% |",
        f"",
        f"## Comparison",
        f"",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| Difference in mean offset | {diff:.2f} ms |",
        f"| Percentage difference | {pct:.1f}% |",
        f"| Better condition | **{better}** |",
        f"",
        f"> {better} achieved a mean absolute offset of {min(mean1, mean2):.2f} ms, "
        f"outperforming {worse} ({max(mean1, mean2):.2f} ms) by {diff:.2f} ms "
        f"({pct:.1f}%).",
        f"",
    ]

    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Saved: {out_path}")


# ── LaTeX report ─────────────────────────────────────────────────────────
def write_latex_report(out_path, song, participant,
                       label1, abs1_raw, abs1_filt, thresh1,
                       label2, abs2_raw, abs2_filt, thresh2):
    """Write a comparative LaTeX report (standalone tables, no preamble)."""
    mean1, mean2 = abs1_filt.mean(), abs2_filt.mean()
    med1, med2 = np.median(abs1_filt), np.median(abs2_filt)
    std1, std2 = abs1_filt.std(), abs2_filt.std()
    diff = abs(mean1 - mean2)
    better = label1 if mean1 < mean2 else label2
    worse = label2 if mean1 < mean2 else label1
    better_mean = min(mean1, mean2)
    pct = (diff / better_mean * 100) if better_mean > 0 else float("inf")

    def within(data, ms):
        return (data <= ms).sum() / len(data) * 100

    lines = [
        r"% Synchronization Report — " + song,
        r"% Participant: " + participant,
        r"% Music reference: pre-computed trajectory (dynamic tempo)",
        r"% Outlier threshold: mean + N*std (per condition)",
        "",
        r"\section*{Synchronization Report --- " + song + "}",
        "",
        r"\subsection*{Per-Condition Statistics}",
        "",
        r"\begin{table}[h!]",
        r"\centering",
        r"\begin{tabular}{|l|c|c|}",
        r"\hline",
        f"Metric & {label1} & {label2} \\\\",
        r"\hline",
        f"Total peaks & {len(abs1_raw)} & {len(abs2_raw)} \\\\",
        f"Outlier threshold (ms) & {thresh1:.1f} & {thresh2:.1f} \\\\",
        f"Peaks retained & {len(abs1_filt)} & {len(abs2_filt)} \\\\",
        f"\\textbf{{Mean abs offset (ms)}} & \\textbf{{{mean1:.2f}}} & \\textbf{{{mean2:.2f}}} \\\\",
        f"Median abs offset (ms) & {med1:.2f} & {med2:.2f} \\\\",
        f"Std abs offset (ms) & {std1:.2f} & {std2:.2f} \\\\",
        f"Min abs offset (ms) & {abs1_filt.min():.2f} & {abs2_filt.min():.2f} \\\\",
        f"Max abs offset (ms) & {abs1_filt.max():.2f} & {abs2_filt.max():.2f} \\\\",
        r"\hline",
        r"\end{tabular}",
        r"\caption{Per-condition synchronization statistics for " + song + ".}",
        r"\label{tab:sync_stats}",
        r"\end{table}",
        "",
        r"\subsection*{Accuracy Thresholds}",
        "",
        r"\begin{table}[h!]",
        r"\centering",
        r"\begin{tabular}{|l|c|c|}",
        r"\hline",
        f"Within threshold & {label1} & {label2} \\\\",
        r"\hline",
        f"$\\leq$ 1 ms & {within(abs1_filt, 1):.1f}\\% & {within(abs2_filt, 1):.1f}\\% \\\\",
        f"$\\leq$ 2 ms & {within(abs1_filt, 2):.1f}\\% & {within(abs2_filt, 2):.1f}\\% \\\\",
        f"$\\leq$ 5 ms & {within(abs1_filt, 5):.1f}\\% & {within(abs2_filt, 5):.1f}\\% \\\\",
        f"$\\leq$ 10 ms & {within(abs1_filt, 10):.1f}\\% & {within(abs2_filt, 10):.1f}\\% \\\\",
        r"\hline",
        r"\end{tabular}",
        r"\caption{Proportion of peaks within accuracy thresholds.}",
        r"\label{tab:sync_accuracy}",
        r"\end{table}",
        "",
        r"\subsection*{Comparison}",
        "",
        r"\begin{table}[h!]",
        r"\centering",
        r"\begin{tabular}{|l|c|}",
        r"\hline",
        f"Metric & Value \\\\",
        r"\hline",
        f"Difference in mean offset & {diff:.2f} ms \\\\",
        f"Percentage difference & {pct:.1f}\\% \\\\",
        f"Better condition & \\textbf{{{better}}} \\\\",
        r"\hline",
        r"\end{tabular}",
        r"\caption{Comparison of synchronization conditions.}",
        r"\label{tab:sync_comparison}",
        r"\end{table}",
        "",
        f"{better} achieved a mean absolute offset of {min(mean1, mean2):.2f}~ms, "
        f"outperforming {worse} ({max(mean1, mean2):.2f}~ms) by {diff:.2f}~ms "
        f"({pct:.1f}\\%).",
        "",
    ]

    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Saved: {out_path}")


# ── CSV export ────────────────────────────────────────────────────────────
def write_csv_report(out_dir, prefix, song, participant,
                     label1, df1, abs1_raw, abs1_filt, thresh1,
                     label2, df2, abs2_raw, abs2_filt, thresh2):
    """Export per-peak offsets and summary statistics as CSV files."""

    # ── Per-peak offsets ──────────────────────────────────────────────
    offsets_path = os.path.join(out_dir, f"{prefix}_offsets.csv")
    rows = []
    for _, row in df1.iterrows():
        rows.append((row["peak_time_s"], row["timing_offset_ms"], label1))
    for _, row in df2.iterrows():
        rows.append((row["peak_time_s"], row["timing_offset_ms"], label2))
    offsets_df = pd.DataFrame(rows, columns=["peak_time_s", "timing_offset_ms", "condition"])
    offsets_df.to_csv(offsets_path, index=False)
    print(f"  Saved: {offsets_path}")

    # ── Summary statistics ────────────────────────────────────────────
    stats_path = os.path.join(out_dir, f"{prefix}_statistics.csv")

    def within(data, ms):
        return (data <= ms).sum() / len(data) * 100

    stats_rows = []
    for label, abs_raw, abs_filt, thresh in [
        (label1, abs1_raw, abs1_filt, thresh1),
        (label2, abs2_raw, abs2_filt, thresh2),
    ]:
        stats_rows.append({
            "song": song,
            "participant": participant,
            "condition": label,
            "total_peaks": len(abs_raw),
            "outlier_threshold_ms": round(thresh, 2),
            "peaks_retained": len(abs_filt),
            "peaks_removed": len(abs_raw) - len(abs_filt),
            "mean_abs_offset_ms": round(abs_filt.mean(), 2),
            "median_abs_offset_ms": round(float(np.median(abs_filt)), 2),
            "std_abs_offset_ms": round(abs_filt.std(), 2),
            "min_abs_offset_ms": round(abs_filt.min(), 2),
            "max_abs_offset_ms": round(abs_filt.max(), 2),
            "within_1ms_pct": round(within(abs_filt, 1), 1),
            "within_2ms_pct": round(within(abs_filt, 2), 1),
            "within_5ms_pct": round(within(abs_filt, 5), 1),
            "within_10ms_pct": round(within(abs_filt, 10), 1),
        })

    stats_df = pd.DataFrame(stats_rows)
    stats_df.to_csv(stats_path, index=False)
    print(f"  Saved: {stats_path}")


# ── Analyze a single pair of files ────────────────────────────────────────
def analyze_pair(path1: str, path2: str, folder: str, args):
    """Run the full analysis pipeline for one pair of condition files.

    Returns a dict with sync data on success, or None if skipped.
    Dict keys: song, bpm, label1, label2, df1, df2
    """
    participant = os.path.basename(folder)
    label1 = label_from_filename(path1)
    label2 = label_from_filename(path2)
    song = song_from_filename(path1)

    print(f"\n{'━' * 60}")
    print(f"  Song:  {song}")
    print(f"  File 1 ({label1}): {os.path.basename(path1)}")
    print(f"  File 2 ({label2}): {os.path.basename(path2)}")
    print(f"{'━' * 60}")

    # ── Look up song in index.json ────────────────────────────────────
    song_entry = _find_song_entry(song)
    if song_entry is None:
        print(f"  ⚠ Skipping: song '{song}' not found in index.json")
        return None
    print(f"  Matched song: {song_entry['name']} (BPM={song_entry['bpm']:.1f})")

    # ── Parse actual motor data from CSVs ─────────────────────────────
    print(f"\n  Parsing time series from CSVs …")
    times1, actual1, _ = parse_sync_csv_timeseries(path1)
    times2, actual2, _ = parse_sync_csv_timeseries(path2)

    for times, path in [(times1, path1), (times2, path2)]:
        if len(times) == 0:
            print(f"  ⚠ Skipping: no time-series data in {os.path.basename(path)}.")
            return None
    print(f"  File 1: {len(times1)} samples, {times1[-1]:.1f}s")
    print(f"  File 2: {len(times2)} samples, {times2[-1]:.1f}s")

    # ── Load trajectories ─────────────────────────────────────────────
    print(f"\n  Loading trajectories …")
    traj1 = _load_trajectory(song_entry, label1)
    traj2 = _load_trajectory(song_entry, label2)

    # ── Compute peak offsets using trajectory as reference ─────────────
    print(f"\n  Computing peak offsets …")
    print(f"  [{label1}]")
    df1 = compute_peak_offsets(traj1, times1, actual1)
    print(f"  [{label2}]")
    df2 = compute_peak_offsets(traj2, times2, actual2)

    for df, path in [(df1, path1), (df2, path2)]:
        if df.empty:
            print(f"  ⚠ Skipping: no peak offsets from {os.path.basename(path)}.")
            return None

    # ── Half-period correction ────────────────────────────────────────
    bpm = song_entry["bpm"]
    df1 = correct_offsets(df1, bpm)
    df2 = correct_offsets(df2, bpm)
    print(f"\n  Half-period correction applied (BPM={bpm:.1f}, "
          f"half-period={60_000/bpm/2:.1f} ms)")

    abs1_raw = df1["timing_offset_ms"].abs().values
    abs2_raw = df2["timing_offset_ms"].abs().values

    # ── Filter outliers ───────────────────────────────────────────────
    abs1_filt, thresh1 = filter_outliers(abs1_raw, args.outlier_std)
    abs2_filt, thresh2 = filter_outliers(abs2_raw, args.outlier_std)

    # ── Statistics ────────────────────────────────────────────────────
    print_stats(label1, abs1_raw, abs1_filt, thresh1)
    print_stats(label2, abs2_raw, abs2_filt, thresh2)
    print_comparison(label1, abs1_filt.mean(),
                     label2, abs2_filt.mean())

    # ── Output folder and file prefix ────────────────────────────────
    song_folder = song.replace(" ", "_")
    pair_suffix = f"{label1}_vs_{label2}"
    out_dir = os.path.join(folder, "plots_post_user_study",
                           song_folder, pair_suffix)
    os.makedirs(out_dir, exist_ok=True)

    prefix = f"{song_folder}_{pair_suffix}"

    def out(name: str) -> str:
        return os.path.join(out_dir, f"{prefix}_{name}.png")

    # ── Generate requested plots ──────────────────────────────────────
    print("\n  Generating plots …")
    if "histogram" in args.plots:
        plot_histogram(abs1_filt, abs2_filt,
                       label1, label2, song, out("histogram"))
    if "timeseries" in args.plots:
        plot_timeseries(df1, df2, label1, label2, song, out("timeseries"))
    if "ecdf" in args.plots:
        plot_ecdf(abs1_filt, abs2_filt,
                  label1, label2, song, out("ecdf"))
    if "boxplot" in args.plots:
        plot_boxplot(abs1_filt, abs2_filt,
                     label1, label2, song, out("boxplot"))
    if "rolling" in args.plots:
        plot_rolling(df1, df2, label1, label2, song, 20, out("rolling"))
    if "sync" in args.plots:
        sync_dir = os.path.join(folder, "plots_post")
        os.makedirs(sync_dir, exist_ok=True)
        sync_prefix = song.replace(" ", "_")
        plot_sync_waveform(df1, label1, song, bpm,
                           os.path.join(sync_dir, f"{sync_prefix}_sync_{label1.lower()}.png"))
        plot_sync_waveform(df2, label2, song, bpm,
                           os.path.join(sync_dir, f"{sync_prefix}_sync_{label2.lower()}.png"))

    # ── Write reports ─────────────────────────────────────────────────
    report_path = os.path.join(out_dir, f"{prefix}_report.md")
    write_report(report_path, song, participant,
                 label1, abs1_raw, abs1_filt, thresh1,
                 label2, abs2_raw, abs2_filt, thresh2)

    latex_path = os.path.join(out_dir, f"{prefix}_report.tex")
    write_latex_report(latex_path, song, participant,
                       label1, abs1_raw, abs1_filt, thresh1,
                       label2, abs2_raw, abs2_filt, thresh2)

    write_csv_report(out_dir, prefix, song, participant,
                     label1, df1, abs1_raw, abs1_filt, thresh1,
                     label2, df2, abs2_raw, abs2_filt, thresh2)

    return {
        'song': song, 'bpm': bpm, 'participant': participant,
        'label1': label1, 'label2': label2, 'df1': df1, 'df2': df2,
    }


# ── Auto-discover and group CSVs by song ─────────────────────────────────
def discover_song_pairs(folder: str) -> list[tuple[str, str]]:
    """Find all sync CSVs in a participant folder, group by song,
    and return all unique condition pairs per song.

    Returns a list of (path1, path2) tuples, one per pair.
    """
    from itertools import combinations

    data_dir = os.path.join(folder, "plots_during_user_study")
    if not os.path.isdir(data_dir):
        data_dir = folder

    csvs = sorted(f for f in os.listdir(data_dir)
                   if f.endswith("_synchronization.csv")
                   and "_none_" not in f.lower())

    # Group by song name
    songs: dict[str, list[str]] = {}
    for csv_name in csvs:
        song = song_from_filename(os.path.join(data_dir, csv_name))
        songs.setdefault(song, []).append(os.path.join(data_dir, csv_name))

    # Generate all unique pairs per song
    pairs = []
    for song, files in sorted(songs.items()):
        for f1, f2 in combinations(files, 2):
            pairs.append((f1, f2))

    return pairs


# ── Summary table generation ─────────────────────────────────────────────
def _collect_summary_rows(outlier_std: float) -> list[dict]:
    """Iterate all participants and songs, compute simple vs complex offsets.

    Returns a list of dicts with keys:
        participant, song, simple_offset, complex_offset, diff, better
    """
    base = os.path.abspath(BASE_DATA_DIR)
    if not os.path.isdir(base):
        print(f"Error: data directory not found: {base}")
        sys.exit(1)

    participants = sorted(
        d for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d))
    )

    rows = []
    for participant_name in participants:
        folder = os.path.join(base, participant_name)
        data_dir = os.path.join(folder, "plots_during_user_study")
        if not os.path.isdir(data_dir):
            continue

        csvs = sorted(f for f in os.listdir(data_dir)
                       if f.endswith("_synchronization.csv")
                       and "_none_" not in f.lower())

        # Group by song
        songs: dict[str, dict[str, str]] = {}
        for csv_name in csvs:
            full_path = os.path.join(data_dir, csv_name)
            song = song_from_filename(full_path)
            condition = label_from_filename(full_path).lower()
            songs.setdefault(song, {})[condition] = full_path

        for song, conditions in sorted(songs.items()):
            if "simple" not in conditions or "complex" not in conditions:
                continue

            song_entry = _find_song_entry(song)
            if song_entry is None:
                continue

            # Process both conditions (signed offsets)
            offsets = {}
            for cond, path in [("simple", conditions["simple"]),
                                ("complex", conditions["complex"])]:
                times, actual, _ = parse_sync_csv_timeseries(path)
                if len(times) == 0:
                    break
                traj = _load_trajectory(song_entry, cond.capitalize())
                df = compute_peak_offsets(traj, times, actual)
                if df.empty:
                    break
                bpm = song_entry["bpm"]
                df = correct_offsets(df, bpm)
                signed = df["timing_offset_ms"].values
                # Filter outliers on absolute values but keep signs
                abs_vals = np.abs(signed)
                threshold = abs_vals.mean() + outlier_std * abs_vals.std()
                mask = abs_vals <= threshold
                offsets[cond] = round(float(signed[mask].mean()), 2)

            if len(offsets) != 2:
                continue

            s = offsets["simple"]
            c = offsets["complex"]
            diff = round(abs(abs(s) - abs(c)), 2)
            if abs(abs(s) - abs(c)) < 0.005:
                better = "tie"
            elif abs(s) < abs(c):
                better = "simple"
            else:
                better = "complex"

            # Short participant label
            p_num = participant_name.replace("Participant_", "P")

            rows.append({
                "participant": p_num,
                "song": song,
                "simple_offset": s,
                "complex_offset": c,
                "diff": diff,
                "better": better,
            })

    return rows


def _write_summary_latex(rows: list[dict], out_path: str):
    """Write a LaTeX summary table."""
    lines = [
        r"% Auto-generated synchronization summary table",
        r"% Simple vs Complex — mean absolute timing offset (filtered)",
        r"",
        r"\definecolor{simplebg}{RGB}{209,241,224}",
        r"\definecolor{simplefg}{RGB}{15,110,86}",
        r"\definecolor{complexbg}{RGB}{209,228,248}",
        r"\definecolor{complexfg}{RGB}{12,68,124}",
        r"\definecolor{tinyb}{RGB}{235,235,230}",
        r"\definecolor{tinyfg}{RGB}{120,119,114}",
        r"\newcommand{\Sbetter}[1]{\cellcolor{simplebg}\textcolor{simplefg}{#1}}",
        r"\newcommand{\Cbetter}[1]{\cellcolor{complexbg}\textcolor{complexfg}{#1}}",
        r"\newcommand{\Tiny}[1]{\cellcolor{tinyb}\textcolor{tinyfg}{#1}}",
        r"",
        r"\begin{table}[ht]",
        r"\centering",
        r"\small",
        r"\begin{tabular}{l l rr r r}",
        r"\toprule",
        r"\textbf{P} & \textbf{Song} &",
        r"\textbf{Simple (ms)} & \textbf{Complex (ms)} &",
        r"\textbf{Diff (ms)} & \textbf{Better} \\",
        r"\midrule",
    ]

    prev_participant = None
    for row in rows:
        # Add spacing between participants
        if prev_participant is not None and row["participant"] != prev_participant:
            lines.append(r"\addlinespace[4pt]")
        prev_participant = row["participant"]

        # Format the "better" cell
        if row["better"] == "simple":
            better_cell = r"\Sbetter{simple}"
        elif row["better"] == "complex":
            better_cell = r"\Cbetter{complex}"
        else:
            better_cell = r"\Tiny{tie}"

        def _signed(v):
            """Format signed value for LaTeX: $+1.23$ or $-1.23$."""
            return f"$+{v:.2f}$" if v >= 0 else f"${v:.2f}$"

        lines.append(
            f"{row['participant']} & {row['song']} & "
            f"{_signed(row['simple_offset'])} & {_signed(row['complex_offset'])} & "
            f"{row['diff']:.2f} & {better_cell} \\\\"
        )

    # Summary row
    simple_wins = sum(1 for r in rows if r["better"] == "simple")
    complex_wins = sum(1 for r in rows if r["better"] == "complex")
    ties = sum(1 for r in rows if r["better"] == "tie")
    avg_simple = np.mean([r["simple_offset"] for r in rows])
    avg_complex = np.mean([r["complex_offset"] for r in rows])
    avg_diff = np.mean([r["diff"] for r in rows])

    def _signed_bf(v):
        return f"$\\mathbf{{+{v:.2f}}}$" if v >= 0 else f"$\\mathbf{{{v:.2f}}}$"

    lines.extend([
        r"\midrule",
        f"\\multicolumn{{2}}{{l}}{{\\textbf{{Average}}}} & "
        f"{_signed_bf(avg_simple)} & {_signed_bf(avg_complex)} & "
        f"$\\mathbf{{{avg_diff:.2f}}}$ & "
        f"\\textbf{{{simple_wins}S / {complex_wins}C / {ties}T}} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Mean signed timing offset (ms) per participant and song, "
        r"comparing Simple and Complex trajectory conditions. "
        r"Positive = motor late, negative = motor early. "
        r"Outliers where $|\mathrm{offset}| > \overline{|\mathrm{offset}|} + 2\sigma_{|\mathrm{offset}|}$ removed.}",
        r"\label{tab:sync_summary}",
        r"\end{table}",
        "",
    ])

    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Saved: {out_path}")


def _write_summary_markdown(rows: list[dict], out_path: str):
    """Write a Markdown summary table."""

    def _signed(v):
        return f"+{v:.2f}" if v >= 0 else f"{v:.2f}"

    lines = [
        "# Synchronization Summary — Simple vs Complex",
        "",
        "Mean signed timing offset (ms). Positive = motor late, negative = motor early.",
        "Outliers where |offset| > mean(|offset|) + 2*std(|offset|) removed.",
        "",
        "| P | Song | Simple (ms) | Complex (ms) | Diff (ms) | Better |",
        "|---|------|------------:|-------------:|----------:|--------|",
    ]

    for row in rows:
        lines.append(
            f"| {row['participant']} | {row['song']} | "
            f"{_signed(row['simple_offset'])} | {_signed(row['complex_offset'])} | "
            f"{row['diff']:.2f} | **{row['better']}** |"
        )

    # Summary
    simple_wins = sum(1 for r in rows if r["better"] == "simple")
    complex_wins = sum(1 for r in rows if r["better"] == "complex")
    ties = sum(1 for r in rows if r["better"] == "tie")
    avg_simple = np.mean([r["simple_offset"] for r in rows])
    avg_complex = np.mean([r["complex_offset"] for r in rows])
    avg_diff = np.mean([r["diff"] for r in rows])

    lines.extend([
        f"| **Avg** | | **{_signed(avg_simple)}** | **{_signed(avg_complex)}** | "
        f"**{avg_diff:.2f}** | "
        f"**{simple_wins}S / {complex_wins}C / {ties}T** |",
        "",
        f"> Simple wins: {simple_wins}, Complex wins: {complex_wins}, Ties: {ties}",
        "",
    ])

    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Saved: {out_path}")


def generate_summary_table(outlier_std: float):
    """Collect data from all participants and generate summary tables."""
    print("\nCollecting data from all participants …")
    rows = _collect_summary_rows(outlier_std)

    if not rows:
        print("Error: no data collected.")
        sys.exit(1)

    print(f"\n  Collected {len(rows)} rows across "
          f"{len(set(r['participant'] for r in rows))} participants.")

    out_dir = os.path.join(os.path.abspath(BASE_DATA_DIR), "summary_tables")
    os.makedirs(out_dir, exist_ok=True)

    _write_summary_latex(rows, os.path.join(out_dir, "sync_summary_table.tex"))
    _write_summary_markdown(rows, os.path.join(out_dir, "sync_summary_table.md"))

    print(f"\n  Output directory: {out_dir}")
    print("Done.")


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Analyze and compare music-motor synchronization data."
    )
    parser.add_argument("--all", action="store_true",
                        help="Automatically analyze all condition pairs for "
                             "all songs across all participants")
    parser.add_argument("--table", action="store_true",
                        help="Generate summary table (LaTeX + Markdown) "
                             "across all participants")
    parser.add_argument("--beat", action="store_true",
                        help="Beat alignment analysis — compare motor end-stops "
                             "to musical beats across all participants")
    parser.add_argument("--beatplot", action="store_true",
                        help="Beat waveform plots — motor position with beat "
                             "markers and end-stop markers")
    parser.add_argument("--compare", action="store_true",
                        help="Beat alignment vs motor tracking comparison plot "
                             "(zoomed window for one participant/song/condition)")
    parser.add_argument("--outlier-std", type=float, default=2.0,
                        help="Outlier threshold multiplier (default: 2.0)")
    parser.add_argument("--output-prefix", default="sync_analysis",
                        help="Filename prefix for saved figures")
    parser.add_argument("--plots", nargs="+",
                        choices=["histogram", "timeseries", "ecdf",
                                 "boxplot", "rolling", "sync"],
                        default=["histogram", "timeseries", "ecdf",
                                 "boxplot", "rolling", "sync"],
                        help="Which plots to generate (default: all)")
    args = parser.parse_args()

    # ── If no mode flags given, show interactive menu ─────────────────
    if not args.all and not args.table and not args.beat and not args.beatplot and not args.compare:
        print("\n=== Sync Analysis ===")
        print("  [1] Calculate — analyze a pair of files (interactive)")
        print("  [2] Calculate all — analyze all participants and songs")
        print("  [3] Make table — generate summary table (all participants)")
        print("  [4] Beat alignment — motor end-stops vs musical beats (all participants)")
        print("  [5] Beat waveform — motor position with beats & end-stops (all participants)")
        print("  [6] Compare — beat alignment vs motor tracking (one zoomed example)")
        choice = _ask_number("\nSelect mode: ", 6)
        if choice == 1:
            pass  # fall through to interactive mode below
        elif choice == 2:
            args.all = True
        elif choice == 3:
            args.table = True
        elif choice == 4:
            args.beat = True
        elif choice == 5:
            args.beatplot = True
        elif choice == 6:
            args.compare = True

    if args.compare:
        # Prompt for participant
        base = os.path.abspath(BASE_DATA_DIR)
        participants = sorted(
            d for d in os.listdir(base)
            if os.path.isdir(os.path.join(base, d)) and d.startswith("Participant_")
        )
        if not participants:
            print(f"Error: no participant folders in {base}")
            sys.exit(1)
        print("\nAvailable participants:")
        for i, name in enumerate(participants, 1):
            short = name.replace("Participant_", "P")
            print(f"  [{i}] {short}")
        p_choice = _ask_number("\nSelect participant: ", len(participants))

        # Prompt for time window
        def _ask_float(prompt_text: str, default: float) -> float:
            while True:
                try:
                    response = input(f"{prompt_text} [{default}]: ").strip()
                    if response == "":
                        return default
                    return float(response)
                except (ValueError, EOFError):
                    print("  Please enter a valid number.")

        print("\nTime window (seconds):")
        t_start = _ask_float("  From", 0.0)
        t_end = _ask_float("  To", 10.0)
        if t_end <= t_start:
            print("  End time must be greater than start time, using defaults.")
            t_start, t_end = 0.0, 10.0

        run_beat_vs_track_plot(participant=participants[p_choice - 1],
                               time_start=t_start, time_end=t_end)
        return

    if args.beatplot:
        run_beat_waveform_plots()
        return

    if args.beat:
        run_beat_alignment_analysis(args.outlier_std)
        return

    if args.table:
        generate_summary_table(args.outlier_std)
        return

    if args.all:
        # ── Auto mode: all participants, all songs, all pairs ─────────
        base = os.path.abspath(BASE_DATA_DIR)
        if not os.path.isdir(base):
            print(f"Error: data directory not found: {base}")
            sys.exit(1)

        participants = sorted(
            d for d in os.listdir(base)
            if os.path.isdir(os.path.join(base, d))
        )
        if not participants:
            print(f"Error: no participant folders in {base}")
            sys.exit(1)

        total_success, total_skipped = 0, 0
        # Collect sync data for collection plots: {(song, condition): [(participant, df)]}
        collection_data: dict[tuple[str, str, float], list[tuple[str, pd.DataFrame]]] = {}

        for participant_name in participants:
            folder = os.path.join(base, participant_name)
            print(f"\n{'╔' + '═' * 58 + '╗'}")
            print(f"  Participant: {participant_name}")
            print(f"{'╚' + '═' * 58 + '╝'}")

            pairs = discover_song_pairs(folder)
            if not pairs:
                print("  No synchronization CSV pairs found, skipping.")
                continue

            print(f"  Found {len(pairs)} condition pair(s).")
            for path1, path2 in pairs:
                result = analyze_pair(path1, path2, folder, args)
                if result is not None:
                    total_success += 1
                    # Collect for collection plots
                    if "sync" in args.plots:
                        p_short = participant_name.replace("Participant_", "P")
                        for label_key, df_key in [('label1', 'df1'), ('label2', 'df2')]:
                            key = (result['song'], result[label_key], result['bpm'])
                            collection_data.setdefault(key, []).append(
                                (p_short, result[df_key]))
                else:
                    total_skipped += 1

        # ── Generate collection plots (one per song+condition) ────────
        if "sync" in args.plots and collection_data:
            print("\nGenerating collection plots …")
            collection_dir = os.path.join(base, "collection_plots")
            os.makedirs(collection_dir, exist_ok=True)

            for (song, condition, bpm), pdata in sorted(collection_data.items()):
                song_slug = song.replace(" ", "_")
                out_path = os.path.join(
                    collection_dir,
                    f"{song_slug}_sync_{condition.lower()}_all_participants.png")
                plot_sync_collection(song, bpm, condition, pdata, out_path)

        print(f"\n{'═' * 60}")
        print(f"  All done: {total_success} pair(s) analyzed across "
              f"{len(participants)} participants, {total_skipped} skipped.")
        print(f"{'═' * 60}")
    else:
        # ── Interactive mode: pick participant and two files ──────────
        folder = select_participant()
        path1, path2 = select_files(folder)
        analyze_pair(path1, path2, folder, args)
        print("\nDone.")


if __name__ == "__main__":
    main()
