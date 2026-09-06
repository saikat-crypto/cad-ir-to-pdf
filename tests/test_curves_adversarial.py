"""
test_curves_adversarial.py — Exhaustive Adversarial Challenge Test Suite for curves.py.

Empirical verification covering:
1. Giant arbitrary-precision integers (10**10000, -10**10000) across all parameters.
2. Non-finite values (NaN, +Inf, -Inf) and invalid types (bool, None, str, list, complex).
3. Degenerate radii (<= 0, negative, denormal floats, astronomical floats).
4. Sweep angle boundaries: 0°, near-zero (< 1e-6), 360°, 720°, inverted/CCW sweeps.
5. Spline mathematical precision: G0 continuity, G1 tangent continuity, radial error < 0.05%.
6. Circular recursion prevention under strict recursion limits.
"""

import math
import sys
from typing import Tuple
import pytest
from cad_ir_to_pdf.curves import arc_to_cubic_beziers, circle_to_cubic_beziers

sys.set_int_max_str_digits(0)

GIANT_POS = 10**10000
GIANT_NEG = -10**10000


def eval_bezier(p0: Tuple[float, float], p1: Tuple[float, float],
                p2: Tuple[float, float], p3: Tuple[float, float], t: float) -> Tuple[float, float]:
    """Evaluates cubic Bézier curve at parameter t in [0, 1]."""
    u = 1.0 - t
    bx = (u**3 * p0[0]) + (3.0 * u**2 * t * p1[0]) + (3.0 * u * t**2 * p2[0]) + (t**3 * p3[0])
    by = (u**3 * p0[1]) + (3.0 * u**2 * t * p1[1]) + (3.0 * u * t**2 * p2[1]) + (t**3 * p3[1])
    return (bx, by)


def eval_bezier_deriv(p0: Tuple[float, float], p1: Tuple[float, float],
                      p2: Tuple[float, float], p3: Tuple[float, float], t: float) -> Tuple[float, float]:
    """Evaluates first derivative (tangent) of cubic Bézier curve at parameter t in [0, 1]."""
    u = 1.0 - t
    dx = 3.0 * u**2 * (p1[0] - p0[0]) + 6.0 * u * t * (p2[0] - p1[0]) + 3.0 * t**2 * (p3[0] - p2[0])
    dy = 3.0 * u**2 * (p1[1] - p0[1]) + 6.0 * u * t * (p2[1] - p1[1]) + 3.0 * t**2 * (p3[1] - p2[1])
    return (dx, dy)


# =============================================================================
# 1. Giant Integers (Arbitrary Precision Overflow Resilience)
# =============================================================================

class TestCurvesGiantIntegers:
    """Stress tests verifying immunity to OverflowError when int too large to convert to float."""

    @pytest.mark.parametrize("giant", [GIANT_POS, GIANT_NEG], ids=["giant_pos", "giant_neg"])
    def test_circle_giant_center(self, giant: int):
        assert circle_to_cubic_beziers(giant, 0.0, 10.0) == ((0.0, 0.0), [])
        assert circle_to_cubic_beziers(0.0, giant, 10.0) == ((0.0, 0.0), [])
        assert circle_to_cubic_beziers(giant, giant, 10.0) == ((0.0, 0.0), [])

    @pytest.mark.parametrize("giant", [GIANT_POS, GIANT_NEG], ids=["giant_pos", "giant_neg"])
    def test_circle_giant_radius(self, giant: int):
        assert circle_to_cubic_beziers(0.0, 0.0, giant) == ((0.0, 0.0), [])

    @pytest.mark.parametrize("giant", [GIANT_POS, GIANT_NEG], ids=["giant_pos", "giant_neg"])
    def test_arc_giant_center_and_radius(self, giant: int):
        assert arc_to_cubic_beziers(giant, 0.0, 10.0, 0.0, 90.0) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, giant, 10.0, 0.0, 90.0) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, 0.0, giant, 0.0, 90.0) == ((0.0, 0.0), [])

    @pytest.mark.parametrize("giant", [GIANT_POS, GIANT_NEG], ids=["giant_pos", "giant_neg"])
    def test_arc_giant_angles(self, giant: int):
        assert arc_to_cubic_beziers(0.0, 0.0, 10.0, giant, 90.0) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, 0.0, 10.0, 0.0, giant) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, 0.0, 10.0, giant, giant) == ((0.0, 0.0), [])

    def test_arc_all_parameters_giant_combinatorial(self):
        """Exhaustive matrix of normal and giant values across all 5 parameters."""
        vals = [0.0, GIANT_POS, GIANT_NEG]
        for cx in vals:
            for cy in vals:
                for r in [10.0, GIANT_POS, GIANT_NEG]:
                    for sa in vals:
                        for ea in [90.0, GIANT_POS, GIANT_NEG]:
                            res = arc_to_cubic_beziers(cx, cy, r, sa, ea)
                            is_giant = any(v in (GIANT_POS, GIANT_NEG) for v in (cx, cy, r, sa, ea))
                            if is_giant:
                                assert res == ((0.0, 0.0), [])


