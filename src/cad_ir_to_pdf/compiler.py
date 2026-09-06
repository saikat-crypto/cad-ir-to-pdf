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
    for layer in (ir_data.get("layers") or []):
        if not isinstance(layer, dict):
            continue
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
    metadata = ir_data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    c.setTitle(metadata.get("source_file", "La Vinci CAD Drawing"))
    c.setAuthor(metadata.get("author", "La Vinci Engine"))
    c.setCreator("cad-ir-to-pdf (La Vinci CAD Compiler)")

    # 5. Draw Background if configured
    if preset.background_color:
        bg_col = hex_to_pdf_color(preset.background_color, fallback="#FFFFFF")
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
    raw_geom = ir_data.get("geometry_primitives") or {}
    geom_prims = (raw_geom.get("primitives") or {}) if isinstance(raw_geom, dict) else {}
    if isinstance(geom_prims, dict):
        for line in (geom_prims.get("lines") or []):
            if not isinstance(line, dict):
                continue
            if target_space and line.get("space") and line.get("space") != target_space:
                continue
            renderer.draw_line(
                start=line.get("start", []),
                end=line.get("end", []),
                color=line.get("color"),
                layer=line.get("layer"),
            )

        for arc in (geom_prims.get("arcs") or []):
            if not isinstance(arc, dict):
                continue
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

        for circle in (geom_prims.get("circles") or []):
            if not isinstance(circle, dict):
                continue
            if target_space and circle.get("space") and circle.get("space") != target_space:
                continue
            renderer.draw_circle(
                center=circle.get("center", []),
                radius=circle.get("radius", 0.0),
                color=circle.get("color"),
                layer=circle.get("layer"),
            )

        for pline in (geom_prims.get("polylines") or []):
            if not isinstance(pline, dict):
                continue
            if target_space and pline.get("space") and pline.get("space") != target_space:
                continue
            renderer.draw_polyline(
                points=pline.get("points", []),
                is_closed=bool(pline.get("is_closed", False)),
                color=pline.get("color"),
                layer=pline.get("layer"),
            )

    # 8. Render Block Component Instances (Filtered by space)
    if preset.draw_components:
        raw_block_defs = ir_data.get("block_definitions") or {}
        block_defs = raw_block_defs if isinstance(raw_block_defs, dict) else {}
        components = ir_data.get("components") or []

        if isinstance(components, (list, tuple)):
            for comp in components:
                if not isinstance(comp, dict):
                    continue
                if target_space and comp.get("space") and comp.get("space") != target_space:
                    continue

                bname = comp.get("block_name") or comp.get("resolved_name")
                bdata = block_defs.get(bname)
                if not isinstance(bdata, dict):
                    continue

                pos = comp.get("position") or [0.0, 0.0, 0.0]
                rot = comp.get("rotation", 0.0)
                scale = comp.get("scale") or [1.0, 1.0, 1.0]
                base_pt = bdata.get("base_point") or [0.0, 0.0, 0.0]
                comp_layer = comp.get("layer")

                sx = scale[0] if (isinstance(scale, (list, tuple)) and len(scale) > 0 and isinstance(scale[0], (int, float))) else 1.0
                sy = scale[1] if (isinstance(scale, (list, tuple)) and len(scale) > 1 and isinstance(scale[1], (int, float))) else 1.0
                px = pos[0] if (isinstance(pos, (list, tuple)) and len(pos) > 0 and isinstance(pos[0], (int, float))) else 0.0
                py = pos[1] if (isinstance(pos, (list, tuple)) and len(pos) > 1 and isinstance(pos[1], (int, float))) else 0.0
                bx = base_pt[0] if (isinstance(base_pt, (list, tuple)) and len(base_pt) > 0 and isinstance(base_pt[0], (int, float))) else 0.0
                by = base_pt[1] if (isinstance(base_pt, (list, tuple)) and len(base_pt) > 1 and isinstance(base_pt[1], (int, float))) else 0.0
                rot_f = rot if (isinstance(rot, (int, float))) else 0.0

                mat = AffineMatrix2D.from_cad_insert(
                    pos_x=px,
                    pos_y=py,
                    rotation_deg=rot_f,
                    scale_x=sx,
                    scale_y=sy,
                    base_x=bx,
                    base_y=by,
                )

                # Scale factor for radii under non-uniform scaling (average scale)
                effective_scale = (abs(sx) + abs(sy)) / 2.0

                for bline in (bdata.get("lines") or []):
                    if not isinstance(bline, dict):
                        continue
                    renderer.draw_line(
                        start=bline.get("start", []),
                        end=bline.get("end", []),
                        color=bline.get("color"),
                        layer=bline.get("layer") or comp_layer,
                        transform=mat,
                    )

                for barc in (bdata.get("arcs") or []):
                    if not isinstance(barc, dict):
                        continue
                    orig_r = barc.get("radius", 0.0)
                    r = orig_r * effective_scale if (isinstance(orig_r, (int, float))) else 0.0
                    ac = barc.get("center") or [0.0, 0.0]
                    acx = ac[0] if (isinstance(ac, (list, tuple)) and len(ac) > 0 and isinstance(ac[0], (int, float))) else 0.0
                    acy = ac[1] if (isinstance(ac, (list, tuple)) and len(ac) > 1 and isinstance(ac[1], (int, float))) else 0.0
                    tx_c = mat.transform_point(acx, acy)
                    sa = barc.get("start_angle", 0.0)
                    ea = barc.get("end_angle", 360.0)
                    sa_f = (sa if isinstance(sa, (int, float)) else 0.0) + rot_f
                    ea_f = (ea if isinstance(ea, (int, float)) else 360.0) + rot_f
                    renderer.draw_arc(
                        center=[tx_c[0], tx_c[1]],
                        radius=r,
                        start_angle_deg=sa_f,
                        end_angle_deg=ea_f,
                        color=barc.get("color"),
                        layer=barc.get("layer") or comp_layer,
                    )

                for bcircle in (bdata.get("circles") or []):
                    if not isinstance(bcircle, dict):
                        continue
                    orig_r = bcircle.get("radius", 0.0)
                    r = orig_r * effective_scale if (isinstance(orig_r, (int, float))) else 0.0
                    cc = bcircle.get("center") or [0.0, 0.0]
                    ccx = cc[0] if (isinstance(cc, (list, tuple)) and len(cc) > 0 and isinstance(cc[0], (int, float))) else 0.0
                    ccy = cc[1] if (isinstance(cc, (list, tuple)) and len(cc) > 1 and isinstance(cc[1], (int, float))) else 0.0
                    tx_c = mat.transform_point(ccx, ccy)
                    renderer.draw_circle(
                        center=[tx_c[0], tx_c[1]],
                        radius=r,
                        color=bcircle.get("color"),
                        layer=bcircle.get("layer") or comp_layer,
                    )

                for bpline in (bdata.get("polylines") or []):
                    if not isinstance(bpline, dict):
                        continue
                    renderer.draw_polyline(
                        points=bpline.get("points", []),
                        is_closed=bool(bpline.get("is_closed", False)),
                        color=bpline.get("color"),
                        layer=bpline.get("layer") or comp_layer,
                        transform=mat,
                    )

    # 9. Render Dimensions & Anonymous Dimension Blocks (*D...)
    if preset.draw_dimensions:
        raw_block_defs = ir_data.get("block_definitions") or {}
        block_defs = raw_block_defs if isinstance(raw_block_defs, dict) else {}
        # A. Render anonymous dimension blocks (*D...)
        for bname, bdata in block_defs.items():
            if not isinstance(bname, str) or not bname.startswith("*D") or not isinstance(bdata, dict):
                continue
            for bline in (bdata.get("lines") or []):
                if not isinstance(bline, dict):
                    continue
                renderer.draw_line(
                    start=bline.get("start", []),
                    end=bline.get("end", []),
                    color=bline.get("color"),
                    layer=bline.get("layer", "dimension"),
                )
            for barc in (bdata.get("arcs") or []):
                if not isinstance(barc, dict):
                    continue
                renderer.draw_arc(
                    center=barc.get("center", []),
                    radius=barc.get("radius", 0.0),
                    start_angle_deg=barc.get("start_angle", 0.0),
                    end_angle_deg=barc.get("end_angle", 360.0),
                    color=barc.get("color"),
                    layer=barc.get("layer", "dimension"),
                )
            for bcircle in (bdata.get("circles") or []):
                if not isinstance(bcircle, dict):
                    continue
                renderer.draw_circle(
                    center=bcircle.get("center", []),
                    radius=bcircle.get("radius", 0.0),
                    color=bcircle.get("color"),
                    layer=bcircle.get("layer", "dimension"),
                )
            for bpline in (bdata.get("polylines") or []):
                if not isinstance(bpline, dict):
                    continue
                renderer.draw_polyline(
                    points=bpline.get("points", []),
                    is_closed=bool(bpline.get("is_closed", False)),
                    color=bpline.get("color"),
                    layer=bpline.get("layer", "dimension"),
                )

        # B. Render dimension measurement text labels
        dims = ir_data.get("dimensions") or []
        if isinstance(dims, (list, tuple)):
            for dim in dims:
                if not isinstance(dim, dict):
                    continue
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
        annots = ir_data.get("annotations") or []
        if isinstance(annots, (list, tuple)):
            for annot in annots:
                if not isinstance(annot, dict):
                    continue
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
