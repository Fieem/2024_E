from __future__ import annotations

import argparse
import json
import time
from collections import Counter, deque
from dataclasses import replace
from pathlib import Path

import cv2

from board_detector import BoardDetector, BoardDetectorConfig
from camera import CameraConfig, UsbCamera
from grid_model import GridModel, GridModelConfig
from piece_detector import PieceDetector, PieceDetectorConfig
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
            smoothed_cells.append(
                replace(
                    cell,
                    state=smoothed_state,
                    confidence=round(smoothed_confidence, 3),
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
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--board-size", type=int, default=700)
    parser.add_argument("--history-size", type=int, default=5)
    parser.add_argument("--consensus-frames", type=int, default=3)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--debug-dir", default="debug")
    parser.add_argument("--exposure", type=float, default=None)
    parser.add_argument("--white-balance", type=float, default=None)
    return parser.parse_args()


def to_board_state(cell_results: list[CellResult], rows: int, cols: int) -> list[list[str]]:
    board_state = [["empty" for _ in range(cols)] for _ in range(rows)]
    for cell in cell_results:
        board_state[cell.row][cell.col] = cell.state
    return board_state


def save_debug_frames(debug_dir: Path, raw_frame, board_view, warped_view) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    cv2.imwrite(str(debug_dir / f"{timestamp}_raw.png"), raw_frame)
    if board_view is not None:
        cv2.imwrite(str(debug_dir / f"{timestamp}_board.png"), board_view)
    if warped_view is not None:
        cv2.imwrite(str(debug_dir / f"{timestamp}_warped.png"), warped_view)


def main() -> None:
    args = parse_args()

    camera = UsbCamera(
        CameraConfig(
            device_index=args.camera_index,
            frame_width=args.width,
            frame_height=args.height,
            fps=args.fps,
            auto_exposure=False,
            exposure=args.exposure,
            auto_white_balance=False,
            white_balance=args.white_balance,
        )
    )
    board_detector = BoardDetector(BoardDetectorConfig(board_size=args.board_size))
    grid_model = GridModel(GridModelConfig(board_size=args.board_size))
    piece_detector = PieceDetector(PieceDetectorConfig())
    smoother = BoardStateSmoother(args.history_size, args.consensus_frames)

    board_rows, board_cols = grid_model.board_shape()
    last_signature: tuple[tuple[str, ...], ...] | None = None

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
                board_state = to_board_state(smoothed_cells, board_rows, board_cols)
                warped_view = grid_model.draw_overlay(detection.warped_image, smoothed_cells)

                vision_result = VisionResult(
                    board_found=True,
                    board_image_size=(args.board_size, args.board_size),
                    cells=smoothed_cells,
                    board_state=board_state,
                    timestamp=time.time(),
                    stable=stable,
                    stable_frames=stable_frames,
                )

                signature = tuple(tuple(row) for row in board_state)
                if stable and signature != last_signature:
                    print(json.dumps(vision_result.to_dict(), ensure_ascii=False))
                    last_signature = signature
            else:
                smoother.reset()
                vision_result = VisionResult(
                    board_found=False,
                    board_image_size=(args.board_size, args.board_size),
                    cells=[],
                    board_state=grid_model.empty_state_matrix(),
                    timestamp=time.time(),
                    stable=False,
                    stable_frames=0,
                )

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
                    )
                    print("Saved current debug frames.")
            else:
                time.sleep(0.01)
    finally:
        camera.release()
        if not args.headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
