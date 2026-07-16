from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

from control_config import (
    DEFAULT_CONTROL_CONFIG_PATH,
    ControlConfig,
    ensure_default_control_config,
    load_control_config,
)
from pulse_planner import (
    PulsePlanningError,
    build_move_pulses,
    cell_to_pulses_with_tilt,
)
from serial_protocol import ProtocolError, format_response_line, parse_request_line
from vision_config import DEFAULT_CONFIG_PATH
from vision_runtime import VisionRuntime, build_runtime_configs, show_runtime_windows
from vision_types import ModeRequest, ModeResponse, RobotColor, VisionStableSnapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOMOKU_AI_PATH = PROJECT_ROOT / "gomoku_ai"
if str(GOMOKU_AI_PATH) not in sys.path:
    sys.path.insert(0, str(GOMOKU_AI_PATH))

from gomoku.ai import get_best_move  # noqa: E402
from gomoku.board import Board  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vision control entrypoint with PLACE and BATTLE modes over serial.",
    )
    parser.add_argument("--vision-config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--control-config", default=str(DEFAULT_CONTROL_CONFIG_PATH))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--debug-dir", default="debug")
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=None)
    return parser.parse_args()


@dataclass
class BattleState:
    mode: str = "idle"
    robot_color: RobotColor | None = None
    expected_board_state: list[list[str]] | None = None

    def reset(self) -> None:
        self.mode = "idle"
        self.robot_color = None
        self.expected_board_state = None

    def start(self, robot_color: RobotColor) -> None:
        self.mode = "battle_active"
        self.robot_color = robot_color
        self.expected_board_state = None


class SerialTextTransport:
    def __init__(self, port: str, baudrate: int, timeout_ms: int) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout_ms = timeout_ms
        self._serial = None

    def open(self) -> None:
        try:
            import serial
        except ImportError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError("pyserial is required for control_main.py") from exc

        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout_ms / 1000.0,
        )
        print(
            f"[SERIAL] opened port={self.port}, baudrate={self.baudrate}",
            flush=True,
        )

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def read_line(self) -> str | None:
        if self._serial is None:
            raise RuntimeError("Serial transport has not been opened")
        data = self._serial.readline()
        if not data:
            return None
        line = data.decode("utf-8", errors="ignore").strip()
        print(f"[SERIAL] RX <- {line}", flush=True)
        return line

    def write_line(self, line: str) -> None:
        if self._serial is None:
            raise RuntimeError("Serial transport has not been opened")
        print(f"[SERIAL] TX -> {line}", flush=True)
        self._serial.write((line + "\n").encode("utf-8"))
        self._serial.flush()


