"""Draw decoded map layers as SVG (no Home Assistant imports).

Rendering adapted from ha-ezviz-vacuum by Stefan Ciubotaru (Apache-2.0).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from xml.sax.saxutils import escape

from .mapdata import CELL_FLOOR, CELL_OBSTACLE, CELL_WALL, MapLayers

ROOM_COLORS = (
    "#2dd4bf",
    "#60a5fa",
    "#a78bfa",
    "#f472b6",
    "#fbbf24",
    "#34d399",
    "#fb923c",
)
PADDING = 6
SCALE = 4  # pixels per cell for viewers that use the intrinsic size


def _runs_path(runs: list[tuple[int, int, int]]) -> str:
    return "".join(f"M{x} {y}h{n}v1h-{n}z" for x, y, n in runs)


def _polygon(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:g},{y:g}" for x, y in points)


def _label_point(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Area centroid of a polygon, falling back to the vertex average."""
    area = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(area) < 1e-6:
        return (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )
    return cx / (3 * area), cy / (3 * area)


def render_svg(
    layers: MapLayers,
    room_names: Mapping[int, str] | None = None,
    *,
    show_path: bool = True,
) -> bytes | None:
    """Return the map as SVG, or ``None`` when there is no grid."""
    grid = layers.grid
    if grid is None:
        return None
    room_names = room_names or {}
    min_x, min_y = grid.x - PADDING, grid.y - PADDING
    width, height = grid.w + 2 * PADDING, grid.h + 2 * PADDING
    font = max(5.0, min(width, height) / 26)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x} {min_y} '
        f'{width} {height}" width="{width * SCALE}" height="{height * SCALE}" '
        'shape-rendering="crispEdges">'
    ]
    # Floor outside rooms (often laser reflections) stays faint.
    if grid.runs.get(CELL_FLOOR):
        parts.append(
            f'<path d="{_runs_path(grid.runs[CELL_FLOOR])}" fill="#64748b" '
            'fill-opacity="0.28"/>'
        )
    for index, (_room_id, points) in enumerate(sorted(layers.rooms.items())):
        color = ROOM_COLORS[index % len(ROOM_COLORS)]
        parts.append(
            f'<polygon points="{_polygon(points)}" fill="{color}" '
            f'fill-opacity="0.55" stroke="{color}" stroke-width="0.6" '
            'shape-rendering="geometricPrecision"/>'
        )
    if grid.runs.get(CELL_WALL):
        parts.append(
            f'<path d="{_runs_path(grid.runs[CELL_WALL])}" fill="#e2e8f0" '
            'fill-opacity="0.85"/>'
        )
    if grid.runs.get(CELL_OBSTACLE):
        parts.append(
            f'<path d="{_runs_path(grid.runs[CELL_OBSTACLE])}" fill="#f59e0b"/>'
        )
    if show_path:
        for segment in layers.path:
            if len(segment) > 1:
                parts.append(
                    f'<polyline points="{_polygon(segment)}" fill="none" '
                    'stroke="#ffffff" stroke-opacity="0.75" stroke-width="0.7" '
                    'stroke-linejoin="round" stroke-linecap="round" '
                    'shape-rendering="geometricPrecision"/>'
                )
    for room_id, points in sorted(layers.rooms.items()):
        name = room_names.get(room_id)
        if not name:
            continue
        x, y = _label_point(points)
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{font:.1f}" '
            'font-family="sans-serif" font-weight="700" fill="#ffffff" '
            'text-anchor="middle" dominant-baseline="middle" '
            'paint-order="stroke" stroke="#0f172a" stroke-opacity="0.55" '
            f'stroke-width="{font / 6:.2f}">{escape(name)}</text>'
        )
    if layers.charger is not None:
        cx, cy = layers.charger
        size = font * 0.9
        parts.append(
            f'<rect x="{cx - size / 2:.1f}" y="{cy - size / 2:.1f}" '
            f'width="{size:.1f}" height="{size:.1f}" rx="{size / 4:.1f}" '
            'fill="#0f172a" stroke="#4ade80" stroke-width="0.8" '
            'shape-rendering="geometricPrecision"/>'
        )
    if layers.robot is not None and layers.robot != layers.charger:
        rx, ry = layers.robot
        radius = font * 0.55
        parts.append(
            f'<circle cx="{rx:.1f}" cy="{ry:.1f}" r="{radius:.1f}" fill="#ffffff" '
            'stroke="#2dd4bf" stroke-width="0.9" shape-rendering="geometricPrecision"/>'
        )
        if layers.robot_degree is not None:
            angle = math.radians(layers.robot_degree)
            hx = rx + math.cos(angle) * radius
            hy = ry - math.sin(angle) * radius
            parts.append(
                f'<line x1="{rx:.1f}" y1="{ry:.1f}" x2="{hx:.1f}" y2="{hy:.1f}" '
                'stroke="#0f172a" stroke-width="0.8" stroke-linecap="round"/>'
            )
    parts.append("</svg>")
    return "".join(parts).encode("utf-8")
