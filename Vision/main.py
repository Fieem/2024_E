from __future__ import annotations

import argparse
import json
import time
from collections import Counter, deque
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from board_detector import BoardDetector, BoardDetectorConfig
from camera import CameraConfig, UsbCamera
from grid_model import GridModel, GridModelConfig
from piece_detector import PieceDetector, PieceDetectorConfig
from vision_config import DEFAULT_CONFIG_PATH, load_config_file, merge_config_values
from vision_types import CellResult, VisionResult


class BoardStateSmoother:
    def __init__(self, history_size: int, consensus_frames: int) -> None:
        self.history_size = max(1, history_size)
        self.consensus_frames = max(1, consensus_frames)
        self.history: deque[tuple[str, ...]] = deque(maxlen=self.history_size)

    def update(self, cell_results: list[CellResult]) -> tuple[list[CellResult], bool, int]:
        states = tuple(cell.state for cell in cell_results)
        self.history.append(states)

        smoothed_cells: list[CellResult] = []
        min_votes = len(self.history)
        stable = True

        for index, cell in enumerate(cell_results):
            votes = Counter(frame[index] for frame in self.history)
            smoothed_state, vote_count = votes.most_common(1)[0]
            min_votes = min(min_votes, vote_count)
            if vote_count < self.consensus_frames:
                stable = False

            smoothed_confidence = max(
                cell.confidence,
                vote_count / len(self.history),
            )
            diagnostics = dict(cell.diagnostics or {})
            diagnostics["raw_state"] = cell.state
            diagnostics["smoothed_state"] = smoothed_state
            diagnostics["vote_count"] = vote_count
            diagnostics["history_size"] = len(self.history)
            smoothed_cells.append(
                replace(
                    cell,
                    state=smoothed_state,
                    confidence=round(smoothed_confidence, 3),
                    diagnostics=diagnostics,
                )
            )
        return smoothed_cells, stable, min_votes

    def reset(self) -> None:
        self.history.clear()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real-time 7x7 board vision pipeline for a red board and black grid lines.",
    )
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--pixel-format", default="MJPG")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--board-size", type=int, default=700)
    parser.add_argument("--theta-zero-ref-deg", type=float, default=0.0)
    parser.add_argument("--history-size", type=int, default=5)
    parser.add_argument("--consensus-frames", type=int, default=3)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--debug-dir", default="debug")
    parser.add_argument("--exposure", type=float, default=180.0)
    parser.add_argument("--white-balance", type=float, default=None)
    parser.add_argument("--sample-radius-ratio", type=float, default=0.42)
    parser.add_argument("--center-sample-radius-ratio", type=float, default=0.24)
    parser.add_argument("--min-piece-area-ratio", type=float, default=0.10)
    parser.add_argument("--white-min-piece-area-ratio", type=float, default=0.05)
    parser.add_argument("--white-relaxed-piece-area-ratio", type=float, default=0.03)
    parser.add_argument("--white-norm-min-piece-area-ratio", type=float, default=0.025)
    parser.add_argument("--white-center-ratio-min", type=float, default=0.12)
    parser.add_argument("--black-value-max", type=int, default=70)
    parser.add_argument("--black-saturation-min", type=int, default=0)
    parser.add_argument("--black-saturation-max", type=int, default=255)
    parser.add_argument("--white-value-min", type=int, default=170)
    parser.add_argument("--white-saturation-max", type=int, default=80)
    parser.add_argument("--white-norm-value-min", type=int, default=150)
    parser.add_argument("--white-norm-saturation-max", type=int, default=140)
    parser.add_argument("--empty-red-ratio-threshold", type=float, default=0.45)
    return parser.parse_args()


def to_board_state(cell_results: list[CellResult], rows: int, cols: int) -> list[list[str]]:
    board_state = [["empty" for _ in range(cols)] for _ in range(rows)]
    for cell in cell_results:
        board_state[cell.row][cell.col] = cell.state
    return board_state


