"""
test_m1_it2_adversarial.py — Empirical Adversarial Stress Test Suite for M1 Iteration 2.

Exhaustively tests cad_ir_to_pdf.geometry against:
1. Giant arbitrary-precision integers (10^10000, -10^10000)
2. Degenerate matrices, singular transforms, NaN/Inf handling
3. Outlier detection boundary conditions in find_primary_cluster_1d (N=20, 25, 49, 50, 100)
"""

import math
import sys
import pytest
from typing import List, Tuple

# Ensure integer string conversions don't fail under Python 3.11+
sys.set_int_max_str_digits(25000)

from cad_ir_to_pdf.geometry import (
    BoundingBox,
    AffineMatrix2D,
    SingularMatrixError,
    ViewportMapping,
    calculate_viewport_mapping,
    is_valid_point,
    find_primary_cluster_1d,
    compute_ir_extents,
    compute_primitive_bbox,
    calculate_arc_bbox,
    _safe_float,
    _coerce_matrix_field,
    MIN_WORLD_COORD,
    MAX_WORLD_COORD,
    MIN_SCALE,
    MAX_SCALE,
    MIN_PDF_COORD,
    MAX_PDF_COORD,
)

GIANT_POS = 10**10000
GIANT_NEG = -10**10000
NAN = float("nan")
INF = float("inf")
NINF = float("-inf")


# =============================================================================
# 1. Giant Integers in Geometry Math
# =============================================================================

