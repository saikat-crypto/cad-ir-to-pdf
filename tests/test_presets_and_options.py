"""
test_presets_and_options.py — Test suite for ready-made presets, PdfOptions overrides,
layer filtering, watermarks, and introspection utilities.
"""

import json
import pytest
from pathlib import Path
import fitz

from cad_ir_to_pdf.config import (
    DEFAULT_PRESET,
    PRESETS,
    PdfOptions,
    PdfPreset,
    get_preset,
    list_presets,
    MONOCHROME_ARCHITECTURAL_PRESET,
    PRESENTATION_COLOR_PRESET,
    PERMIT_ARCH_D_PRESET,
    DARK_BLUEPRINT_PRESET,
    WEB_MOBILE_A4_PRESET,
)
from cad_ir_to_pdf.compiler import compile_ir_to_pdf


@pytest.fixture
def sample_ir_dict():
    """Generates a multi-layer sample CAD IR v3 dictionary."""
    return {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {
            "source_file": "sample_drawing.dwg",
            "cad_version": "R2018",
            "units": 4,
            "measurement_system": "metric",
            "author": "Antigravity Engineering",
        },
        "layers": [
            {"name": "WALLS", "hex_color": "#FF0000", "color_aci": 1, "is_off": False, "is_locked": False, "is_frozen": False, "linetype": "Continuous"},
            {"name": "DOORS", "hex_color": "#00FF00", "color_aci": 3, "is_off": False, "is_locked": False, "is_frozen": False, "linetype": "Continuous"},
            {"name": "DEFPOINTS", "hex_color": "#7F7F7F", "color_aci": 8, "is_off": False, "is_locked": False, "is_frozen": False, "linetype": "Continuous"},
        ],
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0, 0], "end": [1000, 0], "layer": "WALLS", "space": "Model"},
                    {"start": [1000, 0], "end": [1000, 1000], "layer": "WALLS", "space": "Model"},
                    {"start": [0, 0], "end": [0, 1000], "layer": "DOORS", "space": "Model"},
                    {"start": [-100, -100], "end": [-50, -50], "layer": "DEFPOINTS", "space": "Model"},
                ],
                "arcs": [],
                "circles": [],
                "polylines": [],
            }
        },
        "block_definitions": {},
        "components": [],
        "annotations": [
            {"raw_text": "ROOM 101", "clean_text": "ROOM 101", "position": [500, 500], "height": 100, "layer": "WALLS", "space": "Model"}
        ],
        "dimensions": [],
    }


def test_list_presets_catalog():
    """Verify that list_presets returns all 8 distinct presets with required metadata."""
    catalog = list_presets()
    assert len(catalog) == 8
    preset_ids = {p["id"] for p in catalog}
    assert "monochrome-arch" in preset_ids
    assert "presentation-color" in preset_ids
    assert "permit-arch-d" in preset_ids
    assert "dark-blueprint" in preset_ids
    assert "web-mobile-a4" in preset_ids
    assert "high-quality-print" in preset_ids
    assert "review-screened" in preset_ids
    assert "metric-construction-a1" in preset_ids


def test_get_preset_resolution():
    """Verify string preset names and aliases resolve safely to PdfPreset instances."""
    assert get_preset("monochrome-arch") == MONOCHROME_ARCHITECTURAL_PRESET
    assert get_preset("monochrome-architectural") == MONOCHROME_ARCHITECTURAL_PRESET  # Backward-compat alias
    assert get_preset("presentation-color") == PRESENTATION_COLOR_PRESET
    assert get_preset("presentation-fit-vector") == PRESENTATION_COLOR_PRESET          # Backward-compat alias
    assert get_preset("dark-blueprint") == DARK_BLUEPRINT_PRESET
    assert get_preset("DARK-BLUEPRINT") == DARK_BLUEPRINT_PRESET                     # Case insensitive
    assert get_preset("unknown-preset") == DEFAULT_PRESET                             # Safe fallback
    assert get_preset(None) == DEFAULT_PRESET


