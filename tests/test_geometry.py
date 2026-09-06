import math
import pytest
from cad_ir_to_pdf.geometry import (
    BoundingBox,
    AffineMatrix2D,
    ViewportMapping,
    calculate_viewport_mapping,
)


def test_bounding_box_expansion():
    bbox = BoundingBox()
    assert not bbox.is_valid
    bbox.expand(10.0, 20.0)
    assert bbox.is_valid
    assert bbox.min_x == 10.0
    assert bbox.max_x == 10.0
    assert bbox.min_y == 20.0
    assert bbox.max_y == 20.0

    bbox.expand(50.0, 100.0)
    assert bbox.width == 40.0
    assert bbox.height == 80.0
    assert bbox.center == (30.0, 60.0)


def test_affine_identity():
    mat = AffineMatrix2D()
    assert mat.transform_point(10.0, 20.0) == (10.0, 20.0)


def test_affine_translation():
    mat = AffineMatrix2D(tx=15.0, ty=-5.0)
    assert mat.transform_point(10.0, 20.0) == (25.0, 15.0)


def test_affine_rotation():
    # 90 degrees CCW
    mat = AffineMatrix2D.from_cad_insert(pos_x=0.0, pos_y=0.0, rotation_deg=90.0)
    tx, ty = mat.transform_point(10.0, 0.0)
    assert math.isclose(tx, 0.0, abs_tol=1e-6)
    assert math.isclose(ty, 10.0, abs_tol=1e-6)


def test_affine_scale_and_insert():
    mat = AffineMatrix2D.from_cad_insert(
        pos_x=100.0,
        pos_y=200.0,
        rotation_deg=0.0,
        scale_x=2.0,
        scale_y=3.0,
        base_x=5.0,
        base_y=5.0,
    )
    # Point (5, 5) is base point, so it should map exactly to (100, 200)
    tx, ty = mat.transform_point(5.0, 5.0)
    assert math.isclose(tx, 100.0, abs_tol=1e-6)
    assert math.isclose(ty, 200.0, abs_tol=1e-6)


def test_viewport_mapping_isotropic():
    bbox = BoundingBox(min_x=0.0, min_y=0.0, max_x=100.0, max_y=50.0)
    # Page size: 200 x 200, Margin: 10
    # Available area: 180 x 180
    # Scale width: 180 / 100 = 1.8
    # Scale height: 180 / 50 = 3.6
    # Isotropic scale must choose min => 1.8
    vp = calculate_viewport_mapping(
        cad_bbox=bbox,
        page_width_pt=200.0,
        page_height_pt=200.0,
        margin_pt=10.0,
        scale_mode="fit",
    )
    assert math.isclose(vp.scale, 1.8, rel_tol=1e-5)
    # CAD center (50, 25) must map to PDF center (100, 100)
    px, py = vp.to_pdf(50.0, 25.0)
    assert math.isclose(px, 100.0, abs_tol=1e-6)
    assert math.isclose(py, 100.0, abs_tol=1e-6)


def test_find_primary_cluster_pruning():
    from cad_ir_to_pdf.geometry import find_primary_cluster_1d
    # 50 points clustered between 0 and 100, plus 1 outlier at -10,000
    points = [float(i * 2) for i in range(50)] + [-10000.0]
    min_v, max_v = find_primary_cluster_1d(points, min_gap_fraction=0.10, max_outlier_ratio=0.03)
    assert min_v == 0.0
    assert max_v == 98.0


def test_compute_ir_extents_with_outliers():
    from cad_ir_to_pdf.geometry import compute_ir_extents
    # Build IR data with a cluster of lines near (0..100, 0..100) and 1 rogue scratch component at (-90000, 50000)
    lines = [{"start": [float(i), float(i)], "end": [float(i + 1), float(i + 1)], "space": "Model"} for i in range(40)]
    ir_data = {
        "geometry_primitives": {"primitives": {"lines": lines}},
        "components": [{"position": [-90000.0, 50000.0, 0.0], "space": "Model", "block_name": "none"}],
    }

    # Pruned extents should discard the -90000 outlier
    bbox_pruned = compute_ir_extents(ir_data, target_space="Model", prune_outliers=True)
    assert bbox_pruned.min_x == 0.0
    assert bbox_pruned.max_x == 40.0

    # Unpruned extents include the outlier
    bbox_raw = compute_ir_extents(ir_data, target_space="Model", prune_outliers=False)
    assert bbox_raw.min_x == -90000.0


def test_calculate_arc_bbox():
    from cad_ir_to_pdf.geometry import calculate_arc_bbox
    # Arc centered at (0, 0), radius 10, from 0 to 90 degrees (first quadrant)
    min_x, min_y, max_x, max_y = calculate_arc_bbox(0.0, 0.0, 10.0, 0.0, 90.0)
    assert abs(min_x - 0.0) < 1e-5
    assert abs(min_y - 0.0) < 1e-5
    assert abs(max_x - 10.0) < 1e-5
    assert abs(max_y - 10.0) < 1e-5


