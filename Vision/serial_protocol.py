from __future__ import annotations

from vision_types import ModeRequest, ModeResponse, RobotColor


SHORT_ERROR_MESSAGES = {
    "NO_BOARD": "NO BOARD",
    "BAD_CMD": "BAD COMMAND",
    "BAD_COLOR": "BAD COLOR",
    "BAD_POS": "BAD POSITION",
    "NO_SLOT": "NO SLOT",
    "AI_TURN_MISMATCH": "WRONG TURN",
    "ILLEGAL_BOARD": "ILLEGAL BOARD",
    "AI_FAIL": "AI FAILED",
}


class ProtocolError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_request_line(line: str) -> ModeRequest:
    text = line.strip()
    if not text:
        raise ProtocolError("BAD_CMD", "Empty command")

    parts = [part.strip() for part in text.split(",")]
    command = parts[0].upper()

    if command == "PLACE":
        if len(parts) != 5:
            raise ProtocolError("BAD_CMD", "PLACE requires color,piece_no,row,col")
        color = _parse_color(parts[1])
        piece_no = _parse_int(parts[2], "piece_no")
        if not 1 <= piece_no <= 7:
            raise ProtocolError("NO_SLOT", "Piece number must be 1..7")
        piece_index = piece_no - 1
        row = _parse_int(parts[3], "row")
        col = _parse_int(parts[4], "col")
        return ModeRequest(
            kind="place",
            color=color,
            piece_index=piece_index,
            row=row,
            col=col,
        )

    if command == "BATTLE_START":
        if len(parts) != 2:
            raise ProtocolError("BAD_CMD", "BATTLE_START requires color")
        color = _parse_color(parts[1])
        return ModeRequest(kind="battle_start", color=color)

    if command == "READY":
        if len(parts) != 1:
            raise ProtocolError("BAD_CMD", "READY does not accept parameters")
        return ModeRequest(kind="ready")

    raise ProtocolError("BAD_CMD", f"Unknown command: {command}")


def format_response_line(response: ModeResponse) -> str:
    if response.kind == "pulses":
        if response.pulses4 is None:
            raise ValueError("pulses response requires pulses4")
        return "PULSES,{},{},{},{}".format(*response.pulses4)

    if response.kind == "move":
        if response.pulses4 is None:
            raise ValueError("move response requires pulses4")
        return "PULSES,{},{},{},{}".format(
            response.pulses4[0],
            response.pulses4[1],
            response.pulses4[2],
            response.pulses4[3],
        )

    if response.kind == "busy":
        return "BUSY,{}".format(_compact_busy_message(response.message))

    if response.kind == "error":
        error_code = response.error_code or "BAD_CMD"
        return "ERROR,{},{}".format(
            error_code,
            SHORT_ERROR_MESSAGES.get(error_code, "ERROR"),
        )

    raise ValueError(f"Unsupported response kind: {response.kind}")


def _parse_color(text: str) -> RobotColor:
    normalized = text.strip().upper()
    color_map = {
        "B": "BLACK",
        "W": "WHITE",
    }
    if normalized not in color_map:
        raise ProtocolError("BAD_COLOR", f"Invalid color: {text}")
    return color_map[normalized]  # type: ignore[return-value]


def _parse_int(text: str, field_name: str) -> int:
    try:
        return int(text)
    except ValueError as exc:
        raise ProtocolError("BAD_CMD", f"Invalid {field_name}: {text}") from exc


def _compact_busy_message(message: str | None) -> str:
    normalized = (message or "").strip().lower()
    if normalized.startswith("battle_active_"):
        return "BATTLE ON"
    if normalized == "game_over_black_win":
        return "BLACK WIN"
    if normalized == "game_over_white_win":
        return "WHITE WIN"
    if normalized == "game_over_draw":
        return "DRAW"
    return "BUSY"
