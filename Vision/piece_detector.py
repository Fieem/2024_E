from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from board_detector import create_red_mask
from vision_types import CellGeometry, CellResult


@dataclass
class PieceDetectorConfig:
    sample_radius_ratio: float = 0.42
    min_piece_area_ratio: float = 0.10
    black_value_max: int = 70
    white_value_min: int = 170
    white_saturation_max: int = 80
    empty_red_ratio_threshold: float = 0.45


class PieceDetector:
    def __init__(self, config: PieceDetectorConfig) -> None:
        self.config = config

    def detect(
        self,
        board_image: np.ndarray,
        cells: list[CellGeometry],
        board_shape: tuple[int, int],
    ) -> tuple[list[CellResult], list[list[str]]]:
        rows, cols = board_shape
        cell_results: list[CellResult] = []
        state_matrix = [["empty" for _ in range(cols)] for _ in range(rows)]

        for geometry in cells:
            result = self._classify_cell(board_image, geometry)
            cell_results.append(result)
            state_matrix[result.row][result.col] = result.state

        return cell_results, state_matrix

    def _classify_cell(self, board_image: np.ndarray, geometry: CellGeometry) -> CellResult:
        x1, y1, x2, y2 = geometry.bbox
        roi = board_image[y1:y2, x1:x2]
        if roi.size == 0:
            return CellResult.from_geometry(geometry, state="empty", confidence=0.0)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        red_mask = create_red_mask(roi)
        circle_mask = self._build_circle_mask(roi.shape[:2])
        sample_area = float(np.count_nonzero(circle_mask)) or 1.0

        black_mask = cv2.inRange(
            gray,
            0,
            self.config.black_value_max,
        )
        white_mask = cv2.inRange(
            hsv,
            np.array((0, 0, self.config.white_value_min)),
            np.array((180, self.config.white_saturation_max, 255)),
        )

        red_ratio = np.count_nonzero(cv2.bitwise_and(red_mask, red_mask, mask=circle_mask)) / sample_area
        black_area = self._largest_component_area(
            cv2.bitwise_and(black_mask, black_mask, mask=circle_mask)
        )
        white_area = self._largest_component_area(
            cv2.bitwise_and(white_mask, white_mask, mask=circle_mask)
        )

        black_ratio = black_area / sample_area
        white_ratio = white_area / sample_area
        piece_ratio = max(black_ratio, white_ratio)

        if piece_ratio < self.config.min_piece_area_ratio and red_ratio >= self.config.empty_red_ratio_threshold:
            confidence = min(0.99, 0.55 + red_ratio * 0.4)
            return CellResult.from_geometry(geometry, state="empty", confidence=confidence)

        if white_ratio > black_ratio and white_ratio >= self.config.min_piece_area_ratio:
            confidence = min(0.99, 0.55 + white_ratio + max(0.0, white_ratio - black_ratio))
            return CellResult.from_geometry(geometry, state="white", confidence=confidence)

        if black_ratio >= self.config.min_piece_area_ratio:
            confidence = min(0.99, 0.55 + black_ratio + max(0.0, black_ratio - white_ratio))
            return CellResult.from_geometry(geometry, state="black", confidence=confidence)

        # Ambiguous cells default to empty so the frame stabilizer can absorb noise.
        confidence = max(0.3, red_ratio)
        return CellResult.from_geometry(geometry, state="empty", confidence=confidence)

    def _build_circle_mask(self, roi_shape: tuple[int, int]) -> np.ndarray:
        height, width = roi_shape
        radius = int(min(height, width) * self.config.sample_radius_ratio)
        radius = max(radius, 4)
        mask = np.zeros((height, width), dtype=np.uint8)
        center = (width // 2, height // 2)
        cv2.circle(mask, center, radius, 255, -1)
        return mask

    @staticmethod
    def _largest_component_area(mask: np.ndarray) -> int:
        component_count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if component_count <= 1:
            return 0
        return int(stats[1:, cv2.CC_STAT_AREA].max())
