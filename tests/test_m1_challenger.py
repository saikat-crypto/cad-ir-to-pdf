"""
test_m1_challenger.py — Adversarial Stress-Test and Fuzzing Suite for Milestone M1.

Attacks:
1. curves.py: arc_to_cubic_beziers & circle_to_cubic_beziers with NaN/Inf angles,
   negative/zero radius, near-zero sweeps (1e-12 deg), full sweeps (359.999999999, 360, 720),
   negative angles, verifying no ValueError/RecursionError and radial error < 0.05%.
2. AffineMatrix2D: singular matrices (det=0), near-singular (|det| < 1e-12),
   negative scaling (reflection parity), inversion roundtrips, and matrix associativity.
3. calculate_arc_bbox: quadrant boundaries (0, 90, 180, 270), negative angles, full sweeps.
"""

import math
import pytest
from typing import List, Tuple
from cad_ir_to_pdf.curves import arc_to_cubic_beziers, circle_to_cubic_beziers
from cad_ir_to_pdf.geometry import (
    AffineMatrix2D,
    SingularMatrixError,
    calculate_arc_bbox,
    BoundingBox,
    is_valid_point,
)


# =============================================================================
# Helper: Cubic Bezier Evaluator
# =============================================================================
def eval_bezier(p0: Tuple[float, float], p1: Tuple[float, float],
                p2: Tuple[float, float], p3: Tuple[float, float], t: float) -> Tuple[float, float]:
    """Evaluates 2D cubic Bezier at parameter t in [0, 1]."""
    u = 1.0 - t
    bx = (u**3 * p0[0]) + (3.0 * u**2 * t * p1[0]) + (3.0 * u * t**2 * p2[0]) + (t**3 * p3[0])
    by = (u**3 * p0[1]) + (3.0 * u**2 * t * p1[1]) + (3.0 * u * t**2 * p2[1]) + (t**3 * p3[1])
    return (bx, by)


# =============================================================================
# 1. curves.py: arc_to_cubic_beziers & circle_to_cubic_beziers Adversarial Tests
# =============================================================================

