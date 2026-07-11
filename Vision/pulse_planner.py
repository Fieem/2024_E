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
) -> tuple[int, int]:
    if row < 0 or row >= 7 or col < 0 or col >= 7:
        raise PulsePlanningError("BAD_POS", f"Board cell out of range: ({row},{col})")

    effective_theta = normalize_theta_with_dead_zone(theta_deg, dead_zone_deg)
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
    return _interpolate_board_pulses(config.board_cells, sample_row, sample_col)


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
    theta_deg: float | None = None,
    dead_zone_deg: float = 3.0,
) -> tuple[int, int, int, int]:
    slot_index = next_pick_slot(color, board_state)
    pick_p1, pick_p2 = slot_to_pulses(config, color, slot_index)
    place_p1, place_p2 = cell_to_pulses_with_tilt(
        config,
        row,
        col,
        theta_deg,
        dead_zone_deg=dead_zone_deg,
    )
    return pick_p1, pick_p2, place_p1, place_p2


def _color_to_cell_state(color: RobotColor) -> str:
    return "black" if color == "BLACK" else "white"


def normalize_theta_with_dead_zone(theta_deg: float | None, dead_zone_deg: float) -> float:
    if theta_deg is None:
        return 0.0
    theta = float(theta_deg)
    if abs(theta) <= abs(float(dead_zone_deg)):
        return 0.0
    return theta


def _interpolate_board_pulses(
    board_cells: list[list[tuple[int, int]]],
    row_f: float,
    col_f: float,
) -> tuple[int, int]:
    row_f = min(max(row_f, 0.0), 6.0)
    col_f = min(max(col_f, 0.0), 6.0)

    row0 = int(math.floor(row_f))
    col0 = int(math.floor(col_f))
    row1 = min(row0 + 1, 6)
    col1 = min(col0 + 1, 6)
    dy = row_f - row0
    dx = col_f - col0

    p00 = board_cells[row0][col0]
    p01 = board_cells[row0][col1]
    p10 = board_cells[row1][col0]
    p11 = board_cells[row1][col1]

    pulse1 = _bilinear(p00[0], p01[0], p10[0], p11[0], dx, dy)
    pulse2 = _bilinear(p00[1], p01[1], p10[1], p11[1], dx, dy)
    return int(round(pulse1)), int(round(pulse2))


def _bilinear(v00: int, v01: int, v10: int, v11: int, dx: float, dy: float) -> float:
    top = v00 * (1.0 - dx) + v01 * dx
    bottom = v10 * (1.0 - dx) + v11 * dx
    return top * (1.0 - dy) + bottom * dy
