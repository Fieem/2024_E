from __future__ import annotations

from collections import Counter
import math

from vision_types import PulseConfig, RobotColor


class PulsePlanningError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def next_pick_slot(color: RobotColor, board_state: list[list[str]]) -> int:
    counts = Counter(cell for row in board_state for cell in row)
    slot_index = counts[_color_to_cell_state(color)]
    if slot_index >= 7:
        raise PulsePlanningError("NO_SLOT", f"No remaining slot for color {color}")
    return int(slot_index)


def cell_to_pulses(config: PulseConfig, row: int, col: int) -> tuple[int, int]:
    if row < 0 or row >= 7 or col < 0 or col >= 7:
        raise PulsePlanningError("BAD_POS", f"Board cell out of range: ({row},{col})")
    return config.board_cells[row][col]


def cell_to_pulses_with_tilt(
    config: PulseConfig,
    row: int,
    col: int,
    theta_deg: float | None,
    *,
    dead_zone_deg: float = 3.0,
    max_tilt_deg: float = 55.0,
    max_extrapolation_cells: float = 1.25,
) -> tuple[int, int]:
    if row < 0 or row >= 7 or col < 0 or col >= 7:
        raise PulsePlanningError("BAD_POS", f"Board cell out of range: ({row},{col})")

    effective_theta = normalize_theta_with_dead_zone(
        theta_deg,
        dead_zone_deg,
        max_tilt_deg,
    )
    if effective_theta == 0.0:
        return config.board_cells[row][col]

    center = 3.0
    x = float(col) - center
    y = float(row) - center
    radians = math.radians(effective_theta)
    rotated_x = x * math.cos(radians) - y * math.sin(radians)
    rotated_y = x * math.sin(radians) + y * math.cos(radians)
    sample_col = center + rotated_x
    sample_row = center + rotated_y
    return _interpolate_board_pulses(
        config.board_cells,
        sample_row,
        sample_col,
        max_extrapolation_cells=max_extrapolation_cells,
    )


def slot_to_pulses(config: PulseConfig, color: RobotColor, slot_index: int) -> tuple[int, int]:
    if slot_index < 0 or slot_index >= 7:
        raise PulsePlanningError("NO_SLOT", f"Slot index out of range: {slot_index}")
    slots = config.black_slots if color == "BLACK" else config.white_slots
    return slots[slot_index]


def build_move_pulses(
    config: PulseConfig,
    color: RobotColor,
    row: int,
    col: int,
    board_state: list[list[str]],
    *,
    piece_index: int | None = None,
    theta_deg: float | None = None,
    dead_zone_deg: float = 3.0,
    max_tilt_deg: float = 55.0,
    max_extrapolation_cells: float = 1.25,
) -> tuple[int, int, int, int]:
    slot_index = (
        next_pick_slot(color, board_state)
        if piece_index is None
        else piece_index
    )
    pick_p1, pick_p2 = slot_to_pulses(config, color, slot_index)
    place_p1, place_p2 = cell_to_pulses_with_tilt(
        config,
        row,
        col,
        theta_deg,
        dead_zone_deg=dead_zone_deg,
        max_tilt_deg=max_tilt_deg,
        max_extrapolation_cells=max_extrapolation_cells,
    )
    return pick_p1, pick_p2, place_p1, place_p2


def _color_to_cell_state(color: RobotColor) -> str:
    return "black" if color == "BLACK" else "white"


def normalize_theta_with_dead_zone(
    theta_deg: float | None,
    dead_zone_deg: float,
    max_tilt_deg: float = 55.0,
) -> float:
    if theta_deg is None:
        return 0.0
    theta = float(theta_deg)
    max_tilt = abs(float(max_tilt_deg))
    theta = min(max(theta, -max_tilt), max_tilt)
    if abs(theta) <= abs(float(dead_zone_deg)):
        return 0.0
    return theta


def _interpolate_board_pulses(
    board_cells: list[list[tuple[int, int]]],
    row_f: float,
    col_f: float,
    *,
    max_extrapolation_cells: float = 1.25,
) -> tuple[int, int]:
    """Sample the pulse surface with bilinear interpolation/extrapolation.

    Interior samples use the usual four-cell bilinear interpolation.  When a
    sample is just outside the calibrated table, the first/last two rows or
    columns are extended using their boundary slope.  Extrapolation is
    bounded because a large extrapolation is not supported by calibration
    data and can produce unsafe arm targets.
    """
    if len(board_cells) < 2 or any(len(row) < 2 for row in board_cells):
        raise PulsePlanningError(
            "BAD_CONFIG",
            "board_cells must contain at least a 2x2 pulse table",
        )

    max_extrapolation = max(0.0, float(max_extrapolation_cells))
    row0, row1, dy = _axis_segment(
        row_f,
        len(board_cells),
        max_extrapolation,
        axis_name="row",
    )
    col0, col1, dx = _axis_segment(
        col_f,
        len(board_cells[0]),
        max_extrapolation,
        axis_name="col",
    )

    p00 = board_cells[row0][col0]
    p01 = board_cells[row0][col1]
    p10 = board_cells[row1][col0]
    p11 = board_cells[row1][col1]

    pulse1 = _bilinear(p00[0], p01[0], p10[0], p11[0], dx, dy)
    pulse2 = _bilinear(p00[1], p01[1], p10[1], p11[1], dx, dy)
    return int(round(pulse1)), int(round(pulse2))


def _axis_segment(
    value: float,
    size: int,
    max_extrapolation: float,
    *,
    axis_name: str,
) -> tuple[int, int, float]:
    """Return two neighboring indices and the interpolation parameter.

    For ``value < 0`` the segment [0, 1] is extended with a negative
    parameter.  For ``value > size - 1`` the segment [size - 2, size - 1]
    is extended with a parameter greater than one.
    """
    max_index = size - 1
    if not math.isfinite(value):
        raise PulsePlanningError(
            "BAD_POS",
            f"Invalid {axis_name} coordinate: {value}",
        )

    if value < 0.0:
        distance = -value
        if distance > max_extrapolation:
            raise PulsePlanningError(
                "TILT_OUT_OF_RANGE",
                f"{axis_name} extrapolation too large: {distance:.2f}",
            )
        return 0, 1, value

    if value > float(max_index):
        distance = value - max_index
        if distance > max_extrapolation:
            raise PulsePlanningError(
                "TILT_OUT_OF_RANGE",
                f"{axis_name} extrapolation too large: {distance:.2f}",
            )
        return max_index - 1, max_index, value - (max_index - 1)

    if value >= float(max_index):
        return max_index - 1, max_index, 1.0

    index0 = int(math.floor(value))
    return index0, index0 + 1, value - index0


def _bilinear(v00: int, v01: int, v10: int, v11: int, dx: float, dy: float) -> float:
    top = v00 * (1.0 - dx) + v01 * dx
    bottom = v10 * (1.0 - dx) + v11 * dx
    return top * (1.0 - dy) + bottom * dy
