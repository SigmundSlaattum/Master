#!/usr/bin/env python3
"""
BLE Remote Control Diagnostics

Connects to the Arduino Nano BLE rotary encoder remote, records all
incoming data for 40 seconds, and reports whether the remote is behaving
normally or exhibiting anomalies (spikes, jumps, phantom button presses).

Usage:
    python scripts_for_help/ble_remote_diagnostics.py
"""

import asyncio
import time
import sys
from dataclasses import dataclass, field
from bleak import BleakClient, BleakScanner

# BLE identifiers (must match bluetooth_controller.py)
SERVICE_UUID = "19B10000-E8F2-537E-4F6C-D104768A1214"
CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"
DEVICE_NAMES = ["Nano_Encoder", "Arduino"]

RECORD_DURATION_S = 40
ENCODER_STEP_SIZE = 0.005
MAX_AMPLITUDE = 1.0
BASELINE_AMPLITUDE = 0.3


# ── Thresholds for anomaly detection ─────────────────────────────────
# A single encoder tick changes amplitude by 0.005.  A "spike" is an
# instantaneous jump that is far larger than any realistic knob twist
# between two consecutive BLE notifications (~20-50 ms apart).
SPIKE_THRESHOLD_TICKS = 20       # >20 ticks between consecutive readings
AMPLITUDE_SPIKE_THRESHOLD = 0.10  # >0.10 amplitude jump in one step


@dataclass
class Event:
    """Single recorded BLE event."""
    timestamp: float
    kind: str               # "encoder", "switch", "battery", "battery_low", "unknown"
    raw: str                # raw message string
    encoder_value: int = 0  # only for encoder events
    amplitude: float = 0.0  # computed amplitude at this point
    voltage: float = 0.0    # only for battery events


@dataclass
class DiagnosticResult:
    """Collected diagnostic data."""
    events: list = field(default_factory=list)
    encoder_events: list = field(default_factory=list)
    switch_events: list = field(default_factory=list)
    battery_events: list = field(default_factory=list)
    unknown_events: list = field(default_factory=list)
    anomalies: list = field(default_factory=list)
    start_time: float = 0.0


result = DiagnosticResult()
initial_encoder: int | None = None


def compute_amplitude(encoder_value: int) -> float:
    """Mirror the amplitude calculation from BluetoothController."""
    if initial_encoder is None:
        return BASELINE_AMPLITUDE
    delta = -(encoder_value - initial_encoder)  # default direction is reversed
    return max(0.0, min(MAX_AMPLITUDE, BASELINE_AMPLITUDE + delta * ENCODER_STEP_SIZE))


def notification_handler(sender, data: bytearray):
    """Process each BLE notification and record it."""
    global initial_encoder

    now = time.time()
    try:
        message = data.decode("utf-8").strip()
    except UnicodeDecodeError:
        result.unknown_events.append(Event(now, "unknown", repr(data)))
        result.events.append(result.unknown_events[-1])
        return

    # ── Switch press ──────────────────────────────────────────────
    if message == "SWITCH PRESSED":
        ev = Event(now, "switch", message)
        result.switch_events.append(ev)
        result.events.append(ev)
        return

    # ── Encoder position ──────────────────────────────────────────
    if message.startswith("Pos: "):
        try:
            val = int(message.split(": ")[1])
        except (ValueError, IndexError):
            result.unknown_events.append(Event(now, "unknown", message))
            result.events.append(result.unknown_events[-1])
            return

        if initial_encoder is None:
            initial_encoder = val

        amp = compute_amplitude(val)
        ev = Event(now, "encoder", message, encoder_value=val, amplitude=amp)
        result.encoder_events.append(ev)
        result.events.append(ev)
        return

    # ── Battery ───────────────────────────────────────────────────
    if message.startswith("Battery: ") or message.startswith("BATTERY LOW: "):
        kind = "battery_low" if message.startswith("BATTERY LOW") else "battery"
        try:
            voltage = float(message.split(": ")[1].replace("V", ""))
        except (ValueError, IndexError):
            voltage = 0.0
        ev = Event(now, kind, message, voltage=voltage)
        result.battery_events.append(ev)
        result.events.append(ev)
        return

    # ── Unknown ───────────────────────────────────────────────────
    ev = Event(now, "unknown", message)
    result.unknown_events.append(ev)
    result.events.append(ev)


