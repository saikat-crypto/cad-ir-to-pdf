"""
test_geometry_stress.py — Adversarial stress test suite challenging Milestone M1 geometry hardening.

Covers:
- Point validation: giant ints (10^50000), NaN, ±Inf, complex types, booleans, empty tuples.
- BoundingBox: uninitialized centers, inverted boxes, giant coordinates, non-finite bounds.
- ViewportMapping: scale explosion, microscopic scales (10^-15), astronomical scales (10^15),
  extreme offsets (10^30), verifying that `to_pdf` outputs strictly finite coordinates in [-10^5, 10^5] pt.
- Small drawing outlier detection: N=1, 2, 3, 4, 10, 19 points with single extreme outliers at 10^12,
  verifying that the primary cluster is not collapsed.
- AffineMatrix2D and arc bounding boxes under stress.
"""

import math
import pytest
from cad_ir_to_pdf.geometry import (
    BoundingBox,
    AffineMatrix2D,
    SingularMatrixError,
    ViewportMapping,
    calculate_viewport_mapping,
    is_valid_point,
    find_primary_cluster_1d,
    compute_ir_extents,
    calculate_arc_bbox,
    MIN_WORLD_COORD,
    MAX_WORLD_COORD,
    MIN_SCALE,
    MAX_SCALE,
    MIN_PDF_COORD,
    MAX_PDF_COORD,
)


# =========================================================================
# 1. Point Validation Under Stress
# =========================================================================

def test_stress_point_validation_giant_ints():
    """Attack is_valid_point with giant integers exceeding float conversion limits."""
    giant_pos = 10**50000
    giant_neg = -10**50000

    # Giant integers must return False cleanly without raising OverflowError
    assert is_valid_point([giant_pos, 0]) is False
    assert is_valid_point([0, giant_pos]) is False
    assert is_valid_point([giant_neg, 0]) is False
    assert is_valid_point([0, giant_neg]) is False
    assert is_valid_point([giant_pos, giant_pos]) is False
    assert is_valid_point((giant_pos, 0.0)) is False
    assert is_valid_point([1.0, 2.0, giant_pos]) is False


def test_stress_point_validation_non_finite():
    """Attack is_valid_point with NaN and ±Inf in various positions."""
    nan = float("nan")
    inf = float("inf")
    ninf = float("-inf")

    assert is_valid_point([nan, 0.0]) is False
    assert is_valid_point([0.0, nan]) is False
    assert is_valid_point([nan, nan]) is False
    assert is_valid_point([inf, 0.0]) is False
    assert is_valid_point([0.0, inf]) is False
    assert is_valid_point([ninf, 0.0]) is False
    assert is_valid_point([0.0, ninf]) is False
    assert is_valid_point([inf, ninf]) is False
    assert is_valid_point([1.0, 2.0, nan]) is False
    assert is_valid_point([1.0, 2.0, inf]) is False


def test_stress_point_validation_types():
    """Attack is_valid_point with complex numbers, booleans, empty collections, and malformed types."""
    # Complex types
    assert is_valid_point([complex(1, 2), 0.0]) is False
    assert is_valid_point([0.0, complex(3, 4)]) is False

    # Booleans (bool is a subclass of int in Python, must be explicitly rejected)
    assert is_valid_point([True, 0.0]) is False
    assert is_valid_point([0.0, False]) is False
    assert is_valid_point([True, False]) is False
    assert is_valid_point([1.0, 2.0, True]) is False

    # Empty collections and short tuples
    assert is_valid_point(()) is False
    assert is_valid_point([]) is False
    assert is_valid_point((10.0,)) is False
    assert is_valid_point([10.0]) is False

    # Non-sequence types
    assert is_valid_point(None) is False
    assert is_valid_point("10,20") is False
    assert is_valid_point({"x": 10, "y": 20}) is False
    assert is_valid_point({10, 20}) is False
    assert is_valid_point(12345) is False

    # Nested structures
    assert is_valid_point([10.0, [20.0, 30.0]]) is False
    assert is_valid_point([[10.0, 20.0], 30.0]) is False

    # Valid baselines
    assert is_valid_point([0, 0]) is True
    assert is_valid_point([10.5, -20.5]) is True
    assert is_valid_point((100.0, 200.0)) is True
    assert is_valid_point([1.0, 2.0, 3.0]) is True