class TestCurvesAdversarial:
    """Stress tests attacking curves.py."""

    @pytest.mark.parametrize("nan_inf_val", [
        float("nan"), float("inf"), float("-inf")
    ])
    def test_curves_nan_inf_angles(self, nan_inf_val: float):
        """Probe arc_to_cubic_beziers with NaN/Inf angles; must not raise ValueError or RecursionError."""
        # NaN/Inf start angle
        pt1, segs1 = arc_to_cubic_beziers(0.0, 0.0, 10.0, nan_inf_val, 90.0)
        assert len(segs1) == 0
        assert math.isfinite(pt1[0]) and math.isfinite(pt1[1])

        # NaN/Inf end angle
        pt2, segs2 = arc_to_cubic_beziers(0.0, 0.0, 10.0, 0.0, nan_inf_val)
        assert len(segs2) == 0
        assert math.isfinite(pt2[0]) and math.isfinite(pt2[1])

        # Both NaN/Inf
        pt3, segs3 = arc_to_cubic_beziers(0.0, 0.0, 10.0, nan_inf_val, nan_inf_val)
        assert len(segs3) == 0
        assert math.isfinite(pt3[0]) and math.isfinite(pt3[1])

    @pytest.mark.parametrize("nan_inf_val", [
        float("nan"), float("inf"), float("-inf")
    ])
    def test_curves_nan_inf_center_and_radius(self, nan_inf_val: float):
        """Probe center and radius with NaN/Inf; must return safe fallback without crashing."""
        pt1, segs1 = arc_to_cubic_beziers(nan_inf_val, 0.0, 10.0, 0.0, 90.0)
        assert len(segs1) == 0
        assert math.isfinite(pt1[0]) and math.isfinite(pt1[1])

        pt2, segs2 = arc_to_cubic_beziers(0.0, 0.0, nan_inf_val, 0.0, 90.0)
        assert len(segs2) == 0
        assert math.isfinite(pt2[0]) and math.isfinite(pt2[1])

        cpt, csegs = circle_to_cubic_beziers(0.0, 0.0, nan_inf_val)
        assert len(csegs) == 0
        assert math.isfinite(cpt[0]) and math.isfinite(cpt[1])

    @pytest.mark.parametrize("bad_radius", [
        0.0, -0.0, -1e-15, -1e-6, -1.0, -100.0, -1e9
    ])
    def test_curves_negative_and_zero_radius(self, bad_radius: float):
        """Negative and zero radius must return empty segments without raising exceptions."""
        pt_arc, segs_arc = arc_to_cubic_beziers(50.0, 50.0, bad_radius, 0.0, 180.0)
        assert len(segs_arc) == 0
        assert math.isfinite(pt_arc[0]) and math.isfinite(pt_arc[1])

        pt_circ, segs_circ = circle_to_cubic_beziers(50.0, 50.0, bad_radius)
        assert len(segs_circ) == 0
        assert math.isfinite(pt_circ[0]) and math.isfinite(pt_circ[1])

    @pytest.mark.parametrize("sweep_delta", [
        1e-15, 1e-12, 1e-9, 1e-7, 5e-7
    ])
    def test_arc_near_zero_sweeps(self, sweep_delta: float):
        """Near-zero sweeps (< 1e-6) must be safely treated as degenerate point arcs."""
        for base_angle in [0.0, 45.0, 90.0, 180.0, 270.0, 315.0]:
            start_deg = base_angle
            end_deg = base_angle + sweep_delta
            start_pt, segments = arc_to_cubic_beziers(10.0, 20.0, 5.0, start_deg, end_deg)
            # Under 1e-6 delta, degenerate point arc is returned
            assert len(segments) == 0
            expected_x = 10.0 + 5.0 * math.cos(math.radians(base_angle))
            expected_y = 20.0 + 5.0 * math.sin(math.radians(base_angle))
            assert math.isclose(start_pt[0], expected_x, abs_tol=1e-5)
            assert math.isclose(start_pt[1], expected_y, abs_tol=1e-5)

    @pytest.mark.parametrize("start, end, desc", [
        (0.0, 359.999999999, "near 360 sweep"),
        (0.0, 360.0, "exact 360 sweep"),
        (0.0, 720.0, "double turn 720 sweep"),
        (-180.0, 180.0, "negative to positive 360 sweep"),
        (720.0, 1080.0, "offset 360 sweep"),
        (45.0, 405.0, "arbitrary start 360 sweep"),
    ])
    def test_arc_full_sweeps(self, start: float, end: float, desc: float):
        """Full sweeps must delegate cleanly to circle decomposition with exactly 4 segments and no recursion error."""
        cx, cy, r = 10.0, 20.0, 15.0
        start_pt, segments = arc_to_cubic_beziers(cx, cy, r, start, end)
        assert len(segments) == 4, f"Failed on {desc}: expected 4 segments, got {len(segments)}"
        # Start point should be (cx + r, cy) as delegated to circle
        assert math.isclose(start_pt[0], cx + r, abs_tol=1e-5)
        assert math.isclose(start_pt[1], cy, abs_tol=1e-5)
        # Final end point should close the circle
        last_seg = segments[-1]
        assert math.isclose(last_seg[4], cx + r, abs_tol=1e-5)
        assert math.isclose(last_seg[5], cy, abs_tol=1e-5)

    @pytest.mark.parametrize("start_deg, end_deg", [
        (-90.0, 0.0),
        (-180.0, -90.0),
        (-270.0, -180.0),
        (-360.0, -270.0),
        (-45.0, 45.0),
        (-720.0, -630.0),
    ])
    def test_arc_negative_angles(self, start_deg: float, end_deg: float):
        """Negative angles must be normalized cleanly into [0, 360) and render correct CCW geometry."""
        cx, cy, r = 0.0, 0.0, 10.0
        start_pt, segments = arc_to_cubic_beziers(cx, cy, r, start_deg, end_deg)
        assert len(segments) >= 1
        # Start point matches start_deg
        expected_s_rad = math.radians(start_deg % 360.0)
        assert math.isclose(start_pt[0], cx + r * math.cos(expected_s_rad), abs_tol=1e-5)
        assert math.isclose(start_pt[1], cy + r * math.sin(expected_s_rad), abs_tol=1e-5)
        # End point matches end_deg
        expected_e_rad = math.radians(end_deg % 360.0)
        last_seg = segments[-1]
        assert math.isclose(last_seg[4], cx + r * math.cos(expected_e_rad), abs_tol=1e-5)
        assert math.isclose(last_seg[5], cy + r * math.sin(expected_e_rad), abs_tol=1e-5)

    @pytest.mark.parametrize("sweep_deg", [
        1.0, 10.0, 30.0, 45.0, 60.0, 75.0, 90.0, 135.0, 180.0, 270.0, 359.0
    ])
    @pytest.mark.parametrize("radius", [
        0.001, 1.0, 50.0, 1000.0
    ])
    def test_arc_bezier_radial_error_under_0_05_percent(self, sweep_deg: float, radius: float):
        """The maximum relative radial error of all cubic Bezier segments must be strictly < 0.05%."""
        cx, cy = 25.0, -15.0
        start_angle = 33.0
        end_angle = start_angle + sweep_deg

        start_pt, segments = arc_to_cubic_beziers(cx, cy, radius, start_angle, end_angle)
        assert len(segments) > 0

        # Validate radial error across each segment at 21 sample points (t = 0.0 to 1.0 step 0.05)
        curr_pt = start_pt
        for seg in segments:
            p0 = curr_pt
            p1 = (seg[0], seg[1])
            p2 = (seg[2], seg[3])
            p3 = (seg[4], seg[5])

            for step in range(21):
                t = step / 20.0
                bx, by = eval_bezier(p0, p1, p2, p3, t)
                dist = math.hypot(bx - cx, by - cy)
                rel_error = abs(dist - radius) / radius
                assert rel_error < 0.0005, (
                    f"Radial error {rel_error * 100:.4f}% exceeded 0.05% at t={t} "
                    f"for sweep={sweep_deg} deg, radius={radius}"
                )
            curr_pt = p3

    def test_circle_bezier_radial_error_under_0_05_percent(self):
        """Complete 360-degree circle must have radial error < 0.05% at all sample points."""
        cx, cy, radius = -100.0, 200.0, 75.0
        start_pt, segments = circle_to_cubic_beziers(cx, cy, radius)
        assert len(segments) == 4

        curr_pt = start_pt
        for seg_idx, seg in enumerate(segments):
            p0 = curr_pt
            p1 = (seg[0], seg[1])
            p2 = (seg[2], seg[3])
            p3 = (seg[4], seg[5])

            for step in range(21):
                t = step / 20.0
                bx, by = eval_bezier(p0, p1, p2, p3, t)
                dist = math.hypot(bx - cx, by - cy)
                rel_error = abs(dist - radius) / radius
                assert rel_error < 0.0005, (
                    f"Circle segment {seg_idx} radial error {rel_error * 100:.4f}% exceeds 0.05% at t={t}"
                )
            curr_pt = p3


