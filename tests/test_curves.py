import math
import pytest
from cad_ir_to_pdf.curves import arc_to_cubic_beziers, circle_to_cubic_beziers


def test_circle_to_beziers_segment_count():
    start_pt, segments = circle_to_cubic_beziers(cx=0.0, cy=0.0, radius=10.0)
    # Circle has 360 degrees, divided into <= 90 deg segments => exactly 4 segments
    assert len(segments) == 4
    # Check that start point is on circle
    assert math.isclose(start_pt[0], 10.0, abs_tol=1e-6)
    assert math.isclose(start_pt[1], 0.0, abs_tol=1e-6)
    # Last segment end point should return to start point
    last_end_x, last_end_y = segments[-1][4], segments[-1][5]
    assert math.isclose(last_end_x, 10.0, abs_tol=1e-5)
    assert math.isclose(last_end_y, 0.0, abs_tol=1e-5)


def test_arc_quadrant_endpoint_accuracy():
    # 0 to 90 degrees arc of radius 5 at origin
    start_pt, segments = arc_to_cubic_beziers(cx=0.0, cy=0.0, radius=5.0, start_angle_deg=0.0, end_angle_deg=90.0)
    assert len(segments) == 1
    cp1x, cp1y, cp2x, cp2y, endx, endy = segments[0]
    assert math.isclose(start_pt[0], 5.0, abs_tol=1e-6)
    assert math.isclose(start_pt[1], 0.0, abs_tol=1e-6)
    assert math.isclose(endx, 0.0, abs_tol=1e-5)
    assert math.isclose(endy, 5.0, abs_tol=1e-5)


def test_arc_bezier_midpoint_radial_error():
    # Evaluate radial error at t=0.5 of a 90 deg quadrant
    r = 100.0
    start_pt, segments = arc_to_cubic_beziers(cx=0.0, cy=0.0, radius=r, start_angle_deg=0.0, end_angle_deg=90.0)
    p0x, p0y = start_pt
    cp1x, cp1y, cp2x, cp2y, p3x, p3y = segments[0]

    # Evaluate cubic Bezier at t = 0.5: B(t) = (1-t)^3 p0 + 3(1-t)^2 t p1 + 3(1-t) t^2 p2 + t^3 p3
    t = 0.5
    bx = ((1 - t)**3 * p0x) + (3 * (1 - t)**2 * t * cp1x) + (3 * (1 - t) * t**2 * cp2x) + (t**3 * p3x)
    by = ((1 - t)**3 * p0y) + (3 * (1 - t)**2 * t * cp1y) + (3 * (1 - t) * t**2 * cp2y) + (t**3 * p3y)

    mid_radius = math.hypot(bx, by)
    # The radial error of the standard 90-degree cubic Bezier approximation is ~0.027%
    rel_error = abs(mid_radius - r) / r
    assert rel_error < 0.0005, f"Relative error {rel_error} exceeds 0.05%"