# =========================================================================
# 2. BoundingBox Under Stress
# =========================================================================

def test_stress_bounding_box_uninitialized_and_inverted():
    """Attack BoundingBox with default/uninitialized state and inverted coordinate boundaries."""
    # Uninitialized box: min=+inf, max=-inf
    b_empty = BoundingBox()
    assert b_empty.is_valid is False
    assert b_empty.center == (0.0, 0.0)
    assert b_empty.width == 0.0
    assert b_empty.height == 0.0

    # Inverted box (min > max in both axes)
    b_inv = BoundingBox(min_x=100.0, min_y=200.0, max_x=10.0, max_y=20.0)
    assert b_inv.is_valid is False
    assert b_inv.center == (0.0, 0.0)
    assert b_inv.width == 0.0
    assert b_inv.height == 0.0

    # Inverted in X only
    b_inv_x = BoundingBox(min_x=50.0, min_y=10.0, max_x=20.0, max_y=100.0)
    assert b_inv_x.is_valid is False
    assert b_inv_x.center == (0.0, 0.0)
    assert b_inv_x.width == 0.0

    # Inverted in Y only
    b_inv_y = BoundingBox(min_x=10.0, min_y=50.0, max_x=100.0, max_y=20.0)
    assert b_inv_y.is_valid is False
    assert b_inv_y.center == (0.0, 0.0)
    assert b_inv_y.height == 0.0

    # Degenerate single-point box: min == max (valid, 0 dimension)
    b_pt = BoundingBox(min_x=42.0, min_y=84.0, max_x=42.0, max_y=84.0)
    assert b_pt.is_valid is True
    assert b_pt.center == (42.0, 84.0)
    assert b_pt.width == 0.0
    assert b_pt.height == 0.0


def test_stress_bounding_box_giant_and_non_finite():
    """Attack BoundingBox with giant coordinates, non-finite bounds, and invalid expand arguments."""
    nan = float("nan")
    inf = float("inf")
    ninf = float("-inf")

    # Non-finite bounds
    for args in [
        (nan, 0.0, 10.0, 10.0),
        (0.0, nan, 10.0, 10.0),
        (0.0, 0.0, nan, 10.0),
        (0.0, 0.0, 10.0, nan),
        (ninf, 0.0, 10.0, 10.0),
        (0.0, ninf, 10.0, 10.0),
        (0.0, 0.0, inf, 10.0),
        (0.0, 0.0, 10.0, inf),
    ]:
        b = BoundingBox(*args)
        assert b.is_valid is False
        assert b.center == (0.0, 0.0)
        assert b.width == 0.0
        assert b.height == 0.0

    # Giant coordinates: 1e308 + 1e308 overflows to inf, center must return finite (0.0, 0.0)
    b_giant = BoundingBox(min_x=1e308, min_y=1e308, max_x=1e308, max_y=1e308)
    cx, cy = b_giant.center
    assert math.isfinite(cx) and math.isfinite(cy)

    # expand() with giant int
    b = BoundingBox(0.0, 0.0, 100.0, 100.0)
    b.expand(10**50000, 0)
    assert b.max_x == 100.0
    b.expand(0, -10**50000)
    assert b.min_y == 0.0

    # expand() with NaN and ±Inf
    b.expand(nan, 50.0)
    b.expand(50.0, nan)
    b.expand(inf, 50.0)
    b.expand(50.0, ninf)
    assert b.min_x == 0.0 and b.max_x == 100.0
    assert b.min_y == 0.0 and b.max_y == 100.0

    # expand_bbox() with uninitialized or inverted other box
    b.expand_bbox(BoundingBox())
    assert b.min_x == 0.0 and b.max_x == 100.0
    b.expand_bbox(BoundingBox(min_x=500.0, min_y=500.0, max_x=10.0, max_y=10.0))
    assert b.min_x == 0.0 and b.max_x == 100.0


# =========================================================================
# 3. ViewportMapping Under Stress
# =========================================================================