# =============================================================================
# 2. Non-Finite Values & Invalid Types
# =============================================================================

class TestCurvesNonFiniteAndTypes:
    """Stress tests verifying robustness against IEEE non-finite floats and malformed types."""

    @pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
    def test_circle_non_finite(self, non_finite: float):
        assert circle_to_cubic_beziers(non_finite, 0.0, 10.0) == ((0.0, 0.0), [])
        assert circle_to_cubic_beziers(0.0, non_finite, 10.0) == ((0.0, 0.0), [])
        assert circle_to_cubic_beziers(0.0, 0.0, non_finite) == ((0.0, 0.0), [])

    @pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
    def test_arc_non_finite(self, non_finite: float):
        assert arc_to_cubic_beziers(non_finite, 0.0, 10.0, 0.0, 90.0) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, non_finite, 10.0, 0.0, 90.0) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, 0.0, non_finite, 0.0, 90.0) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, 0.0, 10.0, non_finite, 90.0) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, 0.0, 10.0, 0.0, non_finite) == ((0.0, 0.0), [])

    @pytest.mark.parametrize("bad_val", [
        True, False, None, "10", "abc", "", [1.0], (1.0,), {"r": 10}, 1 + 2j
    ])
    def test_circle_invalid_types(self, bad_val):
        assert circle_to_cubic_beziers(bad_val, 0.0, 10.0) == ((0.0, 0.0), [])
        assert circle_to_cubic_beziers(0.0, bad_val, 10.0) == ((0.0, 0.0), [])
        assert circle_to_cubic_beziers(0.0, 0.0, bad_val) == ((0.0, 0.0), [])

    @pytest.mark.parametrize("bad_val", [
        True, False, None, "10", "abc", "", [1.0], (1.0,), {"r": 10}, 1 + 2j
    ])
    def test_arc_invalid_types(self, bad_val):
        assert arc_to_cubic_beziers(bad_val, 0.0, 10.0, 0.0, 90.0) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, bad_val, 10.0, 0.0, 90.0) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, 0.0, bad_val, 0.0, 90.0) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, 0.0, 10.0, bad_val, 90.0) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, 0.0, 10.0, 0.0, bad_val) == ((0.0, 0.0), [])


# =============================================================================
# 3. Degenerate Radii
# =============================================================================

class TestCurvesDegenerateRadii:
    """Stress tests on zero, negative, subnormal, and extreme radii."""

    @pytest.mark.parametrize("bad_r", [
        0.0, -0.0, -1e-15, -1e-6, -1.0, -100.0, -1e9, float("-inf")
    ])
    def test_negative_and_zero_radii(self, bad_r: float):
        assert circle_to_cubic_beziers(0.0, 0.0, bad_r) == ((0.0, 0.0), [])
        assert arc_to_cubic_beziers(0.0, 0.0, bad_r, 0.0, 90.0) == ((0.0, 0.0), [])

    @pytest.mark.parametrize("subnormal_r", [
        1e-15, 1e-100, 1e-300, 5e-324
    ])
    def test_subnormal_positive_radii(self, subnormal_r: float):
        # Must produce valid segments without crashing or generating NaNs
        s_c, segs_c = circle_to_cubic_beziers(0.0, 0.0, subnormal_r)
        assert len(segs_c) == 4
        assert all(math.isfinite(coord) for seg in segs_c for coord in seg)

        s_a, segs_a = arc_to_cubic_beziers(0.0, 0.0, subnormal_r, 0.0, 90.0)
        assert len(segs_a) == 1
        assert all(math.isfinite(coord) for seg in segs_a for coord in seg)

    @pytest.mark.parametrize("extreme_r", [
        1e6, 1e12, 1e50, 1e100
    ])
    def test_astronomical_positive_radii(self, extreme_r: float):
        s_c, segs_c = circle_to_cubic_beziers(0.0, 0.0, extreme_r)
        assert len(segs_c) == 4
        assert all(math.isfinite(coord) for seg in segs_c for coord in seg)


# =============================================================================
# 4. Sweep Angle Boundaries & Inverted Sweeps
# =============================================================================

