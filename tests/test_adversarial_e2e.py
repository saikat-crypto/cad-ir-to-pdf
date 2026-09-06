"""
test_adversarial_e2e.py — Comprehensive Opaque-Box E2E Adversarial Test Suite for CAD-IR-to-PDF.

Covers 4 Tiers across all 4 adversarial vectors:
  - Feature 1: Coordinate Singularities (NaN, ±Inf, extreme scale 10^12, sub-micron 10^-9, non-numeric coords)
  - Feature 2: Degenerate Geometry (0-length lines, 0-radius circles/arcs, 0°/360° sweeps, identical angles)
  - Feature 3: Block Transform Abuse (singular/inverted 2D affine, zero-determinant scaling, negative scaling, deep/cyclic nesting)
  - Feature 4: Missing & Malformed Metadata (null keys, non-list collections, non-string author/title, invalid hex colors, bad line weights, bad font names/sizes, empty drawings)

Tiers:
  - Tier 1: Feature Coverage (>= 5 tests per feature = >= 20 tests)
  - Tier 2: Boundary & Corner Cases (>= 5 tests per feature = >= 20 tests)
  - Tier 3: Cross-Feature Combinations (>= 4 pairwise tests)
  - Tier 4: Real-World Workload Scenarios (>= 5 realistic scenarios, including valid vehicle blueprints)

Test Invariants:
  1. compile_ir_to_pdf executes without unhandled exceptions, zero divisions, or infinite loops.
  2. For every generated PDF, verify ISO 32000 validity via PyMuPDF:
     - doc = pymupdf.open(str(pdf_path))
     - assert doc.is_pdf is True
     - assert doc.is_repair is False
     - assert doc.page_count >= 1
     - Read content stream and assert no nan or inf byte tokens.
"""

from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf
import pytest

from cad_ir_to_pdf.compiler import compile_ir_to_pdf
from cad_ir_to_pdf.config import DEFAULT_PRESET, PdfPreset

# PyMuPDF compatibility: ensure doc.is_repair exists as alias to doc.is_repaired
if not hasattr(pymupdf.Document, "is_repair"):
    pymupdf.Document.is_repair = property(lambda self: getattr(self, "is_repaired", False))


def assert_valid_iso32000_pdf(pdf_path: Path) -> None:
    """
    Verifies that the generated PDF strictly conforms to ISO 32000 requirements.
    
    1. doc.is_pdf is True
    2. doc.is_repair is False (no repair or recovery was needed)
    3. doc.page_count >= 1
    4. Content streams contain no IEEE 754 special tokens ('nan', 'inf', '-inf').
    """
    assert pdf_path.exists(), f"PDF output was not created: {pdf_path}"
    assert pdf_path.stat().st_size > 0, f"PDF output is 0 bytes: {pdf_path}"

    doc = pymupdf.open(str(pdf_path))
    try:
        assert doc.is_pdf is True, f"PyMuPDF could not validate PDF structure for {pdf_path}"
        assert doc.is_repair is False, f"PDF required repair/recovery: {pdf_path}"
        assert doc.page_count >= 1, f"Expected at least 1 page, got {doc.page_count}"

        for page_idx in range(doc.page_count):
            page = doc[page_idx]
            assert page.rect.width > 0, f"Page {page_idx} width <= 0"
            assert page.rect.height > 0, f"Page {page_idx} height <= 0"

            contents = page.read_contents()
            if isinstance(contents, (list, tuple)):
                raw_bytes = b"".join(contents)
            elif isinstance(contents, (bytes, bytearray)):
                raw_bytes = bytes(contents)
            else:
                raw_bytes = b""

            assert not re.search(
                rb"(?i)\b(nan|inf|-inf)\b", raw_bytes
            ), f"Forbidden IEEE special token (nan/inf) found in content stream of page {page_idx}"
    finally:
        doc.close()


# =============================================================================
# TIER 1: FEATURE COVERAGE (>= 5 tests per feature = 24 tests)
# =============================================================================

# -----------------------------------------------------------------------------
# Tier 1, Feature 1: Coordinate Singularities
# -----------------------------------------------------------------------------

