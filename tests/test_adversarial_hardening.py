"""
test_adversarial_hardening.py — Stress-testing cad-ir-to-pdf with extreme edge cases,
malformed inputs, NaN/Inf floats, missing/null keys, non-uniform scaling, and fuzz payloads.
"""

import math
import pytest
from pathlib import Path
from cad_ir_to_pdf.compiler import compile_ir_to_pdf
from cad_ir_to_pdf.config import PdfPreset, DEFAULT_PRESET
from cad_ir_to_pdf.curves import arc_to_cubic_beziers, circle_to_cubic_beziers
from cad_ir_to_pdf.geometry import (
    AffineMatrix2D,
    BoundingBox,
    is_valid_point,
    compute_ir_extents,
    calculate_arc_bbox,
    compute_primitive_bbox,
)
from cad_ir_to_pdf.renderer import hex_to_pdf_color, sanitize_cad_text


# =========================================================================
# 1. Coordinate & Point Sanitization
# =========================================================================

def test_is_valid_point():
    assert is_valid_point([0, 0]) is True
    assert is_valid_point((10.5, -20.2)) is True
    assert is_valid_point([1, 2, 3]) is True  # at least 2 points
    
    # Degenerate / invalid types
    assert is_valid_point(None) is False
    assert is_valid_point([]) is False
    assert is_valid_point([1]) is False
    assert is_valid_point("10,20") is False
    assert is_valid_point([float("nan"), 0]) is False
    assert is_valid_point([0, float("inf")]) is False
    assert is_valid_point([float("-inf"), 0]) is False
    assert is_valid_point([True, 1]) is False  # boolean check
    assert is_valid_point(["0", "0"]) is False


def test_hex_to_pdf_color_hardening():
    # Valid
    c1 = hex_to_pdf_color("#FF0000")
    assert c1 is not None

    # Missing '#' prefix
    c2 = hex_to_pdf_color("00FF00")
    assert c2 is not None

    # None and empty
    c3 = hex_to_pdf_color(None)
    assert c3 is not None
    c4 = hex_to_pdf_color("")
    assert c4 is not None

    # Non-string types
    c5 = hex_to_pdf_color(12345)  # type: ignore
    assert c5 is not None
    c6 = hex_to_pdf_color(["#FF0000"])  # type: ignore
    assert c6 is not None

    # Pure white contrast safety fallback
    c_white = hex_to_pdf_color("#FFFFFF", fallback="#1E1E1E")
    assert c_white is not None

    # Invalid hex string
    c_invalid = hex_to_pdf_color("NOT_A_HEX")
    assert c_invalid is not None


# =========================================================================
# 2. Affine Matrix & Rotation Clamping
# =========================================================================

def test_affine_matrix_nan_inf_safety():
    # NaN or Inf inputs should not crash or produce unhandled exceptions
    mat_nan = AffineMatrix2D.from_cad_insert(
        pos_x=float("nan"),
        pos_y=0.0,
        rotation_deg=float("inf"),
        scale_x=1.0,
        scale_y=float("-inf"),
    )
    # Should fall back cleanly
    assert math.isfinite(mat_nan.a)
    assert math.isfinite(mat_nan.tx)
    tx, ty = mat_nan.transform_point(10.0, 10.0)
    assert math.isfinite(tx) and math.isfinite(ty)


# =========================================================================
# 3. Arc Degree Sweep Logic
# =========================================================================

def test_arc_zero_sweep_degenerate():
    # Zero sweep arc: start == end angle
    start_pt, segments = arc_to_cubic_beziers(
        cx=100.0, cy=50.0, radius=25.0, start_angle_deg=45.0, end_angle_deg=45.0
    )
    # Must be degenerate point arc with 0 bezier segments, NOT full 360 circle
    assert len(segments) == 0
    assert math.isclose(start_pt[0], 100.0 + 25.0 * math.cos(math.radians(45.0)))


def test_calculate_arc_bbox_nan_inf():
    # Invalid numbers should return safe fallback without crashing
    bbox = calculate_arc_bbox(
        cx=float("nan"), cy=0.0, r=10.0, sa_deg=0.0, ea_deg=90.0
    )
    assert len(bbox) == 4
    assert all(math.isfinite(v) for v in bbox)


def test_calculate_arc_bbox_full_sweep():
    # Full circle 360-degree sweep must yield full diameter extents, not a point
    bbox_360 = calculate_arc_bbox(cx=100.0, cy=200.0, r=50.0, sa_deg=0.0, ea_deg=360.0)
    assert bbox_360 == (50.0, 150.0, 150.0, 250.0)

    bbox_multi = calculate_arc_bbox(cx=100.0, cy=200.0, r=50.0, sa_deg=10.0, ea_deg=370.0)
    assert bbox_multi == (50.0, 150.0, 150.0, 250.0)


# =========================================================================
# 4. Dimension Text, Font & Preset Resilience
# =========================================================================

