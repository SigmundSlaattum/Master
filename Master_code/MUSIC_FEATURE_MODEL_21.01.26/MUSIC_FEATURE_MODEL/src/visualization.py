"""
Visualization Module

Handles all visualization components for motor control:
- PyBullet simulation
- Matplotlib plotting
- Unified interface for both simulation and hardware modes
"""

from floor_simulator import FloorPlatformSimulator, SineWavePlotter
from typing import Optional, Tuple


class VisualizationManager:
    """
    Manages visualization for both simulation and hardware modes.
    Provides a unified interface for updating position displays.
    """

    def __init__(self, simulation_mode: bool = False, plot_enabled: bool = False):
        """
        Initialize visualization manager.

        Args:
            simulation_mode: Whether running in simulation mode (uses PyBullet)
            plot_enabled: Whether to enable standalone plotting (hardware mode only)
        """
        self.simulation_mode = simulation_mode
        self.plot_enabled = plot_enabled
        self.simulator = None
        self.standalone_plotter = None

        self._setup_visualization()

    def _setup_visualization(self):
        """Initialize visualization components based on mode."""
        if self.simulation_mode:
            # Always enable the PyBullet built-in plot visualization
            self.simulator = FloorPlatformSimulator(enable_gui=True, show_plot=True)
            print("✓ PyBullet simulator initialized with plot")
        elif self.plot_enabled:
            # In hardware mode with plotting enabled, create standalone plotter
            self.standalone_plotter = SineWavePlotter(window_duration=4.0, update_rate=60)
            self.standalone_plotter.start()
            print("✓ Standalone plotter initialized")

    def update_position(self, command_position: float, feedback_position: float):
        """
        Update visualization with new position data.

        Args:
            command_position: Commanded/expected position
            feedback_position: Actual feedback position from encoder or simulation
        """
        if self.simulation_mode and self.simulator is not None:
            # Update PyBullet visualization
            self.simulator.update_position(command_position, feedback_position=feedback_position)
            self.simulator.step_simulation()
        elif self.standalone_plotter is not None:
            # Update standalone plotter
            self.standalone_plotter.add_point(command_position, feedback_position=feedback_position)
            self.standalone_plotter.update()

    def update_beat_rms(self, beat_phase: float, bpm: float):
        """
        Update beat and RMS visualization (if supported).

        Args:
            beat_phase: Current beat phase (0-1)
            bpm: Current BPM
        """
        if self.standalone_plotter is not None:
            self.standalone_plotter.update_beat_rms(beat_phase, bpm)
        elif self.simulator is not None and self.simulator.plotter is not None:
            self.simulator.plotter.update_beat_rms(beat_phase, bpm)

    def get_actual_position(self) -> Optional[float]:
        """
        Get actual position from simulator (simulation mode only).

        Returns:
            Actual platform position, or None if not in simulation mode
        """
        if self.simulator is not None:
            return self.simulator.get_actual_platform_position()
        return None

    def is_simulation_mode(self) -> bool:
        """Check if running in simulation mode."""
        return self.simulation_mode

    def close(self):
        """Clean up visualization resources."""
        if self.simulator is not None:
            self.simulator.close()
            print("✓ Simulator closed")

        if self.standalone_plotter is not None:
            self.standalone_plotter.close()
            print("✓ Standalone plotter closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically cleanup."""
        self.close()


def create_visualization(simulation_mode: bool, plot_enabled: bool) -> VisualizationManager:
    """
    Factory function to create appropriate visualization.

    Args:
        simulation_mode: Whether running in simulation mode
        plot_enabled: Whether plotting is enabled (hardware mode only)

    Returns:
        VisualizationManager instance
    """
    return VisualizationManager(simulation_mode=simulation_mode, plot_enabled=plot_enabled)