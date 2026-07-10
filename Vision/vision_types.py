from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

CellState = Literal["empty", "black", "white"]


@dataclass(frozen=True)
class CellGeometry:
    id: int
    row: int
    col: int
    center_px: tuple[int, int]
    bbox: tuple[int, int, int, int]


@dataclass(frozen=True)
class CellResult:
    id: int
    row: int
    col: int
    center_px: tuple[int, int]
    bbox: tuple[int, int, int, int]
    state: CellState
    confidence: float
    center_px_raw: tuple[int, int] | None = None
    diagnostics: dict[str, Any] | None = None

    @classmethod
    def from_geometry(
        cls,
        geometry: CellGeometry,
        state: CellState = "empty",
        confidence: float = 0.0,
        center_px_raw: tuple[int, int] | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> "CellResult":
        return cls(
            id=geometry.id,
            row=geometry.row,
            col=geometry.col,
            center_px=geometry.center_px,
            bbox=geometry.bbox,
            state=state,
            confidence=confidence,
            center_px_raw=center_px_raw,
            diagnostics=diagnostics,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BoardDetectionResult:
    found: bool
    corners: Any = None
    contour: Any = None
    warped_image: Any = None
    mask: Any = None
    annotated_frame: Any = None
    homography: Any = None
    angle_deg: float | None = None


@dataclass
class VisionResult:
    board_found: bool
    board_image_size: tuple[int, int]
    cells: list[CellResult]
    board_state: list[list[CellState]]
    timestamp: float
    stable: bool
    stable_frames: int
    theta_deg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "board_found": self.board_found,
            "board_image_size": self.board_image_size,
            "cells": [cell.to_dict() for cell in self.cells],
            "board_state": self.board_state,
            "timestamp": self.timestamp,
            "stable": self.stable,
            "stable_frames": self.stable_frames,
            "theta_deg": self.theta_deg,
        }