class TestGiantIntegersGeometry:
    """Stress tests verifying handling of giant integers in geometry.py."""

    def test_safe_float_giant_ints(self):
        """_safe_float must return default when given giant integers without raising OverflowError."""
        assert _safe_float(GIANT_POS) is None
        assert _safe_float(GIANT_NEG) is None
        assert _safe_float(GIANT_POS, default=0.0) == 0.0
        assert _safe_float(GIANT_NEG, default=-1.0) == -1.0

    def test_is_valid_point_giant_ints(self):
        """is_valid_point must safely reject giant integers without raising OverflowError."""
        assert is_valid_point([GIANT_POS, 0.0]) is False
        assert is_valid_point([0.0, GIANT_NEG]) is False
        assert is_valid_point([GIANT_POS, GIANT_NEG]) is False
        assert is_valid_point((GIANT_POS, 0.0, 0.0)) is False

    def test_bounding_box_giant_ints(self):
        """BoundingBox must safely reject giant bounds and ignore giant expand points."""
        b_giant = BoundingBox(min_x=GIANT_POS, min_y=GIANT_NEG, max_x=GIANT_POS, max_y=GIANT_POS)
        assert b_giant.is_valid is False
        assert b_giant.center == (0.0, 0.0)
        assert b_giant.width == 0.0
        assert b_giant.height == 0.0

        b = BoundingBox(min_x=0.0, min_y=0.0, max_x=100.0, max_y=100.0)
        b.expand(GIANT_POS, 50.0)
        b.expand(50.0, GIANT_NEG)
        assert b.min_x == 0.0 and b.max_x == 100.0
        assert b.min_y == 0.0 and b.max_y == 100.0

        b.expand_bbox(b_giant)
        assert b.min_x == 0.0 and b.max_x == 100.0

        # Must not raise AttributeError when called with None or objects lacking is_valid
        b.expand_bbox(None)
        b.expand_bbox("invalid")  # type: ignore
        b.expand_bbox(123)  # type: ignore
        assert b.min_x == 0.0 and b.max_x == 100.0

    def test_calculate_arc_bbox_giant_ints(self):
        """calculate_arc_bbox must return fallback (0,0,0,0) without raising OverflowError."""
        assert calculate_arc_bbox(GIANT_POS, 0, 10, 0, 90) == (0.0, 0.0, 0.0, 0.0)
        assert calculate_arc_bbox(0, GIANT_NEG, 10, 0, 90) == (0.0, 0.0, 0.0, 0.0)
        assert calculate_arc_bbox(0, 0, GIANT_POS, 0, 90) == (0.0, 0.0, 0.0, 0.0)
        assert calculate_arc_bbox(0, 0, 10, GIANT_POS, 90) == (0.0, 0.0, 0.0, 0.0)
        assert calculate_arc_bbox(0, 0, 10, 0, GIANT_NEG) == (0.0, 0.0, 0.0, 0.0)

    def test_compute_primitive_bbox_giant_ints(self):
        """compute_primitive_bbox must safely skip primitives with giant coordinates."""
        prims = {
            "lines": [{"start": [GIANT_POS, 0], "end": [0, GIANT_NEG]}],
            "arcs": [{"center": [GIANT_POS, 0], "radius": GIANT_POS}],
            "circles": [{"center": [0, GIANT_NEG], "radius": GIANT_POS}],
            "polylines": [{"points": [[GIANT_POS, GIANT_POS]]}],
        }
        bbox = compute_primitive_bbox(prims)
        assert bbox.is_valid is False

    def test_compute_ir_extents_giant_ints(self):
        """compute_ir_extents must safely discard giant coordinates and fallback cleanly."""
        ir = {
            "geometry_primitives": {
                "primitives": {
                    "lines": [{"start": [GIANT_POS, 0], "end": [0, GIANT_NEG]}],
                    "arcs": [{"center": [GIANT_POS, 0], "radius": GIANT_POS}],
                    "circles": [{"center": [0, GIANT_NEG], "radius": GIANT_POS}],
                    "polylines": [{"points": [[GIANT_POS, GIANT_POS]]}],
                }
            },
            "components": [
                {
                    "position": [GIANT_POS, GIANT_NEG],
                    "rotation": GIANT_POS,
                    "scale": [GIANT_POS, GIANT_NEG],
                }
            ],
            "annotations": [{"position": [GIANT_POS, 0]}],
            "dimensions": [{"defpoint": [GIANT_POS, 0], "defpoint2": [0, GIANT_NEG]}],
            "extents": {"min": [GIANT_POS, 0], "max": [0, GIANT_NEG]},
        }
        bbox = compute_ir_extents(ir, prune_outliers=True)
        assert bbox.is_valid is True
        assert bbox.center == (50.0, 50.0)  # default fallback (0, 0, 100, 100)

    def test_calculate_viewport_mapping_giant_ints(self):
        """calculate_viewport_mapping must clamp scale within [1e-9, 1e6] on giant inputs."""
        vp = calculate_viewport_mapping(
            cad_bbox=BoundingBox(GIANT_POS, GIANT_NEG, GIANT_POS, GIANT_POS),
            page_width_pt=GIANT_POS,
            page_height_pt=GIANT_NEG,
            margin_pt=GIANT_POS,
            scale_mode="fixed",
            fixed_scale=GIANT_POS,
        )
        assert MIN_SCALE <= vp.scale <= MAX_SCALE
        assert math.isfinite(vp.cad_center_x)
        assert math.isfinite(vp.cad_center_y)
        assert math.isfinite(vp.pdf_center_x)
        assert math.isfinite(vp.pdf_center_y)

        px, py = vp.to_pdf(GIANT_POS, GIANT_NEG)
        assert math.isfinite(px) and math.isfinite(py)
        assert MIN_PDF_COORD <= px <= MAX_PDF_COORD
        assert MIN_PDF_COORD <= py <= MAX_PDF_COORD

        assert vp.to_pdf_length(GIANT_POS) == 0.0

    def test_affine_from_cad_insert_giant_ints(self):
        """AffineMatrix2D.from_cad_insert must safely sanitize giant ints."""
        m = AffineMatrix2D.from_cad_insert(
            pos_x=GIANT_POS,
            pos_y=GIANT_NEG,
            rotation_deg=GIANT_POS,
            scale_x=GIANT_POS,
            scale_y=GIANT_NEG,
            base_x=GIANT_POS,
            base_y=GIANT_NEG,
        )
        assert math.isfinite(m.a)
        assert math.isfinite(m.b)
        assert math.isfinite(m.c)
        assert math.isfinite(m.d)
        assert math.isfinite(m.tx)
        assert math.isfinite(m.ty)


# =============================================================================
# 2. AffineMatrix2D Crash Vulnerabilities Under Giant Integers
# =============================================================================

