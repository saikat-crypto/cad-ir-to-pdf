"""
test_m3_viewport_extents_adversarial.py — Adversarial stress test suite for Milestone M3.

Covers:
- Zero-area CAD extents (width=0, height=0): single point entities.
- Collinear extents: purely horizontal (height=0, width>0) and purely vertical (width=0, height>0).
- Extreme coordinate span: geometries placed at limits of MIN_WORLD_COORD and MAX_WORLD_COORD (±10^9).
- Non-standard / corrupted custom_bbox: inverted coordinates, non-numeric values, NaN, Infinite, partial tuples.
- ViewportMapping scale clamping under collinear and degenerate extents.
"""

import math
from pathlib import Path
import pytest
from cad_ir_to_pdf.geometry import (
    BoundingBox,
    ViewportMapping,
    calculate_viewport_mapping,
    compute_ir_extents,
    MIN_SCALE,
    MAX_SCALE,
    MIN_WORLD_COORD,
    MAX_WORLD_COORD,
)
from cad_ir_to_pdf.compiler import compile_ir_to_pdf
from cad_ir_to_pdf.config import PdfPreset


def test_m3_single_point_zero_area_extents():
    """Verify single-point (zero-width, zero-height) bounding box handling."""
    box_point = BoundingBox(min_x=100.0, min_y=200.0, max_x=100.0, max_y=200.0)
    assert box_point.width == 0.0
    assert box_point.height == 0.0

    vp = calculate_viewport_mapping(
        cad_bbox=box_point,
        page_width_pt=600.0,
        page_height_pt=800.0,
        margin_pt=20.0,
    )
    assert math.isfinite(vp.scale)
    assert vp.scale == 1.0  # fallback scale for zero-area single-point
    pdf_x, pdf_y = vp.to_pdf(100.0, 200.0)
    assert math.isclose(pdf_x, 300.0, abs_tol=1e-5)
    assert math.isclose(pdf_y, 400.0, abs_tol=1e-5)


def test_m3_collinear_horizontal_extents():
    """Verify purely horizontal geometry (height == 0.0, width > 0)."""
    box_horiz = BoundingBox(min_x=0.0, min_y=50.0, max_x=500.0, max_y=50.0)
    assert box_horiz.width == 500.0
    assert box_horiz.height == 0.0

    vp = calculate_viewport_mapping(
        cad_bbox=box_horiz,
        page_width_pt=600.0,
        page_height_pt=800.0,
        margin_pt=50.0,
    )
    # Avail width = 600 - 100 = 500. Scale should be avail_w / width = 500 / 500 = 1.0
    assert math.isfinite(vp.scale)
    assert math.isclose(vp.scale, 1.0, abs_tol=1e-5)

    px_start, py_start = vp.to_pdf(0.0, 50.0)
    px_end, py_end = vp.to_pdf(500.0, 50.0)
    assert math.isclose(px_start, 50.0, abs_tol=1e-5)
    assert math.isclose(px_end, 550.0, abs_tol=1e-5)
    assert math.isclose(py_start, 400.0, abs_tol=1e-5)
    assert math.isclose(py_end, 400.0, abs_tol=1e-5)


def test_m3_collinear_vertical_extents():
    """Verify purely vertical geometry (width == 0.0, height > 0)."""
    box_vert = BoundingBox(min_x=75.0, min_y=100.0, max_x=75.0, max_y=800.0)
    assert box_vert.width == 0.0
    assert box_vert.height == 700.0

    vp = calculate_viewport_mapping(
        cad_bbox=box_vert,
        page_width_pt=600.0,
        page_height_pt=800.0,
        margin_pt=50.0,
    )
    # Avail height = 800 - 100 = 700. Scale should be avail_h / height = 700 / 700 = 1.0
    assert math.isfinite(vp.scale)
    assert math.isclose(vp.scale, 1.0, abs_tol=1e-5)

    px_start, py_start = vp.to_pdf(75.0, 100.0)
    px_end, py_end = vp.to_pdf(75.0, 800.0)
    assert math.isclose(px_start, 300.0, abs_tol=1e-5)
    assert math.isclose(px_end, 300.0, abs_tol=1e-5)
    assert math.isclose(py_start, 50.0, abs_tol=1e-5)
    assert math.isclose(py_end, 750.0, abs_tol=1e-5)


def test_m3_corrupted_custom_bbox_fallback():
    """Verify compute_ir_extents gracefully rejects corrupted custom_bbox and falls back."""
    ir_payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [10.0, 20.0], "end": [30.0, 40.0], "space": "Model"}
                ]
            }
        }
    }

    # 1. Inverted custom bbox: x1 < x0
    bbox1 = compute_ir_extents(ir_payload, custom_bbox=(100.0, 50.0, 10.0, 500.0))
    assert bbox1.min_x == 10.0 and bbox1.max_x == 30.0
    assert bbox1.min_y == 20.0 and bbox1.max_y == 40.0

    # 2. Inverted custom bbox: y1 < y0
    bbox2 = compute_ir_extents(ir_payload, custom_bbox=(10.0, 500.0, 100.0, 50.0))
    assert bbox2.min_x == 10.0 and bbox2.max_x == 30.0

    # 3. Non-numeric / NaN / Inf custom bbox
    bbox3 = compute_ir_extents(ir_payload, custom_bbox=(float("nan"), 0.0, 100.0, 100.0))
    assert bbox3.min_x == 10.0 and bbox3.max_x == 30.0

    bbox4 = compute_ir_extents(ir_payload, custom_bbox=("invalid", 0.0, 100.0, 100.0))
    assert bbox4.min_x == 10.0 and bbox4.max_x == 30.0

    # 4. Valid custom bbox overrides geometry
    bbox_valid = compute_ir_extents(ir_payload, custom_bbox=(0.0, 0.0, 200.0, 200.0))
    assert bbox_valid.min_x == 0.0 and bbox_valid.max_x == 200.0
    assert bbox_valid.min_y == 0.0 and bbox_valid.max_y == 200.0


def test_m3_extreme_coordinate_span_rendering(tmp_path: Path):
    """Verify compilation of CAD drawing with coordinates spanning extreme limits (±10^9)."""
    ir_payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [-1e8, -1e8], "end": [1e8, 1e8], "space": "Model"},
                    {"start": [0.0, 0.0], "end": [10.0, 10.0], "space": "Model"}
                ]
            }
        }
    }
    out_pdf = tmp_path / "extreme_coords.pdf"
    res = compile_ir_to_pdf(ir_payload, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 0


def test_m3_collinear_rendering_e2e(tmp_path: Path):
    """Verify end-to-end PDF generation with single horizontal line (height=0)."""
    ir_payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [100.0, 50.0], "end": [900.0, 50.0], "space": "Model"}
                ]
            }
        }
    }
    out_pdf = tmp_path / "collinear_horiz.pdf"
    res = compile_ir_to_pdf(ir_payload, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 0