# =============================================================================
# 2. AffineMatrix2D Adversarial Tests
# =============================================================================

class TestAffineMatrix2DAdversarial:
    """Stress tests attacking AffineMatrix2D."""

    def test_singular_matrices_zero_determinant(self):
        """Singular matrices with det == 0 must be identified and raise SingularMatrixError."""
        # Matrix with all zeros
        m_zero = AffineMatrix2D(0.0, 0.0, 0.0, 0.0, 5.0, 10.0)
        assert m_zero.determinant == 0.0
        assert m_zero.is_singular is True
        with pytest.raises(SingularMatrixError):
            m_zero.inverse()

        # Zero fallback return
        fallback = AffineMatrix2D(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        assert m_zero.inverse(fallback=fallback) is fallback

        # Zero X-scale matrix
        m_zero_x = AffineMatrix2D(a=0.0, b=0.0, c=0.0, d=2.0)
        assert m_zero_x.determinant == 0.0
        assert m_zero_x.is_singular is True
        with pytest.raises(SingularMatrixError):
            m_zero_x.inverse()

        # Linearly dependent rows (a*d - b*c = 2*6 - 4*3 = 0)
        m_dep = AffineMatrix2D(a=2.0, b=4.0, c=3.0, d=6.0)
        assert m_dep.determinant == 0.0
        assert m_dep.is_singular is True
        with pytest.raises(SingularMatrixError):
            m_dep.inverse()

    @pytest.mark.parametrize("det_val", [
        1e-13, -1e-13, 1e-15, -1e-15, 0.0, 5e-13
    ])
    def test_near_singular_matrices(self, det_val: float):
        """Near-singular matrices (|det| < 1e-12) must be flagged as is_singular and guarded against zero-division."""
        # Construct matrix with determinant == det_val
        m_near = AffineMatrix2D(a=det_val, b=0.0, c=0.0, d=1.0)
        assert abs(m_near.determinant - det_val) < 1e-18
        assert m_near.is_singular is True
        with pytest.raises(SingularMatrixError):
            m_near.inverse()

        # Non-finite determinant matrix
        m_nan = AffineMatrix2D(a=float("nan"), b=0.0, c=0.0, d=1.0)
        assert m_nan.is_singular is True
        with pytest.raises(SingularMatrixError):
            m_nan.inverse()

    def test_negative_scaling_reflection_parity(self):
        """Negative scaling (det < 0) must trigger parity correction by swapping arc angles."""
        # Reflection across Y-axis: x' = -x, y' = y => det = -1
        m_refl_x = AffineMatrix2D.from_cad_insert(0.0, 0.0, rotation_deg=0.0, scale_x=-1.0, scale_y=1.0)
        assert m_refl_x.determinant == -1.0
        assert m_refl_x.is_singular is False

        # In CAD, an arc from 0 to 90 deg under x' = -x reflects to [90, 180] deg CCW
        sa, ea = m_refl_x.transform_arc_angles(0.0, 90.0)
        assert math.isclose(sa, 90.0, abs_tol=1e-5)
        assert math.isclose(ea, 180.0, abs_tol=1e-5)

        # Reflection across X-axis: x' = x, y' = -y => det = -1
        m_refl_y = AffineMatrix2D.from_cad_insert(0.0, 0.0, rotation_deg=0.0, scale_x=1.0, scale_y=-1.0)
        assert m_refl_y.determinant == -1.0
        sa_y, ea_y = m_refl_y.transform_arc_angles(0.0, 90.0)
        # 0 -> 0 (or 360), 90 -> 270. With parity flip swapped: sa=270, ea=360 (or 0)
        assert math.isclose(sa_y, 270.0, abs_tol=1e-5)
        assert math.isclose(ea_y, 0.0, abs_tol=1e-5) or math.isclose(ea_y, 360.0, abs_tol=1e-5)

        # Double reflection (det = (-1) * (-1) = +1): parity is preserved, no swap
        m_double_refl = AffineMatrix2D.from_cad_insert(0.0, 0.0, rotation_deg=0.0, scale_x=-1.0, scale_y=-1.0)
        assert m_double_refl.determinant == 1.0
        sa_d, ea_d = m_double_refl.transform_arc_angles(0.0, 90.0)
        assert math.isclose(sa_d, 180.0, abs_tol=1e-5)
        assert math.isclose(ea_d, 270.0, abs_tol=1e-5)

    @pytest.mark.parametrize("rot, sx, sy, tx, ty", [
        (0.0, 2.0, 3.0, 10.0, -20.0),
        (37.5, 1.5, 0.8, -50.0, 100.0),
        (90.0, -1.0, 2.0, 0.0, 0.0),
        (-125.0, 0.5, -1.5, 250.0, -350.0),
        (180.0, 1.0, 1.0, 1000.0, 2000.0),
        (270.0, -2.5, -2.5, -5.0, 15.0),
    ])
    def test_inversion_roundtrips(self, rot: float, sx: float, sy: float, tx: float, ty: float):
        """Invertible matrices must satisfy M @ M^-1 == I and M^-1(M(P)) == P within numerical precision."""
        m = AffineMatrix2D.from_cad_insert(pos_x=tx, pos_y=ty, rotation_deg=rot, scale_x=sx, scale_y=sy)
        assert not m.is_singular
        inv_m = m.inverse()

        # Product M @ inv_m should be identity
        ident_fwd = m @ inv_m
        assert math.isclose(ident_fwd.a, 1.0, abs_tol=1e-7)
        assert math.isclose(ident_fwd.b, 0.0, abs_tol=1e-7)
        assert math.isclose(ident_fwd.c, 0.0, abs_tol=1e-7)
        assert math.isclose(ident_fwd.d, 1.0, abs_tol=1e-7)
        assert math.isclose(ident_fwd.tx, 0.0, abs_tol=1e-7)
        assert math.isclose(ident_fwd.ty, 0.0, abs_tol=1e-7)

        # Product inv_m @ m should be identity
        ident_rev = inv_m @ m
        assert math.isclose(ident_rev.a, 1.0, abs_tol=1e-7)
        assert math.isclose(ident_rev.b, 0.0, abs_tol=1e-7)
        assert math.isclose(ident_rev.c, 0.0, abs_tol=1e-7)
        assert math.isclose(ident_rev.d, 1.0, abs_tol=1e-7)
        assert math.isclose(ident_rev.tx, 0.0, abs_tol=1e-7)
        assert math.isclose(ident_rev.ty, 0.0, abs_tol=1e-7)

        # Point roundtrip
        for test_pt in [(0.0, 0.0), (10.0, 20.0), (-123.456, 789.012), (1e5, -1e5)]:
            fwd_pt = m.transform_point(*test_pt)
            back_pt = inv_m.transform_point(*fwd_pt)
            assert math.isclose(back_pt[0], test_pt[0], abs_tol=1e-6)
            assert math.isclose(back_pt[1], test_pt[1], abs_tol=1e-6)

    def test_matrix_composition_associativity(self):
        """Matrix multiplication must be strictly associative: (M1 @ M2) @ M3 == M1 @ (M2 @ M3)."""
        m1 = AffineMatrix2D(1.2, 0.3, -0.4, 1.5, 10.0, -25.0)
        m2 = AffineMatrix2D(0.8, -0.6, 0.6, 0.8, 30.0, 45.0)
        m3 = AffineMatrix2D(2.0, 0.1, -0.2, 0.5, -5.0, 12.0)

        left = (m1 @ m2) @ m3
        right = m1 @ (m2 @ m3)

        assert math.isclose(left.a, right.a, abs_tol=1e-10)
        assert math.isclose(left.b, right.b, abs_tol=1e-10)
        assert math.isclose(left.c, right.c, abs_tol=1e-10)
        assert math.isclose(left.d, right.d, abs_tol=1e-10)
        assert math.isclose(left.tx, right.tx, abs_tol=1e-10)
        assert math.isclose(left.ty, right.ty, abs_tol=1e-10)

        # Verify on point transformation
        pt = (123.45, -67.89)
        pt_left = left.transform_point(*pt)
        pt_right = right.transform_point(*pt)
        assert math.isclose(pt_left[0], pt_right[0], abs_tol=1e-9)
        assert math.isclose(pt_left[1], pt_right[1], abs_tol=1e-9)


# =============================================================================
# 3. calculate_arc_bbox Adversarial Tests
# =============================================================================

class TestCalculateArcBBoxAdversarial:
    """Stress tests attacking calculate_arc_bbox."""

    def test_exact_quadrant_boundaries_snapping(self):
        """Quadrant boundaries (0, 90, 180, 270 deg) must snap cleanly without float drift."""
        cx, cy, r = 0.0, 0.0, 10.0

        # Quadrant 1: 0 to 90 deg -> [0, 0, 10, 10]
        bb1 = calculate_arc_bbox(cx, cy, r, 0.0, 90.0)
        assert bb1 == (0.0, 0.0, 10.0, 10.0)

        # Quadrant 2: 90 to 180 deg -> [-10, 0, 0, 10]
        bb2 = calculate_arc_bbox(cx, cy, r, 90.0, 180.0)
        assert bb2 == (-10.0, 0.0, 0.0, 10.0)

        # Quadrant 3: 180 to 270 deg -> [-10, -10, 0, 0]
        bb3 = calculate_arc_bbox(cx, cy, r, 180.0, 270.0)
        assert bb3 == (-10.0, -10.0, 0.0, 0.0)

        # Quadrant 4: 270 to 360 deg -> [0, -10, 10, 0]
        bb4 = calculate_arc_bbox(cx, cy, r, 270.0, 360.0)
        assert bb4 == (0.0, -10.0, 10.0, 0.0)

    def test_arc_containing_quadrant_extrema(self):
        """Arcs crossing quadrant boundaries must include exact quadrant extrema."""
        cx, cy, r = 100.0, 200.0, 50.0

        # 45 to 135 deg: spans across 90 deg (top extrema y=cy+r=250.0)
        bb_top = calculate_arc_bbox(cx, cy, r, 45.0, 135.0)
        cos45 = 50.0 * math.cos(math.radians(45.0))
        assert math.isclose(bb_top[0], cx - cos45, abs_tol=1e-5)
        assert math.isclose(bb_top[1], cy + cos45, abs_tol=1e-5)
        assert math.isclose(bb_top[2], cx + cos45, abs_tol=1e-5)
        assert bb_top[3] == 250.0  # Exactly cy + r

        # 315 to 45 deg: spans across 0 deg (right extrema x=cx+r=150.0)
        bb_right = calculate_arc_bbox(cx, cy, r, 315.0, 45.0)
        assert bb_right[2] == 150.0  # Exactly cx + r

    @pytest.mark.parametrize("sa, ea", [
        (-90.0, 0.0),
        (-180.0, -90.0),
        (-270.0, -180.0),
        (-360.0, -270.0),
        (-45.0, 45.0),
    ])
    def test_arc_bbox_negative_angles(self, sa: float, ea: float):
        """Negative angles must yield identical bounding boxes to their positive modulo equivalents."""
        cx, cy, r = 0.0, 0.0, 10.0
        bb_neg = calculate_arc_bbox(cx, cy, r, sa, ea)

        pos_sa = sa % 360.0
        pos_ea = ea % 360.0
        bb_pos = calculate_arc_bbox(cx, cy, r, pos_sa, pos_ea)

        assert math.isclose(bb_neg[0], bb_pos[0], abs_tol=1e-5)
        assert math.isclose(bb_neg[1], bb_pos[1], abs_tol=1e-5)
        assert math.isclose(bb_neg[2], bb_pos[2], abs_tol=1e-5)
        assert math.isclose(bb_neg[3], bb_pos[3], abs_tol=1e-5)

    @pytest.mark.parametrize("sa, ea", [
        (0.0, 360.0),
        (0.0, 359.999999999),
        (0.0, 720.0),
        (-180.0, 180.0),
        (10.0, 370.0),
        (45.0, 765.0),
    ])
    def test_arc_bbox_full_and_multi_turn_sweeps(self, sa: float, ea: float):
        """Full sweeps and multi-turn sweeps must yield full circle bounding box."""
        cx, cy, r = 50.0, -50.0, 25.0
        bbox = calculate_arc_bbox(cx, cy, r, sa, ea)
        assert bbox == (cx - r, cy - r, cx + r, cy + r)

    def test_arc_bbox_degenerate_zero_sweep(self):
        """Zero sweep (sa == ea) must yield single point bounding box (x, y, x, y)."""
        cx, cy, r = 0.0, 0.0, 10.0
        bbox = calculate_arc_bbox(cx, cy, r, 90.0, 90.0)
        assert bbox == (0.0, 10.0, 0.0, 10.0)

    @pytest.mark.parametrize("bad_val", [
        float("nan"), float("inf"), float("-inf")
    ])
    def test_arc_bbox_nan_inf_safety(self, bad_val: float):
        """NaN and Inf inputs must not raise unhandled exceptions and must return finite numbers."""
        bbox1 = calculate_arc_bbox(bad_val, 0.0, 10.0, 0.0, 90.0)
        assert all(math.isfinite(v) for v in bbox1)

        bbox2 = calculate_arc_bbox(0.0, 0.0, bad_val, 0.0, 90.0)
        assert all(math.isfinite(v) for v in bbox2)

        bbox3 = calculate_arc_bbox(0.0, 0.0, 10.0, bad_val, 90.0)
        assert all(math.isfinite(v) for v in bbox3)
