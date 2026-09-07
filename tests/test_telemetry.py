"""
test_telemetry.py — Comprehensive test suite for telemetry reporting and compilation metrics in cad-ir-to-pdf.
"""

import math
from pathlib import Path
import pytest

from cad_ir_to_pdf.compiler import compile_ir_to_pdf
from cad_ir_to_pdf.config import PRESETS, PdfPreset
from cad_ir_to_pdf.telemetry import (
    ActionTaken,
    CompilationReport,
    HardeningCategory,
    HardeningWarning,
)


def test_telemetry_clean_compilation(tmp_path: Path):
    """Test that a clean IR payload records accurate entity counts, timing, and viewport dimensions."""
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {
            "source_file": "clean_model.dwg",
            "author": "CAD Engineer",
            "subject": "Clean Architectural Plan",
        },
        "layers": [
            {"name": "Walls", "hex_color": "#FF0000"},
            {"name": "Windows", "hex_color": "#0000FF"},
        ],
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0, 0], "end": [100, 0], "layer": "Walls"},
                    {"start": [100, 0], "end": [100, 100], "layer": "Walls"},
                ],
                "arcs": [
                    {"center": [50, 50], "radius": 25, "start_angle": 0, "end_angle": 180, "layer": "Windows"},
                ],
                "circles": [
                    {"center": [50, 50], "radius": 10, "layer": "Windows"},
                ],
                "polylines": [
                    {"points": [[0, 0], [50, 0], [50, 50]], "is_closed": False, "layer": "Walls"},
                ],
            }
        },
        "annotations": [
            {"clean_text": "LIVING ROOM", "position": [20, 20], "height": 10.0, "layer": "Walls"},
        ],
        "dimensions": [
            {
                "measurement": 100.0,
                "defpoint": [0, 0],
                "defpoint2": [100, 0],
                "text": "100mm",
                "layer": "Walls",
            }
        ],
        "block_definitions": {
            "Table": {
                "name": "Table",
                "base_point": [0, 0],
                "lines": [{"start": [0, 0], "end": [20, 0]}],
            }
        },
        "components": [
            {
                "block_name": "Table",
                "position": [40, 40, 0],
                "rotation": 0.0,
                "scale": [1.0, 1.0, 1.0],
                "layer": "Walls",
            }
        ],
    }

    out_pdf = tmp_path / "clean_report.pdf"
    pdf_path, report = compile_ir_to_pdf(ir_data, out_pdf, return_report=True)

    assert pdf_path == out_pdf
    assert pdf_path.exists()
    assert isinstance(report, CompilationReport)
    assert report.success is True
    assert report.conversion_time_ms > 0.0

    # Total read entities:
    # 2 lines + 1 arc + 1 circle + 1 polyline + 1 component + 1 dimension + 1 annotation = 8
    assert report.total_entities_read == 8

    # Rendered entities:
    # 2 lines + 1 arc + 1 circle + 1 polyline + 1 component line + 1 dimension text + 1 annotation = 8
    assert report.total_entities_rendered == 8
    assert report.total_entities_dropped == 0
    assert report.total_entities_sanitized == 0
    assert len(report.warnings) == 0

    # Extents and Viewport metrics
    assert report.cad_bbox_extents is not None
    assert report.cad_bbox_extents["min_x"] <= 0.0
    assert report.cad_bbox_extents["max_x"] >= 100.0
    assert report.viewport_scale > 0.0
    assert report.page_dimensions_pt is not None
    assert report.page_dimensions_pt["width"] > 0.0
    assert report.page_dimensions_pt["height"] > 0.0


def test_telemetry_degenerate_geometry_warnings(tmp_path: Path):
    """Test that zero-length lines, collapsed polylines, zero radii, and zero arcs are recorded with DEGENERATE_GEOMETRY."""
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [10, 10], "end": [10, 10]},  # Zero-length line
                    {"start": [0, 0], "end": [100, 100]},  # Valid line
                ],
                "arcs": [
                    {"center": [0, 0], "radius": 0.0, "start_angle": 0, "end_angle": 90},  # Zero radius
                    {"center": [0, 0], "radius": 10.0, "start_angle": 45, "end_angle": 45},  # Zero sweep
                ],
                "circles": [
                    {"center": [0, 0], "radius": -5.0},  # Negative radius
                ],
                "polylines": [
                    {"points": [[0, 0]]},  # Fewer than 2 points
                    {"points": [[5, 5], [5, 5]]},  # Coincident collapsed polyline
                ],
            }
        },
    }

    out_pdf = tmp_path / "degenerate_report.pdf"
    _, report = compile_ir_to_pdf(ir_data, out_pdf, return_report=True)

    assert report.total_entities_read == 7
    assert report.total_entities_rendered == 1  # only valid line rendered
    assert report.total_entities_dropped >= 6

    degen_warnings = [w for w in report.warnings if w.category == HardeningCategory.DEGENERATE_GEOMETRY]
    assert len(degen_warnings) >= 5

    actions = [w.action for w in degen_warnings]
    assert all(a == ActionTaken.DROPPED for a in actions)


