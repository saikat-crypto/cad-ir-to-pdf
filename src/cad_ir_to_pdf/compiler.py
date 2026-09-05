"""
compiler.py — Core orchestrator compiling LAVINCI_CAD_IR_V3 to high-fidelity vector PDF.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from reportlab.pdfgen import canvas
from reportlab.lib import colors

from .config import DEFAULT_PRESET, PRESETS, PdfPreset
from .geometry import (
    AffineMatrix2D,
    BoundingBox,
    calculate_viewport_mapping,
    compute_ir_extents,
)
from .renderer import PdfVectorRenderer, hex_to_pdf_color


def compile_ir_to_pdf(
    ir_source: Union[str, Path, Dict[str, Any]],
    output_path: Union[str, Path],
    preset: Optional[PdfPreset] = None,
) -> Path:
    """
    Compiles a LAVINCI_CAD_IR_V3 JSON file, stream, or dict into a vector PDF drawing.

    :param ir_source: Filepath or dictionary containing the IR v3 payload.
    :param output_path: Destination file path for the .pdf file.
    :param preset: Custom or built-in PdfPreset (defaults to `presentation-fit-vector`).
    :return: Resolved Path of the created PDF.
    """
    if preset is None:
        preset = DEFAULT_PRESET

    # 1. Load IR Payload
    if isinstance(ir_source, (str, Path)):
        p = Path(ir_source)
        if not p.exists():
            raise FileNotFoundError(f"CAD IR source file not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            ir_data = json.load(f)
    elif isinstance(ir_source, dict):
        ir_data = ir_source
    else:
        raise TypeError(f"Unsupported IR source type: {type(ir_source)}")

    # 2. Extract Layer Color Map
    layer_colors: Dict[str, str] = {}
    for layer in ir_data.get("layers", []):
        name = layer.get("name")
        hex_c = layer.get("hex_color")
        if name and hex_c:
            layer_colors[name] = hex_c

    # 3. Calculate Model Extents & Viewport Transform
    target_space = preset.target_space if preset.target_space != "all" else None
    bbox = compute_ir_extents(
        ir_data,
        target_space=target_space,
        prune_outliers=preset.prune_outliers,
        custom_bbox=preset.custom_bbox,
    )
    page_w, page_h = preset.get_page_dimensions_pt()
    vp = calculate_viewport_mapping(
        cad_bbox=bbox,
        page_width_pt=page_w,
        page_height_pt=page_h,
        margin_pt=preset.margin_pt,
        scale_mode=preset.scale_mode,
        fixed_scale=preset.fixed_scale,
    )

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # 4. Initialize ReportLab Canvas
    c = canvas.Canvas(str(out_file), pagesize=(page_w, page_h))
    c.setTitle(ir_data.get("metadata", {}).get("source_file", "La Vinci CAD Drawing"))
    c.setAuthor(ir_data.get("metadata", {}).get("author", "La Vinci Engine"))
    c.setCreator("cad-ir-to-pdf (La Vinci CAD Compiler)")

    # 5. Draw Background if configured
    if preset.background_color:
        bg_col = colors.HexColor(preset.background_color)
        c.setFillColor(bg_col)
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # 6. Initialize Renderer
    renderer = PdfVectorRenderer(
        pdf_canvas=c,
        viewport=vp,
        preset=preset,
        layer_color_map=layer_colors,
    )

    # 7. Render Top-Level Geometry Primitives (filtered by space)
    prims = ir_data.get("geometry_primitives", {}).get("primitives", {})
    for line in prims.get("lines", []):
        if target_space and line.get("space") and line.get("space") != target_space:
            continue
        renderer.draw_line(
            start=line.get("start", []),
            end=line.get("end", []),
            color=line.get("color"),
            layer=line.get("layer"),
        )

    for arc in prims.get("arcs", []):
        if target_space and arc.get("space") and arc.get("space") != target_space:
            continue
        renderer.draw_arc(
            center=arc.get("center", []),
            radius=arc.get("radius", 0.0),
            start_angle_deg=arc.get("start_angle", 0.0),
            end_angle_deg=arc.get("end_angle", 360.0),
            color=arc.get("color"),
            layer=arc.get("layer"),
        )

    for circle in prims.get("circles", []):
        if target_space and circle.get("space") and circle.get("space") != target_space:
            continue
        renderer.draw_circle(
            center=circle.get("center", []),
            radius=circle.get("radius", 0.0),
            color=circle.get("color"),
            layer=circle.get("layer"),
        )

    for pline in prims.get("polylines", []):
        if target_space and pline.get("space") and pline.get("space") != target_space:
            continue
        renderer.draw_polyline(
            points=pline.get("points", []),
            is_closed=pline.get("is_closed", False),
            color=pline.get("color"),
            layer=pline.get("layer"),
        )

    # 8. Render Block Component Instances (Filtered by space)
    if preset.draw_components:
        block_defs = ir_data.get("block_definitions", {})
        components = ir_data.get("components", [])

        for comp in components:
            if target_space and comp.get("space") and comp.get("space") != target_space:
                continue

            bname = comp.get("block_name") or comp.get("resolved_name")
            bdata = block_defs.get(bname)
            if not bdata:
                continue

            pos = comp.get("position", [0.0, 0.0, 0.0])
            rot = comp.get("rotation", 0.0)
            scale = comp.get("scale", [1.0, 1.0, 1.0])
            base_pt = bdata.get("base_point", [0.0, 0.0, 0.0])
            comp_layer = comp.get("layer")

            mat = AffineMatrix2D.from_cad_insert(
                pos_x=pos[0],
                pos_y=pos[1],
                rotation_deg=rot,
                scale_x=scale[0] if len(scale) > 0 else 1.0,
                scale_y=scale[1] if len(scale) > 1 else 1.0,
                base_x=base_pt[0],
                base_y=base_pt[1],
            )

            for bline in bdata.get("lines", []):
                renderer.draw_line(
                    start=bline.get("start", []),
                    end=bline.get("end", []),
                    color=bline.get("color"),
                    layer=bline.get("layer") or comp_layer,
                    transform=mat,
                )

            for barc in bdata.get("arcs", []):
                r = barc.get("radius", 0.0) * abs(scale[0] if len(scale) > 0 else 1.0)
                ac = barc.get("center", [0.0, 0.0])
                tx_c = mat.transform_point(ac[0], ac[1])
                renderer.draw_arc(
                    center=[tx_c[0], tx_c[1]],
                    radius=r,
                    start_angle_deg=barc.get("start_angle", 0.0) + rot,
                    end_angle_deg=barc.get("end_angle", 360.0) + rot,
                    color=barc.get("color"),
                    layer=barc.get("layer") or comp_layer,
                )

            for bcircle in bdata.get("circles", []):
                r = bcircle.get("radius", 0.0) * abs(scale[0] if len(scale) > 0 else 1.0)
                cc = bcircle.get("center", [0.0, 0.0])
                tx_c = mat.transform_point(cc[0], cc[1])
                renderer.draw_circle(
                    center=[tx_c[0], tx_c[1]],
                    radius=r,
                    color=bcircle.get("color"),
                    layer=bcircle.get("layer") or comp_layer,
                )

            for bpline in bdata.get("polylines", []):
                renderer.draw_polyline(
                    points=bpline.get("points", []),
                    is_closed=bpline.get("is_closed", False),
                    color=bpline.get("color"),
                    layer=bpline.get("layer") or comp_layer,
                    transform=mat,
                )

    # 9. Render Dimensions & Anonymous Dimension Blocks (*D...)
    if preset.draw_dimensions:
        block_defs = ir_data.get("block_definitions", {})
        # A. Render anonymous dimension blocks (*D...)
        for bname, bdata in block_defs.items():
            if not bname.startswith("*D"):
                continue
            for bline in bdata.get("lines", []):
                renderer.draw_line(
                    start=bline.get("start", []),
                    end=bline.get("end", []),
                    color=bline.get("color"),
                    layer=bline.get("layer", "dimension"),
                )
            for barc in bdata.get("arcs", []):
                renderer.draw_arc(
                    center=barc.get("center", []),
                    radius=barc.get("radius", 0.0),
                    start_angle_deg=barc.get("start_angle", 0.0),
                    end_angle_deg=barc.get("end_angle", 360.0),
                    color=barc.get("color"),
                    layer=barc.get("layer", "dimension"),
                )
            for bcircle in bdata.get("circles", []):
                renderer.draw_circle(
                    center=bcircle.get("center", []),
                    radius=bcircle.get("radius", 0.0),
                    color=bcircle.get("color"),
                    layer=bcircle.get("layer", "dimension"),
                )
            for bpline in bdata.get("polylines", []):
                renderer.draw_polyline(
                    points=bpline.get("points", []),
                    is_closed=bpline.get("is_closed", False),
                    color=bpline.get("color"),
                    layer=bpline.get("layer", "dimension"),
                )

        # B. Render dimension measurement text labels
        for dim in ir_data.get("dimensions", []):
            if target_space and dim.get("space") and dim.get("space") != target_space:
                continue
            meas = dim.get("measurement")
            dp = dim.get("defpoint")
            dp2 = dim.get("defpoint2")
            if meas is not None and dp and dp2:
                renderer.draw_dimension_text(
                    measurement=meas,
                    defpoint=dp,
                    defpoint2=dp2,
                    override_text=dim.get("text"),
                    layer=dim.get("layer", "dimension"),
                )

    # 10. Render Annotations (Filtered by space)
    if preset.draw_annotations:
        for annot in ir_data.get("annotations", []):
            if target_space and annot.get("space") and annot.get("space") != target_space:
                continue
            txt = annot.get("clean_text") or annot.get("raw_text") or ""
            pos = annot.get("position", [0.0, 0.0])
            h = annot.get("height", 250.0)
            renderer.draw_annotation(
                text=txt,
                position=pos,
                height=h,
                color=annot.get("color"),
                layer=annot.get("layer"),
            )

    # 11. Save and Finish PDF
    c.showPage()
    c.save()
    return out_file