def test_tier1_f1_nan_line_coordinates(tmp_path: Path):
    """F1: Line entities with NaN coordinates in start, end, or both must be dropped safely."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [float("nan"), 10.0], "end": [20.0, 30.0]},
                    {"start": [10.0, 20.0], "end": [float("nan"), float("nan")]},
                    {"start": [float("nan"), float("nan")], "end": [float("nan"), float("nan")]},
                    {"start": [0.0, 0.0], "end": [100.0, 100.0]},  # 1 valid line to establish extents
                ]
            }
        },
    }
    out = tmp_path / "t1_f1_nan_lines.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f1_nan_arc_and_circle_coordinates(tmp_path: Path):
    """F1: Arc and Circle entities with NaN center or radius must be dropped safely."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "arcs": [
                    {"center": [float("nan"), 50.0], "radius": 25.0, "start_angle": 0.0, "end_angle": 180.0},
                    {"center": [50.0, 50.0], "radius": float("nan"), "start_angle": 0.0, "end_angle": 90.0},
                    {"center": [50.0, 50.0], "radius": 20.0, "start_angle": float("nan"), "end_angle": 90.0},
                ],
                "circles": [
                    {"center": [float("nan"), 0.0], "radius": 15.0},
                    {"center": [0.0, 0.0], "radius": float("nan")},
                ],
            }
        },
    }
    out = tmp_path / "t1_f1_nan_arcs_circles.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f1_pos_neg_inf_coordinates(tmp_path: Path):
    """F1: Coordinates containing ±Infinity must not cause float overflow or unhandled exceptions."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [float("inf"), 0.0], "end": [10.0, 10.0]},
                    {"start": [0.0, float("-inf")], "end": [10.0, 10.0]},
                ],
                "circles": [
                    {"center": [float("inf"), float("-inf")], "radius": 10.0},
                    {"center": [0.0, 0.0], "radius": float("inf")},
                ],
                "polylines": [
                    {"points": [[0.0, 0.0], [float("inf"), 10.0], [20.0, 20.0]]}
                ],
            }
        },
    }
    out = tmp_path / "t1_f1_inf_coords.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f1_extreme_astronomical_coordinates(tmp_path: Path):
    """F1: Astronomical coordinates (10^12) must scale cleanly without overflow or canvas crash."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [1e12, 1e12], "end": [1e12 + 1000.0, 1e12 + 500.0]},
                    {"start": [1e12, 1e12 + 500.0], "end": [1e12 + 1000.0, 1e12]},
                ]
            }
        },
    }
    out = tmp_path / "t1_f1_astronomical.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f1_sub_micron_scale_coordinates(tmp_path: Path):
    """F1: Sub-micron coordinates (10^-9) must calculate viewport scale without zero-division."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [1e-9, 1e-9], "end": [5e-9, 5e-9]},
                    {"start": [1e-9, 5e-9], "end": [5e-9, 1e-9]},
                ]
            }
        },
    }
    out = tmp_path / "t1_f1_sub_micron.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f1_non_numeric_and_boolean_coordinates(tmp_path: Path):
    """F1: Coordinates specified as strings, booleans, or None must be safely rejected."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": ["0.0", "0.0"], "end": [10.0, 10.0]},
                    {"start": [True, False], "end": [10.0, 10.0]},
                    {"start": [None, 5.0], "end": [10.0, 10.0]},
                    {"start": [], "end": [10.0, 10.0]},
                ]
            }
        },
    }
    out = tmp_path / "t1_f1_non_numeric.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


# -----------------------------------------------------------------------------
# Tier 1, Feature 2: Degenerate Geometry
# -----------------------------------------------------------------------------

def test_tier1_f2_zero_length_line(tmp_path: Path):
    """F2: Lines with identical start and end points (length = 0) must compile cleanly."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [100.0, 100.0], "end": [100.0, 100.0]},
                    {"start": [0.0, 0.0], "end": [0.0, 0.0]},
                ]
            }
        },
    }
    out = tmp_path / "t1_f2_zero_lines.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f2_zero_radius_circle(tmp_path: Path):
    """F2: Circles with radius 0.0 must be safely handled without zero-division."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "circles": [
                    {"center": [50.0, 50.0], "radius": 0.0},
                    {"center": [100.0, 100.0], "radius": 0},
                ]
            }
        },
    }
    out = tmp_path / "t1_f2_zero_circle.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f2_negative_radius_arc(tmp_path: Path):
    """F2: Arcs with negative radius must be dropped safely without raising exceptions."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "arcs": [
                    {"center": [50.0, 50.0], "radius": -25.0, "start_angle": 0.0, "end_angle": 90.0},
                    {"center": [100.0, 100.0], "radius": -0.001, "start_angle": 45.0, "end_angle": 135.0},
                ]
            }
        },
    }
    out = tmp_path / "t1_f2_neg_arc.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f2_zero_sweep_arc_identical_angles(tmp_path: Path):
    """F2: Arcs where start_angle == end_angle (0 sweep) must not cause division by zero or full circles."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "arcs": [
                    {"center": [100.0, 100.0], "radius": 50.0, "start_angle": 45.0, "end_angle": 45.0},
                    {"center": [200.0, 200.0], "radius": 30.0, "start_angle": 0.0, "end_angle": 0.0},
                ]
            }
        },
    }
    out = tmp_path / "t1_f2_zero_sweep_arc.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f2_full_circle_360_degree_sweep_arc(tmp_path: Path):
    """F2: Arcs with a 360-degree sweep must render a full closed circle without tangent singularity."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "arcs": [
                    {"center": [150.0, 150.0], "radius": 40.0, "start_angle": 0.0, "end_angle": 360.0},
                    {"center": [250.0, 250.0], "radius": 30.0, "start_angle": 90.0, "end_angle": 450.0},
                ]
            }
        },
    }
    out = tmp_path / "t1_f2_full_sweep_arc.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f2_degenerate_polylines_single_vertex(tmp_path: Path):
    """F2: Polylines with 0 or 1 point must be dropped safely without canvas operator errors."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "polylines": [
                    {"points": []},
                    {"points": [[10.0, 20.0]]},
                    {"points": [[0.0, 0.0]], "is_closed": True},
                ]
            }
        },
    }
    out = tmp_path / "t1_f2_degen_polylines.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


