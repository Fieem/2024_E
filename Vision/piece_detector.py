from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from board_detector import create_red_mask
from vision_types import CellGeometry, CellResult


@dataclass
class PieceDetectorConfig:
    sample_radius_ratio: float = 0.42
    center_sample_radius_ratio: float = 0.24
    min_piece_area_ratio: float = 0.10
    white_min_piece_area_ratio: float = 0.05
    white_relaxed_piece_area_ratio: float = 0.03
    white_center_ratio_min: float = 0.12
    black_value_max: int = 70
    black_saturation_min: int = 0
    black_saturation_max: int = 255
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
            return CellResult.from_geometry(
                geometry,
                state="empty",
                confidence=0.0,
                diagnostics={"reason": "empty_roi"},
            )

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        red_mask = create_red_mask(roi)
        circle_mask = self._build_circle_mask(
            roi.shape[:2],
            self.config.sample_radius_ratio,
        )
        center_mask = self._build_circle_mask(
            roi.shape[:2],
            self.config.center_sample_radius_ratio,
        )
        sample_area = float(np.count_nonzero(circle_mask)) or 1.0
        center_area = float(np.count_nonzero(center_mask)) or 1.0

        black_mask = cv2.inRange(
            hsv,
            np.array((0, self.config.black_saturation_min, 0)),
            np.array((180, self.config.black_saturation_max, self.config.black_value_max)),
        )
        black_mask = cv2.bitwise_and(black_mask, cv2.bitwise_not(red_mask))
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
        white_center_area = self._largest_component_area(
            cv2.bitwise_and(white_mask, white_mask, mask=center_mask)
        )

        black_ratio = black_area / sample_area
        white_ratio = white_area / sample_area
        white_center_ratio = white_center_area / center_area
        piece_ratio = max(black_ratio, white_ratio)
        center_value_mean = cv2.mean(hsv[:, :, 2], mask=center_mask)[0]
        center_saturation_mean = cv2.mean(hsv[:, :, 1], mask=center_mask)[0]
        diagnostics = {
            "red_ratio": round(float(red_ratio), 4),
            "black_ratio": round(float(black_ratio), 4),
            "white_ratio": round(float(white_ratio), 4),
            "white_center_ratio": round(float(white_center_ratio), 4),
            "piece_ratio": round(float(piece_ratio), 4),
            "sample_area": round(float(sample_area), 1),
            "center_area": round(float(center_area), 1),
            "black_area": int(black_area),
            "white_area": int(white_area),
            "white_center_area": int(white_center_area),
            "center_value_mean": round(float(center_value_mean), 2),
            "center_saturation_mean": round(float(center_saturation_mean), 2),
        }

        no_black_candidate = black_ratio < self.config.min_piece_area_ratio
        no_white_candidate = white_ratio < self.config.white_min_piece_area_ratio
        if no_black_candidate and no_white_candidate and red_ratio >= self.config.empty_red_ratio_threshold:
            confidence = min(0.99, 0.55 + red_ratio * 0.4)
            diagnostics["reason"] = "background_red_dominant"
            return CellResult.from_geometry(
                geometry,
                state="empty",
                confidence=confidence,
                diagnostics=diagnostics,
            )

        strong_white = (
            white_ratio > black_ratio
            and white_ratio >= self.config.white_min_piece_area_ratio
        )
        relaxed_white = (
            white_ratio >= self.config.white_relaxed_piece_area_ratio
            and white_center_ratio >= self.config.white_center_ratio_min
            and center_value_mean >= self.config.white_value_min - 10
            and center_saturation_mean <= self.config.white_saturation_max + 35
        )
        if strong_white or relaxed_white:
            confidence = min(0.99, 0.55 + white_ratio + max(0.0, white_ratio - black_ratio))
            diagnostics["reason"] = (
                "white_component_dominant" if strong_white else "white_center_relaxed"
            )
            return CellResult.from_geometry(
                geometry,
                state="white",
                confidence=confidence,
                diagnostics=diagnostics,
            )

        if black_ratio >= self.config.min_piece_area_ratio:
            confidence = min(0.99, 0.55 + black_ratio + max(0.0, black_ratio - white_ratio))
            diagnostics["reason"] = "black_component_dominant"
            return CellResult.from_geometry(
                geometry,
                state="black",
                confidence=confidence,
                diagnostics=diagnostics,
            )

        # Ambiguous cells default to empty so the frame stabilizer can absorb noise.
        confidence = max(0.3, red_ratio)
        diagnostics["reason"] = "ambiguous_fallback"
        return CellResult.from_geometry(
            geometry,
            state="empty",
            confidence=confidence,
            diagnostics=diagnostics,
        )

    def _build_circle_mask(
        self,
        roi_shape: tuple[int, int],
        radius_ratio: float,
    ) -> np.ndarray:
        height, width = roi_shape
        radius = int(min(height, width) * radius_ratio)
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