def test_preset_with_options_immutability():
    """Verify that with_options does not mutate the base preset."""
    base = MONOCHROME_ARCHITECTURAL_PRESET
    custom = base.with_options(PdfOptions(paper_size="A1", margin_mm=20.0, watermark_text="TEST"))

    # Original remains untouched
    assert base.paper_size == "A3"
    assert base.margin_mm == 12.0
    assert base.watermark_text is None

    # Custom has overrides
    assert custom.paper_size == "A1"
    assert custom.margin_mm == 20.0
    assert custom.watermark_text == "TEST"


def test_compile_with_ready_made_presets(sample_ir_dict, tmp_path):
    """Test compiling across different ready-made presets using string keys."""
    for preset_name in ["monochrome-arch", "presentation-color", "dark-blueprint", "permit-arch-d", "web-mobile-a4"]:
        out_pdf = tmp_path / f"test_{preset_name}.pdf"
        res_path, report = compile_ir_to_pdf(
            ir_source=sample_ir_dict,
            output_path=out_pdf,
            preset=preset_name,
            return_report=True,
        )
        assert res_path.exists()
        assert out_pdf.stat().st_size > 0
        assert report.total_entities_rendered > 0

        # Validate PDF structure via PyMuPDF
        doc = fitz.open(res_path)
        assert len(doc) == 1
        page = doc[0]
        assert page.rect.width > 0
        assert page.rect.height > 0
        doc.close()


def test_compile_with_options_overrides(sample_ir_dict, tmp_path):
    """Test compiling with a preset baseline + surgical PdfOptions overrides."""
    out_pdf = tmp_path / "custom_override.pdf"
    res_path = compile_ir_to_pdf(
        ir_source=sample_ir_dict,
        output_path=out_pdf,
        preset="monochrome-arch",
        options=PdfOptions(
            paper_size="LETTER",
            orientation="portrait",
            watermark_text="CONFIDENTIAL DRAFT",
            line_weight_multiplier=1.5,
        ),
    )
    assert res_path.exists()
    doc = fitz.open(res_path)
    page = doc[0]
    # LETTER portrait is approx 612 x 792 pt
    assert abs(page.rect.width - 612.0) < 1.0
    assert abs(page.rect.height - 792.0) < 1.0
    doc.close()


def test_layer_visibility_filtering(sample_ir_dict, tmp_path):
    """Test hidden_layers and visible_layers filtering."""
    # 1. Hide WALLS layer (which has 2 lines and 1 annotation)
    out_pdf = tmp_path / "hide_walls.pdf"
    _, report_hide = compile_ir_to_pdf(
        ir_source=sample_ir_dict,
        output_path=out_pdf,
        preset="monochrome-arch",
        options=PdfOptions(hidden_layers=["WALLS"]),
        return_report=True,
    )
    # Only DOORS line and DEFPOINTS line should be processed
    assert report_hide.total_entities_rendered < 4

    # 2. Only visible_layers DOORS
    out_doors = tmp_path / "only_doors.pdf"
    _, report_doors = compile_ir_to_pdf(
        ir_source=sample_ir_dict,
        output_path=out_doors,
        preset="monochrome-arch",
        options=PdfOptions(visible_layers=["DOORS"]),
        return_report=True,
    )
    assert report_doors.total_entities_rendered == 1


def test_dict_options_compatibility(sample_ir_dict, tmp_path):
    """Verify that options passed as a raw dict (e.g. from JSON payload) works identically."""
    out_pdf = tmp_path / "dict_options.pdf"
    res_path = compile_ir_to_pdf(
        ir_source=sample_ir_dict,
        output_path=out_pdf,
        options={"paper_size": "A4", "watermark_text": "PRELIMINARY"},
    )
    assert res_path.exists()
    doc = fitz.open(res_path)
    page = doc[0]
    # A4 landscape is 841.89 x 595.28 pt
    assert abs(page.rect.width - 841.89) < 1.0
    assert abs(page.rect.height - 595.28) < 1.0
    doc.close()
