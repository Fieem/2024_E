from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from vision_types import CellGeometry, CellResult


@dataclass(frozen=True)
class GridModelConfig:
    rows: int = 7
    cols: int = 7
    board_size: int = 700
    roi_padding_ratio: float = 0.18
    center_marker_radius: int = 12


class GridModel:
    def __init__(self, config: GridModelConfig) -> None:
        self.config = config
        self._cells = self._build_cells()

    @property
    def cells(self) -> list[CellGeometry]:
        return self._cells

    def _build_cells(self) -> list[CellGeometry]:
        cells: list[CellGeometry] = []
        cell_width = self.config.board_size / self.config.cols
        cell_height = self.config.board_size / self.config.rows
        pad_x = cell_width * self.config.roi_padding_ratio
        pad_y = cell_height * self.config.roi_padding_ratio

        cell_id = 0
        for row in range(self.config.rows):
            for col in range(self.config.cols):
                left = int(round(col * cell_width + pad_x))
                top = int(round(row * cell_height + pad_y))
                right = int(round((col + 1) * cell_width - pad_x))
                bottom = int(round((row + 1) * cell_height - pad_y))
                center_x = int(round((col + 0.5) * cell_width))
                center_y = int(round((row + 0.5) * cell_height))
                cells.append(
                    CellGeometry(
                        id=cell_id,
                        row=row,
                        col=col,
                        center_px=(center_x, center_y),
                        bbox=(left, top, right, bottom),
                    )
                )
                cell_id += 1
        return cells

    def board_shape(self) -> tuple[int, int]:
        return self.config.rows, self.config.cols

    def empty_state_matrix(self) -> list[list[str]]:
        return [["empty" for _ in range(self.config.cols)] for _ in range(self.config.rows)]

    def draw_overlay(
        self,
        board_image: np.ndarray,
        cells: list[CellResult] | None = None,
    ) -> np.ndarray:
        annotated = board_image.copy()
        cell_results = {cell.id: cell for cell in cells or []}
        cell_width = self.config.board_size / self.config.cols
        cell_height = self.config.board_size / self.config.rows

        for row in range(self.config.rows + 1):
            y = int(round(row * cell_height))
            cv2.line(
                annotated,
                (0, y),
                (self.config.board_size, y),
                (40, 40, 40),
                1,
                cv2.LINE_AA,
            )
        for col in range(self.config.cols + 1):
            x = int(round(col * cell_width))
            cv2.line(
                annotated,
                (x, 0),
                (x, self.config.board_size),
                (40, 40, 40),
                1,
                cv2.LINE_AA,
            )

        for cell in self._cells:
            x1, y1, x2, y2 = cell.bbox
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (80, 80, 80), 1)

            cell_result = cell_results.get(cell.id)
            state = cell_result.state if cell_result else "empty"
            color = self._state_color(state)

            cv2.circle(
                annotated,
                cell.center_px,
                self.config.center_marker_radius,
                color,
                2,
            )
            cv2.putText(
                annotated,
                f"{cell.row},{cell.col}",
                (x1 + 2, y1 + 14),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.36,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            if cell_result:
                cv2.putText(
                    annotated,
                    f"{state[0].upper()} {cell_result.confidence:.2f}",
                    (x1 + 2, y2 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.35,
                    color,
                    1,
                    cv2.LINE_AA,
                )
        return annotated

    @staticmethod
    def _state_color(state: str) -> tuple[int, int, int]:
        if state == "black":
            return (0, 0, 0)
        if state == "white":
            return (255, 255, 255)
        return (0, 200, 0)