def test_stress_viewport_mapping_scale_extremes():
    """Attack ViewportMapping with microscopic scales (10^-15), astronomical scales (10^15), and extreme offsets (10^30)."""
    # Microscopic scale: 1e-15
    vp_micro = ViewportMapping(
        scale=1e-15,
        cad_center_x=0.0,
        cad_center_y=0.0,
        pdf_center_x=300.0,
        pdf_center_y=400.0,
    )
    # Extreme offset: 1e30 CAD units
    px, py = vp_micro.to_pdf(1e30, -1e30)
    assert math.isfinite(px) and math.isfinite(py)
    assert px == MAX_PDF_COORD
    assert py == MIN_PDF_COORD

    # Astronomical scale: 1e15
    vp_astro = ViewportMapping(
        scale=1e15,
        cad_center_x=0.0,
        cad_center_y=0.0,
        pdf_center_x=300.0,
        pdf_center_y=400.0,
    )
    px, py = vp_astro.to_pdf(10.0, -10.0)
    assert math.isfinite(px) and math.isfinite(py)
    assert px == MAX_PDF_COORD
    assert py == MIN_PDF_COORD

    # Scale explosion: 1e200 * 1e200 triggers float overflow -> caught and safely returned
    vp_expl = ViewportMapping(
        scale=1e200,
        cad_center_x=0.0,
        cad_center_y=0.0,
        pdf_center_x=300.0,
        pdf_center_y=400.0,
    )
    px, py = vp_expl.to_pdf(1e200, -1e200)
    assert math.isfinite(px) and math.isfinite(py)
    assert px == 300.0 and py == 400.0


def test_stress_viewport_mapping_to_pdf_invariants():
    """Verify that to_pdf strictly guarantees finite coordinates clamped to [-10^5, +10^5] pt across pathological inputs."""
    vp = ViewportMapping(
        scale=2.5,
        cad_center_x=50.0,
        cad_center_y=50.0,
        pdf_center_x=250.0,
        pdf_center_y=250.0,
    )

    # Giant ints
    px, py = vp.to_pdf(10**50000, -10**50000)
    assert px == 250.0 and py == 250.0
    assert MIN_PDF_COORD <= px <= MAX_PDF_COORD
    assert MIN_PDF_COORD <= py <= MAX_PDF_COORD

    # Non-finite inputs
    for pt in [
        (float("nan"), 0.0),
        (0.0, float("nan")),
        (float("inf"), 0.0),
        (0.0, float("-inf")),
        (float("nan"), float("inf")),
    ]:
        px, py = vp.to_pdf(*pt)
        assert math.isfinite(px) and math.isfinite(py)
        assert MIN_PDF_COORD <= px <= MAX_PDF_COORD
        assert MIN_PDF_COORD <= py <= MAX_PDF_COORD

    # NaN scale in ViewportMapping
    vp_nan = ViewportMapping(
        scale=float("nan"),
        cad_center_x=0.0,
        cad_center_y=0.0,
        pdf_center_x=100.0,
        pdf_center_y=200.0,
    )
    px, py = vp_nan.to_pdf(10.0, 20.0)
    assert (px, py) == (100.0, 200.0)


def test_stress_viewport_mapping_to_pdf_length():
    """Verify that to_pdf_length guarantees non-negative finite float clamped to [0, 10^5]."""
    vp = ViewportMapping(
        scale=2.0,
        cad_center_x=0.0,
        cad_center_y=0.0,
        pdf_center_x=0.0,
        pdf_center_y=0.0,
    )

    assert vp.to_pdf_length(10.0) == 20.0
    assert vp.to_pdf_length(0.0) == 0.0
    assert vp.to_pdf_length(-100.0) == 0.0
    assert vp.to_pdf_length(float("nan")) == 0.0
    assert vp.to_pdf_length(float("inf")) == 0.0
    assert vp.to_pdf_length(float("-inf")) == 0.0
    assert vp.to_pdf_length(10**50000) == 0.0
    assert vp.to_pdf_length(1e30) == MAX_PDF_COORD
    assert vp.to_pdf_length(True) == 0.0  # bool rejected