class TestCurvesSweepAngles:
    """Tests testing 0°, 360°, 720°, and inverted sweeps."""

    @pytest.mark.parametrize("angle", [0.0, 45.0, 90.0, 180.0, 270.0, 360.0, -90.0, -180.0])
    def test_zero_sweep_exact(self, angle: float):
        """Identical start and end angle must return degenerate point arc with 0 segments."""
        pt, segs = arc_to_cubic_beziers(10.0, 20.0, 50.0, angle, angle)
        assert len(segs) == 0
        rad = math.radians(angle)
        assert math.isclose(pt[0], 10.0 + 50.0 * math.cos(rad), abs_tol=1e-5)
        assert math.isclose(pt[1], 20.0 + 50.0 * math.sin(rad), abs_tol=1e-5)

    @pytest.mark.parametrize("delta", [1e-9, 1e-7, 5e-7, 9.9e-7])
    def test_near_zero_sweep_tolerance(self, delta: float):
        """Sweeps within 1e-6 must return degenerate point arc."""
        pt, segs = arc_to_cubic_beziers(0.0, 0.0, 10.0, 30.0, 30.0 + delta)
        assert len(segs) == 0

    @pytest.mark.parametrize("start_angle, end_angle", [
        (0.0, 360.0),
        (0.0, -360.0),
        (45.0, 405.0),
        (405.0, 45.0),
        (-180.0, 180.0),
        (180.0, -180.0),
        (360.0, 0.0),
        (-360.0, 0.0),
    ])
    def test_exact_360_sweep(self, start_angle: float, end_angle: float):
        """360-degree sweep must delegate cleanly to circle_to_cubic_beziers."""
        c_pt, c_segs = circle_to_cubic_beziers(5.0, 5.0, 25.0)
        pt, segs = arc_to_cubic_beziers(5.0, 5.0, 25.0, start_angle, end_angle)
        assert len(segs) == 4
        assert pt == c_pt
        assert segs == c_segs

    @pytest.mark.parametrize("start_angle, end_angle", [
        (0.0, 720.0),
        (0.0, -720.0),
        (45.0, 765.0),
        (765.0, 45.0),
        (0.0, 1080.0),
        (-1080.0, 0.0),
    ])
    def test_multi_turn_720_sweep(self, start_angle: float, end_angle: float):
        """Sweeps >= 360° must safely delegate to circle_to_cubic_beziers."""
        c_pt, c_segs = circle_to_cubic_beziers(0.0, 0.0, 10.0)
        pt, segs = arc_to_cubic_beziers(0.0, 0.0, 10.0, start_angle, end_angle)
        assert len(segs) == 4
        assert pt == c_pt
        assert segs == c_segs

    def test_inverted_ccw_sweeps(self):
        """Verify counter-clockwise traversal when end angle < start angle in [0, 360)."""
        # 90° -> 0° is 270° sweep CCW
        pt, segs = arc_to_cubic_beziers(0.0, 0.0, 10.0, 90.0, 0.0)
        assert len(segs) == 3
        assert math.isclose(pt[0], 0.0, abs_tol=1e-5)
        assert math.isclose(pt[1], 10.0, abs_tol=1e-5)
        assert math.isclose(segs[-1][4], 10.0, abs_tol=1e-5)
        assert math.isclose(segs[-1][5], 0.0, abs_tol=1e-5)

        # 0° -> -90° (which is 270°) is 270° sweep CCW
        pt2, segs2 = arc_to_cubic_beziers(0.0, 0.0, 10.0, 0.0, -90.0)
        assert len(segs2) == 3
        assert math.isclose(segs2[-1][4], 0.0, abs_tol=1e-5)
        assert math.isclose(segs2[-1][5], -10.0, abs_tol=1e-5)

        # -90° -> 0° is 90° sweep CCW
        pt3, segs3 = arc_to_cubic_beziers(0.0, 0.0, 10.0, -90.0, 0.0)
        assert len(segs3) == 1
        assert math.isclose(segs3[-1][4], 10.0, abs_tol=1e-5)
        assert math.isclose(segs3[-1][5], 0.0, abs_tol=1e-5)


# =============================================================================
# 5. Spline Mathematical Precision & Smoothness
# =============================================================================

