from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from vision_types import PulseConfig

DEFAULT_CONTROL_CONFIG_PATH = Path(__file__).with_name("vision_control_settings.json")


@dataclass(frozen=True)
class SerialConfig:
    port: str = "/dev/ttyAMA0"
    baudrate: int = 921600
    timeout_ms: int = 100


@dataclass(frozen=True)
class AIConfig:
    difficulty: str = "hard"
    time_limit_ms: int = 8000


@dataclass(frozen=True)
class TiltCompensationConfig:
    enabled: bool = True
    dead_zone_deg: float = 3.0
    max_tilt_deg: float = 55.0


@dataclass(frozen=True)
class ControlConfig:
    serial: SerialConfig
    ai: AIConfig
    tilt_compensation: TiltCompensationConfig
    pulse_config: PulseConfig


def load_control_config(path: str | Path) -> ControlConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Control config not found: {config_path}")

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid control config format in {config_path}")

    serial_section = raw.get("serial", {})
    ai_section = raw.get("ai", {})
    tilt_section = raw.get("tilt_compensation", {})
    pulse_section = raw.get("pulse_config", {})

    pulse_config = PulseConfig(
        black_slots=_parse_slot_list(pulse_section.get("black_slots", []), "black_slots"),
        white_slots=_parse_slot_list(pulse_section.get("white_slots", []), "white_slots"),
        board_cells=_parse_board_cells(pulse_section.get("board_cells", [])),
    )

    return ControlConfig(
        serial=SerialConfig(
            port=str(serial_section.get("port", "/dev/ttyAMA0")),
            baudrate=int(serial_section.get("baudrate", 921600)),
            timeout_ms=int(serial_section.get("timeout_ms", 100)),
        ),
        ai=AIConfig(
            difficulty=str(ai_section.get("difficulty", "hard")),
            time_limit_ms=int(ai_section.get("time_limit_ms", 8000)),
        ),
        tilt_compensation=TiltCompensationConfig(
            enabled=bool(tilt_section.get("enabled", True)),
            dead_zone_deg=float(tilt_section.get("dead_zone_deg", 3.0)),
            max_tilt_deg=float(tilt_section.get("max_tilt_deg", 55.0)),
        ),
        pulse_config=pulse_config,
    )


def save_control_config(path: str | Path, config: ControlConfig) -> None:
    config_path = Path(path)
    payload = {
        "serial": asdict(config.serial),
        "ai": asdict(config.ai),
        "tilt_compensation": asdict(config.tilt_compensation),
        "pulse_config": config.pulse_config.to_dict(),
    }
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_default_control_config() -> ControlConfig:
    zero_slots = [(0, 0) for _ in range(7)]
    zero_cells = [[(0, 0) for _ in range(7)] for _ in range(7)]
    return ControlConfig(
        serial=SerialConfig(),
        ai=AIConfig(),
        tilt_compensation=TiltCompensationConfig(),
        pulse_config=PulseConfig(
            black_slots=zero_slots,
            white_slots=zero_slots,
            board_cells=zero_cells,
        ),
    )


def ensure_default_control_config(path: str | Path = DEFAULT_CONTROL_CONFIG_PATH) -> Path:
    config_path = Path(path)
    if not config_path.exists():
        save_control_config(config_path, create_default_control_config())
    return config_path


def _parse_slot_list(values: Any, field_name: str) -> list[tuple[int, int]]:
    if not isinstance(values, list) or len(values) != 7:
        raise ValueError(f"{field_name} must contain exactly 7 pulse pairs")
    parsed: list[tuple[int, int]] = []
    for item in values:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"{field_name} items must be [pulse1, pulse2]")
        parsed.append((int(item[0]), int(item[1])))
    return parsed


def _parse_board_cells(values: Any) -> list[list[tuple[int, int]]]:
    if not isinstance(values, list) or len(values) != 7:
        raise ValueError("board_cells must contain exactly 7 rows")
    parsed_rows: list[list[tuple[int, int]]] = []
    for row in values:
        if not isinstance(row, list) or len(row) != 7:
            raise ValueError("board_cells rows must contain exactly 7 pulse pairs")
        parsed_row: list[tuple[int, int]] = []
        for item in row:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ValueError("board_cells items must be [pulse1, pulse2]")
            parsed_row.append((int(item[0]), int(item[1])))
        parsed_rows.append(parsed_row)
    return parsed_rows