def test_stress_calculate_viewport_mapping():
    """Verify scale clamping and robustness in calculate_viewport_mapping."""
    # Astronomical box: raw scale ~ 180 / 1e16 ~ 1e-14 -> clamped to MIN_SCALE (1e-9)
    vp_astro = calculate_viewport_mapping(
        cad_bbox=BoundingBox(0.0, 0.0, 1e16, 1e16),
        page_width_pt=500.0,
        page_height_pt=500.0,
        margin_pt=10.0,
    )
    assert vp_astro.scale == MIN_SCALE

    # Microscopic box: raw scale ~ 180 / 1e-15 ~ 1.8e17 -> clamped to MAX_SCALE (1e6)
    vp_micro = calculate_viewport_mapping(
        cad_bbox=BoundingBox(0.0, 0.0, 1e-15, 1e-15),
        page_width_pt=500.0,
        page_height_pt=500.0,
        margin_pt=10.0,
    )
    assert vp_micro.scale == MAX_SCALE

    # Uninitialized bbox fallback
    vp_empty = calculate_viewport_mapping(
        cad_bbox=BoundingBox(),
        page_width_pt=500.0,
        page_height_pt=500.0,
        margin_pt=10.0,
    )
    assert math.isfinite(vp_empty.scale)
    assert MIN_SCALE <= vp_empty.scale <= MAX_SCALE

    # Non-finite and negative page dimensions / margins
    vp_bad_dim = calculate_viewport_mapping(
        cad_bbox=BoundingBox(0.0, 0.0, 100.0, 100.0),
        page_width_pt=-100.0,
        page_height_pt=float("nan"),
        margin_pt=float("inf"),
    )
    assert math.isfinite(vp_bad_dim.scale)
    assert MIN_SCALE <= vp_bad_dim.scale <= MAX_SCALE

    # Fixed scale clamping
    vp_fixed_micro = calculate_viewport_mapping(
        cad_bbox=BoundingBox(0.0, 0.0, 100.0, 100.0),
        page_width_pt=500.0,
        page_height_pt=500.0,
        margin_pt=10.0,
        scale_mode="fixed",
        fixed_scale=1e-15,
    )
    assert vp_fixed_micro.scale == MIN_SCALE

    vp_fixed_astro = calculate_viewport_mapping(
        cad_bbox=BoundingBox(0.0, 0.0, 100.0, 100.0),
        page_width_pt=500.0,
        page_height_pt=500.0,
        margin_pt=10.0,
        scale_mode="fixed",
        fixed_scale=1e15,
    )
    assert vp_fixed_astro.scale == MAX_SCALE


# =========================================================================
# 4. Small Drawing Outlier Detection Under Stress
# =========================================================================

@pytest.mark.parametrize("N", [1, 2, 3, 4, 10, 19])
def test_stress_small_drawing_outlier_detection_1e12(N):
    """
    Stress-test small drawing outlier detection for N=1, 2, 3, 4, 10, 19 points
    with a single extreme outlier at 10^12.
    Verify that the primary cluster is not collapsed.
    """
    if N == 1:
        cluster = [50.0]
    else:
        cluster = [float(i * 100.0 / (N - 1)) for i in range(N)]

    # 1. Test at find_primary_cluster_1d level
    # 10^12 exceeds MAX_WORLD_COORD (1e9) and must be discarded, preserving the cluster
    points_right = cluster + [1e12]
    c_min, c_max = find_primary_cluster_1d(points_right)
    if N >= 2:
        assert c_min == 0.0
        assert c_max == 100.0
    else:
        assert c_min == 50.0 and c_max == 50.0

    # Test left outlier at -10^12
    points_left = [-1e12] + cluster
    c_min_l, c_max_l = find_primary_cluster_1d(points_left)
    if N >= 2:
        assert c_min_l == 0.0
        assert c_max_l == 100.0
    else:
        assert c_min_l == 50.0 and c_max_l == 50.0

    # 2. Test at compute_ir_extents level
    lines = []
    if N == 1:
        lines.append({"start": [50.0, 50.0], "end": [50.0, 50.0], "space": "Model"})
    else:
        for i in range(N - 1):
            x0 = float(i * 100.0 / (N - 1))
            x1 = float((i + 1) * 100.0 / (N - 1))
            lines.append({"start": [x0, x0], "end": [x1, x1], "space": "Model"})

    ir_payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {"primitives": {"lines": lines}},
        "components": [{"position": [1e12, 1e12, 0.0], "space": "Model", "block_name": "none"}],
    }

    bbox = compute_ir_extents(ir_payload, target_space="Model", prune_outliers=True)
    assert bbox.is_valid
    if N >= 2:
        assert bbox.min_x == 0.0
        assert bbox.max_x == 100.0
        assert bbox.min_y == 0.0
        assert bbox.max_y == 100.0
        assert bbox.width == 100.0
        assert bbox.height == 100.0
    else:
        # N=1 degenerate point triggers fallback box (0, 0, 100, 100)
        assert bbox.width > 0.0 and bbox.height > 0.0


