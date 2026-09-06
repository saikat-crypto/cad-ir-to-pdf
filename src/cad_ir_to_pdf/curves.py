"""
curves.py — Analytic Arc & Circle to Cubic Bézier converters for PDF vector streams.

PDF graphics operators (canvas.bezier) require Cubic Bézier splines (p0, p1, p2, p3).
This module provides exact piecewise cubic approximations with sub-millimeter precision.
"""

from __future__ import annotations
import math
from typing import List, Tuple

# Type alias: (x1, y1, x2, y2, x3, y3) — control point 1, control point 2, endpoint
CubicBezierSegment = Tuple[float, float, float, float, float, float]


def circle_to_cubic_beziers(
    cx: float,
    cy: float,
    radius: float,
) -> Tuple[Tuple[float, float], List[CubicBezierSegment]]:
    """
    Renders a complete 360-degree circle into 4 optimal cubic Bézier quadrants.
    Self-contained, closed-form implementation to prevent circular recursion with arc_to_cubic_beziers.
    """
    try:
        if not (
            isinstance(cx, (int, float)) and not isinstance(cx, bool) and math.isfinite(cx)
            and isinstance(cy, (int, float)) and not isinstance(cy, bool) and math.isfinite(cy)
            and isinstance(radius, (int, float)) and not isinstance(radius, bool) and math.isfinite(radius)
            and radius > 0.0
        ):
            return ((0.0, 0.0), [])
    except (OverflowError, TypeError):
        return ((0.0, 0.0), [])

    cx = float(cx)
    cy = float(cy)
    r = float(radius)

    # Standard cubic Bézier arc approximation for 90-degree quadrant:
    # da = pi / 2
    # k = 4/3 * tan(da / 4) = 4/3 * tan(pi / 8) = 4/3 * (sqrt(2) - 1) ~ 0.5522847498307936
    k = (4.0 / 3.0) * (math.sqrt(2.0) - 1.0)
    kr = k * r

    start_pt = (cx + r, cy)
    segments: List[CubicBezierSegment] = [
        # Quadrant 1: 0° to 90° (start: (cx+r, cy), end: (cx, cy+r))
        (cx + r, cy + kr, cx + kr, cy + r, cx, cy + r),
        # Quadrant 2: 90° to 180° (start: (cx, cy+r), end: (cx-r, cy))
        (cx - kr, cy + r, cx - r, cy + kr, cx - r, cy),
        # Quadrant 3: 180° to 270° (start: (cx-r, cy), end: (cx, cy-r))
        (cx - r, cy - kr, cx - kr, cy - r, cx, cy - r),
        # Quadrant 4: 270° to 360° (start: (cx, cy-r), end: (cx+r, cy))
        (cx + kr, cy - r, cx + r, cy - kr, cx + r, cy),
    ]
    return (start_pt, segments)


def arc_to_cubic_beziers(
    cx: float,
    cy: float,
    radius: float,
    start_angle_deg: float,
    end_angle_deg: float,
) -> Tuple[Tuple[float, float], List[CubicBezierSegment]]:
    """
    Subdivides an arc into cubic Bézier segments (each segment <= 90 degrees).
    Returns (start_point, list_of_segments) where each segment is (cp1x, cp1y, cp2x, cp2y, endx, endy).
    """
    # 1. Entry guard: reject non-numeric, bool, non-finite, and degenerate/negative radius
    try:
        if not (
            isinstance(cx, (int, float)) and not isinstance(cx, bool) and math.isfinite(cx)
            and isinstance(cy, (int, float)) and not isinstance(cy, bool) and math.isfinite(cy)
            and isinstance(radius, (int, float)) and not isinstance(radius, bool) and math.isfinite(radius)
            and radius > 0.0
            and isinstance(start_angle_deg, (int, float)) and not isinstance(start_angle_deg, bool) and math.isfinite(start_angle_deg)
            and isinstance(end_angle_deg, (int, float)) and not isinstance(end_angle_deg, bool) and math.isfinite(end_angle_deg)
        ):
            return ((0.0, 0.0), [])
    except (OverflowError, TypeError):
        return ((0.0, 0.0), [])

    cx = float(cx)
    cy = float(cy)
    radius = float(radius)
    start_angle_deg = float(start_angle_deg)
    end_angle_deg = float(end_angle_deg)

    # 2. Point arc check: if start and end angles are virtually identical, return degenerate point arc
    if abs(start_angle_deg - end_angle_deg) < 1e-6:
        start_rad = math.radians(start_angle_deg)
        start_pt = (cx + radius * math.cos(start_rad), cy + radius * math.sin(start_rad))
        return (start_pt, [])

    # 3. Full sweep check: if sweep covers or exceeds full 360 degrees, delegate to circle_to_cubic_beziers
    if abs(end_angle_deg - start_angle_deg) >= 360.0 - 1e-6:
        return circle_to_cubic_beziers(cx, cy, radius)

    # 4. Normalize angles and compute sweep in [0, 360)
    start_deg = start_angle_deg % 360.0
    end_deg = end_angle_deg % 360.0
    sweep_deg = end_deg - start_deg
    if sweep_deg <= 0.0:
        sweep_deg += 360.0

    # Defensive check: ensure sweep_deg is strictly finite and positive
    if not math.isfinite(sweep_deg) or sweep_deg <= 0.0:
        return ((cx, cy), [])

    # Number of segments: subdivide so each segment <= 90 deg
    num_segs = max(1, math.ceil(sweep_deg / 90.0))
    seg_sweep = sweep_deg / num_segs

    start_rad = math.radians(start_deg)
    start_pt = (cx + radius * math.cos(start_rad), cy + radius * math.sin(start_rad))

    segments: List[CubicBezierSegment] = []
    current_angle_deg = start_deg

    for _ in range(num_segs):
        next_angle_deg = current_angle_deg + seg_sweep
        a1 = math.radians(current_angle_deg)
        a2 = math.radians(next_angle_deg)
        da = a2 - a1

        # Standard cubic Bézier arc approximation constant
        # k = 4/3 * tan(da / 4)
        k = (4.0 / 3.0) * math.tan(da / 4.0)

        cos_a1, sin_a1 = math.cos(a1), math.sin(a1)
        cos_a2, sin_a2 = math.cos(a2), math.sin(a2)

        # Start of this segment
        p0x = cx + radius * cos_a1
        p0y = cy + radius * sin_a1

        # End of this segment
        p3x = cx + radius * cos_a2
        p3y = cy + radius * sin_a2

        # Control points
        p1x = p0x - k * radius * sin_a1
        p1y = p0y + k * radius * cos_a1

        p2x = p3x + k * radius * sin_a2
        p2y = p3y - k * radius * cos_a2

        segments.append((p1x, p1y, p2x, p2y, p3x, p3y))
        current_angle_deg = next_angle_deg

    return (start_pt, segments)