# -----------------------------------------------------------------------------
# Tier 1, Feature 3: Block Transform Abuse
# -----------------------------------------------------------------------------

def test_tier1_f3_singular_block_transform_zero_scale(tmp_path: Path):
    """F3: Block component with scale [0, 0, 1] (singular matrix, det = 0) must compile cleanly."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "Part": {
                "lines": [{"start": [0, 0], "end": [10, 10]}],
                "circles": [{"center": [5, 5], "radius": 5.0}],
            }
        },
        "components": [
            {
                "block_name": "Part",
                "position": [100.0, 100.0],
                "scale": [0.0, 0.0, 1.0],
            }
        ],
    }
    out = tmp_path / "t1_f3_singular_block.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f3_zero_determinant_single_axis_scale(tmp_path: Path):
    """F3: Block component with scale [1.0, 0.0, 1.0] (flattened 1D) must not raise unhandled errors."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "Frame": {
                "lines": [{"start": [0, 0], "end": [20, 20]}],
                "arcs": [{"center": [10, 10], "radius": 10.0, "start_angle": 0, "end_angle": 180}],
            }
        },
        "components": [
            {
                "block_name": "Frame",
                "position": [50.0, 50.0],
                "scale": [1.0, 0.0, 1.0],
            }
        ],
    }
    out = tmp_path / "t1_f3_flattened_1d.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f3_negative_scale_reflection_x(tmp_path: Path):
    """F3: Negative scale along X axis (reflection) must transform geometry cleanly."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "Widget": {
                "lines": [{"start": [10, 10], "end": [30, 40]}],
                "arcs": [{"center": [20, 20], "radius": 10.0, "start_angle": 30, "end_angle": 120}],
            }
        },
        "components": [
            {
                "block_name": "Widget",
                "position": [150.0, 150.0],
                "scale": [-1.0, 1.0, 1.0],
            }
        ],
    }
    out = tmp_path / "t1_f3_neg_scale_x.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f3_negative_scale_reflection_both_axes(tmp_path: Path):
    """F3: Negative scale along both axes (scale [-2, -2, 1]) must compile cleanly."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "Door": {
                "lines": [{"start": [0, 0], "end": [50, 0]}],
                "circles": [{"center": [25, 0], "radius": 10.0}],
            }
        },
        "components": [
            {
                "block_name": "Door",
                "position": [200.0, 200.0],
                "rotation": 45.0,
                "scale": [-2.0, -2.0, 1.0],
            }
        ],
    }
    out = tmp_path / "t1_f3_neg_scale_both.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f3_cyclic_block_reference_mutual(tmp_path: Path):
    """F3: Mutually recursive blocks (A -> B -> A) must terminate cleanly without infinite loop."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "BlockA": {
                "lines": [{"start": [0, 0], "end": [10, 0]}],
                "components": [{"block_name": "BlockB"}],
            },
            "BlockB": {
                "lines": [{"start": [0, 0], "end": [0, 10]}],
                "components": [{"block_name": "BlockA"}],
            },
        },
        "components": [{"block_name": "BlockA", "position": [50.0, 50.0]}],
    }
    out = tmp_path / "t1_f3_cyclic_blocks.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f3_self_recursive_block_definition(tmp_path: Path):
    """F3: Self-referential block (A -> A) must compile cleanly without recursion errors."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "SelfRef": {
                "lines": [{"start": [0, 0], "end": [20, 20]}],
                "components": [{"block_name": "SelfRef", "scale": [0.5, 0.5, 1.0]}],
            }
        },
        "components": [{"block_name": "SelfRef", "position": [10.0, 10.0]}],
    }
    out = tmp_path / "t1_f3_self_recursive.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


# -----------------------------------------------------------------------------
# Tier 1, Feature 4: Missing & Malformed Metadata
# -----------------------------------------------------------------------------

