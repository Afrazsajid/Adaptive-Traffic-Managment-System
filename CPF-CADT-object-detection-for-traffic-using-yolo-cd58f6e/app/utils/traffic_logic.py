IDLE_GREEN_SECONDS = 5
MIN_GREEN_SECONDS = 10
SECONDS_PER_ADDITIONAL_VEHICLE = 2
MAX_GREEN_SECONDS = 60


def green_duration_for_count(vehicle_count: int) -> int:
    """Return the planned green time for one approach."""
    if vehicle_count <= 0:
        return IDLE_GREEN_SECONDS

    duration = MIN_GREEN_SECONDS + (vehicle_count - 1) * SECONDS_PER_ADDITIONAL_VEHICLE
    return min(duration, MAX_GREEN_SECONDS)
