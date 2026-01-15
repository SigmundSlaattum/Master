import pybullet as p
import pybullet_data
import time
import numpy as np
import math
import matplotlib.pyplot as plt
from collections import deque
import threading


class SineWavePlotter:
    """
    Real-time sine wave plotter with a 4-second sliding window.
    Shows command signal and simulated feedback with dots tracing current positions.
    Displays beat timing with animated bar showing RMS level.
    """

    def __init__(self, window_duration=4.0, update_rate=30):
        """
        Initialize the sine wave plotter.

        Args:
            window_duration: Time window to display in seconds (default: 4.0)
            update_rate: Plot update rate in Hz (default: 30)
        """
        self.window_duration = window_duration
        self.update_rate = update_rate
        self.running = False

        # Data storage with timestamps for command signal
        self.times = deque(maxlen=1000)
        self.positions = deque(maxlen=1000)

        # Data storage for simulated feedback
        self.feedback_times = deque(maxlen=1000)
        self.feedback_positions = deque(maxlen=1000)

        # Beat visualization data
        self.beat_times = deque(maxlen=1000)
        self.beat_wave = deque(maxlen=1000)  # Sine wave representing beat
        self.current_bpm = 120.0
        self.current_beat_phase = 0.0

        self.start_time = None

        # Plot elements
        self.fig = None
        self.ax = None
        self.command_line = None
        self.command_dot = None
        self.feedback_line = None
        self.feedback_dot = None
        self.beat_line = None  # Beat reference sine wave
        self.beat_dot = None   # Current beat position

        # Thread-safe lock
        self.lock = threading.Lock()

    def start(self):
        """Start the plotting window in a separate thread."""
        self.running = True
        self.start_time = time.time()

        # Create plot on main thread (required for macOS)
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(10, 6))

        # Command signal (what we want)
        self.command_line, = self.ax.plot([], [], 'b-', linewidth=2, label='Command Signal', alpha=0.8)
        self.command_dot, = self.ax.plot([], [], 'bo', markersize=10, label='Command Current')

        # Feedback signal (what we get from simulation)
        self.feedback_line, = self.ax.plot([], [], 'r-', linewidth=2, label='Simulated Feedback', alpha=0.6)
        self.feedback_dot, = self.ax.plot([], [], 'ro', markersize=8, label='Feedback Current')

        # Beat reference wave (simple sine based on BPM)
        self.beat_line, = self.ax.plot([], [], 'g--', linewidth=1.5, label='Beat Reference', alpha=0.5)
        self.beat_dot, = self.ax.plot([], [], 'go', markersize=6, label='Beat Position')

        self.ax.set_xlabel('Time (s)', fontsize=12)
        self.ax.set_ylabel('Motor Position', fontsize=12)
        self.ax.set_title('Real-Time Sine Wave: Command vs Feedback', fontsize=14)
        self.ax.grid(True, alpha=0.3)
        self.ax.set_ylim(-15, 15)

        self.ax.legend(loc='upper right')

        plt.show(block=False)
        print("Sine wave plotter started")

    def add_point(self, command_position, feedback_position=None):
        """
        Add new position data points for both command and feedback.

        Args:
            command_position: Commanded motor position value
            feedback_position: Simulated feedback position (optional, defaults to command)
        """
        if not self.running or self.start_time is None:
            return

        current_time = time.time() - self.start_time

        with self.lock:
            # Add command signal
            self.times.append(current_time)
            self.positions.append(command_position)

            # Add feedback signal (use command if not provided)
            if feedback_position is not None:
                self.feedback_times.append(current_time)
                self.feedback_positions.append(feedback_position)

            # Generate beat reference wave (simple sine at BPM frequency)
            # Amplitude of 10 to be visible but not overwhelming
            beat_frequency = self.current_bpm / 60.0  # Hz
            beat_value = 10.0 * math.sin(2 * math.pi * beat_frequency * current_time)
            self.beat_times.append(current_time)
            self.beat_wave.append(beat_value)

            # Remove old data outside the window for command signal
            while len(self.times) > 0 and self.times[0] < (current_time - self.window_duration):
                self.times.popleft()
                self.positions.popleft()

            # Remove old data outside the window for feedback signal
            while len(self.feedback_times) > 0 and self.feedback_times[0] < (current_time - self.window_duration):
                self.feedback_times.popleft()
                self.feedback_positions.popleft()

            # Remove old beat data
            while len(self.beat_times) > 0 and self.beat_times[0] < (current_time - self.window_duration):
                self.beat_times.popleft()
                self.beat_wave.popleft()

    def update_beat_rms(self, beat_phase, bpm):
        """
        Update beat phase and BPM for beat visualization.

        Args:
            beat_phase: Current beat phase (0-1)
            bpm: Current beats per minute
        """
        with self.lock:
            self.current_beat_phase = beat_phase
            self.current_bpm = bpm

    def update(self):
        """Update the plot visualization. Should be called periodically."""
        if not self.running or self.fig is None:
            return

        try:
            with self.lock:
                if len(self.times) == 0:
                    return

                # Copy command signal data
                times_list = list(self.times)
                positions_list = list(self.positions)

                # Copy feedback signal data
                feedback_times_list = list(self.feedback_times)
                feedback_positions_list = list(self.feedback_positions)

                # Copy beat wave data
                beat_times_list = list(self.beat_times)
                beat_wave_list = list(self.beat_wave)

                current_time = times_list[-1] if times_list else 0

            # Update command line and dot
            self.command_line.set_data(times_list, positions_list)
            if len(times_list) > 0:
                self.command_dot.set_data([times_list[-1]], [positions_list[-1]])

            # Update feedback line and dot
            if len(feedback_times_list) > 0:
                self.feedback_line.set_data(feedback_times_list, feedback_positions_list)
                self.feedback_dot.set_data([feedback_times_list[-1]], [feedback_positions_list[-1]])

            # Update beat reference line and dot
            if len(beat_times_list) > 0:
                self.beat_line.set_data(beat_times_list, beat_wave_list)
                self.beat_dot.set_data([beat_times_list[-1]], [beat_wave_list[-1]])

            # Update x-axis to show sliding window
            self.ax.set_xlim(max(0, current_time - self.window_duration), current_time + 0.1)

            # Redraw
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()

        except Exception as e:
            print(f"Plot update error: {e}")

    def close(self):
        """Close the plotting window."""
        self.running = False
        if self.fig is not None:
            plt.close(self.fig)
            self.fig = None
        print("Sine wave plotter closed")


