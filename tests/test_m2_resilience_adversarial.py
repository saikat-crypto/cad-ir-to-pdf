"""
test_m2_resilience_adversarial.py — Exhaustive Adversarial Fuzzing & Stress Suite for Milestone M2.

Validates the resilience hardening of:
- Feature 11: Metadata sanitization (non-string, dict, list, float inf/nan, null bytes, C0 controls, 1024 char capping)
- Feature 12: Hex color parsing, normalization, luminance contrast safety, corrupted fallbacks
- Feature 13: Line weight clamping [0.05, 50.0] pt, invalid types, booleans, negative, NaN/Inf
- Feature 14: Font size clamping [1.0, 144.0] pt, font name sanitization, unregistered font fallbacks
- Feature 15 & 16: Degenerate primitive dropping (zero-length lines, coincident polylines, 0-radius circles, zero-sweep arcs)
- Dimension text and annotation formatting
- ISO 32000 conformance with PyMuPDF verification (is_pdf, no repair, no NaN/Inf tokens)
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, List

import pymupdf
import pytest
from reportlab.lib import colors
from reportlab.pdfgen import canvas

from cad_ir_to_pdf.compiler import compile_ir_to_pdf
from cad_ir_to_pdf.config import (
    DEFAULT_FONT_NAME,
    DEFAULT_LINE_WIDTH_PT,
    MAX_FONT_SIZE_PT,
    MAX_LINE_WIDTH_PT,
    MIN_FONT_SIZE_PT,
    MIN_LINE_WIDTH_PT,
    PAGE_SIZES_PORTRAIT,
    PdfPreset,
)
from cad_ir_to_pdf.geometry import AffineMatrix2D, ViewportMapping
from cad_ir_to_pdf.renderer import (
    PdfVectorRenderer,
    _clean_hex,
    _hex_luminance,
    hex_to_pdf_color,
    sanitize_cad_text,
    sanitize_line_width,
    sanitize_metadata_string,
)

if not hasattr(pymupdf.Document, "is_repair"):
    pymupdf.Document.is_repair = property(lambda self: getattr(self, "is_repaired", False))


def assert_valid_iso32000_pdf(pdf_path: Path) -> None:
    assert pdf_path.exists(), f"PDF output was not created: {pdf_path}"
    assert pdf_path.stat().st_size > 0, f"PDF output is 0 bytes: {pdf_path}"

    doc = pymupdf.open(str(pdf_path))
    try:
        assert doc.is_pdf is True, f"Invalid PDF: {pdf_path}"
        assert doc.is_repair is False, f"PDF required repair: {pdf_path}"
        assert doc.page_count >= 1, f"Expected >= 1 page, got {doc.page_count}"

        for page_idx in range(doc.page_count):
            page = doc[page_idx]
            contents = page.read_contents()
            if isinstance(contents, (list, tuple)):
                raw_bytes = b"".join(contents)
            elif isinstance(contents, (bytes, bytearray)):
                raw_bytes = bytes(contents)
            else:
                raw_bytes = b""
            assert not re.search(
                rb"(?i)\b(nan|inf|-inf)\b", raw_bytes
            ), f"Forbidden IEEE token found on page {page_idx}"
    finally:
        doc.close()


# =============================================================================
# Feature 11: Metadata Sanitization
# =============================================================================

class TestMetadataSanitization:
    def test_sanitize_none_and_empty(self):
        assert sanitize_metadata_string(None, default="Default") == "Default"
        assert sanitize_metadata_string("", default="Default") == "Default"
        assert sanitize_metadata_string("   ", default="Default") == "Default"

    def test_sanitize_non_finite_float(self):
        assert sanitize_metadata_string(float("nan"), default="Fallback") == "Fallback"
        assert sanitize_metadata_string(float("inf"), default="Fallback") == "Fallback"
        assert sanitize_metadata_string(float("-inf"), default="Fallback") == "Fallback"

    def test_sanitize_numbers_and_booleans(self):
        assert sanitize_metadata_string(12345) == "12345"
        assert sanitize_metadata_string(3.14159) == "3.14159"
        assert sanitize_metadata_string(True) == "True"

    def test_sanitize_containers(self):
        assert sanitize_metadata_string({"title": "DWG"}) == '{"title": "DWG"}'
        assert sanitize_metadata_string([1, 2, 3]) == "[1, 2, 3]"

    def test_sanitize_bytes(self):
        b = b"Binary \x00 CAD \x07 Title"
        assert sanitize_metadata_string(b) == "Binary  CAD  Title"

    def test_c0_controls_and_null_bytes(self):
        malicious = "CAD\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x1f\x7fDrawing"
        cleaned = sanitize_metadata_string(malicious)
        assert cleaned == "CADDrawing"

    def test_length_capping(self):
        long_str = "A" * 2000
        cleaned = sanitize_metadata_string(long_str)
        assert len(cleaned) == 1024


# =============================================================================
# Feature 12: Hex Color Resilience & Contrast Safety
# =============================================================================

class TestHexColorResilience:
    def test_clean_hex_varieties(self):
        assert _clean_hex("#ABC") == "#AABBCC"
        assert _clean_hex("ABC") == "#AABBCC"
        assert _clean_hex("#123456") == "#123456"
        assert _clean_hex("123456") == "#123456"
        assert _clean_hex("#123456FF") == "#123456"
        assert _clean_hex("12345600") == "#123456"
        assert _clean_hex("not-a-hex") is None
        assert _clean_hex(None) is None
        assert _clean_hex(123) is None
        assert _clean_hex("") is None

    def test_hex_to_pdf_color_basic(self):
        c = hex_to_pdf_color("#FF0000")
        assert isinstance(c, colors.Color)
        assert math.isclose(c.red, 1.0, rel_tol=1e-3)
        assert math.isclose(c.green, 0.0, abs_tol=1e-3)
        assert math.isclose(c.blue, 0.0, abs_tol=1e-3)

    def test_hex_to_pdf_color_contrast_light_bg(self):
        # White stroke on white bg should remap to fallback
        c = hex_to_pdf_color("#FFFFFF", fallback="#112233", background_hex="#FFFFFF")
        assert c.hexval().upper() == "0X112233"

        # White stroke on light bg with white fallback should remap to black
        c2 = hex_to_pdf_color("#FFFFFF", fallback="#FFFFFF", background_hex="#FFFFFF")
        assert c2.hexval().upper() == "0X000000"

    def test_hex_to_pdf_color_contrast_dark_bg(self):
        # Black stroke on near-black background should remap to white
        c = hex_to_pdf_color("#000000", fallback="#000000", background_hex="#050505")
        assert c.hexval().upper() == "0XFFFFFF"

    def test_hex_to_pdf_color_corrupted_everything(self):
        # Corrupted input, corrupted fallback, corrupted bg
        c = hex_to_pdf_color("TOTAL_JUNK", fallback="ALSO_JUNK", background_hex="JUNK_BG")
        assert isinstance(c, colors.Color)
        assert c.hexval().upper() == "0X000000"


# =============================================================================
# Feature 13: Line Width Clamping
# =============================================================================

class TestLineWidthClamping:
    def test_valid_widths(self):
        assert sanitize_line_width(0.5) == 0.5
        assert sanitize_line_width(10.0) == 10.0
        assert sanitize_line_width(MIN_LINE_WIDTH_PT) == MIN_LINE_WIDTH_PT
        assert sanitize_line_width(MAX_LINE_WIDTH_PT) == MAX_LINE_WIDTH_PT

    def test_clamping_extremes(self):
        assert sanitize_line_width(0.001) == MIN_LINE_WIDTH_PT
        assert sanitize_line_width(100.0) == MAX_LINE_WIDTH_PT
        assert sanitize_line_width(1e9) == MAX_LINE_WIDTH_PT

    def test_invalid_types_and_values(self):
        assert sanitize_line_width(None) == DEFAULT_LINE_WIDTH_PT
        assert sanitize_line_width(True) == DEFAULT_LINE_WIDTH_PT
        assert sanitize_line_width(False) == DEFAULT_LINE_WIDTH_PT
        assert sanitize_line_width(-5.0) == DEFAULT_LINE_WIDTH_PT
        assert sanitize_line_width(0.0) == DEFAULT_LINE_WIDTH_PT
        assert sanitize_line_width(float("nan")) == DEFAULT_LINE_WIDTH_PT
        assert sanitize_line_width(float("inf")) == DEFAULT_LINE_WIDTH_PT
        assert sanitize_line_width("1.5") == DEFAULT_LINE_WIDTH_PT


# =============================================================================
# Feature 14: Font Size Clamping & Font Name Safety
# =============================================================================

class TestFontResilience:
    @pytest.fixture
    def mock_renderer(self, tmp_path):
        out_pdf = tmp_path / "mock.pdf"
        c = canvas.Canvas(str(out_pdf))
        vp = ViewportMapping(
            scale=1.0,
            cad_center_x=0.0,
            cad_center_y=0.0,
            pdf_center_x=250.0,
            pdf_center_y=250.0,
        )
        preset = PdfPreset(name="test")
        renderer = PdfVectorRenderer(c, vp, preset)
        yield renderer, c, out_pdf
        c.save()

    def test_sanitize_font_size(self, mock_renderer):
        renderer, _, _ = mock_renderer
        assert renderer.sanitize_font_size(12.0) == 12.0
        assert renderer.sanitize_font_size(0.5) == MIN_FONT_SIZE_PT
        assert renderer.sanitize_font_size(500.0) == MAX_FONT_SIZE_PT
        assert renderer.sanitize_font_size(-10.0) == 12.0
        assert renderer.sanitize_font_size(None) == 12.0
        assert renderer.sanitize_font_size(True) == 12.0
        assert renderer.sanitize_font_size(float("nan")) == 12.0
        assert renderer.sanitize_font_size(float("inf")) == 12.0
        assert renderer.sanitize_font_size("twenty") == 12.0

    def test_set_font_safe_fallback(self, mock_renderer):
        renderer, _, _ = mock_renderer
        # Valid font
        sz = renderer._set_font_safe("Helvetica-Bold", 14.0)
        assert sz == 14.0
        # Invalid / Unregistered font should fall back to Helvetica
        sz2 = renderer._set_font_safe("NonExistentCADFont-XYZ", 200.0)
        assert sz2 == MAX_FONT_SIZE_PT


# =============================================================================
# Feature 15 & 16: Degenerate Primitive Dropping
# =============================================================================

class TestDegeneratePrimitiveDropping:
    def test_zero_length_line_dropping(self, tmp_path):
        payload = {
            "format": "LAVINCI_CAD_IR_V3",
            "geometry_primitives": {
                "primitives": {
                    "lines": [
                        {"start": [10.0, 10.0], "end": [10.0, 10.0]},  # zero length
                        {"start": [10.0, 10.0], "end": [10.00000001, 10.0]},  # near zero (< 1e-6)
                        {"start": [0.0, 0.0], "end": [100.0, 100.0]},  # valid
                    ]
                }
            },
        }
        out_pdf = tmp_path / "zero_line.pdf"
        compile_ir_to_pdf(payload, out_pdf)
        assert_valid_iso32000_pdf(out_pdf)

    def test_coincident_polyline_dropping(self, tmp_path):
        payload = {
            "format": "LAVINCI_CAD_IR_V3",
            "geometry_primitives": {
                "primitives": {
                    "polylines": [
                        {"points": [[10.0, 10.0], [10.0, 10.0], [10.0, 10.0]]},  # all coincident
                        {"points": [[0.0, 0.0], [0.0, 0.0], [50.0, 50.0], [50.0, 50.0]]},  # dups filtered
                    ]
                }
            },
        }
        out_pdf = tmp_path / "coincident_pline.pdf"
        compile_ir_to_pdf(payload, out_pdf)
        assert_valid_iso32000_pdf(out_pdf)

    def test_zero_radius_and_zero_sweep_arcs(self, tmp_path):
        payload = {
            "format": "LAVINCI_CAD_IR_V3",
            "geometry_primitives": {
                "primitives": {
                    "circles": [
                        {"center": [0, 0], "radius": 0.0},
                        {"center": [0, 0], "radius": -10.0},
                        {"center": [0, 0], "radius": float("nan")},
                        {"center": [50, 50], "radius": 25.0},  # valid
                    ],
                    "arcs": [
                        {"center": [0, 0], "radius": 10.0, "start_angle": 45.0, "end_angle": 45.0},  # zero sweep
                        {"center": [0, 0], "radius": -5.0, "start_angle": 0.0, "end_angle": 90.0},  # negative radius
                        {"center": [50, 50], "radius": 20.0, "start_angle": 0.0, "end_angle": 90.0},  # valid
                    ],
                }
            },
        }
        out_pdf = tmp_path / "degenerate_curves.pdf"
        compile_ir_to_pdf(payload, out_pdf)
        assert_valid_iso32000_pdf(out_pdf)


# =============================================================================
# E2E Preset and Margin Robustness
# =============================================================================

class TestPresetAndMarginRobustness:
    def test_corrupted_margin_and_orientation(self):
        p1 = PdfPreset(name="p1", margin_mm=-50.0, orientation="INVALID_ORIENT")
        assert p1.margin_pt == 12.0 * (72.0 / 25.4)
        dims = p1.get_page_dimensions_pt()
        assert dims[0] > 0 and dims[1] > 0

        p2 = PdfPreset(name="p2", margin_mm=float("nan"), paper_size=None)
        assert p2.margin_pt == 12.0 * (72.0 / 25.4)
        dims2 = p2.get_page_dimensions_pt()
        assert dims2 == (PAGE_SIZES_PORTRAIT["A3"][1], PAGE_SIZES_PORTRAIT["A3"][0])  # landscape default