def test_telemetry_coordinate_singularity_warnings(tmp_path: Path):
    """Test that NaN, Inf, and invalid point coordinates trigger COORDINATE_SINGULARITY warnings."""
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [float("nan"), 0], "end": [10, 10]},
                    {"start": [0, 0], "end": [float("inf"), 10]},
                ],
                "circles": [
                    {"center": [None, 10], "radius": 10.0},
                ],
                "arcs": [
                    {"center": [10, float("-inf")], "radius": 10.0, "start_angle": 0, "end_angle": 90},
                ],
            }
        },
        "annotations": [
            {"clean_text": "Bad Point", "position": [float("nan"), 0], "height": 10.0},
        ],
    }

    out_pdf = tmp_path / "singularity_report.pdf"
    _, report = compile_ir_to_pdf(ir_data, out_pdf, return_report=True)

    assert report.total_entities_read == 5
    assert report.total_entities_rendered == 0
    assert report.total_entities_dropped == 5

    singularity_warnings = [w for w in report.warnings if w.category == HardeningCategory.COORDINATE_SINGULARITY]
    assert len(singularity_warnings) == 5
    assert all(w.action == ActionTaken.DROPPED for w in singularity_warnings)


def test_telemetry_font_and_color_fallback(tmp_path: Path):
    """Test that invalid font names and malformed colors record fallback warnings."""
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "layers": [
            {"name": "CorruptedLayer", "hex_color": "NOT_A_HEX_VALUE"},
        ],
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0, 0], "end": [10, 10], "color": "INVALID_HEX_CODE", "layer": "CorruptedLayer"},
                ],
            }
        },
        "annotations": [
            {"clean_text": "Sample Text", "position": [5, 5], "height": 12.0},
        ],
    }

    preset = PdfPreset(
        name="custom_test_preset",
        font_name="NonExistentFontXYZ123",
        color_mode="full_color",
    )

    out_pdf = tmp_path / "fallback_report.pdf"
    _, report = compile_ir_to_pdf(ir_data, out_pdf, preset=preset, return_report=True)

    assert report.total_entities_read == 2
    assert report.total_entities_rendered == 2  # line + annotation rendered using fallbacks

    font_fallbacks = [w for w in report.warnings if w.category == HardeningCategory.FONT_FALLBACK]
    color_fallbacks = [w for w in report.warnings if w.category == HardeningCategory.COLOR_FALLBACK]

    assert len(font_fallbacks) >= 1
    assert any("NonExistentFontXYZ123" in w.reason for w in font_fallbacks)
    assert any(w.action == ActionTaken.FALLBACK_APPLIED for w in font_fallbacks)

    assert len(color_fallbacks) >= 1
    assert any(w.action == ActionTaken.FALLBACK_APPLIED for w in color_fallbacks)


def test_telemetry_metadata_sanitization(tmp_path: Path):
    """Test that null bytes, non-string, or malformed metadata record METADATA_MALFORMED warnings."""
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {
            "source_file": "drawing\x00corrupt.dwg",
            "author": {"nested": "dict_instead_of_str"},
            "subject": "A" * 2000,  # exceeds 1024 cap
        },
        "geometry_primitives": {
            "primitives": {
                "lines": [{"start": [0, 0], "end": [5, 5]}],
            }
        },
    }

    out_pdf = tmp_path / "metadata_report.pdf"
    _, report = compile_ir_to_pdf(ir_data, out_pdf, return_report=True)

    metadata_warnings = [w for w in report.warnings if w.category == HardeningCategory.METADATA_MALFORMED]
    assert len(metadata_warnings) >= 1
    assert all(w.action == ActionTaken.SANITIZED for w in metadata_warnings)
    assert report.total_entities_sanitized >= 1


def test_telemetry_backwards_compatibility(tmp_path: Path):
    """Verify that calling compile_ir_to_pdf without return_report returns a Path instance."""
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [{"start": [0, 0], "end": [10, 10]}],
            }
        },
    }

    out_pdf = tmp_path / "backwards_compat.pdf"
    res = compile_ir_to_pdf(ir_data, out_pdf)
    assert isinstance(res, Path)
    assert res == out_pdf
    assert res.exists()


def test_telemetry_block_abuse_warnings(tmp_path: Path):
    """Verify that missing block definitions and circular block references log BLOCK_ABUSE warnings."""
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "CycleA": {
                "name": "CycleA",
                "components": [{"block_name": "CycleA", "position": [1, 1]}],
                "lines": [{"start": [0, 0], "end": [5, 5]}],
            }
        },
        "components": [
            {"block_name": "NonExistentBlock", "position": [10, 10]},
            {"block_name": "CycleA", "position": [20, 20]},
        ],
    }

    out_pdf = tmp_path / "block_abuse.pdf"
    _, report = compile_ir_to_pdf(ir_data, out_pdf, return_report=True)

    block_warnings = [w for w in report.warnings if w.category == HardeningCategory.BLOCK_ABUSE]
    assert len(block_warnings) >= 2

    reasons = [w.reason for w in block_warnings]
    assert any("not found or invalid" in r for r in reasons)
    assert any("Circular block reference" in r for r in reasons)


def test_telemetry_to_dict_serialization(tmp_path: Path):
    """Verify that CompilationReport and HardeningWarning serialize cleanly to dict for MCP/JSON transport."""
    ir_data = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0, 0], "end": [10, 10]},
                    {"start": [0, 0], "end": [0, 0]},  # degenerate
                ],
            }
        },
    }

    out_pdf = tmp_path / "to_dict_test.pdf"
    _, report = compile_ir_to_pdf(ir_data, out_pdf, return_report=True)

    data = report.to_dict()
    assert isinstance(data, dict)
    assert data["success"] is True
    assert data["total_entities_read"] == 2
    assert data["total_entities_rendered"] == 1
    assert data["total_entities_dropped"] == 1
    assert data["warning_count"] == 1
    assert len(data["warnings"]) == 1

    w0 = data["warnings"][0]
    assert w0["category"] == "degenerate_geometry"
    assert w0["action"] == "dropped"
    assert w0["entity_type"] == "line"