def attach_raw_centers(
    cell_results: list[CellResult],
    homography,
) -> list[CellResult]:
    if homography is None or not cell_results:
        return cell_results

    inverse_homography = np.linalg.inv(homography)
    warped_points = np.array(
        [[cell.center_px] for cell in cell_results],
        dtype=np.float32,
    )
    raw_points = cv2.perspectiveTransform(warped_points, inverse_homography).reshape(-1, 2)
    updated_cells: list[CellResult] = []
    for cell, raw_point in zip(cell_results, raw_points):
        updated_cells.append(
            replace(
                cell,
                center_px_raw=(int(round(float(raw_point[0]))), int(round(float(raw_point[1])))),
            )
        )
    return updated_cells


def build_board_state_event(vision_result: VisionResult) -> dict[str, object]:
    payload = vision_result.to_dict()
    payload["event_type"] = "board_state"
    return payload


def build_move_event(
    previous_board_state: list[list[str]] | None,
    vision_result: VisionResult,
) -> dict[str, object] | None:
    if previous_board_state is None:
        return None

    changes: list[tuple[int, int, str, str]] = []
    for row_index, row in enumerate(vision_result.board_state):
        for col_index, state in enumerate(row):
            previous_state = previous_board_state[row_index][col_index]
            if previous_state != state:
                changes.append((row_index, col_index, previous_state, state))

    if len(changes) != 1:
        return None

    row, col, previous_state, current_state = changes[0]
    if previous_state != "empty" or current_state not in {"black", "white"}:
        return None

    cell = next(
        (item for item in vision_result.cells if item.row == row and item.col == col),
        None,
    )
    return {
        "event_type": "move",
        "row": row,
        "col": col,
        "piece": current_state,
        "board_state": vision_result.board_state,
        "timestamp": vision_result.timestamp,
        "confidence": cell.confidence if cell is not None else 0.0,
        "theta_deg": vision_result.theta_deg,
        "center_px_warped": cell.center_px if cell is not None else None,
        "center_px_raw": cell.center_px_raw if cell is not None else None,
    }


def summarize_cells(cell_results: list[CellResult]) -> dict[str, int]:
    counts = {"empty": 0, "black": 0, "white": 0}
    for cell in cell_results:
        counts[cell.state] = counts.get(cell.state, 0) + 1
    return counts


def low_confidence_cells(
    cell_results: list[CellResult],
    threshold: float = 0.7,
) -> list[str]:
    labels: list[str] = []
    for cell in cell_results:
        if cell.confidence < threshold:
            labels.append(f"{cell.row},{cell.col}:{cell.state[0].upper()}:{cell.confidence:.2f}")
    return labels


