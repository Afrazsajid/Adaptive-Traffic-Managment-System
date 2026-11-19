"""
Global Traffic Logic Controller
Coordinates sequential light phases across multiple cameras.
"""

from PySide6.QtCore import QObject, QSignalBlocker, QTimer, Slot
from app.config import TRAFFIC_LIGHT_SETTINGS
from app.utils.traffic_logic import green_duration_for_count


class GlobalTrafficController(QObject):
    """Manages the dynamic traffic flow based on YOLO car counts."""

    # Using imported settings for global logic
    TRANSITION_DELAY = int(TRAFFIC_LIGHT_SETTINGS.get("all_red_delay", 1.5) * 1000)

    def __init__(self, camera_widgets: list, parent=None):
        super().__init__(parent)
        self.cameras = camera_widgets
        self._current_idx = 0
        self._is_running = False

        # Periodic update timer for dynamic adjustment
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(2000)  # Update every 2 seconds
        self._update_timer.timeout.connect(self._recalculate_green_times)

        # Connect signals
        for i, cam in enumerate(self.cameras):
            cam.cycle_finished.connect(self._on_camera_cycle_finished)
            cam.request_transition.connect(self._on_transition_requested)

    def start(self):
        """Start the global traffic cycle."""
        self._is_running = True
        self._current_idx = 0  # Points to Index 0 (Camera 1)

        # Start dynamic updates
        self._update_timer.start()

        # Recalculate once immediately using current YOLO detections
        self._recalculate_green_times()

        # Start the first camera
        self._activate_next()

    def stop(self):
        """Stop the cycle."""
        self._is_running = False
        self._update_timer.stop()

    def _recalculate_green_times(self):
        """Dynamic calculation based on car counts."""
        if not self._is_running:
            return

        for cam in self.cameras:
            self._update_camera_green_duration(cam)

    def _update_camera_green_duration(self, cam):
        duration = green_duration_for_count(cam._car_count)
        cam.TIMERS["green"] = duration
        # Refresh the next green time without resetting an active countdown.
        with QSignalBlocker(cam.header.timer_input):
            cam.header.timer_input.setValue(duration)

    def _activate_next(self):
        """Activate the next camera in a strict 1-2-3-4 sequence."""
        if not self._is_running:
            return

        # 1. Skip logic for the *current* target in the loop
        cam = self.cameras[self._current_idx]
        if cam._car_count == 0:
            print(
                f"DEBUG: Camera {cam._camera_id} is empty. Skipping to next in sequence..."
            )
            self._current_idx = (self._current_idx + 1) % len(self.cameras)
            # Short delay for skip animation/log
            QTimer.singleShot(500, self._activate_next)
            return

        print(
            f"DEBUG: Activating green for Camera {cam._camera_id} ({cam._car_count} cars)"
        )

        self._update_camera_green_duration(cam)
        cam.set_light("GREEN")

    @Slot(int)
    def _on_transition_requested(self, camera_id):
        """Called when a camera hits 0s Green. Decides if skipping Yellow is possible."""
        if not self._running:
            return

        # Check if ANY other camera currently has vehicles
        # (Exclude the current active camera)
        other_total_cars = sum(
            self.cameras[i]._car_count
            for i in range(len(self.cameras))
            if i != self._current_idx
        )

        current_cam = self.cameras[self._current_idx]

        # REQUIREMENT: If NO other camera has cars, STAY GREEN (Skip Yellow/Red)
        if other_total_cars == 0:
            print(
                f"DEBUG: No cars detected on other roads (C1, C2, C3, C4). Keeping Camera {camera_id} GREEN..."
            )
            # Extend green by 10 seconds to keep flow moving
            current_cam._remaining_time = 10
            current_cam._active_light = "green"
            current_cam.update_ui_state()
        else:
            # Normal Flow: Others have cars, so switch from Green -> Yellow -> Red
            print(
                f"DEBUG: {other_total_cars} cars waiting on other roads. Switching Camera {camera_id} to YELLOW."
            )
            # Trigger the standard transition to yellow
            current_cam.set_light("YELLOW")

    @Slot(int)
    def _on_camera_cycle_finished(self, camera_id):
        """Called when a camera finishes its Green + Yellow phase."""
        if not self._is_running:
            return

        # --- SMART HOLD LOGIC ---
        # Check if there are ANY cars waiting on the other 3 roads
        other_cars = sum(
            self.cameras[i]._car_count
            for i in range(len(self.cameras))
            if i != self._current_idx
        )

        current_cam = self.cameras[self._current_idx]

        # If no one is waiting on other roads, and current road still has traffic,
        # RENEW the green light instead of turning Red.
        if other_cars == 0 and current_cam._car_count > 0:
            print(
                f"DEBUG: No cars on other roads. Holding GREEN for Camera {camera_id}..."
            )
            self._update_camera_green_duration(current_cam)
            current_cam.set_light("GREEN")
            return
        # ------------------------

        # Ensure the camera that just finished is set to RED
        finished_cam = self.cameras[self._current_idx]
        finished_cam.set_light("RED")

        # Move to next index (Strict C1 -> C2 -> C3 -> C4)
        self._current_idx = (self._current_idx + 1) % len(self.cameras)

        # Wait a bit (All Red transition) before starting next
        print(
            f"DEBUG: All Red phase for {self.TRANSITION_DELAY}ms before Camera {self._current_idx + 1}"
        )
        QTimer.singleShot(self.TRANSITION_DELAY, self._activate_next)
