from __future__ import annotations

from vision_types import ModeRequest, ModeResponse, RobotColor


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
        if len(parts) != 4:
            raise ProtocolError("BAD_CMD", "PLACE requires color,row,col")
        color = _parse_color(parts[1])
        row = _parse_int(parts[2], "row")
        col = _parse_int(parts[3], "col")
        return ModeRequest(kind="place", color=color, row=row, col=col)

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
        if response.pulses4 is None or response.row is None or response.col is None:
            raise ValueError("move response requires row,col,pulses4")
        return "MOVE,{},{},{},{},{},{}".format(
            response.row,
            response.col,
            response.pulses4[0],
            response.pulses4[1],
            response.pulses4[2],
            response.pulses4[3],
        )

    if response.kind == "busy":
        return "BUSY,{}".format(_sanitize_message(response.message or "busy"))

    if response.kind == "error":
        return "ERROR,{},{}".format(
            response.error_code or "BAD_CMD",
            _sanitize_message(response.message or "error"),
        )

    raise ValueError(f"Unsupported response kind: {response.kind}")


def _parse_color(text: str) -> RobotColor:
    normalized = text.strip().upper()
    if normalized not in {"BLACK", "WHITE"}:
        raise ProtocolError("BAD_COLOR", f"Invalid color: {text}")
    return normalized  # type: ignore[return-value]


def _parse_int(text: str, field_name: str) -> int:
    try:
        return int(text)
    except ValueError as exc:
        raise ProtocolError("BAD_CMD", f"Invalid {field_name}: {text}") from exc


def _sanitize_message(message: str) -> str:
    return message.replace(",", ";").replace("\n", " ").strip()