def annotate_warped_view(
    warped_view,
    vision_result: VisionResult,
) -> np.ndarray | None:
    if warped_view is None:
        return warped_view

    counts = summarize_cells(vision_result.cells)
    status_lines = [
        f"Stable: {'YES' if vision_result.stable else 'NO'}  Votes: {vision_result.stable_frames}",
        f"Empty: {counts['empty']}  Black: {counts['black']}  White: {counts['white']}",
    ]
    if vision_result.theta_deg is not None:
        status_lines.append(f"Theta: {vision_result.theta_deg:.2f} deg")
    uncertain = low_confidence_cells(vision_result.cells)
    if uncertain:
        status_lines.append("Low conf: " + ", ".join(uncertain[:5]))

    panel_height = 14 + len(status_lines) * 22
    panel = np.full(
        (panel_height, vision_result.board_image_size[0], 3),
        20,
        dtype=np.uint8,
    )
    for index, line in enumerate(status_lines):
        cv2.putText(
            panel,
            line,
            (10, 18 + index * 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return np.vstack((warped_view, panel))


def save_debug_frames(
    debug_dir: Path,
    raw_frame,
    board_view,
    warped_view,
    vision_result: VisionResult | None,
    camera_config: CameraConfig,
    detector_config: PieceDetectorConfig,
) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    cv2.imwrite(str(debug_dir / f"{timestamp}_raw.png"), raw_frame)
    if board_view is not None:
        cv2.imwrite(str(debug_dir / f"{timestamp}_board.png"), board_view)
    if warped_view is not None:
        cv2.imwrite(str(debug_dir / f"{timestamp}_warped.png"), warped_view)

    payload = {
        "timestamp": timestamp,
        "camera": {
            "device_index": camera_config.device_index,
            "frame_width": camera_config.frame_width,
            "frame_height": camera_config.frame_height,
            "fps": camera_config.fps,
            "pixel_format": camera_config.pixel_format,
            "exposure": camera_config.exposure,
            "auto_exposure": camera_config.auto_exposure,
            "white_balance": camera_config.white_balance,
            "auto_white_balance": camera_config.auto_white_balance,
        },
        "piece_detector": {
            "sample_radius_ratio": detector_config.sample_radius_ratio,
            "center_sample_radius_ratio": detector_config.center_sample_radius_ratio,
            "min_piece_area_ratio": detector_config.min_piece_area_ratio,
            "white_min_piece_area_ratio": detector_config.white_min_piece_area_ratio,
            "white_relaxed_piece_area_ratio": detector_config.white_relaxed_piece_area_ratio,
            "white_norm_min_piece_area_ratio": detector_config.white_norm_min_piece_area_ratio,
            "white_center_ratio_min": detector_config.white_center_ratio_min,
            "black_value_max": detector_config.black_value_max,
            "black_saturation_min": detector_config.black_saturation_min,
            "black_saturation_max": detector_config.black_saturation_max,
            "white_value_min": detector_config.white_value_min,
            "white_saturation_max": detector_config.white_saturation_max,
            "white_norm_value_min": detector_config.white_norm_value_min,
            "white_norm_saturation_max": detector_config.white_norm_saturation_max,
            "empty_red_ratio_threshold": detector_config.empty_red_ratio_threshold,
        },
        "vision_result": vision_result.to_dict() if vision_result is not None else None,
    }
    (debug_dir / f"{timestamp}_result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()

    config_overrides = load_config_file(args.config)
    current_camera_values = merge_config_values(
        {
            "device_index": args.camera_index,
            "frame_width": args.width,
            "frame_height": args.height,
            "fps": args.fps,
            "pixel_format": args.pixel_format,
            "auto_exposure": False,
            "exposure": args.exposure,
            "auto_white_balance": False,
            "white_balance": args.white_balance,
        },
        config_overrides.get("camera", {}),
    )
    current_board_values = merge_config_values(
        {
            "board_size": args.board_size,
            "min_area_ratio": 0.08,
            "smoothing_alpha": 0.35,
            "angle_smoothing_alpha": 0.4,
            "use_lighting_normalization": True,
            "clahe_clip_limit": 2.5,
            "clahe_tile_grid_size": 8,
            "theta_zero_ref_deg": args.theta_zero_ref_deg,
            "red_lower_1": (0, 70, 50),
            "red_upper_1": (12, 255, 255),
            "red_lower_2": (165, 70, 50),
            "red_upper_2": (180, 255, 255),
            "morph_kernel_size": 7,
        },
        config_overrides.get("board_detector", {}),
    )
    current_piece_values = merge_config_values(
        {
            "sample_radius_ratio": args.sample_radius_ratio,
            "center_sample_radius_ratio": args.center_sample_radius_ratio,
            "min_piece_area_ratio": args.min_piece_area_ratio,
            "white_min_piece_area_ratio": args.white_min_piece_area_ratio,
            "white_relaxed_piece_area_ratio": args.white_relaxed_piece_area_ratio,
            "white_norm_min_piece_area_ratio": args.white_norm_min_piece_area_ratio,
            "white_center_ratio_min": args.white_center_ratio_min,
            "black_value_max": args.black_value_max,
            "black_saturation_min": args.black_saturation_min,
            "black_saturation_max": args.black_saturation_max,
            "white_value_min": args.white_value_min,
            "white_saturation_max": args.white_saturation_max,
            "white_norm_value_min": args.white_norm_value_min,
            "white_norm_saturation_max": args.white_norm_saturation_max,
            "empty_red_ratio_threshold": args.empty_red_ratio_threshold,
        },
        config_overrides.get("piece_detector", {}),
    )
    current_camera_config = CameraConfig(**current_camera_values)
    current_board_config = BoardDetectorConfig(**current_board_values)
    current_piece_config = PieceDetectorConfig(**current_piece_values)
    camera = UsbCamera(current_camera_config)
    board_detector = BoardDetector(current_board_config)
    grid_model = GridModel(GridModelConfig(board_size=current_board_config.board_size))
    piece_detector = PieceDetector(current_piece_config)
    smoother = BoardStateSmoother(args.history_size, args.consensus_frames)

    board_rows, board_cols = grid_model.board_shape()
    last_signature: tuple[tuple[str, ...], ...] | None = None
    latest_result: VisionResult | None = None
    last_board_state: list[list[str]] | None = None

    camera.open()
    try:
        while True:
            raw_frame = camera.read()
            detection = board_detector.detect(raw_frame)

            board_view = detection.annotated_frame if detection.annotated_frame is not None else raw_frame
            warped_view = None

            if detection.found and detection.warped_image is not None:
                cell_results, _ = piece_detector.detect(
                    detection.warped_image,
                    grid_model.cells,
                    grid_model.board_shape(),
                )
                smoothed_cells, stable, stable_frames = smoother.update(cell_results)
                smoothed_cells = attach_raw_centers(smoothed_cells, detection.homography)
                board_state = to_board_state(smoothed_cells, board_rows, board_cols)
                warped_view = grid_model.draw_overlay(detection.warped_image, smoothed_cells)

                vision_result = VisionResult(
                    board_found=True,
                    board_image_size=(
                        current_board_config.board_size,
                        current_board_config.board_size,
                    ),
                    cells=smoothed_cells,
                    board_state=board_state,
                    timestamp=time.time(),
                    stable=stable,
                    stable_frames=stable_frames,
                    theta_deg=detection.angle_deg,
                )
                latest_result = vision_result
                warped_view = annotate_warped_view(warped_view, vision_result)

                signature = tuple(tuple(row) for row in board_state)
                if stable and signature != last_signature:
                    print(json.dumps(build_board_state_event(vision_result), ensure_ascii=False))
                    move_event = build_move_event(last_board_state, vision_result)
                    if move_event is not None:
                        print(json.dumps(move_event, ensure_ascii=False))
                    last_signature = signature
                    last_board_state = [list(row) for row in board_state]
            else:
                smoother.reset()
                last_signature = None
                last_board_state = None
                vision_result = VisionResult(
                    board_found=False,
                    board_image_size=(
                        current_board_config.board_size,
                        current_board_config.board_size,
                    ),
                    cells=[],
                    board_state=grid_model.empty_state_matrix(),
                    timestamp=time.time(),
                    stable=False,
                    stable_frames=0,
                    theta_deg=None,
                )
                latest_result = vision_result

            if not args.headless:
                cv2.imshow("raw", raw_frame)
                cv2.imshow("board_detection", board_view)
                if detection.mask is not None:
                    cv2.imshow("red_mask", detection.mask)
                if warped_view is not None:
                    cv2.imshow("warped_board", warped_view)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("s"):
                    save_debug_frames(
                        Path(args.debug_dir),
                        raw_frame,
                        board_view,
                        warped_view,
                        latest_result,
                        current_camera_config,
                        current_piece_config,
                    )
                    print("Saved current debug frames and result metadata.")
            else:
                time.sleep(0.01)
    finally:
        camera.release()
        if not args.headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
