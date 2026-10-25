"""Decode EZVIZ robot map layers (no Home Assistant imports).

Map decoding adapted from ha-ezviz-vacuum by Stefan Ciubotaru (Apache-2.0).

The cloud returns three layers per map, each with its own version:

* ``map``    – the occupancy grid (``mapData``) and the charger position,
* ``region`` – one outline per room,
* ``path``   – the cleaning path and the robot position.

Grids and outlines share one coordinate system: cell ``(x, y)`` of the map
grid is drawn at ``x``, ``y``. Compressed fields are gzip, then base64.
"""

from __future__ import annotations

import base64
import gzip
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

CELL_FLOOR = "floor"
CELL_WALL = "wall"
CELL_OBSTACLE = "obstacle"

# Default (legacy) encoding: base64 digits each carry two 3-bit cell types.
_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_B64_VALUE = {char: index for index, char in enumerate(_B64)}
_RLE = re.compile(r"(.)\((\d+)\)")
_LEGACY_TYPES = {2: CELL_FLOOR, 1: CELL_WALL}


@dataclass
class Grid:
    """Occupancy grid; ``cells`` maps a cell type to row runs."""

    x: int
    y: int
    w: int
    h: int
    runs: dict[str, list[tuple[int, int, int]]] = field(default_factory=dict)
    """``type -> [(x, y, length)]`` horizontal runs in map coordinates."""


@dataclass
class MapLayers:
    """Everything needed to draw a map."""

    grid: Grid | None = None
    charger: tuple[float, float] | None = None
    charger_degree: float | None = None
    rooms: dict[int, list[tuple[float, float]]] = field(default_factory=dict)
    path: list[list[tuple[float, float]]] = field(default_factory=list)
    robot: tuple[float, float] | None = None
    robot_degree: float | None = None


def unzip_text(value: str | None) -> str | None:
    """Decode a base64 + gzip field; return ``None`` when it is not one."""
    if not value:
        return None
    try:
        raw = base64.b64decode(value)
    except (ValueError, TypeError):
        return None
    if raw[:2] != b"\x1f\x8b":
        return None
    try:
        return gzip.decompress(raw).decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _add_run(runs: dict[str, list[list[int]]], kind: str, x: int, y: int) -> None:
    bucket = runs.setdefault(kind, [])
    last = bucket[-1] if bucket else None
    if last is not None and last[1] == y and last[0] + last[2] == x:
        last[2] += 1
    else:
        bucket.append([x, y, 1])


def _me2_types(text: str) -> list[str | None]:
    result: list[str | None] = []
    for char in text:
        code = ord(char)
        if code & 4:
            result.append(CELL_FLOOR)
        elif code & 2:
            result.append(CELL_WALL)
        elif code & 8:
            result.append(CELL_OBSTACLE)
        else:
            result.append(None)
    return result


def _legacy_types(text: str) -> list[str | None]:
    expanded = _RLE.sub(lambda m: m.group(1) * int(m.group(2)), text)
    result: list[str | None] = []
    for char in expanded:
        value = _B64_VALUE.get(char, 0)
        for part in ((value >> 3) & 7, value & 7):
            result.append(_LEGACY_TYPES.get(part))
    return result


def decode_grid(layer: Mapping[str, Any]) -> Grid | None:
    """Decode the ``mapData`` grid of a map layer."""
    try:
        x, y, w, h = (int(layer[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    extra = layer.get("extra") if isinstance(layer.get("extra"), Mapping) else {}
    encoding = str(extra.get("mapEncodeType") or "").lower()
    data = layer.get("mapData")
    text = unzip_text(data) if isinstance(data, str) else None
    if text is not None and (encoding.startswith("me") or not encoding):
        types = _me2_types(text)
    elif isinstance(data, str):
        types = _legacy_types(data)
    else:
        return None

    runs: dict[str, list[list[int]]] = {}
    for index, kind in enumerate(types[: w * h]):
        if kind is not None:
            _add_run(runs, kind, x + index % w, y + index // w)
    return Grid(x, y, w, h, {k: [tuple(r) for r in v] for k, v in runs.items()})


def _points(value: str | None) -> list[list[tuple[float, float]]]:
    """Parse ``x,y;x,y|...``; compressed values are delta encoded."""
    if not value:
        return []
    absolute = "," in value
    text = value if absolute else unzip_text(value)
    if not text:
        return []
    segments: list[list[tuple[float, float]]] = []
    cx = cy = 0.0
    first = True
    for segment in text.split("|"):
        points: list[tuple[float, float]] = []
        for pair in segment.split(";"):
            parts = pair.split(",")
            if len(parts) < 2 or not parts[0] or not parts[1]:
                continue
            try:
                px, py = float(parts[0]), float(parts[1])
            except ValueError:
                continue
            if absolute or first:
                cx, cy = px, py
                first = False
            else:
                cx += px
                cy += py
            points.append((cx, cy))
        if points:
            segments.append(points)
    return segments


def decode_rooms(layer: Mapping[str, Any]) -> dict[int, list[tuple[float, float]]]:
    """Return ``room id -> outline`` from a region layer."""
    rooms: dict[int, list[tuple[float, float]]] = {}
    for room in layer.get("room") or []:
        if not isinstance(room, Mapping):
            continue
        try:
            room_id = int(room["roomID"])
        except (KeyError, TypeError, ValueError):
            continue
        outline = [p for segment in _points(room.get("coordinate")) for p in segment]
        if len(outline) >= 3:
            rooms[room_id] = outline
    return rooms


def decode_path(layer: Mapping[str, Any]) -> list[list[tuple[float, float]]]:
    """Return the cleaning path as line segments."""
    return _points(layer.get("pathdata"))


def _position(value: Any) -> tuple[tuple[float, float] | None, float | None]:
    if not isinstance(value, Mapping):
        return None, None
    try:
        point = (float(value["x"]), float(value["y"]))
    except (KeyError, TypeError, ValueError):
        return None, None
    degree = value.get("degree")
    return point, float(degree) if isinstance(degree, (int, float)) else None


def build_layers(
    map_layer: Mapping[str, Any] | None,
    region_layer: Mapping[str, Any] | None,
    path_layer: Mapping[str, Any] | None,
) -> MapLayers:
    """Combine decoded layers."""
    layers = MapLayers()
    if isinstance(map_layer, Mapping):
        layers.grid = decode_grid(map_layer)
        try:
            layers.charger = (
                float(map_layer["chargerX"]),
                float(map_layer["chargerY"]),
            )
        except (KeyError, TypeError, ValueError):
            layers.charger = None
        extra = (
            map_layer.get("extra")
            if isinstance(map_layer.get("extra"), Mapping)
            else {}
        )
        degree = extra.get("chargerDegree", map_layer.get("chargerDegree"))
        layers.charger_degree = (
            float(degree) if isinstance(degree, (int, float)) else None
        )
    if isinstance(region_layer, Mapping):
        layers.rooms = decode_rooms(region_layer)
    if isinstance(path_layer, Mapping):
        layers.path = decode_path(path_layer)
        layers.robot, layers.robot_degree = _position(path_layer.get("currentPosition"))
    return layers
