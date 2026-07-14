from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np

from vision_types import BoardDetectionResult


@dataclass
class BoardDetectorConfig:
    board_size: int = 700
    min_area_ratio: float = 0.08
    smoothing_alpha: float = 0.35
    angle_smoothing_alpha: float = 0.4
    use_lighting_normalization: bool = True
    clahe_clip_limit: float = 2.5
    clahe_tile_grid_size: int = 8
    theta_zero_ref_deg: float = 0.0
    red_lower_1: tuple[int, int, int] = (0, 70, 50)
    red_upper_1: tuple[int, int, int] = (12, 255, 255)
    red_lower_2: tuple[int, int, int] = (165, 70, 50)
    red_upper_2: tuple[int, int, int] = (180, 255, 255)
    morph_kernel_size: int = 7


def create_red_mask(
    image_bgr: np.ndarray,
    lower_1: tuple[int, int, int] = (0, 70, 50),
    upper_1: tuple[int, int, int] = (12, 255, 255),
    lower_2: tuple[int, int, int] = (165, 70, 50),
    upper_2: tuple[int, int, int] = (180, 255, 255),
) -> np.ndarray:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    mask_1 = cv2.inRange(hsv, np.array(lower_1), np.array(upper_1))
    mask_2 = cv2.inRange(hsv, np.array(lower_2), np.array(upper_2))
    return cv2.bitwise_or(mask_1, mask_2)


def normalize_board_lighting(
    image_bgr: np.ndarray,
    clip_limit: float = 2.5,
    tile_grid_size: int = 8,
) -> np.ndarray:
    grid_size = max(1, int(tile_grid_size))
    clahe = cv2.createCLAHE(
        clipLimit=max(0.1, float(clip_limit)),
        tileGridSize=(grid_size, grid_size),
    )
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(lab)
    normalized_lightness = clahe.apply(lightness)
    normalized_lab = cv2.merge((normalized_lightness, channel_a, channel_b))
    return cv2.cvtColor(normalized_lab, cv2.COLOR_LAB2BGR)


