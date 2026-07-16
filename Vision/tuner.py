from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2

from board_detector import BoardDetector, BoardDetectorConfig
from camera import CameraConfig, UsbCamera
from grid_model import GridModel, GridModelConfig
from main import (
    BoardStateSmoother,
    attach_raw_centers,
    annotate_warped_view,
    build_board_state_event,
    build_move_event,
    save_debug_frames,
    to_board_state,
)
from piece_detector import PieceDetector, PieceDetectorConfig
from vision_config import (
    DEFAULT_CONFIG_PATH,
    load_config_file,
    merge_config_values,
    save_config_file,
)
from vision_types import VisionResult

CAMERA_WINDOW = "tuner_camera_board"
WHITE_WINDOW = "tuner_white_piece"
BLACK_WINDOW = "tuner_black_misc"


@dataclass
class TrackbarBinding:
    window: str
    name: str
    max_value: int
    getter: Callable[[], int]
    setter: Callable[[int], None]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive threshold tuner for the 7x7 board vision pipeline.",
    )
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--pixel-format", default="MJPG")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--board-size", type=int, default=700)
    parser.add_argument("--debug-dir", default="debug")
    parser.add_argument("--exposure", type=float, default=180.0)
    parser.add_argument("--white-balance", type=float, default=None)
    return parser.parse_args()


