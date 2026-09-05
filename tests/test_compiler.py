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