class BoardDetector:
    def __init__(self, config: BoardDetectorConfig) -> None:
        self.config = config
        self._smoothed_corners: np.ndarray | None = None
        self._smoothed_angle_deg: float | None = None

    def detect(self, frame: np.ndarray) -> BoardDetectionResult:
        board_frame = frame
        if self.config.use_lighting_normalization:
            board_frame = normalize_board_lighting(
                frame,
                clip_limit=self.config.clahe_clip_limit,
                tile_grid_size=self.config.clahe_tile_grid_size,
            )

        raw_mask = create_red_mask(
            board_frame,
            self.config.red_lower_1,
            self.config.red_upper_1,
            self.config.red_lower_2,
            self.config.red_upper_2,
        )
        kernel = np.ones(
            (self.config.morph_kernel_size, self.config.morph_kernel_size),
            dtype=np.uint8,
        )
        mask = cv2.morphologyEx(raw_mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        annotated = frame.copy()
        if not contours:
            self._reset_tracking()
            self._draw_status(annotated, "Board not found")
            return BoardDetectionResult(
                found=False,
                mask=mask,
                annotated_frame=annotated,
            )

        image_area = frame.shape[0] * frame.shape[1]
        candidates = [
            contour
            for contour in contours
            if cv2.contourArea(contour) >= image_area * self.config.min_area_ratio
        ]
        if not candidates:
            self._reset_tracking()
            self._draw_status(annotated, "Board too small")
            return BoardDetectionResult(
                found=False,
                mask=mask,
                annotated_frame=annotated,
            )

        contour = max(candidates, key=cv2.contourArea)
        rect = cv2.minAreaRect(contour)
        corners = cv2.boxPoints(rect).astype(np.float32)
        ordered_corners = self._order_corners(corners)
        ordered_corners = self._smooth_corners(ordered_corners)

        destination = np.array(
            [
                [0, 0],
                [self.config.board_size - 1, 0],
                [self.config.board_size - 1, self.config.board_size - 1],
                [0, self.config.board_size - 1],
            ],
            dtype=np.float32,
        )
        homography = cv2.getPerspectiveTransform(ordered_corners, destination)
        warped = cv2.warpPerspective(
            frame,
            homography,
            (self.config.board_size, self.config.board_size),
        )
        normalized_warped = cv2.warpPerspective(
            board_frame,
            homography,
            (self.config.board_size, self.config.board_size),
        )
        raw_angle_deg = self._compute_top_edge_angle_deg(ordered_corners)
        angle_deg = self._smooth_angle_deg(
            self._normalize_angle_deg(raw_angle_deg - self.config.theta_zero_ref_deg)
        )

        cv2.drawContours(annotated, [contour], -1, (0, 255, 255), 2)
        cv2.polylines(
            annotated,
            [ordered_corners.astype(np.int32)],
            isClosed=True,
            color=(255, 0, 0),
            thickness=2,
        )
        for index, point in enumerate(ordered_corners.astype(int)):
            cv2.circle(annotated, tuple(point), 6, (0, 255, 0), -1)
            cv2.putText(
                annotated,
                str(index),
                (point[0] + 8, point[1] - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
        self._draw_status(annotated, "Board locked")

        return BoardDetectionResult(
            found=True,
            corners=ordered_corners,
            contour=contour,
            warped_image=warped,
            normalized_warped_image=normalized_warped,
            mask=mask,
            annotated_frame=annotated,
            homography=homography,
            angle_deg=angle_deg,
        )

    def _reset_tracking(self) -> None:
        self._smoothed_corners = None
        self._smoothed_angle_deg = None

    def _smooth_corners(self, corners: np.ndarray) -> np.ndarray:
        if self._smoothed_corners is None:
            self._smoothed_corners = corners.copy()
            return corners

        alpha = float(np.clip(self.config.smoothing_alpha, 0.0, 1.0))
        self._smoothed_corners = (
            (1.0 - alpha) * self._smoothed_corners + alpha * corners
        )
        return self._smoothed_corners.copy()

    def _smooth_angle_deg(self, angle_deg: float) -> float:
        if self._smoothed_angle_deg is None:
            self._smoothed_angle_deg = angle_deg
            return angle_deg

        alpha = float(np.clip(self.config.angle_smoothing_alpha, 0.0, 1.0))
        delta = self._normalize_angle_deg(angle_deg - self._smoothed_angle_deg)
        self._smoothed_angle_deg = self._normalize_angle_deg(
            self._smoothed_angle_deg + alpha * delta
        )
        return float(self._smoothed_angle_deg)

    @staticmethod
    def _order_corners(points: np.ndarray) -> np.ndarray:
        ordered = np.zeros((4, 2), dtype=np.float32)
        sums = points.sum(axis=1)
        diffs = np.diff(points, axis=1).reshape(-1)

        ordered[0] = points[np.argmin(sums)]
        ordered[2] = points[np.argmax(sums)]
        ordered[1] = points[np.argmin(diffs)]
        ordered[3] = points[np.argmax(diffs)]
        return ordered

    @staticmethod
    def _compute_top_edge_angle_deg(ordered_corners: np.ndarray) -> float:
        top_left = ordered_corners[0]
        top_right = ordered_corners[1]
        dx = float(top_right[0] - top_left[0])
        dy = float(top_right[1] - top_left[1])
        return math.degrees(math.atan2(dy, dx))

    @staticmethod
    def _normalize_angle_deg(angle_deg: float) -> float:
        normalized = (angle_deg + 180.0) % 360.0 - 180.0
        return float(normalized)

    @staticmethod
    def _draw_status(image: np.ndarray, text: str) -> None:
        cv2.rectangle(image, (10, 10), (240, 42), (0, 0, 0), -1)
        cv2.putText(
            image,
            text,
            (18, 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