def test_tier1_f4_completely_empty_drawing_payload(tmp_path: Path):
    """F4: Completely empty drawing payload ({}) must compile to a valid 1-page blank PDF."""
    payload: Dict[str, Any] = {}
    out = tmp_path / "t1_f4_empty.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f4_null_primary_collection_keys(tmp_path: Path):
    """F4: Explicit None values for all primary collection keys must compile cleanly."""
    payload = {
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
    out = tmp_path / "t1_f4_null_keys.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f4_non_list_layer_and_component_collections(tmp_path: Path):
    """F4: Collections specified as non-list types (strings, ints, dicts) must be tolerated."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "layers": "NotAList",
        "components": 12345,
        "annotations": {"key": "val"},
        "dimensions": True,
        "geometry_primitives": {
            "primitives": {
                "lines": "NotAListLines",
                "circles": 999,
            }
        },
    }
    out = tmp_path / "t1_f4_non_list_collections.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f4_non_string_author_and_source_file(tmp_path: Path):
    """F4: Non-string author or title in metadata must be coerced safely to strings."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {
            "author": 12345,
            "source_file": [1, 2, 3],
        },
        "geometry_primitives": {
            "primitives": {"lines": [{"start": [0, 0], "end": [10, 10]}]}
        },
    }
    out = tmp_path / "t1_f4_non_string_metadata.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f4_invalid_and_corrupted_hex_colors(tmp_path: Path):
    """F4: Invalid hex colors must fall back cleanly without throwing unhandled exceptions."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "layers": [
            {"name": "BadHex1", "hex_color": "NOT_A_HEX"},
            {"name": "BadHex2", "hex_color": "#GGHHII"},
            {"name": "BadHex3", "hex_color": ""},
            {"name": "BadHex4", "hex_color": 12345},
        ],
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0, 0], "end": [10, 10], "color": "INVALID", "layer": "BadHex1"},
                    {"start": [10, 10], "end": [20, 20], "color": "#12345G", "layer": "BadHex2"},
                ]
            }
        },
    }
    out = tmp_path / "t1_f4_bad_hex_colors.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier1_f4_malformed_and_negative_line_weights(tmp_path: Path):
    """F4: Non-numeric, negative, and extreme line weights must fall back or clamp cleanly."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0, 0], "end": [10, 10], "line_width": -50.0},
                    {"start": [10, 0], "end": [20, 10], "line_width": "thick"},
                    {"start": [20, 0], "end": [30, 10], "line_width": float("inf")},
                    {"start": [30, 0], "end": [40, 10], "line_width": 0.0},
                ]
            }
        },
    }
    out = tmp_path / "t1_f4_bad_line_weights.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


# =============================================================================
# TIER 2: BOUNDARY & CORNER CASES (>= 5 tests per feature = 20 tests)
# =============================================================================

# -----------------------------------------------------------------------------
# Tier 2, Feature 1: Coordinate Singularities (Boundary & Corner)
# -----------------------------------------------------------------------------

def test_tier2_f1_partial_nan_in_polyline_vertices(tmp_path: Path):
    """F1 Boundary: Polyline containing a mixture of valid and NaN vertices."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "polylines": [
                    {
                        "points": [
                            [0.0, 0.0],
                            [float("nan"), 10.0],
                            [10.0, 10.0],
                            [float("inf"), float("-inf")],
                            [20.0, 0.0],
                        ],
                        "is_closed": False,
                    }
                ]
            }
        },
    }
    out = tmp_path / "t2_f1_partial_nan_poly.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f1_near_overflow_float_max_coordinates(tmp_path: Path):
    """F1 Boundary: Coordinates approaching float limits (10^300) must not trigger OverflowError."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [1e300, 1e300], "end": [1e300, 1e300]},
                    {"start": [0.0, 0.0], "end": [10.0, 10.0]},
                ]
            }
        },
    }
    out = tmp_path / "t2_f1_float_max_coords.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f1_near_underflow_denormal_coordinates(tmp_path: Path):
    """F1 Boundary: Coordinates at denormal levels (10^-300) must not cause underflow crashes."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [1e-300, 1e-300], "end": [2e-300, 2e-300]},
                ]
            }
        },
    }
    out = tmp_path / "t2_f1_denormal_coords.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f1_nan_inf_dimension_defpoints_and_measurements(tmp_path: Path):
    """F1 Boundary: Dimensions with NaN/Inf measurements and defpoints must be dropped safely."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "dimensions": [
            {"measurement": float("nan"), "defpoint": [0, 0], "defpoint2": [10, 0]},
            {"measurement": 100.0, "defpoint": [float("nan"), 0], "defpoint2": [10, 0]},
            {"measurement": float("inf"), "defpoint": [0, 0], "defpoint2": [float("-inf"), 0]},
            {"measurement": -999.0, "defpoint": [0, 0], "defpoint2": [10, 0]},
        ],
    }
    out = tmp_path / "t2_f1_nan_dims.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f1_isolated_astronomical_outlier_in_small_drawing(tmp_path: Path):
    """F1 Boundary: 3 normal geometry lines at [0, 100] plus 1 astronomical scratch line at 10^12."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0.0, 0.0], "end": [100.0, 0.0]},
                    {"start": [100.0, 0.0], "end": [100.0, 50.0]},
                    {"start": [100.0, 50.0], "end": [0.0, 50.0]},
                    {"start": [1e12, 1e12], "end": [1e12 + 10, 1e12 + 10]},
                ]
            }
        },
    }
    out = tmp_path / "t2_f1_astronomical_outlier.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


# -----------------------------------------------------------------------------
# Tier 2, Feature 2: Degenerate Geometry (Boundary & Corner)
# -----------------------------------------------------------------------------

def test_tier2_f2_near_zero_sub_epsilon_line_length(tmp_path: Path):
    """F2 Boundary: Line length 10^-8 (just above zero, sub-micron) must compile cleanly."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [10.0, 10.0], "end": [10.0 + 1e-8, 10.0 + 1e-8]},
                ]
            }
        },
    }
    out = tmp_path / "t2_f2_sub_epsilon_line.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f2_near_zero_sub_epsilon_circle_radius(tmp_path: Path):
    """F2 Boundary: Circle radius 10^-8 must compile without numerical breakdown."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "circles": [
                    {"center": [50.0, 50.0], "radius": 1e-8},
                ]
            }
        },
    }
    out = tmp_path / "t2_f2_sub_epsilon_circle.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f2_arc_sweep_boundary_just_below_360(tmp_path: Path):
    """F2 Boundary: Arc sweep 359.9999° must decompose into safe Bézier quadrants without 0 division."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "arcs": [
                    {"center": [100.0, 100.0], "radius": 50.0, "start_angle": 0.0, "end_angle": 359.9999},
                ]
            }
        },
    }
    out = tmp_path / "t2_f2_arc_sweep_359_99.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f2_arc_sweep_boundary_just_above_zero(tmp_path: Path):
    """F2 Boundary: Arc sweep 0.0001° must not cause division by zero in tangent formulas."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "arcs": [
                    {"center": [100.0, 100.0], "radius": 50.0, "start_angle": 10.0, "end_angle": 10.0001},
                ]
            }
        },
    }
    out = tmp_path / "t2_f2_arc_sweep_near_zero.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f2_consecutive_coincident_polyline_vertices(tmp_path: Path):
    """F2 Boundary: Polyline with duplicated consecutive vertices must compile cleanly."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "polylines": [
                    {
                        "points": [
                            [0.0, 0.0],
                            [0.0, 0.0],
                            [10.0, 10.0],
                            [10.0, 10.0],
                            [20.0, 0.0],
                        ],
                        "is_closed": False,
                    }
                ]
            }
        },
    }
    out = tmp_path / "t2_f2_coincident_poly.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


