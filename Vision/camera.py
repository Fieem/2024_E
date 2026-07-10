from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass
class CameraConfig:
    device_index: int = 0
    frame_width: int = 1600
    frame_height: int = 1200
    fps: int = 60
    pixel_format: str = "MJPG"
    auto_exposure: bool = False
    exposure: Optional[float] = 166.0
    auto_white_balance: bool = False
    white_balance: Optional[float] = None
    warmup_frames: int = 5


class UsbCamera:
    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self.capture: Optional[cv2.VideoCapture] = None

    def open(self) -> None:
        backend = self._select_backend()
        self.capture = cv2.VideoCapture(self.config.device_index, backend)
        if not self.capture.isOpened():
            raise RuntimeError(
                f"Unable to open USB camera at index {self.config.device_index}."
            )

        self._set_pixel_format(self.config.pixel_format)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
        self.capture.set(cv2.CAP_PROP_FPS, self.config.fps)

        self._set_auto_exposure(self.config.auto_exposure)
        if self.config.exposure is not None:
            self.capture.set(cv2.CAP_PROP_EXPOSURE, float(self.config.exposure))

        self._set_auto_white_balance(self.config.auto_white_balance)
        if self.config.white_balance is not None:
            self.capture.set(
                cv2.CAP_PROP_WB_TEMPERATURE,
                float(self.config.white_balance),
            )

        for _ in range(max(0, self.config.warmup_frames)):
            self.read()

    def read(self) -> np.ndarray:
        if self.capture is None:
            raise RuntimeError("Camera has not been opened yet.")

        ok, frame = self.capture.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to read a frame from the USB camera.")
        return frame

    def release(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None

    def update_controls(
        self,
        *,
        exposure: Optional[float] = None,
        white_balance: Optional[float] = None,
        auto_exposure: Optional[bool] = None,
        auto_white_balance: Optional[bool] = None,
    ) -> None:
        if self.capture is None:
            return

        if auto_exposure is not None:
            self.config.auto_exposure = auto_exposure
            self._set_auto_exposure(auto_exposure)
        if exposure is not None:
            self.config.exposure = float(exposure)
            self.capture.set(cv2.CAP_PROP_EXPOSURE, float(exposure))

        if auto_white_balance is not None:
            self.config.auto_white_balance = auto_white_balance
            self._set_auto_white_balance(auto_white_balance)
        if white_balance is not None:
            self.config.white_balance = float(white_balance)
            self.capture.set(cv2.CAP_PROP_WB_TEMPERATURE, float(white_balance))

    def _set_auto_exposure(self, enabled: bool) -> None:
        if self.capture is None:
            return

        # Different camera stacks expose this property differently.
        preferred_values = [3.0, 0.75] if enabled else [1.0, 0.25]
        for value in preferred_values:
            self.capture.set(cv2.CAP_PROP_AUTO_EXPOSURE, value)

    def _set_auto_white_balance(self, enabled: bool) -> None:
        if self.capture is None or not hasattr(cv2, "CAP_PROP_AUTO_WB"):
            return
        self.capture.set(cv2.CAP_PROP_AUTO_WB, 1.0 if enabled else 0.0)

    def _set_pixel_format(self, pixel_format: str) -> None:
        if self.capture is None or not pixel_format:
            return

        fourcc = cv2.VideoWriter_fourcc(*pixel_format[:4])
        self.capture.set(cv2.CAP_PROP_FOURCC, fourcc)

    @staticmethod
    def _select_backend() -> int:
        system = platform.system().lower()
        if system == "windows" and hasattr(cv2, "CAP_DSHOW"):
            return cv2.CAP_DSHOW
        if system == "linux" and hasattr(cv2, "CAP_V4L2"):
            return cv2.CAP_V4L2
        return cv2.CAP_ANY