class VisionTuner:
    def __init__(
        self,
        camera: UsbCamera,
        camera_config: CameraConfig,
        board_detector: BoardDetector,
        board_config: BoardDetectorConfig,
        grid_model: GridModel,
        piece_detector: PieceDetector,
        piece_config: PieceDetectorConfig,
        config_path: str,
        debug_dir: str,
    ) -> None:
        self.camera = camera
        self.camera_config = camera_config
        self.board_detector = board_detector
        self.board_config = board_config
        self.grid_model = grid_model
        self.piece_detector = piece_detector
        self.piece_config = piece_config
        self.config_path = config_path
        self.debug_dir = debug_dir
        self.smoother = BoardStateSmoother(history_size=5, consensus_frames=3)
        self.latest_result: VisionResult | None = None
        self.last_signature: tuple[tuple[str, ...], ...] | None = None
        self.last_board_state: list[list[str]] | None = None
        self._bindings = self._build_bindings()

    def run(self) -> None:
        cv2.namedWindow(CAMERA_WINDOW, cv2.WINDOW_NORMAL)
        cv2.namedWindow(WHITE_WINDOW, cv2.WINDOW_NORMAL)
        cv2.namedWindow(BLACK_WINDOW, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(CAMERA_WINDOW, 640, 760)
        cv2.resizeWindow(WHITE_WINDOW, 640, 360)
        cv2.resizeWindow(BLACK_WINDOW, 640, 420)
        self._create_trackbars()

        print("Tuner ready.")
        print("Keys: q=quit, p=save current config, s=save debug snapshot")
        print("Windows: tuner_camera_board / tuner_white_piece / tuner_black_misc")

        self.camera.open()
        try:
            while True:
                self._sync_from_trackbars()
                raw_frame = self.camera.read()
                detection = self.board_detector.detect(raw_frame)
                board_view = detection.annotated_frame if detection.annotated_frame is not None else raw_frame
                warped_view = None

                if detection.found and detection.warped_image is not None:
                    cell_results, _ = self.piece_detector.detect(
                        detection.warped_image,
                        self.grid_model.cells,
                        self.grid_model.board_shape(),
                        red_board_image=detection.normalized_warped_image,
                    )
                    smoothed_cells, stable, stable_frames = self.smoother.update(cell_results)
                    smoothed_cells = attach_raw_centers(smoothed_cells, detection.homography)
                    board_state = to_board_state(
                        smoothed_cells,
                        self.grid_model.board_shape()[0],
                        self.grid_model.board_shape()[1],
                    )
                    warped_view = self.grid_model.draw_overlay(
                        detection.warped_image,
                        smoothed_cells,
                    )
                    self.latest_result = VisionResult(
                        board_found=True,
                        board_image_size=(
                            self.board_config.board_size,
                            self.board_config.board_size,
                        ),
                        cells=smoothed_cells,
                        board_state=board_state,
                        timestamp=time.time(),
                        stable=stable,
                        stable_frames=stable_frames,
                        theta_deg=detection.angle_deg,
                    )
                    warped_view = annotate_warped_view(warped_view, self.latest_result)

                    signature = tuple(tuple(row) for row in board_state)
                    if stable and signature != self.last_signature:
                        print(json.dumps(build_board_state_event(self.latest_result), ensure_ascii=False))
                        move_event = build_move_event(self.last_board_state, self.latest_result)
                        if move_event is not None:
                            print(json.dumps(move_event, ensure_ascii=False))
                        self.last_signature = signature
                        self.last_board_state = [list(row) for row in board_state]
                else:
                    self.smoother.reset()
                    self.last_signature = None
                    self.last_board_state = None
                    self.latest_result = VisionResult(
                        board_found=False,
                        board_image_size=(
                            self.board_config.board_size,
                            self.board_config.board_size,
                        ),
                        cells=[],
                        board_state=self.grid_model.empty_state_matrix(),
                        timestamp=time.time(),
                        stable=False,
                        stable_frames=0,
                        theta_deg=None,
                    )

                self._draw_status_panel(raw_frame)
                cv2.imshow("raw", raw_frame)
                cv2.imshow("board_detection", board_view)
                if detection.mask is not None:
                    cv2.imshow("red_mask", detection.mask)
                if warped_view is not None:
                    cv2.imshow("warped_board", warped_view)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("p"):
                    save_config_file(
                        self.config_path,
                        self.camera_config,
                        self.board_config,
                        self.piece_config,
                    )
                    print(f"Saved current config to {self.config_path}")
                if key == ord("s"):
                    save_debug_frames(
                        Path(self.debug_dir),
                        raw_frame,
                        board_view,
                        warped_view,
                        self.latest_result,
                        self.camera_config,
                        self.piece_config,
                    )
                    print("Saved debug frames and result metadata.")
        finally:
            self.camera.release()
            cv2.destroyAllWindows()

    def _draw_status_panel(self, image) -> None:
        lines = [
            "Tuner: q quit | p save config | s save snapshot",
            f"Config: {Path(self.config_path).name}",
            f"Exposure: {self.camera_config.exposure:.0f}  BlackV: {self.piece_config.black_value_max}  WhiteMin: {self.piece_config.white_value_min}",
            f"EmptyRed: {self.piece_config.empty_red_ratio_threshold:.2f}",
            f"BoardNorm: {'ON' if self.board_config.use_lighting_normalization else 'OFF'}  CLAHE: {self.board_config.clahe_clip_limit:.1f}/{self.board_config.clahe_tile_grid_size}",
        ]
        if self.latest_result is not None:
            lines.append(
                f"Stable: {'YES' if self.latest_result.stable else 'NO'}  Votes: {self.latest_result.stable_frames}"
            )
            if self.latest_result.theta_deg is not None:
                lines.append(f"Theta: {self.latest_result.theta_deg:.2f} deg")
        panel_height = 16 + len(lines) * 18
        cv2.rectangle(image, (0, 0), (image.shape[1], panel_height), (25, 25, 25), -1)
        for index, line in enumerate(lines):
            cv2.putText(
                image,
                line,
                (10, 16 + index * 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

    def _create_trackbars(self) -> None:
        for binding in self._bindings:
            cv2.createTrackbar(
                binding.name,
                binding.window,
                max(0, min(binding.max_value, binding.getter())),
                binding.max_value,
                self._noop,
            )

    def _sync_from_trackbars(self) -> None:
        for binding in self._bindings:
            binding.setter(cv2.getTrackbarPos(binding.name, binding.window))

    def _build_bindings(self) -> list[TrackbarBinding]:
        return [
            TrackbarBinding(
                CAMERA_WINDOW,
                "camera_exposure",
                300,
                lambda: int(self.camera_config.exposure or 0),
                self._set_exposure,
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "board_min_area_x1000",
                300,
                lambda: int(round(self.board_config.min_area_ratio * 1000)),
                lambda value: setattr(
                    self.board_config,
                    "min_area_ratio",
                    max(0.01, value / 1000.0),
                ),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "board_smooth_x100",
                100,
                lambda: int(round(self.board_config.smoothing_alpha * 100)),
                lambda value: setattr(
                    self.board_config,
                    "smoothing_alpha",
                    min(1.0, max(0.0, value / 100.0)),
                ),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "board_norm_enable",
                1,
                lambda: 1 if self.board_config.use_lighting_normalization else 0,
                lambda value: setattr(
                    self.board_config,
                    "use_lighting_normalization",
                    bool(value),
                ),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "clahe_clip_x10",
                80,
                lambda: int(round(self.board_config.clahe_clip_limit * 10)),
                lambda value: setattr(
                    self.board_config,
                    "clahe_clip_limit",
                    max(0.1, value / 10.0),
                ),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "clahe_tile",
                32,
                lambda: int(self.board_config.clahe_tile_grid_size),
                lambda value: setattr(
                    self.board_config,
                    "clahe_tile_grid_size",
                    max(1, value),
                ),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "theta_smooth_x100",
                100,
                lambda: int(round(self.board_config.angle_smoothing_alpha * 100)),
                lambda value: setattr(
                    self.board_config,
                    "angle_smoothing_alpha",
                    min(1.0, max(0.0, value / 100.0)),
                ),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "board_kernel",
                31,
                lambda: int(self.board_config.morph_kernel_size),
                self._set_board_kernel,
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red1_h_low",
                180,
                lambda: int(self.board_config.red_lower_1[0]),
                lambda value: self._set_tuple_value("red_lower_1", 0, value),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red1_s_low",
                255,
                lambda: int(self.board_config.red_lower_1[1]),
                lambda value: self._set_tuple_value("red_lower_1", 1, value),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red1_v_low",
                255,
                lambda: int(self.board_config.red_lower_1[2]),
                lambda value: self._set_tuple_value("red_lower_1", 2, value),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red1_h_high",
                180,
                lambda: int(self.board_config.red_upper_1[0]),
                lambda value: self._set_tuple_value("red_upper_1", 0, value),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red1_s_high",
                255,
                lambda: int(self.board_config.red_upper_1[1]),
                lambda value: self._set_tuple_value("red_upper_1", 1, value),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red1_v_high",
                255,
                lambda: int(self.board_config.red_upper_1[2]),
                lambda value: self._set_tuple_value("red_upper_1", 2, value),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red2_h_low",
                180,
                lambda: int(self.board_config.red_lower_2[0]),
                lambda value: self._set_tuple_value("red_lower_2", 0, value),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red2_s_low",
                255,
                lambda: int(self.board_config.red_lower_2[1]),
                lambda value: self._set_tuple_value("red_lower_2", 1, value),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red2_v_low",
                255,
                lambda: int(self.board_config.red_lower_2[2]),
                lambda value: self._set_tuple_value("red_lower_2", 2, value),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red2_h_high",
                180,
                lambda: int(self.board_config.red_upper_2[0]),
                lambda value: self._set_tuple_value("red_upper_2", 0, value),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red2_s_high",
                255,
                lambda: int(self.board_config.red_upper_2[1]),
                lambda value: self._set_tuple_value("red_upper_2", 1, value),
            ),
            TrackbarBinding(
                CAMERA_WINDOW,
                "red2_v_high",
                255,
                lambda: int(self.board_config.red_upper_2[2]),
                lambda value: self._set_tuple_value("red_upper_2", 2, value),
            ),
            TrackbarBinding(
                WHITE_WINDOW,
                "sample_radius_x100",
                100,
                lambda: int(round(self.piece_config.sample_radius_ratio * 100)),
                lambda value: setattr(
                    self.piece_config,
                    "sample_radius_ratio",
                    max(0.05, value / 100.0),
                ),
            ),
            TrackbarBinding(
                WHITE_WINDOW,
                "center_radius_x100",
                100,
                lambda: int(round(self.piece_config.center_sample_radius_ratio * 100)),
                lambda value: setattr(
                    self.piece_config,
                    "center_sample_radius_ratio",
                    max(0.05, value / 100.0),
                ),
            ),
            TrackbarBinding(
                BLACK_WINDOW,
                "piece_min_x100",
                100,
                lambda: int(round(self.piece_config.min_piece_area_ratio * 100)),
                lambda value: setattr(
                    self.piece_config,
                    "min_piece_area_ratio",
                    max(0.0, value / 100.0),
                ),
            ),
            TrackbarBinding(
                WHITE_WINDOW,
                "white_min_area_x100",
                100,
                lambda: int(round(self.piece_config.white_min_piece_area_ratio * 100)),
                lambda value: setattr(
                    self.piece_config,
                    "white_min_piece_area_ratio",
                    max(0.0, value / 100.0),
                ),
            ),
            TrackbarBinding(
                WHITE_WINDOW,
                "white_relaxed_x100",
                100,
                lambda: int(round(self.piece_config.white_relaxed_piece_area_ratio * 100)),
                lambda value: setattr(
                    self.piece_config,
                    "white_relaxed_piece_area_ratio",
                    max(0.0, value / 100.0),
                ),
            ),
            TrackbarBinding(
                WHITE_WINDOW,
                "white_norm_area_x100",
                100,
                lambda: int(round(self.piece_config.white_norm_min_piece_area_ratio * 100)),
                lambda value: setattr(
                    self.piece_config,
                    "white_norm_min_piece_area_ratio",
                    max(0.0, value / 100.0),
                ),
            ),
            TrackbarBinding(
                WHITE_WINDOW,
                "white_center_min_x100",
                100,
                lambda: int(round(self.piece_config.white_center_ratio_min * 100)),
                lambda value: setattr(
                    self.piece_config,
                    "white_center_ratio_min",
                    max(0.0, value / 100.0),
                ),
            ),
            TrackbarBinding(
                BLACK_WINDOW,
                "black_v_max",
                255,
                lambda: int(self.piece_config.black_value_max),
                lambda value: setattr(self.piece_config, "black_value_max", value),
            ),
            TrackbarBinding(
                BLACK_WINDOW,
                "black_s_min",
                255,
                lambda: int(self.piece_config.black_saturation_min),
                lambda value: setattr(self.piece_config, "black_saturation_min", value),
            ),
            TrackbarBinding(
                BLACK_WINDOW,
                "black_s_max",
                255,
                lambda: int(self.piece_config.black_saturation_max),
                lambda value: setattr(self.piece_config, "black_saturation_max", max(value, self.piece_config.black_saturation_min)),
            ),
            TrackbarBinding(
                WHITE_WINDOW,
                "white_value_min",
                255,
                lambda: int(self.piece_config.white_value_min),
                lambda value: setattr(self.piece_config, "white_value_min", value),
            ),
            TrackbarBinding(
                WHITE_WINDOW,
                "white_sat_max",
                255,
                lambda: int(self.piece_config.white_saturation_max),
                lambda value: setattr(self.piece_config, "white_saturation_max", value),
            ),
            TrackbarBinding(
                WHITE_WINDOW,
                "white_norm_value_min",
                255,
                lambda: int(self.piece_config.white_norm_value_min),
                lambda value: setattr(self.piece_config, "white_norm_value_min", value),
            ),
            TrackbarBinding(
                WHITE_WINDOW,
                "white_norm_sat_max",
                255,
                lambda: int(self.piece_config.white_norm_saturation_max),
                lambda value: setattr(self.piece_config, "white_norm_saturation_max", value),
            ),
            TrackbarBinding(
                BLACK_WINDOW,
                "empty_red_ratio_x100",
                100,
                lambda: int(round(self.piece_config.empty_red_ratio_threshold * 100)),
                lambda value: setattr(
                    self.piece_config,
                    "empty_red_ratio_threshold",
                    max(0.0, value / 100.0),
                ),
            ),
        ]

    def _set_exposure(self, value: int) -> None:
        self.camera.update_controls(exposure=float(value))

    def _set_board_kernel(self, value: int) -> None:
        kernel = max(1, value)
        if kernel % 2 == 0:
            kernel += 1
        self.board_config.morph_kernel_size = kernel

    def _set_tuple_value(self, field_name: str, index: int, value: int) -> None:
        current = list(getattr(self.board_config, field_name))
        current[index] = value
        setattr(self.board_config, field_name, tuple(current))

    @staticmethod
    def _noop(_: int) -> None:
        return


def build_configs(args: argparse.Namespace) -> tuple[CameraConfig, BoardDetectorConfig, PieceDetectorConfig]:
    config_overrides = load_config_file(args.config)
    camera_values = merge_config_values(
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
    board_values = merge_config_values(
        {
            "board_size": args.board_size,
            "min_area_ratio": 0.08,
            "smoothing_alpha": 0.35,
            "angle_smoothing_alpha": 0.4,
            "use_lighting_normalization": True,
            "clahe_clip_limit": 2.5,
            "clahe_tile_grid_size": 8,
            "theta_zero_ref_deg": 0.0,
            "red_lower_1": (0, 70, 50),
            "red_upper_1": (12, 255, 255),
            "red_lower_2": (165, 70, 50),
            "red_upper_2": (180, 255, 255),
            "morph_kernel_size": 7,
        },
        config_overrides.get("board_detector", {}),
    )
    piece_values = merge_config_values(
        {
            "sample_radius_ratio": 0.42,
            "center_sample_radius_ratio": 0.24,
            "min_piece_area_ratio": 0.10,
            "white_min_piece_area_ratio": 0.05,
            "white_relaxed_piece_area_ratio": 0.03,
            "white_norm_min_piece_area_ratio": 0.025,
            "white_center_ratio_min": 0.12,
            "black_value_max": 70,
            "black_saturation_min": 0,
            "black_saturation_max": 255,
            "white_value_min": 155,
            "white_saturation_max": 80,
            "white_norm_value_min": 135,
            "white_norm_saturation_max": 140,
            "empty_red_ratio_threshold": 0.45,
        },
        config_overrides.get("piece_detector", {}),
    )
    return (
        CameraConfig(**camera_values),
        BoardDetectorConfig(**board_values),
        PieceDetectorConfig(**piece_values),
    )


def main() -> None:
    args = parse_args()
    camera_config, board_config, piece_config = build_configs(args)
    camera = UsbCamera(camera_config)
    board_detector = BoardDetector(board_config)
    grid_model = GridModel(GridModelConfig(board_size=board_config.board_size))
    piece_detector = PieceDetector(piece_config, board_config)
    tuner = VisionTuner(
        camera,
        camera_config,
        board_detector,
        board_config,
        grid_model,
        piece_detector,
        piece_config,
        args.config,
        args.debug_dir,
    )
    tuner.run()


if __name__ == "__main__":
    main()