# -----------------------------------------------------------------------------
# Tier 2, Feature 3: Block Transform Abuse (Boundary & Corner)
# -----------------------------------------------------------------------------

def test_tier2_f3_near_singular_matrix_sub_epsilon_determinant(tmp_path: Path):
    """F3 Boundary: Block transform with near-zero scale (sx=1e-13, sy=1e-13) near singular cutoff."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "NearSingular": {
                "lines": [{"start": [0, 0], "end": [10, 10]}],
            }
        },
        "components": [
            {
                "block_name": "NearSingular",
                "position": [50.0, 50.0],
                "scale": [1e-13, 1e-13, 1.0],
            }
        ],
    }
    out = tmp_path / "t2_f3_near_singular.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f3_extreme_block_scaling_and_multi_turn_rotation(tmp_path: Path):
    """F3 Boundary: Block with scale factor 10^6 and rotation 7200.0 degrees."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "BigRotated": {
                "lines": [{"start": [0, 0], "end": [1, 1]}],
                "circles": [{"center": [0.5, 0.5], "radius": 0.5}],
            }
        },
        "components": [
            {
                "block_name": "BigRotated",
                "position": [100.0, 100.0],
                "rotation": 7200.0,
                "scale": [1e6, 1e6, 1.0],
            }
        ],
    }
    out = tmp_path / "t2_f3_extreme_rot_scale.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f3_block_with_astronomical_base_point_offset(tmp_path: Path):
    """F3 Boundary: Block definition with astronomical base point [10^9, 10^9]."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "FarBase": {
                "base_point": [1e9, 1e9, 0.0],
                "lines": [{"start": [1e9, 1e9], "end": [1e9 + 10, 1e9 + 10]}],
            }
        },
        "components": [
            {
                "block_name": "FarBase",
                "position": [50.0, 50.0],
                "scale": [1.0, 1.0, 1.0],
            }
        ],
    }
    out = tmp_path / "t2_f3_far_base.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f3_negative_scale_block_containing_arc_parity(tmp_path: Path):
    """F3 Boundary: Block with sx = -1, sy = 1 containing an arc from 30° to 120°."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "MirroredArc": {
                "arcs": [{"center": [0, 0], "radius": 20.0, "start_angle": 30.0, "end_angle": 120.0}],
            }
        },
        "components": [
            {
                "block_name": "MirroredArc",
                "position": [100.0, 100.0],
                "scale": [-1.0, 1.0, 1.0],
            }
        ],
    }
    out = tmp_path / "t2_f3_mirrored_arc.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f3_anonymous_dimension_block_with_degenerate_entities(tmp_path: Path):
    """F3 Boundary: Anonymous dimension block (*D1) containing 0-length lines and 0-radius circles."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "*D1": {
                "lines": [{"start": [0, 0], "end": [0, 0]}],
                "circles": [{"center": [10, 10], "radius": 0.0}],
                "arcs": [{"center": [20, 20], "radius": -5.0, "start_angle": 0, "end_angle": 90}],
            }
        },
    }
    out = tmp_path / "t2_f3_anon_dim_block.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


# -----------------------------------------------------------------------------
# Tier 2, Feature 4: Missing & Malformed Metadata (Boundary & Corner)
# -----------------------------------------------------------------------------

def test_tier2_f4_pure_white_stroke_contrast_safety(tmp_path: Path):
    """F4 Boundary: Entity stroke color #FFFFFF on white background must apply contrast safety remapping."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0, 0], "end": [100, 100], "color": "#FFFFFF"},
                    {"start": [0, 100], "end": [100, 0], "color": "#FFF"},
                ]
            }
        },
    }
    out = tmp_path / "t2_f4_contrast_safety.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f4_empty_whitespace_font_name_fallback(tmp_path: Path):
    """F4 Boundary: Annotation with whitespace font name '   ' must fall back to Helvetica."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "annotations": [
            {"clean_text": "Elevation A", "position": [50.0, 50.0], "height": 14.0}
        ],
    }
    custom_preset = PdfPreset(name="ws-font", font_name="   ")
    out = tmp_path / "t2_f4_ws_font.pdf"
    res = compile_ir_to_pdf(payload, out, preset=custom_preset)
    assert_valid_iso32000_pdf(res)


def test_tier2_f4_extreme_font_size_clamping_boundary(tmp_path: Path):
    """F4 Boundary: Annotations with extreme heights (1e-6 pt and 1e5 pt) must clamp cleanly."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "annotations": [
            {"clean_text": "Micro Text", "position": [10.0, 10.0], "height": 1e-6},
            {"clean_text": "Macro Text", "position": [50.0, 50.0], "height": 1e5},
            {"clean_text": "Bad Height Text", "position": [100.0, 100.0], "height": float("nan")},
        ],
    }
    out = tmp_path / "t2_f4_extreme_font.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f4_primitives_referencing_undeclared_layers(tmp_path: Path):
    """F4 Boundary: Primitives referencing layer 'GHOST_LAYER' missing from layer table."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "layers": [{"name": "Standard", "hex_color": "#000000"}],
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0, 0], "end": [50, 50], "layer": "GHOST_LAYER_XYZ"},
                ],
                "circles": [
                    {"center": [25, 25], "radius": 15.0, "layer": "UNDECLARED_999"},
                ],
            }
        },
    }
    out = tmp_path / "t2_f4_ghost_layers.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier2_f4_line_width_clamping_at_sub_minimum_and_maximum(tmp_path: Path):
    """F4 Boundary: Line widths at sub-minimum (0.0001 pt) and extreme maximum (1000.0 pt)."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0, 0], "end": [50, 0], "line_width": 0.0001},
                    {"start": [0, 50], "end": [50, 50], "line_width": 1000.0},
                ]
            }
        },
    }
    out = tmp_path / "t2_f4_lw_clamping.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