class TestAffineMatrix2DVulnerabilities:
    """Demonstrates whether AffineMatrix2D methods are crash-proof when instantiated with giant ints."""

    def test_affine_raw_giant_determinant_and_is_singular(self):
        """When linear coefficients are giant ints, determinant returns nan and is_singular is True."""
        m_a = AffineMatrix2D(a=GIANT_POS)
        assert math.isnan(m_a.determinant)
        assert m_a.is_singular is True

        m_b = AffineMatrix2D(b=GIANT_NEG)
        assert math.isnan(m_b.determinant)
        assert m_b.is_singular is True

    def test_affine_raw_giant_tx_is_singular_and_safe_inverse(self):
        """When tx=10**10000, matrix is flagged as singular and inverse raises SingularMatrixError."""
        m = AffineMatrix2D(tx=GIANT_POS)
        assert m.is_singular is True
        with pytest.raises(SingularMatrixError):
            m.inverse()

    def test_affine_raw_giant_ty_is_singular_and_safe_inverse(self):
        """When ty=10**10000, matrix is flagged as singular and inverse raises SingularMatrixError."""
        m = AffineMatrix2D(ty=GIANT_POS)
        assert m.is_singular is True
        with pytest.raises(SingularMatrixError):
            m.inverse()

    def test_affine_raw_giant_inverse_with_fallback(self):
        """When tx=10**10000 and fallback is supplied, m.inverse(fallback=...) cleanly returns fallback."""
        m = AffineMatrix2D(tx=GIANT_POS)
        fallback = AffineMatrix2D()
        assert m.inverse(fallback=fallback) is fallback

    def test_affine_compose_giant_safe(self):
        """m1.compose(m2) and m1 @ m2 execute without OverflowError when coefficients are giant ints."""
        m_giant_tx = AffineMatrix2D(tx=GIANT_POS)
        m_ident = AffineMatrix2D()
        res1 = m_giant_tx.compose(m_ident)
        assert res1.is_singular is True
        res2 = m_ident.compose(m_giant_tx)
        assert res2.is_singular is True
        res3 = m_giant_tx @ m_ident
        assert res3.is_singular is True

    def test_coerce_matrix_field_behavior(self):
        """_coerce_matrix_field must reject bools and non-numerics, convert giant ints to nan, and preserve floats."""
        assert _coerce_matrix_field(True, default=1.0) == 1.0
        assert _coerce_matrix_field(False, default=0.0) == 0.0
        assert _coerce_matrix_field("invalid", default=5.0) == 5.0
        assert _coerce_matrix_field(None, default=2.0) == 2.0
        assert _coerce_matrix_field([1, 2], default=3.0) == 3.0
        assert math.isnan(_coerce_matrix_field(GIANT_POS, default=1.0))
        assert math.isnan(_coerce_matrix_field(GIANT_NEG, default=0.0))
        assert _coerce_matrix_field(10.5, default=1.0) == 10.5
        assert _coerce_matrix_field(0.0, default=1.0) == 0.0
        assert math.isnan(_coerce_matrix_field(NAN, default=1.0))
        assert math.isinf(_coerce_matrix_field(INF, default=1.0))

    def test_affine_matrix_coercion_non_numeric_and_bools(self):
        """AffineMatrix2D instantiation with non-numerics or booleans reverts to safe defaults."""
        m = AffineMatrix2D(a=True, b=False, c="str", d=None, tx=[1], ty={"k": "v"})  # type: ignore
        assert m.a == 1.0
        assert m.b == 0.0
        assert m.c == 0.0
        assert m.d == 1.0
        assert m.tx == 0.0
        assert m.ty == 0.0
        assert m.is_singular is False
        assert m.determinant == 1.0


# =============================================================================
# 3. Degenerate Matrices, Singular Transforms, NaN/Inf
# =============================================================================

class TestDegenerateTransforms:
    """Stress tests attacking singular matrices and non-finite numbers."""

    def test_zero_determinant_matrix(self):
        """Zero matrix must report det=0, is_singular=True, and raise SingularMatrixError on inverse."""
        m_zero = AffineMatrix2D(a=0.0, b=0.0, c=0.0, d=0.0)
        assert m_zero.determinant == 0.0
        assert m_zero.is_singular is True

        with pytest.raises(SingularMatrixError):
            m_zero.inverse()

        fb = AffineMatrix2D()
        assert m_zero.inverse(fallback=fb) is fb

    @pytest.mark.parametrize("det_val", [0.0, 1e-13, -1e-13, 1e-15, -1e-15])
    def test_near_singular_matrix(self, det_val):
        """Matrices with |det| < 1e-12 must be identified as singular."""
        m = AffineMatrix2D(a=det_val, b=0.0, c=0.0, d=1.0)
        assert m.is_singular is True
        fb = AffineMatrix2D()
        assert m.inverse(fallback=fb) is fb

    @pytest.mark.parametrize("nan_inf", [NAN, INF, NINF])
    def test_nan_inf_determinant_and_inverse(self, nan_inf):
        """Non-finite matrices must be identified as singular and return fallback cleanly."""
        m = AffineMatrix2D(a=nan_inf, b=0.0, c=0.0, d=1.0)
        assert m.is_singular is True
        fb = AffineMatrix2D()
        assert m.inverse(fallback=fb) is fb

    def test_reflection_matrix_arc_angles(self):
        """Negative scaling (det < 0) must flip CCW/CW parity and swap arc angles."""
        m_refl_x = AffineMatrix2D.from_cad_insert(0, 0, scale_x=-1.0, scale_y=1.0)
        assert m_refl_x.determinant < 0
        sa, ea = m_refl_x.transform_arc_angles(10.0, 80.0)
        # Expected: transformed angles are swapped to preserve CCW sweep
        assert math.isclose(sa, 100.0, abs_tol=1e-5)
        assert math.isclose(ea, 170.0, abs_tol=1e-5)