class FloorPlatformSimulator:
    """
    PyBullet simulation of a robotic moving floor platform.

    Platform specs:
    - Dimensions: 60cm x 60cm x 30cm high
    - Top plate moves up/down and sideways by 1cm in off-center fashion
    - Made of aluminum struts and wooden top plate
    """

    def __init__(self, enable_gui=True, show_plot=False):
        """
        Initialize the PyBullet simulation.

        Args:
            enable_gui: If True, show visualization window; if False, run headless
            show_plot: If True, show real-time sine wave plot in separate window
        """
        self.enable_gui = enable_gui
        self.show_plot = show_plot
        self.physics_client = None
        self.platform_id = None
        self.base_id = None
        self.position_scale = 0.01  # Scale factor: 1 ODrive unit = 1cm = 0.01m

        # Platform parameters (in meters)
        self.platform_width = 0.60
        self.platform_depth = 0.60
        self.platform_height = 0.30
        self.top_plate_thickness = 0.02
        self.strut_radius = 0.01

        # Movement limits (1cm = 0.01m)
        self.max_vertical_displacement = 0.01
        self.max_horizontal_displacement = 0.01

        # Off-center offset for asymmetric movement
        self.offset_x = 0.1  # 10cm offset from center
        self.offset_y = 0.1

        # Current position
        self.current_position = 0.0

        # Sine wave plotter
        self.plotter = None
        if self.show_plot:
            self.plotter = SineWavePlotter(window_duration=4.0, update_rate=60)

        # Update counter for plot refresh
        self.update_counter = 0

        self.setup_simulation()

    def setup_simulation(self):
        """Initialize PyBullet physics engine and create the platform."""
        # Connect to PyBullet
        if self.enable_gui:
            self.physics_client = p.connect(p.GUI)
        else:
            self.physics_client = p.connect(p.DIRECT)

        # Set up the simulation environment
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)

        # Load ground plane
        p.loadURDF("plane.urdf")

        # Create the platform components
        self._create_platform()

        # Set camera view (if GUI enabled)
        if self.enable_gui:
            p.resetDebugVisualizerCamera(
                cameraDistance=1.2,
                cameraYaw=45,
                cameraPitch=-30,
                cameraTargetPosition=[0, 0, 0.15]
            )
            # Disable the synthetic camera windows
            p.configureDebugVisualizer(p.COV_ENABLE_RGB_BUFFER_PREVIEW, 0)
            p.configureDebugVisualizer(p.COV_ENABLE_DEPTH_BUFFER_PREVIEW, 0)
            p.configureDebugVisualizer(p.COV_ENABLE_SEGMENTATION_MARK_PREVIEW, 0)

        # Start the plotter if enabled
        if self.plotter is not None:
            self.plotter.start()

        print("Floor platform simulation initialized")

    def _create_platform(self):
        """Create the platform structure with base and moving top plate."""

        # Corner positions for struts
        corner_offset = 0.25
        corner_positions = [
            [corner_offset, corner_offset],
            [corner_offset, -corner_offset],
            [-corner_offset, corner_offset],
            [-corner_offset, -corner_offset]
        ]

        # Create bottom wooden plate (static base)
        bottom_plate_visual = p.createVisualShape(
            shapeType=p.GEOM_BOX,
            halfExtents=[self.platform_width/2, self.platform_depth/2, self.top_plate_thickness/2],
            rgbaColor=[0.6, 0.4, 0.2, 1]  # Brown for wood
        )
        bottom_plate_collision = p.createCollisionShape(
            shapeType=p.GEOM_BOX,
            halfExtents=[self.platform_width/2, self.platform_depth/2, self.top_plate_thickness/2]
        )
        self.base_id = p.createMultiBody(
            baseMass=0,  # Static base
            baseCollisionShapeIndex=bottom_plate_collision,
            baseVisualShapeIndex=bottom_plate_visual,
            basePosition=[0, 0, self.top_plate_thickness/2]
        )

        # Create vertical aluminum struts (4 corners)
        strut_visual = p.createVisualShape(
            shapeType=p.GEOM_CYLINDER,
            radius=self.strut_radius,
            length=self.platform_height,
            rgbaColor=[0.7, 0.7, 0.7, 1]
        )
        strut_collision = p.createCollisionShape(
            shapeType=p.GEOM_CYLINDER,
            radius=self.strut_radius,
            height=self.platform_height
        )

        # Create 4 vertical struts at corners
        for corner in corner_positions:
            p.createMultiBody(
                baseMass=0,
                baseCollisionShapeIndex=strut_collision,
                baseVisualShapeIndex=strut_visual,
                basePosition=[corner[0], corner[1], self.top_plate_thickness + self.platform_height/2]
            )

        # Create horizontal aluminum struts connecting vertical struts
        # Lower horizontal struts (just above bottom plate)
        lower_strut_height = self.top_plate_thickness + 0.02
        self._create_horizontal_struts(corner_positions, lower_strut_height)

        # Upper horizontal struts (just below top plate)
        upper_strut_height = self.top_plate_thickness + self.platform_height - 0.02
        self._create_horizontal_struts(corner_positions, upper_strut_height)

        # Create the moving top plate
        self._create_top_plate()

    def _create_horizontal_struts(self, corner_positions, height):
        """
        Create horizontal aluminum struts connecting the vertical struts.

        Args:
            corner_positions: List of [x, y] corner positions
            height: Z-height for the horizontal struts
        """
        # Calculate strut lengths
        # Front strut (connects corners 0 and 1)
        front_length = abs(corner_positions[0][1] - corner_positions[1][1])
        # Side strut
        side_length = abs(corner_positions[0][0] - corner_positions[2][0])

        # Create horizontal strut shape (rotated cylinder)
        h_strut_visual = p.createVisualShape(
            shapeType=p.GEOM_CYLINDER,
            radius=self.strut_radius,
            length=front_length,
            rgbaColor=[0.7, 0.7, 0.7, 1]
        )
        h_strut_collision = p.createCollisionShape(
            shapeType=p.GEOM_CYLINDER,
            radius=self.strut_radius,
            height=front_length
        )

        # Front strut (along Y-axis, positive X)
        front_orn = p.getQuaternionFromEuler([np.pi/2, 0, 0])  # Rotate to align with Y
        p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=h_strut_collision,
            baseVisualShapeIndex=h_strut_visual,
            basePosition=[corner_positions[0][0], 0, height],
            baseOrientation=front_orn
        )

        # Back strut (along Y-axis, negative X)
        p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=h_strut_collision,
            baseVisualShapeIndex=h_strut_visual,
            basePosition=[corner_positions[2][0], 0, height],
            baseOrientation=front_orn
        )

        # Create side strut shape
        s_strut_visual = p.createVisualShape(
            shapeType=p.GEOM_CYLINDER,
            radius=self.strut_radius,
            length=side_length,
            rgbaColor=[0.7, 0.7, 0.7, 1]
        )
        s_strut_collision = p.createCollisionShape(
            shapeType=p.GEOM_CYLINDER,
            radius=self.strut_radius,
            height=side_length
        )

        # Left strut (along X-axis, positive Y)
        side_orn = p.getQuaternionFromEuler([0, np.pi/2, 0])  # Rotate to align with X
        p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=s_strut_collision,
            baseVisualShapeIndex=s_strut_visual,
            basePosition=[0, corner_positions[0][1], height],
            baseOrientation=side_orn
        )

        # Right strut (along X-axis, negative Y)
        p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=s_strut_collision,
            baseVisualShapeIndex=s_strut_visual,
            basePosition=[0, corner_positions[1][1], height],
            baseOrientation=side_orn
        )

    def _create_top_plate(self):
        """Create the moving top plate (called after struts are built)."""
        # Create moving top plate (wood)
        plate_visual = p.createVisualShape(
            shapeType=p.GEOM_BOX,
            halfExtents=[self.platform_width/2, self.platform_depth/2, self.top_plate_thickness/2],
            rgbaColor=[0.6, 0.4, 0.2, 1]  # Brown for wood
        )
        plate_collision = p.createCollisionShape(
            shapeType=p.GEOM_BOX,
            halfExtents=[self.platform_width/2, self.platform_depth/2, self.top_plate_thickness/2]
        )
        self.platform_id = p.createMultiBody(
            baseMass=5.0,  # 5kg wooden plate
            baseCollisionShapeIndex=plate_collision,
            baseVisualShapeIndex=plate_visual,
            basePosition=[0, 0, self.top_plate_thickness + self.platform_height + self.top_plate_thickness/2]
        )

        # Add constraint to allow only vertical and limited horizontal movement
        # We'll control position directly for simplicity
        p.changeDynamics(
            self.platform_id,
            -1,
            linearDamping=0.5,
            angularDamping=0.5
        )

    def update_position(self, motor_position, feedback_position=None):
        """
        Update the platform position based on motor position command.

        Args:
            motor_position: Motor position command in ODrive units (scaled to cm)
            feedback_position: Simulated feedback position (optional)
        """
        self.current_position = motor_position

        # Add data to plotter (both command and feedback if available)
        if self.plotter is not None:
            self.plotter.add_point(motor_position, feedback_position)

        # Convert motor position to platform movement
        # Motor position drives vertical movement (primary axis)
        vertical_displacement = np.clip(
            motor_position * self.position_scale,
            -self.max_vertical_displacement,
            self.max_vertical_displacement
        )

        # Add off-center horizontal movement (creates asymmetric motion)
        # Horizontal movement is derived from vertical position with phase offset
        horizontal_x = np.clip(
            self.offset_x * np.sin(motor_position * 0.5) * self.position_scale,
            -self.max_horizontal_displacement,
            self.max_horizontal_displacement
        )
        horizontal_y = np.clip(
            self.offset_y * np.cos(motor_position * 0.3) * self.position_scale,
            -self.max_horizontal_displacement,
            self.max_horizontal_displacement
        )

        # Calculate new position (account for bottom plate + platform height)
        base_height = self.top_plate_thickness + self.platform_height + self.top_plate_thickness/2
        new_position = [
            horizontal_x,
            horizontal_y,
            base_height + vertical_displacement
        ]

        # Update platform position with smooth constraint
        current_pos, current_orn = p.getBasePositionAndOrientation(self.platform_id)

        # Apply position with damping for realistic movement
        damping_factor = 0.3
        smoothed_position = [
            current_pos[0] + damping_factor * (new_position[0] - current_pos[0]),
            current_pos[1] + damping_factor * (new_position[1] - current_pos[1]),
            current_pos[2] + damping_factor * (new_position[2] - current_pos[2])
        ]

        p.resetBasePositionAndOrientation(
            self.platform_id,
            smoothed_position,
            current_orn
        )

    def step_simulation(self):
        """Advance the physics simulation by one step."""
        p.stepSimulation()
        if self.enable_gui:
            time.sleep(1.0/240.0)  # 240 Hz physics

        # Update plotter every call for 60Hz refresh
        if self.plotter is not None:
            self.plotter.update()

    def get_current_position(self):
        """
        Get the current platform position.

        Returns:
            float: Simulated encoder position (matches motor_position input)
        """
        return self.current_position

    def get_actual_platform_position(self):
        """
        Get the actual platform position from PyBullet physics.
        This converts the physical vertical position back to encoder units.

        Returns:
            float: Actual position in encoder units (equivalent to motor position)
        """
        if self.platform_id is None:
            return 0.0

        # Get actual position from PyBullet
        current_pos, _ = p.getBasePositionAndOrientation(self.platform_id)

        # Calculate base height (reference position)
        base_height = self.top_plate_thickness + self.platform_height + self.top_plate_thickness/2

        # Convert vertical displacement back to encoder units
        vertical_displacement = current_pos[2] - base_height

        # Convert from meters to encoder units (reverse of position_scale)
        encoder_position = vertical_displacement / self.position_scale

        return encoder_position

    def close(self):
        """Clean up and disconnect from PyBullet."""
        # Close plotter first
        if self.plotter is not None:
            self.plotter.close()
            self.plotter = None

        if self.physics_client is not None:
            p.disconnect()
            self.physics_client = None
            print("Floor platform simulation closed")

    def reset(self):
        """Reset the platform to its initial position."""
        base_height = self.top_plate_thickness + self.platform_height + self.top_plate_thickness/2
        p.resetBasePositionAndOrientation(
            self.platform_id,
            [0, 0, base_height],
            [0, 0, 0, 1]
        )
        self.current_position = 0.0


def test_simulator():
    """Test the floor platform simulator with a simple sinusoidal motion."""
    print("Testing floor platform simulator...")

    # Create simulator with GUI and plot
    simulator = FloorPlatformSimulator(enable_gui=True, show_plot=True)

    try:
        # Run a simple test pattern
        duration = 10.0  # seconds
        frequency = 1.0  # Hz
        amplitude = 10.0  # ODrive units (will be scaled to cm)

        start_time = time.time()

        while (time.time() - start_time) < duration:
            current_time = time.time() - start_time

            # Generate sinusoidal position command
            position = amplitude * math.sin(2 * math.pi * frequency * current_time)

            # Update simulator
            simulator.update_position(position)
            simulator.step_simulation()

            # Print status every second
            if int(current_time * 10) % 10 == 0:
                print(f"Time: {current_time:.1f}s | Position: {position:.2f}")

        print("\nTest complete!")

    except KeyboardInterrupt:
        print("\nTest interrupted")
    finally:
        simulator.close()


if __name__ == "__main__":
    test_simulator()