def test_compiler_with_invalid_background_color(tmp_path):
    bad_bg_preset = PdfPreset(
        name="bad-bg",
        background_color="NOT_A_VALID_HEX",
    )
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {"primitives": {"lines": [{"start": [0, 0], "end": [10, 10]}]}},
    }
    out_pdf = tmp_path / "bad_bg.pdf"
    res = compile_ir_to_pdf(ir_data, out_pdf, preset=bad_bg_preset)
    assert res.exists()
    assert res.stat().st_size > 300

def test_compiler_with_invalid_font_preset(tmp_path):
    # Custom preset specifying an unregistered or non-existent font
    bad_font_preset = PdfPreset(
        name="bad-font",
        font_name="TotallyNonExistentFont-X",
    )
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "annotations": [
            {"clean_text": "Room 101", "position": [10.0, 10.0], "height": 10.0}
        ],
        "dimensions": [
            {
                "measurement": 500.0,
                "defpoint": [0.0, 0.0],
                "defpoint2": [500.0, 0.0],
            }
        ],
    }
    out_pdf = tmp_path / "bad_font_output.pdf"
    res = compile_ir_to_pdf(ir_data, out_pdf, preset=bad_font_preset)
    assert res.exists()
    assert res.stat().st_size > 500


def test_dimension_nan_and_negative_measurement(tmp_path):
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "dimensions": [
            {"measurement": float("nan"), "defpoint": [0, 0], "defpoint2": [10, 0]},
            {"measurement": float("inf"), "defpoint": [0, 0], "defpoint2": [10, 0]},
            {"measurement": -50.0, "defpoint": [0, 0], "defpoint2": [10, 0]},
            {"measurement": None, "defpoint": [0, 0], "defpoint2": [10, 0]},
        ],
    }
    out_pdf = tmp_path / "nan_dims.pdf"
    res = compile_ir_to_pdf(ir_data, out_pdf)
    assert res.exists()


# =========================================================================
# 5. Non-Uniform Block Scaling on Arcs and Circles
# =========================================================================

def test_non_uniform_block_scaling(tmp_path):
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "Elongated": {
                "base_point": [0.0, 0.0],
                "lines": [{"start": [0, 0], "end": [10, 10]}],
                "arcs": [{"center": [5, 5], "radius": 5.0, "start_angle": 0, "end_angle": 180}],
                "circles": [{"center": [5, 5], "radius": 5.0}],
            }
        },
        "components": [
            {
                "block_name": "Elongated",
                "position": [100.0, 100.0],
                "rotation": 30.0,
                "scale": [2.0, 5.0, 1.0],  # Non-uniform scaling!
            }
        ],
    }
    out_pdf = tmp_path / "non_uniform_scale.pdf"
    res = compile_ir_to_pdf(ir_data, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 500


# =========================================================================
# 6. Defensive Normalization: Null-keys, Missing Keys, Corrupted Payloads
# =========================================================================

def test_adversarial_null_payload_keys(tmp_path):
    # Payload with explicitly None values for all primary collections
    ir_nulls = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": None,
        "layers": None,
        "geometry_primitives": None,
        "block_definitions": None,
        "components": None,
        "annotations": None,
        "dimensions": None,
        "extents": None,
    }
    out_pdf = tmp_path / "nulls_output.pdf"
    res = compile_ir_to_pdf(ir_nulls, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 300


def test_adversarial_malformed_primitives(tmp_path):
    # Primitives containing corrupted types: lists with None, strings instead of floats, missing coords
    ir_corrupted = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    None,
                    {},
                    {"start": None, "end": [10, 20]},
                    {"start": ["invalid", "coord"], "end": [10, 20]},
                    {"start": [0], "end": [10, 20]},
                    {"start": [0, 0], "end": [float("inf"), 10]},
                ],
                "arcs": [
                    None,
                    {"center": None, "radius": 10},
                    {"center": [0, 0], "radius": -5},
                    {"center": [0, 0], "radius": float("nan")},
                    {"center": [0, 0], "radius": 10, "start_angle": float("inf")},
                ],
                "circles": [
                    None,
                    {"center": None, "radius": 10},
                    {"center": [0, 0], "radius": 0},
                    {"center": [0, 0], "radius": float("inf")},
                ],
                "polylines": [
                    None,
                    {"points": None},
                    {"points": []},
                    {"points": [[0, 0]]},  # only 1 point
                    {"points": [[0, 0], None, ["bad", "pt"], [10, 10]]},
                ],
            }
        },
        "components": [
            None,
            {},
            {"block_name": "NonExistentBlock"},
            {"block_name": None, "position": [0, 0]},
        ],
        "block_definitions": {
            "BadBlock": None,
            "BrokenBlock": "not a dict",
            "*D_Broken": None,
        },
    }
    out_pdf = tmp_path / "corrupted_output.pdf"
    res = compile_ir_to_pdf(ir_corrupted, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 300