@pytest.mark.parametrize("total_N", [4, 10, 19])
def test_stress_small_drawing_outlier_within_world_bounds(total_N):
    """
    Test outlier detection for small drawings (total N in {4, 10, 19})
    where 1 point is an outlier at 10^8 (within world bounds [-10^9, 10^9]).
    """
    cluster_count = total_N - 1
    cluster = [float(i * 100.0 / (cluster_count - 1)) for i in range(cluster_count)]

    # Single right outlier at 1e8
    pts_r = cluster + [1e8]
    c_min, c_max = find_primary_cluster_1d(pts_r)
    assert c_min == 0.0 and c_max == 100.0

    # Single left outlier at -1e8
    pts_l = [-1e8] + cluster
    c_min_l, c_max_l = find_primary_cluster_1d(pts_l)
    assert c_min_l == 0.0 and c_max_l == 100.0


# =========================================================================
# 5. Affine Matrix & Arc Bounding Box Under Stress
# =========================================================================

def test_stress_affine_matrix_inversion():
    """Verify AffineMatrix2D determinant, singularity detection, and safe inverse."""
    # Singular matrix (zero determinant)
    m_zero = AffineMatrix2D(a=0.0, b=0.0, c=0.0, d=0.0)
    assert m_zero.determinant == 0.0
    assert m_zero.is_singular is True

    with pytest.raises(SingularMatrixError):
        m_zero.inverse()

    fallback = AffineMatrix2D()
    assert m_zero.inverse(fallback=fallback) is fallback

    # Non-finite determinant
    m_nan = AffineMatrix2D(a=float("nan"), b=0.0, c=0.0, d=1.0)
    assert m_nan.is_singular is True
    assert m_nan.inverse(fallback=fallback) is fallback

    # Invertible matrix
    m_valid = AffineMatrix2D.from_cad_insert(10.0, 20.0, rotation_deg=45.0, scale_x=2.0, scale_y=2.0)
    assert m_valid.is_singular is False
    m_inv = m_valid.inverse()
    pt = (15.0, 25.0)
    roundtrip = m_inv.transform_point(*m_valid.transform_point(*pt))
    assert math.isclose(roundtrip[0], pt[0], abs_tol=1e-6)
    assert math.isclose(roundtrip[1], pt[1], abs_tol=1e-6)


def test_stress_arc_bbox_pathological():
    """Verify calculate_arc_bbox under pathological conditions."""
    nan = float("nan")
    inf = float("inf")

    # Non-finite center or radius
    assert calculate_arc_bbox(nan, 0.0, 10.0, 0.0, 90.0) == (0.0, 0.0, 0.0, 0.0)
    assert calculate_arc_bbox(0.0, 0.0, nan, 0.0, 90.0) == (0.0, 0.0, 0.0, 0.0)
    assert calculate_arc_bbox(0.0, 0.0, inf, 0.0, 90.0) == (0.0, 0.0, 0.0, 0.0)
    assert calculate_arc_bbox(0.0, 0.0, -5.0, 0.0, 90.0) == (0.0, 0.0, 0.0, 0.0)

    # Full sweep (360 degrees)
    min_x, min_y, max_x, max_y = calculate_arc_bbox(10.0, 20.0, 5.0, 0.0, 360.0)
    assert math.isclose(min_x, 5.0) and math.isclose(min_y, 15.0)
    assert math.isclose(max_x, 15.0) and math.isclose(max_y, 25.0)

    # Zero sweep degenerate
    pt_x, pt_y, pt_x2, pt_y2 = calculate_arc_bbox(10.0, 20.0, 5.0, 45.0, 45.0)
    assert math.isclose(pt_x, pt_x2) and math.isclose(pt_y, pt_y2)
