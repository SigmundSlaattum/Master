#!/usr/bin/env python3
"""Collect summary lines from all sync_analysis_report.md files into one text file."""

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DATA_DIR = os.path.join(SCRIPT_DIR, "..", "src", "user_study_data")
OUTPUT_FILE = os.path.join(BASE_DATA_DIR, "sync_summary.txt")


def main():
    results = []  # (participant, song, summary_line)

    base = os.path.abspath(BASE_DATA_DIR)
    for participant in sorted(os.listdir(base)):
        post_dir = os.path.join(base, participant, "plots_post_user_study")
        if not os.path.isdir(post_dir):
            continue
        for song_folder in sorted(os.listdir(post_dir)):
            report = os.path.join(post_dir, song_folder, "sync_analysis_report.md")
            if not os.path.isfile(report):
                continue
            with open(report) as f:
                for line in f:
                    if line.startswith("> ") and "achieved a mean absolute offset" in line:
                        summary = line.strip().lstrip("> ").rstrip()
                        song = song_folder.replace("_", " ")
                        results.append((participant, song, summary))
                        break

    lines = ["Synchronization Summary — All Participants", "=" * 50, ""]
    current_participant = None
    for participant, song, summary in results:
        if participant != current_participant:
            if current_participant is not None:
                lines.append("")
            lines.append(participant)
            lines.append("-" * len(participant))
            current_participant = participant
        lines.append(f"  {song}: {summary}")

    lines.append("")
    with open(OUTPUT_FILE, "w") as f:
        f.write("\n".join(lines))
    print(f"Saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