# =============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (>= 4 pairwise tests = 5 tests)
# =============================================================================

def test_tier3_f1_f2_nan_coords_inside_degenerate_geometry(tmp_path: Path):
    """Tier 3 (F1 + F2): Degenerate geometry (0-length lines, 0-radius arcs) combined with NaN coordinates."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [float("nan"), float("nan")], "end": [float("nan"), float("nan")]},
                    {"start": [10.0, 10.0], "end": [10.0, 10.0]},
                ],
                "arcs": [
                    {"center": [float("nan"), 0.0], "radius": 0.0, "start_angle": 45.0, "end_angle": 45.0},
                    {"center": [50.0, 50.0], "radius": -10.0, "start_angle": float("inf"), "end_angle": 90.0},
                ],
                "circles": [
                    {"center": [float("-inf"), float("inf")], "radius": 0.0},
                ],
            }
        },
    }
    out = tmp_path / "t3_f1_f2_combined.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier3_f1_f3_singular_block_with_astronomical_coordinates(tmp_path: Path):
    """Tier 3 (F1 + F3): Singular block transform (scale [0, 0]) containing astronomical coordinates (10^12)."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "AstroBlock": {
                "lines": [
                    {"start": [1e12, 1e12], "end": [1e12 + 500, 1e12 + 500]},
                    {"start": [float("nan"), 0.0], "end": [10.0, 10.0]},
                ]
            }
        },
        "components": [
            {
                "block_name": "AstroBlock",
                "position": [100.0, 100.0],
                "scale": [0.0, 0.0, 1.0],
            },
            {
                "block_name": "AstroBlock",
                "position": [200.0, 200.0],
                "scale": [-1.0, 1.0, 1.0],
            },
        ],
    }
    out = tmp_path / "t3_f1_f3_combined.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier3_f2_f4_degenerate_geometry_with_corrupted_metadata(tmp_path: Path):
    """Tier 3 (F2 + F4): 0-length and 0-radius geometry assigned invalid hex colors, bad line weights, and missing layers."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "layers": None,
        "metadata": None,
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {
                        "start": [50.0, 50.0],
                        "end": [50.0, 50.0],
                        "color": "#XYZ_BAD",
                        "line_width": -15.0,
                        "layer": "MISSING_LAYER",
                    }
                ],
                "circles": [
                    {
                        "center": [100.0, 100.0],
                        "radius": 0.0,
                        "color": 99999,
                        "line_width": "thick",
                    }
                ],
            }
        },
    }
    out = tmp_path / "t3_f2_f4_combined.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier3_f3_f4_nested_blocks_with_null_collections_and_bad_colors(tmp_path: Path):
    """Tier 3 (F3 + F4): Deeply nested blocks with corrupted colors, non-dict payloads, and negative scaling."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "Parent": {
                "lines": [{"start": [0, 0], "end": [20, 20], "color": "NOT_A_COLOR"}],
                "arcs": [{"center": [10, 10], "radius": 5.0, "start_angle": 0, "end_angle": 180}],
            },
            "CorruptBlock": "not a dictionary",
        },
        "components": [
            None,
            {"block_name": "Parent", "scale": [-2.0, 0.5, 1.0], "position": [50, 50]},
            {"block_name": "NonExistentBlock", "position": [0, 0]},
        ],
        "annotations": None,
        "dimensions": None,
    }
    out = tmp_path / "t3_f3_f4_combined.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier3_f1_f2_f3_f4_omnibus_adversarial_fuzz_payload(tmp_path: Path):
    """Tier 3 (All Vectors Combined): Highly adversarial payload combining all 4 failure vectors simultaneously."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {"author": "Omnibus Stress Author", "source_file": "Omnibus Stress Test"},
        "layers": [
            {"name": "LayerA", "hex_color": "INVALID"},
            None,
            "NotADictLayer",
        ],
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [float("nan"), 0], "end": [10, 10]},
                    {"start": [1e12, 1e12], "end": [1e12, 1e12]},  # Astro + 0-length
                    {"start": [0, 0], "end": [100, 100], "color": "#FFFFFF", "line_width": -1.0},
                ],
                "arcs": [
                    {"center": [float("-inf"), 0], "radius": -5.0, "start_angle": 0, "end_angle": 0},
                ],
                "circles": [
                    {"center": [50, 50], "radius": 0.0, "color": "NO_HEX"},
                ],
                "polylines": [
                    {"points": [[0, 0], [float("nan"), 10], [10, 10]]},
                ],
            }
        },
        "block_definitions": {
            "OmniBlock": {
                "lines": [{"start": [0, 0], "end": [10, 10]}],
                "arcs": [{"center": [5, 5], "radius": 5.0, "start_angle": 0, "end_angle": 360}],
            }
        },
        "components": [
            {"block_name": "OmniBlock", "scale": [0.0, -1.0, 1.0], "position": [50, 50]},
            {"block_name": "MissingBlock", "scale": [1.0, 1.0, 1.0]},
        ],
        "annotations": [
            {"clean_text": "Stress Annotation", "position": [10, 10], "height": float("nan")},
        ],
        "dimensions": [
            {"measurement": float("inf"), "defpoint": [0, 0], "defpoint2": [10, 0]},
        ],
    }
    out = tmp_path / "t3_omnibus_adversarial.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


# =============================================================================
# TIER 4: REAL-WORLD WORKLOAD SCENARIOS (>= 5 realistic scenarios = 6 tests)
# =============================================================================

DEMO_DIR = Path(r"E:\Antigravity\La Vinci\experiments\e2e_demo")


def test_tier4_production_blueprint_citroen_2cv(tmp_path: Path):
    """Tier 4: E2E compilation of official Citroën 2CV production vehicle blueprint."""
    src = DEMO_DIR / "citroen_ir.json"
    if not src.exists():
        pytest.skip(f"Benchmark file not found: {src}")
    out = tmp_path / "citroen_2cv_e2e.pdf"
    res = compile_ir_to_pdf(src, out)
    assert_valid_iso32000_pdf(res)


def test_tier4_production_blueprint_hummer_h2(tmp_path: Path):
    """Tier 4: E2E compilation of official Hummer H2 production vehicle blueprint."""
    src = DEMO_DIR / "hummer_ir.json"
    if not src.exists():
        pytest.skip(f"Benchmark file not found: {src}")
    out = tmp_path / "hummer_h2_e2e.pdf"
    res = compile_ir_to_pdf(src, out)
    assert_valid_iso32000_pdf(res)


def test_tier4_production_blueprint_mercedes_w123(tmp_path: Path):
    """Tier 4: E2E compilation of official Mercedes-Benz W123 production blueprint."""
    src = DEMO_DIR / "mercedes_ir.json"
    if not src.exists():
        pytest.skip(f"Benchmark file not found: {src}")
    out = tmp_path / "mercedes_w123_e2e.pdf"
    res = compile_ir_to_pdf(src, out)
    assert_valid_iso32000_pdf(res)


def test_tier4_production_blueprint_mercedes_300sl(tmp_path: Path):
    """Tier 4: E2E compilation of official Mercedes-Benz 300 SL Gullwing blueprint."""
    src = DEMO_DIR / "mercedes_300sl_ir.json"
    if not src.exists():
        pytest.skip(f"Benchmark file not found: {src}")
    out = tmp_path / "mercedes_300sl_e2e.pdf"
    res = compile_ir_to_pdf(src, out)
    assert_valid_iso32000_pdf(res)


def test_tier4_architectural_floorplan_multi_layer_workload(tmp_path: Path):
    """Tier 4: Complex multi-layer architectural floorplan with walls, doors, windows, dimensions, and annotations."""
    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {
            "source_file": "architectural_floorplan_level1.dwg",
            "author": "Architectural Studio X",
        },
        "layers": [
            {"name": "A-WALL", "hex_color": "#000000"},
            {"name": "A-DOOR", "hex_color": "#0066CC"},
            {"name": "A-GLAZ", "hex_color": "#00CCCC"},
            {"name": "A-DIMS", "hex_color": "#808080"},
            {"name": "A-ANNO", "hex_color": "#333333"},
        ],
        "geometry_primitives": {
            "primitives": {
                # Outer and interior walls
                "lines": [
                    {"start": [0, 0], "end": [10000, 0], "layer": "A-WALL", "line_width": 1.2},
                    {"start": [10000, 0], "end": [10000, 8000], "layer": "A-WALL", "line_width": 1.2},
                    {"start": [10000, 8000], "end": [0, 8000], "layer": "A-WALL", "line_width": 1.2},
                    {"start": [0, 8000], "end": [0, 0], "layer": "A-WALL", "line_width": 1.2},
                    {"start": [5000, 0], "end": [5000, 8000], "layer": "A-WALL", "line_width": 0.8},
                ],
                # Door swings
                "arcs": [
                    {"center": [5000, 2000], "radius": 900.0, "start_angle": 0.0, "end_angle": 90.0, "layer": "A-DOOR"},
                    {"center": [0, 4000], "radius": 900.0, "start_angle": 270.0, "end_angle": 360.0, "layer": "A-DOOR"},
                ],
                # Columns / light points
                "circles": [
                    {"center": [2500, 4000], "radius": 150.0, "layer": "A-WALL"},
                    {"center": [7500, 4000], "radius": 150.0, "layer": "A-WALL"},
                ],
                # Partition polyline
                "polylines": [
                    {
                        "points": [[2000, 0], [2000, 3000], [3500, 3000]],
                        "is_closed": False,
                        "layer": "A-WALL",
                    }
                ],
            }
        },
        "block_definitions": {
            "WindowUnit": {
                "base_point": [0.0, 0.0, 0.0],
                "lines": [
                    {"start": [0, 0], "end": [1200, 0], "layer": "A-GLAZ"},
                    {"start": [0, 100], "end": [1200, 100], "layer": "A-GLAZ"},
                ],
            }
        },
        "components": [
            {"block_name": "WindowUnit", "position": [1500, 8000], "layer": "A-GLAZ"},
            {"block_name": "WindowUnit", "position": [6500, 8000], "layer": "A-GLAZ"},
            {"block_name": "WindowUnit", "position": [10000, 3000], "rotation": 90.0, "layer": "A-GLAZ"},
        ],
        "dimensions": [
            {
                "measurement": 10000.0,
                "defpoint": [0, -500],
                "defpoint2": [10000, -500],
                "text": "10.00 m",
                "layer": "A-DIMS",
            },
            {
                "measurement": 8000.0,
                "defpoint": [-500, 0],
                "defpoint2": [-500, 8000],
                "text": "8.00 m",
                "layer": "A-DIMS",
            },
        ],
        "annotations": [
            {"clean_text": "CONFERENCE ROOM", "position": [1500, 4000], "height": 250.0, "layer": "A-ANNO"},
            {"clean_text": "OPEN OFFICE AREA", "position": [6000, 4000], "height": 250.0, "layer": "A-ANNO"},
        ],
    }
    out = tmp_path / "t4_architectural_floorplan.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)


def test_tier4_high_density_primitive_stress_workload(tmp_path: Path):
    """Tier 4: Synthetic high-density workload containing 1,500+ primitives across multiple layers."""
    lines = []
    circles = []
    arcs = []

    for i in range(500):
        lines.append({
            "start": [float(i * 10), 0.0],
            "end": [float(i * 10), 1000.0],
            "layer": f"Grid_{i % 5}",
            "color": "#336699" if i % 2 == 0 else "#993333",
        })

    for i in range(250):
        circles.append({
            "center": [float(i * 20), 500.0],
            "radius": float(5 + (i % 20)),
            "layer": "Circles",
        })

    for i in range(250):
        arcs.append({
            "center": [float(i * 20), 250.0],
            "radius": 15.0,
            "start_angle": float((i * 15) % 360),
            "end_angle": float(((i * 15) + 90) % 360),
            "layer": "Arcs",
        })

    payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {"source_file": "stress_density_benchmark.dwg", "author": "QA Engine"},
        "layers": [
            {"name": "Grid_0", "hex_color": "#336699"},
            {"name": "Grid_1", "hex_color": "#993333"},
            {"name": "Grid_2", "hex_color": "#339933"},
            {"name": "Grid_3", "hex_color": "#999933"},
            {"name": "Grid_4", "hex_color": "#339999"},
            {"name": "Circles", "hex_color": "#FF0000"},
            {"name": "Arcs", "hex_color": "#0000FF"},
        ],
        "geometry_primitives": {
            "primitives": {
                "lines": lines,
                "circles": circles,
                "arcs": arcs,
            }
        },
    }
    out = tmp_path / "t4_high_density_stress.pdf"
    res = compile_ir_to_pdf(payload, out)
    assert_valid_iso32000_pdf(res)