async def run_diagnostics():
    """Main async routine: scan, connect, record, analyse, report."""
    # ── Scan ──────────────────────────────────────────────────────
    print(f"Scanning for BLE devices ({', '.join(DEVICE_NAMES)})...")
    devices = await BleakScanner.discover(timeout=10.0)

    target = None
    for d in devices:
        if d.name in DEVICE_NAMES:
            target = d
            break

    if target is None:
        print("\nDevice not found. Discovered devices:")
        for d in devices:
            print(f"  {d.name}  ({d.address})")
        print("\nMake sure the remote is powered on and in range.")
        sys.exit(1)

    print(f"Found: {target.name} ({target.address})")

    # ── Connect ───────────────────────────────────────────────────
    async with BleakClient(target.address) as client:
        if not client.is_connected:
            print("Failed to connect.")
            sys.exit(1)

        print("Connected. Subscribing to notifications...")
        await client.start_notify(CHAR_UUID, notification_handler)

        result.start_time = time.time()
        print(f"\nRecording for {RECORD_DURATION_S} seconds — do NOT touch the encoder.\n"
              f"(Button presses are tracked separately and allowed.)\n")

        # Live progress
        for elapsed in range(RECORD_DURATION_S):
            await asyncio.sleep(1)
            bar = "#" * (elapsed + 1) + "-" * (RECORD_DURATION_S - elapsed - 1)
            enc_count = len(result.encoder_events)
            sw_count = len(result.switch_events)
            sys.stdout.write(f"\r  [{bar}] {elapsed + 1}/{RECORD_DURATION_S}s  "
                             f"encoder: {enc_count}  button: {sw_count}")
            sys.stdout.flush()

        print("\n\nRecording complete. Disconnecting...")
        await client.stop_notify(CHAR_UUID)

    # ── Analyse ───────────────────────────────────────────────────
    analyse()

    # ── Report ────────────────────────────────────────────────────
    print_report()


def analyse():
    """Walk through recorded encoder events and detect anomalies."""
    enc = result.encoder_events
    if len(enc) < 2:
        return

    for i in range(1, len(enc)):
        prev = enc[i - 1]
        curr = enc[i]
        dt = curr.timestamp - prev.timestamp

        # Tick jump
        tick_delta = abs(curr.encoder_value - prev.encoder_value)
        if tick_delta >= SPIKE_THRESHOLD_TICKS:
            result.anomalies.append(
                f"ENCODER SPIKE at t={curr.timestamp - result.start_time:.2f}s: "
                f"jumped {tick_delta} ticks in {dt*1000:.0f}ms "
                f"(value {prev.encoder_value} -> {curr.encoder_value})"
            )

        # Amplitude jump
        amp_delta = abs(curr.amplitude - prev.amplitude)
        if amp_delta >= AMPLITUDE_SPIKE_THRESHOLD:
            result.anomalies.append(
                f"AMPLITUDE SPIKE at t={curr.timestamp - result.start_time:.2f}s: "
                f"jumped {amp_delta:.3f} in {dt*1000:.0f}ms "
                f"(amplitude {prev.amplitude:.3f} -> {curr.amplitude:.3f})"
            )

    # Check if amplitude ever hit exactly 1.0 without gradual build-up
    for i, ev in enumerate(enc):
        if ev.amplitude >= MAX_AMPLITUDE:
            # See if it jumped there from well below
            if i > 0 and enc[i - 1].amplitude < MAX_AMPLITUDE - AMPLITUDE_SPIKE_THRESHOLD:
                dt = ev.timestamp - enc[i - 1].timestamp
                result.anomalies.append(
                    f"PEAK HIT at t={ev.timestamp - result.start_time:.2f}s: "
                    f"amplitude reached {ev.amplitude:.3f} from {enc[i-1].amplitude:.3f} "
                    f"in {dt*1000:.0f}ms (possible phantom spike)"
                )

    # Check for unexpected switch presses (informational)
    for sw in result.switch_events:
        result.anomalies.append(
            f"BUTTON PRESS at t={sw.timestamp - result.start_time:.2f}s "
            f"(verify this was intentional)"
        )


