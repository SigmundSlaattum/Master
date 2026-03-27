#!/usr/bin/env python3
"""
Bluetooth Controller Module

Handles communication with Arduino Nano BLE rotary encoder remote control.
"""

import asyncio
import threading
from typing import Optional, Callable
from bleak import BleakClient, BleakScanner


class BluetoothController:
    """
    Manages Bluetooth connection to Arduino Nano rotary encoder remote.
    """

    # BLE UUIDs from Arduino code
    SERVICE_UUID = "19B10000-E8F2-537E-4F6C-D104768A1214"
    CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"
    DEVICE_NAMES = ["Nano_Encoder", "Arduino"]  # Search for both possible names

    def __init__(self):
        """Initialize Bluetooth controller."""
        self.client: Optional[BleakClient] = None
        self.connected = False
        self.initial_encoder_value: Optional[int] = None
        self.current_encoder_value: int = 0
        self.user_amplitude: float = 0.3

        # Configuration
        self.encoder_step_size: float = 0.005  # Amplitude change per encoder click
        self.encoder_direction_reversed: bool = True  # Direction toggle (default reversed)
        self.max_amplitude: float = 0.6  # Maximum user amplitude limit (0.6 = safe operating limit)

        # Button toggle state
        self.amplitude_before_stop: Optional[float] = None  # Store amplitude before button press

        # Battery monitoring
        self.battery_voltage: float = 0.0  # Current battery voltage
        self.low_battery_warning: bool = False  # Low battery flag
        self.last_battery_update: float = 0.0  # Timestamp of last battery update

        # Auto-reconnect
        self.auto_reconnect_enabled: bool = False  # Enable automatic reconnection
        self.reconnect_interval: float = 5.0  # Seconds between reconnection attempts

        # Callbacks
        self.on_amplitude_change: Optional[Callable[[float], None]] = None
        self.on_switch_press: Optional[Callable[[], None]] = None
        self.on_connection_change: Optional[Callable[[bool], None]] = None
        self.on_battery_update: Optional[Callable[[float, bool], None]] = None

        # Threading
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def set_amplitude_callback(self, callback: Callable[[float], None]):
        """
        Set callback for amplitude changes.

        Args:
            callback: Function to call with new amplitude value
        """
        self.on_amplitude_change = callback

    def set_switch_callback(self, callback: Callable[[], None]):
        """
        Set callback for switch press events.

        Args:
            callback: Function to call when switch is pressed
        """
        self.on_switch_press = callback

    def set_connection_callback(self, callback: Callable[[bool], None]):
        """
        Set callback for connection state changes.

        Args:
            callback: Function to call with connection state (True/False)
        """
        self.on_connection_change = callback

    def set_battery_callback(self, callback: Callable[[float, bool], None]):
        """
        Set callback for battery voltage updates.

        Args:
            callback: Function to call with (voltage, low_battery_warning)
        """
        self.on_battery_update = callback

    def _notification_handler(self, sender, data: bytearray):
        """
        Handle notifications from Arduino.

        Args:
            sender: BLE characteristic that sent the notification
            data: Data received
        """
        try:
            message = data.decode('utf-8').strip()

            # Check for switch press - toggle between 0 and previous value
            if message == "SWITCH PRESSED":
                if self.user_amplitude != 0.0:
                    # Currently active - save current amplitude and set to 0
                    self.amplitude_before_stop = self.user_amplitude
                    self.user_amplitude = 0.0
                    print(f"[BLE] Switch pressed - pausing (saved amplitude: {self.amplitude_before_stop:.2f})")
                else:
                    # Currently stopped - restore previous amplitude
                    if self.amplitude_before_stop is not None:
                        self.user_amplitude = self.amplitude_before_stop
                        print(f"[BLE] Switch pressed - resuming (amplitude: {self.user_amplitude:.2f})")
                    else:
                        # No previous value, restore to 0.3
                        self.user_amplitude = 0.3
                        print("[BLE] Switch pressed - resuming (amplitude: 0.3)")

                if self.on_switch_press:
                    self.on_switch_press()
                if self.on_amplitude_change:
                    self.on_amplitude_change(self.user_amplitude)
                return

            # Parse encoder position
            if message.startswith("Pos: "):
                try:
                    encoder_value = int(message.split(": ")[1])
                    self.current_encoder_value = encoder_value

                    # Set initial value on first reading
                    if self.initial_encoder_value is None:
                        self.initial_encoder_value = encoder_value
                        print(f"[BLE] Initial encoder position: {encoder_value} (amplitude = 0.3)")

                    # Calculate amplitude based on change from initial position
                    # Apply direction reversal if enabled
                    delta = encoder_value - self.initial_encoder_value
                    if self.encoder_direction_reversed:
                        delta = -delta
                    # Clamp between 0.0 and max_amplitude
                    self.user_amplitude = max(0.0, min(self.max_amplitude, 0.3 + (delta * self.encoder_step_size)))

                    # Notify callback
                    if self.on_amplitude_change:
                        self.on_amplitude_change(self.user_amplitude)

                except (ValueError, IndexError) as e:
                    print(f"[BLE] Error parsing encoder value: {e}")
                return

            # Parse battery voltage updates
            if message.startswith("Battery: "):
                try:
                    voltage_str = message.split(": ")[1].replace("V", "")
                    voltage = float(voltage_str)
                    self.battery_voltage = voltage
                    import time
                    self.last_battery_update = time.time()

                    # Check for low battery (< 7V)
                    is_low = voltage < 7.0
                    if is_low != self.low_battery_warning:
                        self.low_battery_warning = is_low
                        if is_low:
                            print(f"[BLE] WARNING: Low battery detected! {voltage:.2f}V")
                        else:
                            print(f"[BLE] Battery level restored: {voltage:.2f}V")

                    # Notify callback
                    if self.on_battery_update:
                        self.on_battery_update(voltage, is_low)

                except (ValueError, IndexError) as e:
                    print(f"[BLE] Error parsing battery voltage: {e}")
                return

            # Parse low battery warnings
            if message.startswith("BATTERY LOW: "):
                try:
                    voltage_str = message.split(": ")[1].replace("V", "")
                    voltage = float(voltage_str)
                    self.battery_voltage = voltage
                    self.low_battery_warning = True
                    import time
                    self.last_battery_update = time.time()

                    print(f"[BLE] LOW BATTERY WARNING! {voltage:.2f}V")

                    # Notify callback
                    if self.on_battery_update:
                        self.on_battery_update(voltage, True)

                except (ValueError, IndexError) as e:
                    print(f"[BLE] Error parsing low battery warning: {e}")
                return

        except UnicodeDecodeError as e:
            print(f"[BLE] Error decoding message: {e}")

    async def _scan_and_connect(self) -> bool:
        """
        Scan for and connect to the Arduino device.

        Returns:
            bool: True if connected successfully
        """
        try:
            print(f"[BLE] Scanning for devices: {', '.join(self.DEVICE_NAMES)}...")

            # Scan for devices
            devices = await BleakScanner.discover(timeout=10.0)

            # Debug: Print all discovered devices
            print(f"[BLE] Found {len(devices)} devices:")
            for device in devices:
                print(f"  - {device.name} ({device.address})")

            # Look for our device by name
            target_device = None
            for device in devices:
                if device.name in self.DEVICE_NAMES:
                    target_device = device
                    print(f"[BLE] Matched device: {device.name}")
                    break

            if target_device is None:
                print(f"[BLE] Device not found. Expected names: {', '.join(self.DEVICE_NAMES)}")
                return False

            print(f"[BLE] Connecting to: {target_device.name} ({target_device.address})")

            # Connect to device
            self.client = BleakClient(target_device.address)
            await self.client.connect()

            if not self.client.is_connected:
                print("[BLE] Failed to connect")
                return False

            print("[BLE] Connected successfully")

            # Subscribe to notifications
            await self.client.start_notify(self.CHAR_UUID, self._notification_handler)
            print("[BLE] Subscribed to encoder notifications")

            self.connected = True
            if self.on_connection_change:
                self.on_connection_change(True)

            return True

        except Exception as e:
            print(f"[BLE] Connection error: {e}")
            return False

    async def _run_loop(self):
        """Main async loop for Bluetooth communication with auto-reconnect."""
        while not self._stop_event.is_set():
            try:
                # Connect to device
                if not await self._scan_and_connect():
                    if self.auto_reconnect_enabled:
                        print(f"[BLE] Connection failed. Retrying in {self.reconnect_interval}s...")
                        await asyncio.sleep(self.reconnect_interval)
                        continue
                    else:
                        return

                # Keep connection alive
                while not self._stop_event.is_set() and self.client and self.client.is_connected:
                    await asyncio.sleep(0.5)

                # Connection lost
                if not self._stop_event.is_set() and self.auto_reconnect_enabled:
                    print(f"[BLE] Connection lost. Attempting to reconnect in {self.reconnect_interval}s...")
                    await self._disconnect_async()
                    await asyncio.sleep(self.reconnect_interval)
                else:
                    break

            except Exception as e:
                print(f"[BLE] Error in communication loop: {e}")
                if self.auto_reconnect_enabled and not self._stop_event.is_set():
                    print(f"[BLE] Retrying in {self.reconnect_interval}s...")
                    await asyncio.sleep(self.reconnect_interval)
                else:
                    break

        # Final cleanup
        await self._disconnect_async()

    async def _disconnect_async(self):
        """Disconnect from device (async)."""
        if self.client and self.client.is_connected:
            try:
                await self.client.stop_notify(self.CHAR_UUID)
                await self.client.disconnect()
                print("[BLE] Disconnected")
            except Exception as e:
                print(f"[BLE] Error during disconnect: {e}")

        self.connected = False
        self.initial_encoder_value = None
        if self.on_connection_change:
            self.on_connection_change(False)

    def _thread_target(self):
        """Thread target function."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._run_loop())
        finally:
            self.loop.close()

    def connect(self, auto_reconnect: bool = True) -> bool:
        """
        Start Bluetooth connection in background thread.

        Args:
            auto_reconnect: Enable automatic reconnection on disconnect (default: True)

        Returns:
            bool: True if thread started successfully
        """
        if self.connected or self.thread is not None:
            print("[BLE] Already connected or connecting")
            return False

        self.auto_reconnect_enabled = auto_reconnect
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._thread_target, daemon=True)
        self.thread.start()

        # Wait a moment for connection attempt
        import time
        time.sleep(2)

        return self.connected

    def disconnect(self):
        """Stop Bluetooth connection."""
        if not self.connected and self.thread is None:
            return

        print("[BLE] Disconnecting...")
        self._stop_event.set()

        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None

    def get_user_amplitude(self) -> float:
        """
        Get current user amplitude multiplier.

        Returns:
            float: Amplitude multiplier (0.0 to max)
        """
        return self.user_amplitude

    def is_connected(self) -> bool:
        """
        Check if connected to device.

        Returns:
            bool: True if connected
        """
        return self.connected

    def reset_baseline(self):
        """Reset the encoder baseline to current position (sets amplitude to 0.3)."""
        if self.connected:
            self.initial_encoder_value = self.current_encoder_value
            self.user_amplitude = 0.3
            print(f"[BLE] Baseline reset to {self.current_encoder_value} (amplitude = 0.3)")
            if self.on_amplitude_change:
                self.on_amplitude_change(self.user_amplitude)

    def toggle_direction(self):
        """Toggle encoder direction (clockwise/counter-clockwise)."""
        self.encoder_direction_reversed = not self.encoder_direction_reversed
        direction = "reversed" if self.encoder_direction_reversed else "normal"
        print(f"[BLE] Encoder direction: {direction}")

        # Recalculate amplitude with new direction
        if self.connected and self.initial_encoder_value is not None:
            delta = self.current_encoder_value - self.initial_encoder_value
            if self.encoder_direction_reversed:
                delta = -delta
            self.user_amplitude = max(0.0, min(self.max_amplitude, 0.3 + (delta * self.encoder_step_size)))
            if self.on_amplitude_change:
                self.on_amplitude_change(self.user_amplitude)

    def set_step_size(self, step_size: float):
        """
        Set encoder step size (amplitude change per click).

        Args:
            step_size: Amplitude change per encoder click
        """
        self.encoder_step_size = step_size
        print(f"[BLE] Encoder step size: {step_size}")

    def set_max_amplitude(self, max_amplitude: float):
        """
        Set maximum amplitude limit.

        Args:
            max_amplitude: Maximum user amplitude (e.g., 2.0)
        """
        self.max_amplitude = max_amplitude
        print(f"[BLE] Max amplitude: {max_amplitude}")

        # Clamp current amplitude if it exceeds new max
        if self.user_amplitude > max_amplitude:
            self.user_amplitude = max_amplitude
            if self.on_amplitude_change:
                self.on_amplitude_change(self.user_amplitude)

    def get_battery_voltage(self) -> float:
        """
        Get current battery voltage.

        Returns:
            float: Battery voltage in volts
        """
        return self.battery_voltage

    def is_low_battery(self) -> bool:
        """
        Check if battery is low (< 7V).

        Returns:
            bool: True if battery is low
        """
        return self.low_battery_warning

    def get_status(self) -> dict:
        """
        Get current status information.

        Returns:
            dict: Status information
        """
        return {
            'connected': self.connected,
            'user_amplitude': self.user_amplitude,
            'encoder_value': self.current_encoder_value,
            'initial_encoder': self.initial_encoder_value,
            'step_size': self.encoder_step_size,
            'direction_reversed': self.encoder_direction_reversed,
            'max_amplitude': self.max_amplitude,
            'auto_reconnect_enabled': self.auto_reconnect_enabled,
            'battery_voltage': self.battery_voltage,
            'low_battery_warning': self.low_battery_warning,
            'last_battery_update': self.last_battery_update
        }
