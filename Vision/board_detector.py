from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from vision_types import BoardDetectionResult


@dataclass
class BoardDetectorConfig:
    board_size: int = 700
    min_area_ratio: float = 0.08
    smoothing_alpha: float = 0.35
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


class BoardDetector:
    def __init__(self, config: BoardDetectorConfig) -> None:
        self.config = config
        self._smoothed_corners: np.ndarray | None = None

    def detect(self, frame: np.ndarray) -> BoardDetectionResult:
        raw_mask = create_red_mask(
            frame,
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
            mask=mask,
            annotated_frame=annotated,
            homography=homography,
        )

    def _smooth_corners(self, corners: np.ndarray) -> np.ndarray:
        if self._smoothed_corners is None:
            self._smoothed_corners = corners.copy()
            return corners

        alpha = float(np.clip(self.config.smoothing_alpha, 0.0, 1.0))
        self._smoothed_corners = (
            (1.0 - alpha) * self._smoothed_corners + alpha * corners
        )
        return self._smoothed_corners.copy()

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