class VisionController:
    def __init__(self, control_config: ControlConfig) -> None:
        self.control_config = control_config
        self.battle_state = BattleState()
        self._place_used_slots: dict[RobotColor, set[int]] = {
            "BLACK": set(),
            "WHITE": set(),
        }
        self._place_used_targets: set[tuple[int, int]] = set()
        self._place_board_was_nonempty = False

    def handle_request(
        self,
        request: ModeRequest,
        snapshot: VisionStableSnapshot | None,
    ) -> ModeResponse:
        if request.kind == "battle_start":
            if request.color is None:
                return self._error("BAD_COLOR", "Missing battle color")
            self.battle_state.start(request.color)
            return ModeResponse(kind="busy", message=f"battle_active_{request.color}")

        if request.kind == "new":
            self._reset_place_state()
            return ModeResponse(kind="busy", message="place_reset")

        if request.kind == "place":
            return self._handle_place(request, snapshot)

        if request.kind == "ready":
            return self._handle_ready(snapshot)

        return self._error("BAD_CMD", f"Unsupported mode request: {request.kind}")

    def _handle_place(
        self,
        request: ModeRequest,
        snapshot: VisionStableSnapshot | None,
    ) -> ModeResponse:
        if snapshot is None:
            return self._error("NO_BOARD", "No stable board available")
        self._sync_place_slot_state(snapshot.board_state)
        if (
            request.color is None
            or request.piece_index is None
            or request.row is None
            or request.col is None
        ):
            return self._error("BAD_CMD", "PLACE requires color,piece_no,row,col")
        if not 0 <= request.piece_index < 7:
            return self._error("NO_SLOT", f"Piece index out of range: {request.piece_index}")
        if request.piece_index in self._place_used_slots[request.color]:
            return self._error(
                "NO_SLOT",
                f"Piece slot already used: {request.piece_index + 1}",
            )
        if not _is_in_bounds(request.row, request.col):
            return self._error("BAD_POS", f"Out of bounds: ({request.row},{request.col})")
        target = (request.row, request.col)
        if target in self._place_used_targets:
            return self._error("BAD_POS", f"Target already reserved: {target}")
        if snapshot.board_state[request.row][request.col] != "empty":
            return self._error("BAD_POS", f"Target occupied: ({request.row},{request.col})")
        try:
            tilt_theta = None
            tilt_dead_zone = 0.0
            if self.control_config.tilt_compensation.enabled:
                tilt_theta = snapshot.theta_deg
                tilt_dead_zone = self.control_config.tilt_compensation.dead_zone_deg
            pulses4 = build_move_pulses(
                self.control_config.pulse_config,
                request.color,
                request.row,
                request.col,
                snapshot.board_state,
                piece_index=request.piece_index,
                theta_deg=tilt_theta,
                dead_zone_deg=tilt_dead_zone,
                max_tilt_deg=self.control_config.tilt_compensation.max_tilt_deg,
            )
        except PulsePlanningError as exc:
            return self._error(exc.code, exc.message)
        self._place_used_slots[request.color].add(request.piece_index)
        self._place_used_targets.add(target)
        return ModeResponse(kind="pulses", pulses4=pulses4)

    def _sync_place_slot_state(self, board_state: list[list[str]]) -> None:
        board_is_nonempty = any(
            cell != "empty"
            for row in board_state
            for cell in row
        )
        if self._place_board_was_nonempty and not board_is_nonempty:
            self._reset_place_state()
        self._place_board_was_nonempty = board_is_nonempty

    def _reset_place_state(self) -> None:
        self._place_used_slots = {"BLACK": set(), "WHITE": set()}
        self._place_used_targets = set()

    def _handle_ready(self, snapshot: VisionStableSnapshot | None) -> ModeResponse:
        if self.battle_state.mode != "battle_active" or self.battle_state.robot_color is None:
            return self._error("BAD_CMD", "Battle mode has not been started")
        if snapshot is None:
            return self._error("NO_BOARD", "No stable board available")

        legality_error = _check_board_legality(snapshot.board_state)
        if legality_error is not None:
            return legality_error

        expected_board = self.battle_state.expected_board_state
        if expected_board is not None and expected_board != snapshot.board_state:
            human_color = "WHITE" if self.battle_state.robot_color == "BLACK" else "BLACK"
            correction = self._build_piece_correction(
                expected_board,
                snapshot.board_state,
                snapshot.theta_deg,
            )
            if correction is not None:
                return correction
            if not _is_single_human_placement(
                expected_board,
                snapshot.board_state,
                human_color,
            ):
                return self._error(
                    "ILLEGAL_BOARD",
                    "Unexpected board change",
                )

        game_over_message = _check_game_over(snapshot.board_state)
        if game_over_message is not None:
            self.battle_state.mode = "game_over"
            return ModeResponse(kind="busy", message=game_over_message)

        current_turn = _current_turn(snapshot.board_state)
        if current_turn != self.battle_state.robot_color:
            return self._error(
                "AI_TURN_MISMATCH",
                f"Current turn is {current_turn}, robot is {self.battle_state.robot_color}",
            )

        ai_grid = _board_state_to_ai_grid(snapshot.board_state, self.battle_state.robot_color)
        try:
            move = get_best_move(
                ai_grid,
                ai_player=Board.BLACK,
                difficulty=self.control_config.ai.difficulty,
                time_limit_ms=self.control_config.ai.time_limit_ms,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            return self._error("AI_FAIL", f"AI exception: {exc}")

        if move is None:
            return self._error("AI_FAIL", "AI did not return a move")

        row, col = int(move[0]), int(move[1])
        if not _is_in_bounds(row, col) or snapshot.board_state[row][col] != "empty":
            return self._error("AI_FAIL", f"AI returned illegal move: ({row},{col})")

        try:
            pulses4 = build_move_pulses(
                self.control_config.pulse_config,
                self.battle_state.robot_color,
                row,
                col,
                snapshot.board_state,
            )
        except PulsePlanningError as exc:
            return self._error(exc.code, exc.message)

        expected_after_move = _copy_board_state(snapshot.board_state)
        expected_after_move[row][col] = _robot_color_to_cell_state(
            self.battle_state.robot_color,
        )
        self.battle_state.expected_board_state = expected_after_move

        return ModeResponse(kind="move", row=row, col=col, pulses4=pulses4)

    def _build_piece_correction(
        self,
        expected_board: list[list[str]],
        current_board: list[list[str]],
        theta_deg: float | None,
    ) -> ModeResponse | None:
        relocation = _find_relocated_piece(expected_board, current_board)
        if relocation is None:
            return None

        source_row, source_col, target_row, target_col = relocation
        tilt_theta = None
        tilt_dead_zone = 0.0
        if self.control_config.tilt_compensation.enabled:
            tilt_theta = theta_deg
            tilt_dead_zone = self.control_config.tilt_compensation.dead_zone_deg

        try:
            pick_p1, pick_p2 = cell_to_pulses_with_tilt(
                self.control_config.pulse_config,
                target_row,
                target_col,
                tilt_theta,
                dead_zone_deg=tilt_dead_zone,
                max_tilt_deg=self.control_config.tilt_compensation.max_tilt_deg,
            )
            place_p1, place_p2 = cell_to_pulses_with_tilt(
                self.control_config.pulse_config,
                source_row,
                source_col,
                tilt_theta,
                dead_zone_deg=tilt_dead_zone,
                max_tilt_deg=self.control_config.tilt_compensation.max_tilt_deg,
            )
        except PulsePlanningError as exc:
            return self._error(exc.code, exc.message)

        return ModeResponse(
            kind="pulses",
            pulses4=(pick_p1, pick_p2, place_p1, place_p2),
        )

    @staticmethod
    def _error(code: str, message: str) -> ModeResponse:
        return ModeResponse(kind="error", error_code=code, message=message)


def main() -> None:
    args = parse_args()
    ensure_default_control_config(args.control_config)
    control_config = load_control_config(args.control_config)
    if args.port:
        control_config = ControlConfig(
            serial=control_config.serial.__class__(
                port=args.port,
                baudrate=args.baudrate or control_config.serial.baudrate,
                timeout_ms=control_config.serial.timeout_ms,
            ),
            ai=control_config.ai,
            tilt_compensation=control_config.tilt_compensation,
            pulse_config=control_config.pulse_config,
        )
    elif args.baudrate is not None:
        control_config = ControlConfig(
            serial=control_config.serial.__class__(
                port=control_config.serial.port,
                baudrate=args.baudrate,
                timeout_ms=control_config.serial.timeout_ms,
            ),
            ai=control_config.ai,
            tilt_compensation=control_config.tilt_compensation,
            pulse_config=control_config.pulse_config,
        )

    camera_config, board_config, piece_config = build_runtime_configs(args.vision_config)
    runtime = VisionRuntime(camera_config, board_config, piece_config)
    controller = VisionController(control_config)
    transport = SerialTextTransport(
        control_config.serial.port,
        control_config.serial.baudrate,
        control_config.serial.timeout_ms,
    )

    runtime.open()
    transport.open()
    try:
        while True:
            frame = runtime.step()
            snapshot = runtime.latest_stable_snapshot()

            incoming = transport.read_line()
            if incoming:
                try:
                    request = parse_request_line(incoming)
                    response = controller.handle_request(request, snapshot)
                except ProtocolError as exc:
                    response = ModeResponse(kind="error", error_code=exc.code, message=exc.message)
                line = format_response_line(response)
                transport.write_line(line)

            if not args.headless:
                key = show_runtime_windows(frame)
                if key == ord("q"):
                    break
                if key == ord("s"):
                    runtime.save_debug_snapshot(args.debug_dir, frame)
                    print("Saved current debug frames and result metadata.")
            else:
                time.sleep(0.005)
    finally:
        transport.close()
        runtime.release()
        if not args.headless:
            cv2.destroyAllWindows()


def _copy_board_state(board_state: list[list[str]]) -> list[list[str]]:
    return [list(row) for row in board_state]


def _robot_color_to_cell_state(robot_color: RobotColor) -> str:
    return "black" if robot_color == "BLACK" else "white"


def _find_relocated_piece(
    expected_board: list[list[str]],
    current_board: list[list[str]],
) -> tuple[int, int, int, int] | None:
    removed: list[tuple[int, int, str]] = []
    added: list[tuple[int, int, str]] = []

    for row in range(7):
        for col in range(7):
            expected = expected_board[row][col]
            current = current_board[row][col]
            if expected == current:
                continue
            if expected != "empty" and current == "empty":
                removed.append((row, col, expected))
            elif expected == "empty" and current != "empty":
                added.append((row, col, current))
            else:
                return None

    if len(removed) != 1 or len(added) != 1:
        return None
    return removed[0][0], removed[0][1], added[0][0], added[0][1]


def _is_single_human_placement(
    expected_board: list[list[str]],
    current_board: list[list[str]],
    human_color: RobotColor,
) -> bool:
    human_state = _robot_color_to_cell_state(human_color)
    changes = []
    for row in range(7):
        for col in range(7):
            expected = expected_board[row][col]
            current = current_board[row][col]
            if expected != current:
                changes.append((expected, current))
    return len(changes) == 1 and changes[0] == ("empty", human_state)


def _is_in_bounds(row: int, col: int) -> bool:
    return 0 <= row < 7 and 0 <= col < 7


def _check_board_legality(board_state: list[list[str]]) -> ModeResponse | None:
    black_count = sum(cell == "black" for row in board_state for cell in row)
    white_count = sum(cell == "white" for row in board_state for cell in row)
    if black_count < white_count or black_count - white_count > 1:
        return ModeResponse(
            kind="error",
            error_code="ILLEGAL_BOARD",
            message=f"Illegal piece counts: black={black_count}, white={white_count}",
        )
    if black_count > 7 or white_count > 7:
        return ModeResponse(
            kind="error",
            error_code="ILLEGAL_BOARD",
            message=f"Piece count exceeds slot capacity: black={black_count}, white={white_count}",
        )
    return None


def _current_turn(board_state: list[list[str]]) -> RobotColor:
    black_count = sum(cell == "black" for row in board_state for cell in row)
    white_count = sum(cell == "white" for row in board_state for cell in row)
    return "BLACK" if black_count == white_count else "WHITE"


def _board_state_to_ai_grid(board_state: list[list[str]], robot_color: RobotColor) -> list[list[int]]:
    ai_grid: list[list[int]] = []
    for row in board_state:
        ai_row: list[int] = []
        for cell in row:
            if cell == "empty":
                ai_row.append(Board.EMPTY)
            elif robot_color == "BLACK":
                ai_row.append(Board.BLACK if cell == "black" else Board.WHITE)
            else:
                ai_row.append(Board.BLACK if cell == "white" else Board.WHITE)
        ai_grid.append(ai_row)
    return ai_grid


def _check_game_over(board_state: list[list[str]]) -> str | None:
    board = Board()
    absolute_grid = []
    for row in board_state:
        absolute_row = []
        for cell in row:
            if cell == "empty":
                absolute_row.append(Board.EMPTY)
            elif cell == "black":
                absolute_row.append(Board.BLACK)
            else:
                absolute_row.append(Board.WHITE)
        absolute_grid.append(absolute_row)
    board.from_grid(absolute_grid)
    winner = board.check_winner_global()
    if winner == Board.BLACK:
        return "game_over_black_win"
    if winner == Board.WHITE:
        return "game_over_white_win"
    if board.is_full():
        return "game_over_draw"
    return None


if __name__ == "__main__":
    main()
