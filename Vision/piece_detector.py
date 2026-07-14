from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from board_detector import BoardDetectorConfig, create_red_mask
from vision_types import CellGeometry, CellResult


@dataclass
class PieceDetectorConfig:
    sample_radius_ratio: float = 0.42
    center_sample_radius_ratio: float = 0.24
    min_piece_area_ratio: float = 0.10
    white_min_piece_area_ratio: float = 0.05
    white_relaxed_piece_area_ratio: float = 0.03
    white_norm_min_piece_area_ratio: float = 0.025
    white_center_ratio_min: float = 0.12
    black_value_max: int = 70
    black_saturation_min: int = 0
    black_saturation_max: int = 255
    white_value_min: int = 170
    white_saturation_max: int = 80
    white_norm_value_min: int = 150
    white_norm_saturation_max: int = 140
    empty_red_ratio_threshold: float = 0.45


class PieceDetector:
    def __init__(
        self,
        config: PieceDetectorConfig,
        red_mask_config: BoardDetectorConfig | None = None,
    ) -> None:
        self.config = config
        # Use the same HSV thresholds as board localization so red_ratio matches red_mask.
        self.red_mask_config = red_mask_config

    def detect(
        self,
        board_image: np.ndarray,
        cells: list[CellGeometry],
        board_shape: tuple[int, int],
        red_board_image: np.ndarray | None = None,
    ) -> tuple[list[CellResult], list[list[str]]]:
        rows, cols = board_shape
        cell_results: list[CellResult] = []
        state_matrix = [["empty" for _ in range(cols)] for _ in range(rows)]

        for geometry in cells:
            result = self._classify_cell(board_image, geometry, red_board_image)
            cell_results.append(result)
            state_matrix[result.row][result.col] = result.state

        return cell_results, state_matrix

    def _classify_cell(
        self,
        board_image: np.ndarray,
        geometry: CellGeometry,
        red_board_image: np.ndarray | None = None,
    ) -> CellResult:
        x1, y1, x2, y2 = geometry.bbox
        roi = board_image[y1:y2, x1:x2]
        if roi.size == 0:
            return CellResult.from_geometry(
                geometry,
                state="empty",
                confidence=0.0,
                diagnostics={"reason": "empty_roi"},
            )

        red_source = red_board_image if red_board_image is not None else board_image
        red_roi = red_source[y1:y2, x1:x2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        red_config = self.red_mask_config
        red_mask = create_red_mask(
            red_roi if red_roi.size else roi,
            lower_1=red_config.red_lower_1 if red_config else (0, 70, 50),
            upper_1=red_config.red_upper_1 if red_config else (12, 255, 255),
            lower_2=red_config.red_lower_2 if red_config else (165, 70, 50),
            upper_2=red_config.red_upper_2 if red_config else (180, 255, 255),
        )
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
        normalized_value = self._normalize_value_channel(hsv[:, :, 2])
        white_norm_mask = cv2.inRange(
            normalized_value,
            self.config.white_norm_value_min,
            255,
        )
        white_norm_mask = cv2.bitwise_and(
            white_norm_mask,
            cv2.inRange(
                hsv[:, :, 1],
                0,
                self.config.white_norm_saturation_max,
            ),
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
        white_norm_area = self._largest_component_area(
            cv2.bitwise_and(white_norm_mask, white_norm_mask, mask=circle_mask)
        )
        white_norm_center_area = self._largest_component_area(
            cv2.bitwise_and(white_norm_mask, white_norm_mask, mask=center_mask)
        )

        black_ratio = black_area / sample_area
        white_ratio = white_area / sample_area
        white_center_ratio = white_center_area / center_area
        white_norm_ratio = white_norm_area / sample_area
        white_norm_center_ratio = white_norm_center_area / center_area
        effective_white_ratio = max(white_ratio, white_norm_ratio)
        effective_white_center_ratio = max(white_center_ratio, white_norm_center_ratio)
        piece_ratio = max(black_ratio, effective_white_ratio)
        center_value_mean = cv2.mean(hsv[:, :, 2], mask=center_mask)[0]
        center_saturation_mean = cv2.mean(hsv[:, :, 1], mask=center_mask)[0]
        normalized_center_value_mean = cv2.mean(normalized_value, mask=center_mask)[0]
        diagnostics = {
            "red_ratio": round(float(red_ratio), 4),
            "black_ratio": round(float(black_ratio), 4),
            "white_ratio": round(float(white_ratio), 4),
            "white_center_ratio": round(float(white_center_ratio), 4),
            "white_norm_ratio": round(float(white_norm_ratio), 4),
            "white_norm_center_ratio": round(float(white_norm_center_ratio), 4),
            "effective_white_ratio": round(float(effective_white_ratio), 4),
            "effective_white_center_ratio": round(float(effective_white_center_ratio), 4),
            "piece_ratio": round(float(piece_ratio), 4),
            "sample_area": round(float(sample_area), 1),
            "center_area": round(float(center_area), 1),
            "black_area": int(black_area),
            "white_area": int(white_area),
            "white_center_area": int(white_center_area),
            "white_norm_area": int(white_norm_area),
            "white_norm_center_area": int(white_norm_center_area),
            "center_value_mean": round(float(center_value_mean), 2),
            "center_saturation_mean": round(float(center_saturation_mean), 2),
            "normalized_center_value_mean": round(float(normalized_center_value_mean), 2),
        }

        red_background_dominant = red_ratio >= self.config.empty_red_ratio_threshold
        has_piece = not red_background_dominant
        diagnostics["red_threshold"] = round(float(self.config.empty_red_ratio_threshold), 4)
        diagnostics["red_background_dominant"] = red_background_dominant
        diagnostics["has_piece"] = has_piece

        if not has_piece:
            confidence = min(0.99, 0.55 + red_ratio * 0.4)
            diagnostics["black_present"] = False
            diagnostics["white_present"] = False
            diagnostics["reason"] = "background_red_dominant"
            return CellResult.from_geometry(
                geometry,
                state="empty",
                confidence=confidence,
                diagnostics=diagnostics,
            )

        # A specular highlight on a black piece can satisfy the relaxed white
        # rule. Require raw white evidence to clearly dominate black evidence
        # before allowing a white result, and reserve normalized evidence for
        # cells without a convincing black component.
        black_present = black_ratio >= self.config.min_piece_area_ratio
        white_dominant = white_ratio >= black_ratio + 0.05
        strong_white = white_dominant and (
            white_ratio >= self.config.white_min_piece_area_ratio
            or (
                white_norm_ratio >= self.config.white_norm_min_piece_area_ratio
                and not black_present
            )
        )
        relaxed_white = (
            not black_present
            and effective_white_ratio >= min(
                self.config.white_relaxed_piece_area_ratio,
                self.config.white_norm_min_piece_area_ratio,
            )
            and effective_white_center_ratio >= self.config.white_center_ratio_min
            and (
                center_value_mean >= self.config.white_value_min - 10
                or normalized_center_value_mean >= self.config.white_norm_value_min
            )
            and center_saturation_mean <= max(
                self.config.white_saturation_max + 35,
                self.config.white_norm_saturation_max,
            )
        )
        white_present = strong_white or relaxed_white
        diagnostics["black_present"] = black_present
        diagnostics["white_present"] = white_present
        diagnostics["white_dominant"] = white_dominant

        if strong_white or relaxed_white:
            confidence = min(
                0.99,
                0.55 + effective_white_ratio + max(0.0, effective_white_ratio - black_ratio),
            )
            diagnostics["reason"] = (
                "white_component_dominant"
                if strong_white and white_ratio >= white_norm_ratio
                else "white_normalized_dominant"
                if strong_white
                else "white_center_relaxed"
            )
            return CellResult.from_geometry(
                geometry,
                state="white",
                confidence=confidence,
                diagnostics=diagnostics,
            )

        if black_present:
            confidence = min(
                0.99,
                0.55 + black_ratio + max(0.0, black_ratio - effective_white_ratio),
            )
            diagnostics["reason"] = "black_component_dominant"
            return CellResult.from_geometry(
                geometry,
                state="black",
                confidence=confidence,
                diagnostics=diagnostics,
            )

        # Presence is already confirmed by red background occlusion. If color evidence is weak,
        # choose the more likely color with low confidence instead of dropping back to empty.
        fallback_state = "white" if effective_white_ratio >= black_ratio else "black"
        fallback_strength = effective_white_ratio if fallback_state == "white" else black_ratio
        confidence = min(
            0.75,
            max(0.25, 0.3 + fallback_strength + abs(effective_white_ratio - black_ratio) * 0.5),
        )
        diagnostics["reason"] = f"piece_present_{fallback_state}_fallback"
        return CellResult.from_geometry(
            geometry,
            state=fallback_state,
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
    def _normalize_value_channel(value_channel: np.ndarray) -> np.ndarray:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        return clahe.apply(value_channel)

    @staticmethod
    def _largest_component_area(mask: np.ndarray) -> int:
        component_count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if component_count <= 1:
            return 0
        return int(stats[1:, cv2.CC_STAT_AREA].max())