def print_report():
    """Print the final diagnostic report to the terminal."""
    enc = result.encoder_events
    sw = result.switch_events
    bat = result.battery_events

    print("\n" + "=" * 64)
    print("  BLE REMOTE CONTROL DIAGNOSTIC REPORT")
    print("=" * 64)

    # ── Summary ───────────────────────────────────────────────────
    total_duration = (result.events[-1].timestamp - result.start_time) if result.events else 0
    print(f"\n  Duration recorded:    {total_duration:.1f}s")
    print(f"  Total events:         {len(result.events)}")
    print(f"  Encoder events:       {len(enc)}")
    print(f"  Button presses:       {len(sw)}")
    print(f"  Battery updates:      {len(bat)}")
    print(f"  Unknown messages:     {len(result.unknown_events)}")

    # ── Encoder statistics ────────────────────────────────────────
    if enc:
        values = [e.encoder_value for e in enc]
        amplitudes = [e.amplitude for e in enc]
        tick_deltas = [abs(enc[i].encoder_value - enc[i - 1].encoder_value)
                       for i in range(1, len(enc))]
        amp_deltas = [abs(enc[i].amplitude - enc[i - 1].amplitude)
                      for i in range(1, len(enc))]

        print(f"\n  Encoder value range:  {min(values)} .. {max(values)}  "
              f"(span: {max(values) - min(values)} ticks)")
        print(f"  Amplitude range:      {min(amplitudes):.3f} .. {max(amplitudes):.3f}")

        if tick_deltas:
            avg_dt = sum(tick_deltas) / len(tick_deltas)
            max_dt = max(tick_deltas)
            print(f"  Avg tick delta:       {avg_dt:.2f}  (max: {max_dt})")
            print(f"  Avg amplitude delta:  {sum(amp_deltas)/len(amp_deltas):.4f}  "
                  f"(max: {max(amp_deltas):.4f})")

        # Notification rate
        if len(enc) >= 2:
            intervals = [enc[i].timestamp - enc[i - 1].timestamp for i in range(1, len(enc))]
            avg_interval = sum(intervals) / len(intervals)
            print(f"  Avg notification interval: {avg_interval*1000:.1f}ms  "
                  f"(~{1/avg_interval:.0f} Hz)" if avg_interval > 0 else "")

    # ── Button events ─────────────────────────────────────────────
    if sw:
        print(f"\n  Button press times:")
        for s in sw:
            print(f"    t = {s.timestamp - result.start_time:.2f}s")

    # ── Battery ───────────────────────────────────────────────────
    if bat:
        voltages = [e.voltage for e in bat if e.voltage > 0]
        if voltages:
            print(f"\n  Battery:              {voltages[-1]:.2f}V "
                  f"(range: {min(voltages):.2f}V .. {max(voltages):.2f}V)")
            low = [e for e in bat if e.kind == "battery_low"]
            if low:
                print(f"  Low battery warnings: {len(low)}")

    # ── Unknown messages ──────────────────────────────────────────
    if result.unknown_events:
        print(f"\n  Unknown messages received:")
        for u in result.unknown_events[:10]:
            print(f"    [{u.raw}]")
        if len(result.unknown_events) > 10:
            print(f"    ... and {len(result.unknown_events) - 10} more")

    # ── Verdict ───────────────────────────────────────────────────
    # Separate real anomalies from informational button press notes
    real_anomalies = [a for a in result.anomalies if not a.startswith("BUTTON PRESS")]
    button_notes = [a for a in result.anomalies if a.startswith("BUTTON PRESS")]

    print("\n" + "-" * 64)

    if real_anomalies:
        print("\n  RESULT: ANOMALIES DETECTED\n")
        for a in real_anomalies:
            print(f"    >> {a}")
        if button_notes:
            print()
            for b in button_notes:
                print(f"    (i) {b}")
        print(f"\n  Total anomalies: {len(real_anomalies)}")
        print("\n  Recommendation: The remote is sending unexpected value changes.")
        print("  Possible causes:")
        print("    - Loose encoder wiring or bad solder joint")
        print("    - Electrical noise on the signal lines")
        print("    - Low battery causing erratic BLE transmission")
        print("    - Arduino firmware bug (debounce / interrupt issue)")
    else:
        print("\n  RESULT: REMOTE CONTROL WORKS PROPERLY")
        if button_notes:
            print(f"\n  Button presses detected ({len(button_notes)}):")
            for b in button_notes:
                print(f"    (i) {b}")
        print("\n  Encoder values changed smoothly with no spikes or jumps.")
        print("  No anomalies detected during the recording window.")

    print("\n" + "=" * 64 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(run_diagnostics())
    except KeyboardInterrupt:
        print("\n\nInterrupted. Generating partial report...\n")
        analyse()
        print_report()
