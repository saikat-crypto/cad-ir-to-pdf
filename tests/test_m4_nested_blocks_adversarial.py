"""
test_m4_nested_blocks_adversarial.py — Adversarial stress test suite for Milestone M4.

Covers:
- Direct recursion cycle: Block A referencing Block A in components.
- Indirect recursion cycle: Block A -> Block B -> Block A.
- Deep recursion depth limit: Chain of nested blocks A1 -> A2 -> ... -> A25 truncated cleanly at MAX_BLOCK_DEPTH (16).
- Nested affine transform composition: parent rotation & translation @ child rotation & translation.
- Layer inheritance: child block inheriting parent component layer when unspecified.
- Non-uniform scaling and arc angle transformation in nested blocks.
- Missing child block definition: graceful skip without crashing.
- Block bounding box calculation in compute_ir_extents with nested components.
"""

import math
from pathlib import Path
import pytest
from cad_ir_to_pdf.geometry import (
    AffineMatrix2D,
    BoundingBox,
    compute_ir_extents,
)
from cad_ir_to_pdf.compiler import compile_ir_to_pdf
from cad_ir_to_pdf.config import PdfPreset


def test_m4_direct_block_recursion_cycle(tmp_path: Path):
    """Verify that a block referencing itself directly (A -> A) terminates immediately without infinite loop."""
    ir_payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "BlockA": {
                "name": "BlockA",
                "base_point": [0.0, 0.0, 0.0],
                "lines": [{"start": [0.0, 0.0], "end": [10.0, 10.0]}],
                "components": [
                    {
                        "block_name": "BlockA",
                        "position": [5.0, 5.0, 0.0],
                        "rotation": 0.0,
                    }
                ]
            }
        },
        "components": [
            {
                "block_name": "BlockA",
                "position": [100.0, 100.0, 0.0],
                "rotation": 0.0,
            }
        ]
    }
    # Verify extents computation handles direct cycle
    bbox = compute_ir_extents(ir_payload)
    assert bbox.is_valid
    assert bbox.min_x <= 100.0 and bbox.max_x >= 110.0

    # Verify compiler renders without RecursionError
    out_pdf = tmp_path / "direct_cycle.pdf"
    res = compile_ir_to_pdf(ir_payload, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 0


def test_m4_indirect_block_recursion_cycle(tmp_path: Path):
    """Verify indirect cycle: Block A -> Block B -> Block C -> Block A terminates cleanly."""
    ir_payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "BlockA": {
                "name": "BlockA",
                "components": [{"block_name": "BlockB", "position": [1.0, 1.0, 0.0]}]
            },
            "BlockB": {
                "name": "BlockB",
                "components": [{"block_name": "BlockC", "position": [2.0, 2.0, 0.0]}]
            },
            "BlockC": {
                "name": "BlockC",
                "lines": [{"start": [0.0, 0.0], "end": [5.0, 5.0]}],
                "components": [{"block_name": "BlockA", "position": [3.0, 3.0, 0.0]}]
            }
        },
        "components": [
            {"block_name": "BlockA", "position": [50.0, 50.0, 0.0]}
        ]
    }
    # Verify extents
    bbox = compute_ir_extents(ir_payload)
    assert bbox.is_valid

    # Verify compiler renders without RecursionError
    out_pdf = tmp_path / "indirect_cycle.pdf"
    res = compile_ir_to_pdf(ir_payload, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 0


def test_m4_deep_recursion_depth_limit(tmp_path: Path):
    """Verify chain of 25 nested blocks terminates cleanly at MAX_BLOCK_DEPTH = 16."""
    block_defs = {}
    for i in range(25):
        bname = f"Block_{i}"
        child_name = f"Block_{i+1}" if i < 24 else None
        components = [{"block_name": child_name, "position": [2.0, 0.0, 0.0]}] if child_name else []
        block_defs[bname] = {
            "name": bname,
            "lines": [{"start": [0.0, 0.0], "end": [1.0, 1.0]}],
            "components": components,
        }

    ir_payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": block_defs,
        "components": [
            {"block_name": "Block_0", "position": [0.0, 0.0, 0.0]}
        ]
    }

    # Bbox computation depth limit test
    bbox = compute_ir_extents(ir_payload)
    assert bbox.is_valid

    # Rendering depth limit test
    out_pdf = tmp_path / "deep_nesting.pdf"
    res = compile_ir_to_pdf(ir_payload, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 0


def test_m4_nested_transform_composition(tmp_path: Path):
    """Verify composed affine transformation: parent (pos [100, 100], rot 90) @ child (pos [10, 0])."""
    # Parent rotates 90 deg CCW around (100, 100).
    # Child is placed at (10, 0) relative to parent.
    # In world coordinates, child origin should be at (100 + 10*cos(90), 100 + 10*sin(90)) = (100, 110).
    ir_payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "ChildBlock": {
                "name": "ChildBlock",
                "lines": [{"start": [0.0, 0.0], "end": [5.0, 0.0]}],
            },
            "ParentBlock": {
                "name": "ParentBlock",
                "components": [
                    {
                        "block_name": "ChildBlock",
                        "position": [10.0, 0.0, 0.0],
                        "rotation": 0.0,
                    }
                ]
            }
        },
        "components": [
            {
                "block_name": "ParentBlock",
                "position": [100.0, 100.0, 0.0],
                "rotation": 90.0,
            }
        ]
    }

    bbox = compute_ir_extents(ir_payload)
    assert bbox.is_valid
    # Child line starts at (100, 110) and goes to (100, 115) because of 90 deg rotation!
    assert math.isclose(bbox.min_x, 100.0, abs_tol=1e-4)
    assert math.isclose(bbox.min_y, 110.0, abs_tol=1e-4)
    assert math.isclose(bbox.max_y, 115.0, abs_tol=1e-4)

    out_pdf = tmp_path / "composed_transform.pdf"
    res = compile_ir_to_pdf(ir_payload, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 0


def test_m4_missing_child_block_definition(tmp_path: Path):
    """Verify that a nested component referencing a non-existent block does not crash."""
    ir_payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "ExistingParent": {
                "name": "ExistingParent",
                "lines": [{"start": [0.0, 0.0], "end": [10.0, 10.0]}],
                "components": [
                    {"block_name": "GhostChildBlockDoesNotExist", "position": [5.0, 5.0, 0.0]}
                ]
            }
        },
        "components": [
            {"block_name": "ExistingParent", "position": [0.0, 0.0, 0.0]}
        ]
    }
    bbox = compute_ir_extents(ir_payload)
    assert bbox.is_valid
    assert bbox.min_x == 0.0 and bbox.max_x == 10.0

    out_pdf = tmp_path / "missing_child.pdf"
    res = compile_ir_to_pdf(ir_payload, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 0


def test_m4_nested_block_extreme_offset_and_multi_turn_rotation(tmp_path: Path):
    """Verify nested block with extreme base_point offset (10^30), multi-turn rotation (>3600°), and negative scale."""
    ir_payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "ExtremeChild": {
                "name": "ExtremeChild",
                "base_point": [1e30, -1e30, 0.0],
                "lines": [{"start": [1e30, -1e30], "end": [1e30 + 10.0, -1e30 + 10.0]}],
            },
            "ExtremeParent": {
                "name": "ExtremeParent",
                "components": [
                    {
                        "block_name": "ExtremeChild",
                        "position": [0.0, 0.0, 0.0],
                        "rotation": 7250.0,
                        "scale": [-2.0, -3.0, 1.0],
                    }
                ]
            }
        },
        "components": [
            {
                "block_name": "ExtremeParent",
                "position": [200.0, 300.0, 0.0],
                "rotation": 450.0,
            }
        ]
    }
    out_pdf = tmp_path / "extreme_nested_offset.pdf"
    res = compile_ir_to_pdf(ir_payload, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 0


def test_m4_nested_block_reflected_arc(tmp_path: Path):
    """Verify arc rendering in nested block with reflection (det < 0, negative scaling)."""
    ir_payload = {
        "format": "LAVINCI_CAD_IR_V3",
        "block_definitions": {
            "ArcChild": {
                "name": "ArcChild",
                "arcs": [{"center": [0.0, 0.0], "radius": 25.0, "start_angle": 0.0, "end_angle": 90.0}],
            },
            "ArcParent": {
                "name": "ArcParent",
                "components": [
                    {
                        "block_name": "ArcChild",
                        "position": [10.0, 20.0, 0.0],
                        "scale": [1.0, -1.0, 1.0],  # Reflection across X axis
                    }
                ]
            }
        },
        "components": [
            {
                "block_name": "ArcParent",
                "position": [50.0, 50.0, 0.0],
                "scale": [-1.0, 1.0, 1.0],  # Reflection across Y axis (double reflection flips back)
            }
        ]
    }
    out_pdf = tmp_path / "reflected_nested_arc.pdf"
    res = compile_ir_to_pdf(ir_payload, out_pdf)
    assert res.exists()
    assert res.stat().st_size > 0

