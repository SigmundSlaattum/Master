#!/usr/bin/env python3
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
    fig.suptitle(f"{song} — Distribution of Absolute Timing Offsets (filtered)",
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
    ax.set_title(f"{song} — Signed Timing Offset vs. Peak Time")
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
    ax.set_title(f"{song} — Proportion of Peaks Within X ms of Perfect Sync (ECDF)")
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
    ax.set_title(f"{song} — Box Plot of Absolute Timing Offsets (filtered)")
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
    ax.set_title(f"{song} — Rolling Mean (window={window}) of Absolute Offset")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


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


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Analyze and compare music-motor synchronization data."
    )
    parser.add_argument("--outlier-std", type=float, default=2.0,
                        help="Outlier threshold multiplier (default: 2.0)")
    parser.add_argument("--output-prefix", default="sync_analysis",
                        help="Filename prefix for saved figures")
    parser.add_argument("--plots", nargs="+",
                        choices=["histogram", "timeseries", "ecdf",
                                 "boxplot", "rolling"],
                        default=["histogram", "timeseries", "ecdf",
                                 "boxplot", "rolling"],
                        help="Which plots to generate (default: all)")
    args = parser.parse_args()

    # ── Select participant, then files ────────────────────────────────
    folder = select_participant()
    participant = os.path.basename(folder)
    path1, path2 = select_files(folder)

    # ── Derive labels and song name from filenames ────────────────────
    label1 = label_from_filename(path1)
    label2 = label_from_filename(path2)
    song = song_from_filename(path1)
    print(f"\n  Song:  {song}")
    print(f"  File 1 ({label1}): {os.path.basename(path1)}")
    print(f"  File 2 ({label2}): {os.path.basename(path2)}")

    # ── Look up song in index.json ────────────────────────────────────
    song_entry = _find_song_entry(song)
    if song_entry is None:
        print(f"\nError: song '{song}' not found in {SONGS_DIR}/index.json")
        print("  Available songs:")
        for e in _load_song_index():
            print(f"    - {e['name']}")
        sys.exit(1)
    print(f"  Matched song: {song_entry['name']} (BPM={song_entry['bpm']:.1f})")

    # ── Parse actual motor data from CSVs ─────────────────────────────
    print(f"\n  Parsing time series from CSVs …")
    times1, actual1, _ = parse_sync_csv_timeseries(path1)
    times2, actual2, _ = parse_sync_csv_timeseries(path2)

    for times, path in [(times1, path1), (times2, path2)]:
        if len(times) == 0:
            print(f"\nError: no time-series data in {os.path.basename(path)}.")
            print("  The CSV may be in an older format without the full time series.")
            sys.exit(1)
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
            print(f"\nError: no peak offsets computed from {os.path.basename(path)}.")
            sys.exit(1)

    # ── Half-period correction (still useful for nearest-peak artifacts)
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

    # ── Output folder (per song) ──────────────────────────────────────
    song_folder = song.replace(" ", "_")
    out_dir = os.path.join(folder, "plots_post_user_study", song_folder)
    os.makedirs(out_dir, exist_ok=True)

    def out(name: str) -> str:
        return os.path.join(out_dir, f"{args.output_prefix}_{name}.png")

    # ── Generate requested plots ──────────────────────────────────────
    print("\nGenerating plots …")
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

    # ── Write markdown report ─────────────────────────────────────────
    report_path = os.path.join(out_dir, f"{args.output_prefix}_report.md")
    write_report(report_path, song, participant,
                 label1, abs1_raw, abs1_filt, thresh1,
                 label2, abs2_raw, abs2_filt, thresh2)

    # ── Write LaTeX report ────────────────────────────────────────────
    latex_path = os.path.join(out_dir, f"{args.output_prefix}_report.tex")
    write_latex_report(latex_path, song, participant,
                       label1, abs1_raw, abs1_filt, thresh1,
                       label2, abs2_raw, abs2_filt, thresh2)

    print("\nDone.")


if __name__ == "__main__":
    main()
