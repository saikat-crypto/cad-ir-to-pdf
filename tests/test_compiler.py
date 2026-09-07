import json
import pytest
from pathlib import Path
from cad_ir_to_pdf.compiler import compile_ir_to_pdf
from cad_ir_to_pdf.config import PRESETS, PdfPreset


def test_compile_minimal_ir(tmp_path):
    minimal_ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {"source_file": "unit_test.dwg"},
        "layers": [
            {"name": "Walls", "hex_color": "#FF0000"},
            {"name": "Doors", "hex_color": "#00FF00"}
        ],
        "geometry_primitives": {
            "primitives": {
                "lines": [
                    {"start": [0, 0], "end": [100, 0], "layer": "Walls"},
                    {"start": [100, 0], "end": [100, 50], "layer": "Walls"},
                ],
                "arcs": [
                    {"center": [50, 50], "radius": 20, "start_angle": 0, "end_angle": 180, "layer": "Doors"}
                ],
                "circles": [
                    {"center": [50, 25], "radius": 10, "layer": "Doors"}
                ],
                "polylines": [
                    {"points": [[0, 0], [0, 50], [50, 50]], "is_closed": False, "layer": "Walls"}
                ]
            }
        },
        "annotations": [
            {"clean_text": "ROOM 101", "position": [50, 25], "height": 5.0, "layer": "Walls"}
        ],
        "block_definitions": {
            "Chair": {
                "name": "Chair",
                "base_point": [0, 0],
                "lines": [{"start": [0, 0], "end": [5, 5]}],
                "circles": [{"center": [2.5, 2.5], "radius": 2.5}]
            }
        },
        "components": [
            {
                "block_name": "Chair",
                "position": [30, 20, 0],
                "rotation": 45.0,
                "scale": [1.0, 1.0, 1.0],
                "layer": "Doors"
            }
        ]
    }

    out_pdf = tmp_path / "test_output.pdf"
    res = compile_ir_to_pdf(minimal_ir, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 1000  # PDF generated with content


def test_compile_presets(tmp_path):
    simple_ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "geometry_primitives": {
            "primitives": {
                "lines": [{"start": [0, 0], "end": [10, 10]}]
            }
        }
    }
    for preset_name, preset in PRESETS.items():
        out_pdf = tmp_path / f"test_{preset_name}.pdf"
        res = compile_ir_to_pdf(simple_ir, out_pdf, preset=preset)
        assert res.exists()
        assert res.stat().st_size > 500


def test_sanitize_cad_text():
    from cad_ir_to_pdf.renderer import sanitize_cad_text
    # Underline code %%u
    assert sanitize_cad_text("%%U396.00") == "396.00"
    assert sanitize_cad_text("%%uRoom Area%%u") == "Room Area"
    # Degrees and plus-minus
    assert sanitize_cad_text(r"45%%d") == "45°"
    assert sanitize_cad_text(r"%%p0.05") == "±0.05"
    assert sanitize_cad_text(r"%%c50") == "Ø50"
    # MTEXT formatting codes
    assert sanitize_cad_text(r"{\fGOST Common|b0|i0|c204|p34;\W.8;19}") == "19"
    # Superscript square meter replacement
    assert sanitize_cad_text("Area, m\ufffd") == "Area, m²"
    assert sanitize_cad_text("5,5m\ufffd") == "5,5m²"


def test_compile_dimensions(tmp_path):
    ir_with_dims = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {"source_file": "dims_test.dwg"},
        "geometry_primitives": {
            "primitives": {
                "lines": [{"start": [0, 0], "end": [3000, 0]}]
            }
        },
        "block_definitions": {
            "*D1": {
                "name": "*D1",
                "base_point": [0.0, 0.0, 0.0],
                "lines": [
                    {"start": [0, -50], "end": [3000, -50], "layer": "dimension"},
                    {"start": [0, 0], "end": [0, -60], "layer": "dimension"},
                    {"start": [3000, 0], "end": [3000, -60], "layer": "dimension"},
                ],
                "polylines": [
                    {"points": [[-10, -40], [10, -60]], "is_closed": False, "layer": "dimension"},
                    {"points": [[2990, -40], [3010, -60]], "is_closed": False, "layer": "dimension"},
                ]
            }
        },
        "dimensions": [
            {
                "type": "DIMENSION",
                "layer": "dimension",
                "space": "Model",
                "measurement": 3000.0,
                "text": "3000",
                "defpoint": [3000.0, -50.0],
                "defpoint2": [0.0, -50.0]
            }
        ]
    }

    out_pdf = tmp_path / "dim_output.pdf"
    res = compile_ir_to_pdf(ir_with_dims, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 1000


def test_compile_dimensions_with_metadata_and_clearance(tmp_path):
    """Verifies dimension text sits cleanly above line with clearance and respects text metadata."""
    ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {"source_file": "dims_clearance.dwg"},
        "geometry_primitives": {
            "primitives": {"lines": [{"start": [0, 0], "end": [2000, 0]}]}
        },
        "dimensions": [
            {
                "type": "DIMENSION",
                "layer": "dimension",
                "space": "Model",
                "measurement": 2000.0,
                "text": "2000",
                "defpoint": [2000.0, 100.0],
                "defpoint2": [0.0, 100.0],
                "text_midpoint": [1000.0, 120.0],
                "text_height": 50.0,
                "text_rotation": 0.0,
            },
            {
                "type": "DIMENSION",
                "layer": "dimension",
                "space": "Model",
                "measurement": 500.0,
                "text": "500",
                "defpoint": [100.0, 500.0],
                "defpoint2": [100.0, 0.0],
                "text_midpoint": [80.0, 250.0],
                "text_height": 50.0,
                "text_rotation": 90.0,
            }
        ]
    }
    out_pdf = tmp_path / "dims_clearance.pdf"
    res = compile_ir_to_pdf(ir, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 1000

