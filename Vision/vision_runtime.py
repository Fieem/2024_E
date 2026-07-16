from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import cv2

from board_detector import BoardDetector, BoardDetectorConfig
from camera import CameraConfig, UsbCamera
from grid_model import GridModel, GridModelConfig
from main import (
    BoardStateSmoother,
    annotate_warped_view,
    attach_raw_centers,
    save_debug_frames,
    to_board_state,
)
from piece_detector import PieceDetector, PieceDetectorConfig
from vision_config import load_config_file, merge_config_values
from vision_types import VisionResult, VisionStableSnapshot


@dataclass(frozen=True)
class RuntimeFrame:
    raw_frame: object
    board_view: object
    warped_view: object | None
    red_mask: object | None
    vision_result: VisionResult


def build_runtime_configs(
    config_path: str | Path,
    *,
    camera_index: int = 0,
    width: int = 1600,
    height: int = 1200,
    fps: int = 60,
    pixel_format: str = "MJPG",
    board_size: int = 700,
    theta_zero_ref_deg: float = 0.0,
    exposure: float = 180.0,
    white_balance: float | None = None,
) -> tuple[CameraConfig, BoardDetectorConfig, PieceDetectorConfig]:
    config_overrides = load_config_file(config_path)
    camera_values = merge_config_values(
        {
            "device_index": camera_index,
            "frame_width": width,
            "frame_height": height,
            "fps": fps,
            "pixel_format": pixel_format,
            "auto_exposure": False,
            "exposure": exposure,
            "auto_white_balance": False,
            "white_balance": white_balance,
        },
        config_overrides.get("camera", {}),
    )
    board_values = merge_config_values(
        {
            "board_size": board_size,
            "min_area_ratio": 0.08,
            "smoothing_alpha": 0.35,
            "angle_smoothing_alpha": 0.4,
            "use_lighting_normalization": True,
            "clahe_clip_limit": 2.5,
            "clahe_tile_grid_size": 8,
            "theta_zero_ref_deg": theta_zero_ref_deg,
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


class VisionRuntime:
    def __init__(
        self,
        camera_config: CameraConfig,
        board_config: BoardDetectorConfig,
        piece_config: PieceDetectorConfig,
        *,
        history_size: int = 5,
        consensus_frames: int = 3,
    ) -> None:
        self.camera_config = camera_config
        self.board_config = board_config
        self.piece_config = piece_config
        self.camera = UsbCamera(camera_config)
        self.board_detector = BoardDetector(board_config)
        self.grid_model = GridModel(GridModelConfig(board_size=board_config.board_size))
        self.piece_detector = PieceDetector(piece_config, board_config)
        self.smoother = BoardStateSmoother(history_size, consensus_frames)
        self.board_rows, self.board_cols = self.grid_model.board_shape()
        self.latest_result: VisionResult | None = None

    def open(self) -> None:
        self.camera.open()

    def release(self) -> None:
        self.camera.release()

    def step(self) -> RuntimeFrame:
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
            board_state = to_board_state(smoothed_cells, self.board_rows, self.board_cols)
            warped_view = self.grid_model.draw_overlay(detection.warped_image, smoothed_cells)
            vision_result = VisionResult(
                board_found=True,
                board_image_size=(self.board_config.board_size, self.board_config.board_size),
                cells=smoothed_cells,
                board_state=board_state,
                timestamp=time.time(),
                stable=stable,
                stable_frames=stable_frames,
                theta_deg=detection.angle_deg,
            )
            warped_view = annotate_warped_view(warped_view, vision_result)
        else:
            self.smoother.reset()
            vision_result = VisionResult(
                board_found=False,
                board_image_size=(self.board_config.board_size, self.board_config.board_size),
                cells=[],
                board_state=self.grid_model.empty_state_matrix(),
                timestamp=time.time(),
                stable=False,
                stable_frames=0,
                theta_deg=None,
            )

        self.latest_result = vision_result
        return RuntimeFrame(
            raw_frame=raw_frame,
            board_view=board_view,
            warped_view=warped_view,
            red_mask=detection.mask,
            vision_result=vision_result,
        )

    def latest_stable_snapshot(self) -> VisionStableSnapshot | None:
        if self.latest_result is None:
            return None
        return vision_result_to_snapshot(self.latest_result)

    def save_debug_snapshot(self, debug_dir: str | Path, frame: RuntimeFrame) -> None:
        save_debug_frames(
            Path(debug_dir),
            frame.raw_frame,
            frame.board_view,
            frame.warped_view,
            frame.vision_result,
            self.camera_config,
            self.piece_config,
        )


def vision_result_to_snapshot(vision_result: VisionResult) -> VisionStableSnapshot | None:
    if not vision_result.board_found or not vision_result.stable:
        return None
    return VisionStableSnapshot(
        board_found=vision_result.board_found,
        stable=vision_result.stable,
        board_state=[list(row) for row in vision_result.board_state],
        theta_deg=vision_result.theta_deg,
        timestamp=vision_result.timestamp,
    )


def show_runtime_windows(frame: RuntimeFrame) -> int:
    cv2.imshow("raw", frame.raw_frame)
    cv2.imshow("board_detection", frame.board_view)
    if frame.red_mask is not None:
        cv2.imshow("red_mask", frame.red_mask)
    if frame.warped_view is not None:
        cv2.imshow("warped_board", frame.warped_view)
    return cv2.waitKey(1) & 0xFF