# =============================================================================
# 4. Outlier Detection Boundary Conditions (N=20, 25, 49, 50, 100)
# =============================================================================

class TestOutlierDetectionBoundaryConditions:
    """Boundary condition verification for find_primary_cluster_1d."""

    @pytest.mark.parametrize("N", [20, 25, 49, 50, 100])
    def test_single_right_outlier_within_world_bounds(self, N):
        """
        For N in [20, 25, 49, 50, 100], a single extreme outlier at 1e8
        (within world bounds [-1e9, 1e9]) must be pruned.
        """
        cluster = [float(i * 100.0 / (N - 2)) for i in range(N - 1)]
        pts = cluster + [1e8]
        c_min, c_max = find_primary_cluster_1d(pts)
        assert c_min == 0.0, f"N={N}: Expected c_min=0.0, got {c_min}"
        assert c_max == 100.0, f"N={N}: Expected c_max=100.0, got {c_max}"

    @pytest.mark.parametrize("N", [20, 25, 49, 50, 100])
    def test_single_left_outlier_within_world_bounds(self, N):
        """
        For N in [20, 25, 49, 50, 100], a single extreme outlier at -1e8
        must be pruned.
        """
        cluster = [float(i * 100.0 / (N - 2)) for i in range(N - 1)]
        pts = [-1e8] + cluster
        c_min, c_max = find_primary_cluster_1d(pts)
        assert c_min == 0.0, f"N={N}: Expected c_min=0.0, got {c_min}"
        assert c_max == 100.0, f"N={N}: Expected c_max=100.0, got {c_max}"

    @pytest.mark.parametrize("N", [20, 25, 49, 50, 100])
    def test_outlier_outside_world_bounds_1e12(self, N):
        """Outliers outside [-1e9, 1e9] must be filtered by valid_vals guard."""
        cluster = [float(i * 100.0 / (N - 2)) for i in range(N - 1)]
        pts = cluster + [1e12]
        c_min, c_max = find_primary_cluster_1d(pts)
        assert c_min == 0.0 and c_max == 100.0

    @pytest.mark.parametrize("N", [20, 25, 49, 50, 100])
    def test_outlier_with_giant_ints_and_nan(self, N):
        """Giant ints (10^10000) and NaN/Inf must be safely excluded without crashing."""
        cluster = [float(i * 100.0 / (N - 1)) for i in range(N)]
        pts = [GIANT_POS, GIANT_NEG, NAN, INF, NINF] + cluster
        c_min, c_max = find_primary_cluster_1d(pts)
        assert c_min == 0.0 and c_max == 100.0

    def test_outlier_both_sides_for_n_ge_50(self):
        """
        For N=50 and N=100, max_pts >= 1 on both sides, so simultaneous left & right
        outliers at +/-1e8 must both be pruned.
        """
        for N in [50, 100]:
            cluster = [float(i * 100.0 / (N - 3)) for i in range(N - 2)]
            pts = [-1e8] + cluster + [1e8]
            c_min, c_max = find_primary_cluster_1d(pts)
            assert c_min == 0.0 and c_max == 100.0, f"N={N}: failed both sides pruning"

    def test_pathological_all_identical_points(self):
        """When all points are identical, span is 0 and must return (val, val)."""
        pts = [42.0] * 50
        assert find_primary_cluster_1d(pts) == (42.0, 42.0)

    def test_empty_and_sub_four_points(self):
        """Collections with < 4 points must handle gracefully."""
        assert find_primary_cluster_1d([]) == (0.0, 100.0)
        assert find_primary_cluster_1d([10.0]) == (10.0, 10.0)
        assert find_primary_cluster_1d([10.0, 20.0]) == (10.0, 20.0)
        assert find_primary_cluster_1d([10.0, 20.0, 30.0]) == (10.0, 30.0)