class TestCurvesMathematicalAccuracy:
    """Rigorous verification of G0 continuity, G1 tangent continuity, and < 0.05% radial error."""

    def test_circle_spline_continuity_and_accuracy(self):
        cx, cy, r = 12.3, -45.6, 78.9
        start_pt, segs = circle_to_cubic_beziers(cx, cy, r)
        assert len(segs) == 4

        cur_p = start_pt
        max_err = 0.0
        for i, seg in enumerate(segs):
            p0 = cur_p
            p1 = (seg[0], seg[1])
            p2 = (seg[2], seg[3])
            p3 = (seg[4], seg[5])

            # Sample 20 points along the segment
            for step in range(21):
                t = step / 20.0
                x, y = eval_bezier(p0, p1, p2, p3, t)
                dist = math.hypot(x - cx, y - cy)
                rel_err = abs(dist - r) / r
                max_err = max(max_err, rel_err)
                assert rel_err < 0.0005, f"Radial error {rel_err} exceeds 0.05% on circle"

            # Check G1 continuity at boundary with next segment
            next_seg = segs[(i + 1) % len(segs)]
            dx1, dy1 = eval_bezier_deriv(p0, p1, p2, p3, 1.0)
            dx2, dy2 = eval_bezier_deriv(p3, (next_seg[0], next_seg[1]), (next_seg[2], next_seg[3]), (next_seg[4], next_seg[5]), 0.0)
            u1 = (dx1 / math.hypot(dx1, dy1), dy1 / math.hypot(dx1, dy1))
            u2 = (dx2 / math.hypot(dx2, dy2), dy2 / math.hypot(dx2, dy2))
            dot = u1[0] * u2[0] + u1[1] * u2[1]
            assert math.isclose(dot, 1.0, abs_tol=1e-5), f"Circle G1 discontinuity at junction {i}: dot={dot}"

            cur_p = p3

        # Closed curve check
        assert math.isclose(cur_p[0], start_pt[0], abs_tol=1e-5)
        assert math.isclose(cur_p[1], start_pt[1], abs_tol=1e-5)
        # Standard 4-quadrant cubic Bézier relative radial error is ~0.0273%
        assert max_err < 0.0003

    @pytest.mark.parametrize("sa, ea", [
        (0.0, 45.0),
        (0.0, 90.0),
        (45.0, 135.0),
        (0.0, 180.0),
        (0.0, 270.0),
        (30.0, 315.0),
        (350.0, 20.0),
        (-45.0, 45.0),
    ])
    def test_arc_spline_continuity_and_accuracy(self, sa: float, ea: float):
        cx, cy, r = 100.0, 200.0, 50.0
        start_pt, segs = arc_to_cubic_beziers(cx, cy, r, sa, ea)
        assert len(segs) >= 1

        # Check endpoints
        sa_rad = math.radians(sa % 360.0)
        ea_rad = math.radians(ea % 360.0)
        assert math.isclose(start_pt[0], cx + r * math.cos(sa_rad), abs_tol=1e-4)
        assert math.isclose(start_pt[1], cy + r * math.sin(sa_rad), abs_tol=1e-4)
        assert math.isclose(segs[-1][4], cx + r * math.cos(ea_rad), abs_tol=1e-4)
        assert math.isclose(segs[-1][5], cy + r * math.sin(ea_rad), abs_tol=1e-4)

        cur_p = start_pt
        for i, seg in enumerate(segs):
            p0 = cur_p
            p1 = (seg[0], seg[1])
            p2 = (seg[2], seg[3])
            p3 = (seg[4], seg[5])

            # Radial error check
            for step in range(21):
                t = step / 20.0
                x, y = eval_bezier(p0, p1, p2, p3, t)
                dist = math.hypot(x - cx, y - cy)
                rel_err = abs(dist - r) / r
                assert rel_err < 0.0005, f"Arc radial error {rel_err} exceeds 0.05% for {sa}->{ea}"

            # G1 continuity between adjacent segments
            if i + 1 < len(segs):
                next_seg = segs[i + 1]
                dx1, dy1 = eval_bezier_deriv(p0, p1, p2, p3, 1.0)
                dx2, dy2 = eval_bezier_deriv(p3, (next_seg[0], next_seg[1]), (next_seg[2], next_seg[3]), (next_seg[4], next_seg[5]), 0.0)
                u1 = (dx1 / math.hypot(dx1, dy1), dy1 / math.hypot(dx1, dy1))
                u2 = (dx2 / math.hypot(dx2, dy2), dy2 / math.hypot(dx2, dy2))
                dot = u1[0] * u2[0] + u1[1] * u2[1]
                assert math.isclose(dot, 1.0, abs_tol=1e-5), f"Arc G1 discontinuity at junction {i}"

            cur_p = p3


# =============================================================================
# 6. Circular Recursion Immunity Under Tight Recursion Limit
# =============================================================================

class TestCurvesNoCircularRecursion:
    """Verify that curves functions never enter circular recursion under any circumstances."""

    def test_low_recursion_limit_immunity(self):
        """Even with recursion limit lowered to 50, functions execute without RecursionError."""
        orig_limit = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(50)
            # Full circles
            circle_to_cubic_beziers(0.0, 0.0, 10.0)
            arc_to_cubic_beziers(0.0, 0.0, 10.0, 0.0, 360.0)
            arc_to_cubic_beziers(0.0, 0.0, 10.0, 0.0, 720.0)
            arc_to_cubic_beziers(0.0, 0.0, 10.0, 10.0, 370.0)
            # Giant numbers
            circle_to_cubic_beziers(GIANT_POS, 0.0, 10.0)
            arc_to_cubic_beziers(0.0, 0.0, 10.0, GIANT_POS, GIANT_NEG)
        finally:
            sys.setrecursionlimit(orig_limit)
