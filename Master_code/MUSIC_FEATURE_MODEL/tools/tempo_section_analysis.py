#!/usr/bin/env python3
"""
Tempo Section Analysis

Analyses the local tempo (BPM) of a song within specified time intervals.
Uses librosa beat tracking and inter-beat interval analysis, matching the
method used by the project's FeatureExtractor.

Default: Lacrimosa (song_002) with sections 13-23s, 33-44s, 47-58s.

Usage:
    python tools/tempo_section_analysis.py
    python tools/tempo_section_analysis.py --audio path/to/audio.wav
    python tools/tempo_section_analysis.py --sections 10-20 30-40 50-60
"""

import argparse
import sys
from pathlib import Path

import librosa
import numpy as np


# Default audio path (Lacrimosa)
DEFAULT_AUDIO = Path(__file__).parent.parent / "songs" / "song_002" / "audio.wav"

# Default sections to analyse (start_s, end_s)
DEFAULT_SECTIONS = [
    (13, 23),
    (33, 44),
    (47, 58),
]


def detect_beats(audio_path: str, sr: int = 44100, hop_length: int = 512):
    """Load audio and run beat tracking.

    Returns:
        y: audio signal (mono)
        sr: sample rate
        beat_times: array of beat positions in seconds
        global_bpm: estimated global BPM
    """
    print(f"Loading: {audio_path}")
    y, sr = librosa.load(audio_path, sr=sr, mono=True)
    duration = len(y) / sr
    print(f"Duration: {duration:.1f}s  Sample rate: {sr}")

    print("Running beat tracking...")
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)

    global_bpm = float(np.asarray(tempo).flatten()[0])
    print(f"Global BPM: {global_bpm:.1f}  Beats detected: {len(beat_times)}")

    return y, sr, beat_times, global_bpm


def compute_local_tempo(beat_times: np.ndarray, resolution_s: float = 0.01):
    """Compute smoothed local tempo curve from beat times.

    Uses the same method as FeatureExtractor._extract_local_tempo:
    inter-beat intervals -> instantaneous BPM -> 5-beat moving average -> interpolation.

    Returns:
        timestamps: uniform time array at given resolution
        local_bpm: smoothed local BPM at each timestamp
    """
    if len(beat_times) < 3:
        raise ValueError("Too few beats detected for local tempo analysis")

    # Inter-beat intervals and their midpoint times
    ibis = np.diff(beat_times)
    ibi_times = (beat_times[:-1] + beat_times[1:]) / 2.0

    # Convert to instantaneous BPM
    local_bpms = 60.0 / ibis

    # Filter unrealistic values
    valid = (local_bpms >= 20) & (local_bpms <= 300)
    if np.sum(valid) < 2:
        raise ValueError("Too few valid tempo estimates")

    valid_times = ibi_times[valid]
    valid_bpms = local_bpms[valid]

    # Smooth with 5-beat moving average
    window = min(5, len(valid_bpms))
    if window > 1:
        kernel = np.ones(window) / window
        smoothed = np.convolve(valid_bpms, kernel, mode='same')
    else:
        smoothed = valid_bpms

    # Interpolate to uniform timestamps
    t_max = beat_times[-1]
    timestamps = np.arange(0, t_max, resolution_s)
    local_bpm = np.interp(timestamps, valid_times, smoothed,
                          left=smoothed[0], right=smoothed[-1])

    return timestamps, local_bpm


def analyse_section(timestamps, local_bpm, beat_times, start_s, end_s):
    """Compute tempo statistics for a time section.

    Returns a dict with mean, median, min, max, std of local BPM
    and the number of beats within the section.
    """
    mask = (timestamps >= start_s) & (timestamps <= end_s)
    section_bpm = local_bpm[mask]

    beats_in_section = beat_times[(beat_times >= start_s) & (beat_times <= end_s)]

    return {
        'start': start_s,
        'end': end_s,
        'mean_bpm': float(np.mean(section_bpm)),
        'median_bpm': float(np.median(section_bpm)),
        'min_bpm': float(np.min(section_bpm)),
        'max_bpm': float(np.max(section_bpm)),
        'std_bpm': float(np.std(section_bpm)),
        'num_beats': len(beats_in_section),
    }


def print_report(sections_data, global_bpm):
    """Print a formatted report to terminal."""
    print("\n" + "=" * 64)
    print("  TEMPO SECTION ANALYSIS")
    print("=" * 64)
    print(f"\n  Global BPM (librosa estimate): {global_bpm:.1f}")

    print(f"\n  {'Section':<14} {'Mean BPM':<11} {'Min':<9} {'Max':<9} {'Std':<8} {'Beats'}")
    print(f"  {'-'*60}")

    for s in sections_data:
        label = f"{s['start']}–{s['end']}s"
        print(f"  {label:<14} {s['mean_bpm']:<11.1f} {s['min_bpm']:<9.1f} "
              f"{s['max_bpm']:<9.1f} {s['std_bpm']:<8.2f} {s['num_beats']}")

    # Overall comparison
    if len(sections_data) > 1:
        means = [s['mean_bpm'] for s in sections_data]
        print(f"\n  Fastest section:  {sections_data[np.argmax(means)]['start']}–"
              f"{sections_data[np.argmax(means)]['end']}s ({max(means):.1f} BPM)")
        print(f"  Slowest section:  {sections_data[np.argmin(means)]['start']}–"
              f"{sections_data[np.argmin(means)]['end']}s ({min(means):.1f} BPM)")
        print(f"  Tempo spread:     {max(means) - min(means):.1f} BPM across sections")

    print("\n" + "=" * 64 + "\n")


def parse_section(s: str):
    """Parse a section string like '13-23' into (13, 23)."""
    parts = s.split('-')
    if len(parts) != 2:
        raise ValueError(f"Invalid section format: '{s}' (expected start-end, e.g. 13-23)")
    return float(parts[0]), float(parts[1])


def main():
    parser = argparse.ArgumentParser(description="Analyse local tempo in specific song sections")
    parser.add_argument('--audio', type=str, default=str(DEFAULT_AUDIO),
                        help=f"Path to audio file (default: Lacrimosa)")
    parser.add_argument('--sections', nargs='+', type=str, default=None,
                        help="Time sections as start-end pairs, e.g. 13-23 33-44 47-58")
    args = parser.parse_args()

    audio_path = args.audio
    if not Path(audio_path).exists():
        print(f"Audio file not found: {audio_path}")
        sys.exit(1)

    sections = DEFAULT_SECTIONS
    if args.sections:
        sections = [parse_section(s) for s in args.sections]

    # Run analysis
    y, sr, beat_times, global_bpm = detect_beats(audio_path)
    timestamps, local_bpm = compute_local_tempo(beat_times)

    # Analyse each section
    sections_data = []
    for start_s, end_s in sections:
        if end_s > timestamps[-1]:
            print(f"Warning: section {start_s}-{end_s}s exceeds audio duration ({timestamps[-1]:.1f}s)")
            continue
        sections_data.append(analyse_section(timestamps, local_bpm, beat_times, start_s, end_s))

    print_report(sections_data, global_bpm)


if __name__ == "__main__":
    main()
