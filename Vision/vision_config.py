from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from board_detector import BoardDetectorConfig
from camera import CameraConfig
from piece_detector import PieceDetectorConfig

DEFAULT_CONFIG_PATH = Path(__file__).with_name("vision_settings.json")

_BOARD_TUPLE_FIELDS = {
    "red_lower_1",
    "red_upper_1",
    "red_lower_2",
    "red_upper_2",
}


def load_config_file(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {}

    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config format in {config_path}.")

    board_section = dict(data.get("board_detector", {}))
    for key in _BOARD_TUPLE_FIELDS:
        if key in board_section and isinstance(board_section[key], list):
            board_section[key] = tuple(int(value) for value in board_section[key])
    data["board_detector"] = board_section
    return data


def save_config_file(
    path: str | Path,
    camera_config: CameraConfig,
    board_config: BoardDetectorConfig,
    piece_config: PieceDetectorConfig,
) -> None:
    config_path = Path(path)
    payload = build_config_payload(camera_config, board_config, piece_config)
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_config_payload(
    camera_config: CameraConfig,
    board_config: BoardDetectorConfig,
    piece_config: PieceDetectorConfig,
) -> dict[str, Any]:
    return {
        "camera": asdict(camera_config),
        "board_detector": asdict(board_config),
        "piece_detector": asdict(piece_config),
    }


def merge_config_values(
    defaults: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in overrides.items():
        if key in merged:
            merged[key] = value
    return merged
