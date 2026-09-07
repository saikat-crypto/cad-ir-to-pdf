"""
compiler.py — Core orchestrator compiling LAVINCI_CAD_IR_V3 to high-fidelity vector PDF.
"""

from __future__ import annotations
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from reportlab.pdfgen import canvas
from reportlab.lib import colors

from .config import DEFAULT_PRESET, PRESETS, PdfPreset
from .geometry import (
    AffineMatrix2D,
    BoundingBox,
    calculate_viewport_mapping,
    compute_ir_extents,
)
from .renderer import (
    PdfVectorRenderer,
    coerce_metadata_str,
    hex_to_pdf_color,
    sanitize_metadata_string,
)
from .telemetry import ActionTaken, CompilationReport, HardeningCategory, HardeningWarning


def compile_ir_to_pdf(
    ir_source: Union[str, Path, Dict[str, Any]],
    output_path: Union[str, Path],
    preset: Optional[PdfPreset] = None,
    report: Optional[CompilationReport] = None,
    return_report: bool = False,
) -> Union[Path, Tuple[Path, CompilationReport]]:
    """
    Compiles a LAVINCI_CAD_IR_V3 JSON file, stream, or dict into a vector PDF drawing.

    :param ir_source: Filepath or dictionary containing the IR v3 payload.
    :param output_path: Destination file path for the .pdf file.
    :param preset: Custom or built-in PdfPreset (defaults to `presentation-fit-vector`).
    :param report: Optional pre-allocated CompilationReport to populate.
    :param return_report: If True, returns (output_path, CompilationReport). If False, returns output_path.
    :return: Resolved Path of the created PDF, or (Path, CompilationReport) if return_report=True.
    """
    t0 = time.perf_counter()
    out_file = Path(output_path)
    if report is None:
        report = CompilationReport(pdf_path=out_file)
    else:
        report.pdf_path = out_file
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
    raw_layers = ir_data.get("layers")
    if isinstance(raw_layers, (list, tuple)):
        for layer in raw_layers:
            if not isinstance(layer, dict):
                continue
            name = layer.get("name")
            hex_c = layer.get("hex_color")
            if isinstance(name, str) and isinstance(hex_c, str):
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

    # Populate telemetry report geometry & viewport metrics
    report.cad_bbox_extents = {
        "min_x": bbox.min_x,
        "min_y": bbox.min_y,
        "max_x": bbox.max_x,
        "max_y": bbox.max_y,
        "width": bbox.width,
        "height": bbox.height,
    }
    report.viewport_scale = vp.scale
    report.page_dimensions_pt = {
        "width": page_w,
        "height": page_h,
    }

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # 4. Initialize ReportLab Canvas (Feature 11)
    c = canvas.Canvas(str(out_file), pagesize=(page_w, page_h))

    # 5. Draw Background if configured
    if preset.background_color:
        bg_col = hex_to_pdf_color(preset.background_color, fallback="#FFFFFF", is_background=True)
        c.setFillColor(bg_col)
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # 6. Initialize Renderer
    renderer = PdfVectorRenderer(
        pdf_canvas=c,
        viewport=vp,
        preset=preset,
        layer_color_map=layer_colors,
        report=report,
    )

    # Set document metadata safely via renderer helper (Feature 11)
    metadata = ir_data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    renderer.set_document_metadata(
        title=metadata.get("source_file"),
        author=metadata.get("author"),
        subject=metadata.get("subject"),
        creator=metadata.get("creator") or "cad-ir-to-pdf (La Vinci CAD Compiler)",
    )

    # 7. Render Top-Level Geometry Primitives (filtered by space)
    raw_geom = ir_data.get("geometry_primitives") or {}
    geom_prims = (raw_geom.get("primitives") or {}) if isinstance(raw_geom, dict) else {}
    if isinstance(geom_prims, dict):
        raw_lines = geom_prims.get("lines")
        for line in (raw_lines if isinstance(raw_lines, (list, tuple)) else []):
            if not isinstance(line, dict):
                continue
            if target_space and line.get("space") and line.get("space") != target_space:
                continue
            report.total_entities_read += 1
            renderer.draw_line(
                start=line.get("start", []),
                end=line.get("end", []),
                color=line.get("color"),
                layer=line.get("layer"),
                line_width=line.get("line_width"),
            )

        raw_arcs = geom_prims.get("arcs")
        for arc in (raw_arcs if isinstance(raw_arcs, (list, tuple)) else []):
            if not isinstance(arc, dict):
                continue
            if target_space and arc.get("space") and arc.get("space") != target_space:
                continue
            report.total_entities_read += 1
            renderer.draw_arc(
                center=arc.get("center", []),
                radius=arc.get("radius", 0.0),
                start_angle_deg=arc.get("start_angle", 0.0),
                end_angle_deg=arc.get("end_angle", 360.0),
                color=arc.get("color"),
                layer=arc.get("layer"),
                line_width=arc.get("line_width"),
            )

        raw_circles = geom_prims.get("circles")
        for circle in (raw_circles if isinstance(raw_circles, (list, tuple)) else []):
            if not isinstance(circle, dict):
                continue
            if target_space and circle.get("space") and circle.get("space") != target_space:
                continue
            report.total_entities_read += 1
            renderer.draw_circle(
                center=circle.get("center", []),
                radius=circle.get("radius", 0.0),
                color=circle.get("color"),
                layer=circle.get("layer"),
                line_width=circle.get("line_width"),
            )

        raw_plines = geom_prims.get("polylines")
        for pline in (raw_plines if isinstance(raw_plines, (list, tuple)) else []):
            if not isinstance(pline, dict):
                continue
            if target_space and pline.get("space") and pline.get("space") != target_space:
                continue
            report.total_entities_read += 1
            renderer.draw_polyline(
                points=pline.get("points", []),
                is_closed=bool(pline.get("is_closed", False)),
                color=pline.get("color"),
                layer=pline.get("layer"),
                line_width=pline.get("line_width"),
            )

    # 8. Render Block Component Instances (Filtered by space, with recursive nested blocks)
    if preset.draw_components:
        raw_block_defs = ir_data.get("block_definitions") or {}
        block_defs = raw_block_defs if isinstance(raw_block_defs, dict) else {}
        components = ir_data.get("components") or []

        MAX_BLOCK_DEPTH = 16

        def _render_block_recursive(
            bname: str,
            current_mat: AffineMatrix2D,
            parent_layer: Optional[str],
            depth: int,
            visited_path: set,
        ) -> None:
            if depth > MAX_BLOCK_DEPTH:
                report.add_warning(
                    category=HardeningCategory.BLOCK_ABUSE,
                    action=ActionTaken.DROPPED,
                    entity_type="component",
                    reason=f"Block nesting depth exceeded limit ({MAX_BLOCK_DEPTH}) for block '{bname}'",
                    layer=parent_layer,
                    original_value=bname,
                )
                return
            if bname in visited_path:
                report.add_warning(
                    category=HardeningCategory.BLOCK_ABUSE,
                    action=ActionTaken.DROPPED,
                    entity_type="component",
                    reason=f"Circular block reference detected for block '{bname}'",
                    layer=parent_layer,
                    original_value=bname,
                )
                return
            bdata = block_defs.get(bname)
            if not isinstance(bdata, dict):
                report.add_warning(
                    category=HardeningCategory.BLOCK_ABUSE,
                    action=ActionTaken.DROPPED,
                    entity_type="component",
                    reason=f"Block definition '{bname}' not found or invalid",
                    layer=parent_layer,
                    original_value=bname,
                )
                return

            visited_path.add(bname)

            # Radii scaling under affine matrix: average axis scale
            sx_len = math.hypot(current_mat.a, current_mat.b)
            sy_len = math.hypot(current_mat.c, current_mat.d)
            effective_scale = (sx_len + sy_len) / 2.0

            # Render lines
            raw_blines = bdata.get("lines")
            for bline in (raw_blines if isinstance(raw_blines, (list, tuple)) else []):
                if not isinstance(bline, dict):
                    continue
                renderer.draw_line(
                    start=bline.get("start", []),
                    end=bline.get("end", []),
                    color=bline.get("color"),
                    layer=bline.get("layer") or parent_layer,
                    line_width=bline.get("line_width"),
                    transform=current_mat,
                )

            # Render arcs
            raw_barcs = bdata.get("arcs")
            for barc in (raw_barcs if isinstance(raw_barcs, (list, tuple)) else []):
                if not isinstance(barc, dict):
                    continue
                orig_r = barc.get("radius", 0.0)
                r = orig_r * effective_scale if isinstance(orig_r, (int, float)) else 0.0
                ac = barc.get("center") or [0.0, 0.0]
                acx = ac[0] if (isinstance(ac, (list, tuple)) and len(ac) > 0 and isinstance(ac[0], (int, float))) else 0.0
                acy = ac[1] if (isinstance(ac, (list, tuple)) and len(ac) > 1 and isinstance(ac[1], (int, float))) else 0.0
                tx_c = current_mat.transform_point(acx, acy)
                sa = barc.get("start_angle", 0.0)
                ea = barc.get("end_angle", 360.0)
                sa_in = sa if isinstance(sa, (int, float)) else 0.0
                ea_in = ea if isinstance(ea, (int, float)) else 360.0
                sa_f, ea_f = current_mat.transform_arc_angles(sa_in, ea_in)
                renderer.draw_arc(
                    center=[tx_c[0], tx_c[1]],
                    radius=r,
                    start_angle_deg=sa_f,
                    end_angle_deg=ea_f,
                    color=barc.get("color"),
                    layer=barc.get("layer") or parent_layer,
                    line_width=barc.get("line_width"),
                )

            # Render circles
            raw_bcircles = bdata.get("circles")
            for bcircle in (raw_bcircles if isinstance(raw_bcircles, (list, tuple)) else []):
                if not isinstance(bcircle, dict):
                    continue
                orig_r = bcircle.get("radius", 0.0)
                r = orig_r * effective_scale if isinstance(orig_r, (int, float)) else 0.0
                cc = bcircle.get("center") or [0.0, 0.0]
                ccx = cc[0] if (isinstance(cc, (list, tuple)) and len(cc) > 0 and isinstance(cc[0], (int, float))) else 0.0
                ccy = cc[1] if (isinstance(cc, (list, tuple)) and len(cc) > 1 and isinstance(cc[1], (int, float))) else 0.0
                tx_c = current_mat.transform_point(ccx, ccy)
                renderer.draw_circle(
                    center=[tx_c[0], tx_c[1]],
                    radius=r,
                    color=bcircle.get("color"),
                    layer=bcircle.get("layer") or parent_layer,
                    line_width=bcircle.get("line_width"),
                )

            # Render polylines
            raw_bplines = bdata.get("polylines")
            for bpline in (raw_bplines if isinstance(raw_bplines, (list, tuple)) else []):
                if not isinstance(bpline, dict):
                    continue
                renderer.draw_polyline(
                    points=bpline.get("points", []),
                    is_closed=bool(bpline.get("is_closed", False)),
                    color=bpline.get("color"),
                    layer=bpline.get("layer") or parent_layer,
                    line_width=bpline.get("line_width"),
                    transform=current_mat,
                )

            # Render nested block components
            raw_nested = bdata.get("components")
            nested_comps = raw_nested if isinstance(raw_nested, (list, tuple)) else []
            for n_comp in nested_comps:
                if not isinstance(n_comp, dict):
                    continue
                child_bname = n_comp.get("block_name") or n_comp.get("resolved_name")
                if not child_bname:
                    continue
                child_bdef = block_defs.get(child_bname) if isinstance(block_defs.get(child_bname), dict) else {}
                child_base = child_bdef.get("base_point") or [0.0, 0.0, 0.0]
                n_pos = n_comp.get("position") or [0.0, 0.0, 0.0]
                n_rot = n_comp.get("rotation", 0.0)
                n_scale = n_comp.get("scale") or [1.0, 1.0, 1.0]

                n_sx = n_scale[0] if (isinstance(n_scale, (list, tuple)) and len(n_scale) > 0 and isinstance(n_scale[0], (int, float))) else 1.0
                n_sy = n_scale[1] if (isinstance(n_scale, (list, tuple)) and len(n_scale) > 1 and isinstance(n_scale[1], (int, float))) else 1.0
                n_px = n_pos[0] if (isinstance(n_pos, (list, tuple)) and len(n_pos) > 0 and isinstance(n_pos[0], (int, float))) else 0.0
                n_py = n_pos[1] if (isinstance(n_pos, (list, tuple)) and len(n_pos) > 1 and isinstance(n_pos[1], (int, float))) else 0.0
                n_bx = child_base[0] if (isinstance(child_base, (list, tuple)) and len(child_base) > 0 and isinstance(child_base[0], (int, float))) else 0.0
                n_by = child_base[1] if (isinstance(child_base, (list, tuple)) and len(child_base) > 1 and isinstance(child_base[1], (int, float))) else 0.0
                n_rot_f = n_rot if isinstance(n_rot, (int, float)) else 0.0

                child_local_mat = AffineMatrix2D.from_cad_insert(
                    pos_x=n_px,
                    pos_y=n_py,
                    rotation_deg=n_rot_f,
                    scale_x=n_sx,
                    scale_y=n_sy,
                    base_x=n_bx,
                    base_y=n_by,
                )
                child_composed_mat = current_mat @ child_local_mat
                child_layer = n_comp.get("layer") or parent_layer
                _render_block_recursive(child_bname, child_composed_mat, child_layer, depth + 1, visited_path)

            visited_path.remove(bname)

        if isinstance(components, (list, tuple)):
            for comp in components:
                if not isinstance(comp, dict):
                    continue
                if target_space and comp.get("space") and comp.get("space") != target_space:
                    continue
                report.total_entities_read += 1

                bname = comp.get("block_name") or comp.get("resolved_name")
                if not bname:
                    continue
                bdata = block_defs.get(bname)
                if not isinstance(bdata, dict):
                    report.add_warning(
                        category=HardeningCategory.BLOCK_ABUSE,
                        action=ActionTaken.DROPPED,
                        entity_type="component",
                        reason=f"Block definition '{bname}' not found or invalid",
                        layer=comp.get("layer"),
                        original_value=bname,
                    )
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
                rot_f = rot if isinstance(rot, (int, float)) else 0.0

                mat = AffineMatrix2D.from_cad_insert(
                    pos_x=px,
                    pos_y=py,
                    rotation_deg=rot_f,
                    scale_x=sx,
                    scale_y=sy,
                    base_x=bx,
                    base_y=by,
                )

                _render_block_recursive(bname, mat, comp_layer, depth=0, visited_path=set())

    # 9. Render Dimensions & Anonymous Dimension Blocks (*D...)
    if preset.draw_dimensions:
        raw_block_defs = ir_data.get("block_definitions") or {}
        block_defs = raw_block_defs if isinstance(raw_block_defs, dict) else {}
        # A. Render anonymous dimension blocks (*D...)
        for bname, bdata in block_defs.items():
            if not isinstance(bname, str) or not bname.startswith("*D") or not isinstance(bdata, dict):
                continue
            raw_dlines = bdata.get("lines")
            for bline in (raw_dlines if isinstance(raw_dlines, (list, tuple)) else []):
                if not isinstance(bline, dict):
                    continue
                report.total_entities_read += 1
                renderer.draw_line(
                    start=bline.get("start", []),
                    end=bline.get("end", []),
                    color=bline.get("color"),
                    layer=bline.get("layer", "dimension"),
                    line_width=bline.get("line_width"),
                )
            raw_darcs = bdata.get("arcs")
            for barc in (raw_darcs if isinstance(raw_darcs, (list, tuple)) else []):
                if not isinstance(barc, dict):
                    continue
                report.total_entities_read += 1
                renderer.draw_arc(
                    center=barc.get("center", []),
                    radius=barc.get("radius", 0.0),
                    start_angle_deg=barc.get("start_angle", 0.0),
                    end_angle_deg=barc.get("end_angle", 360.0),
                    color=barc.get("color"),
                    layer=barc.get("layer", "dimension"),
                    line_width=barc.get("line_width"),
                )
            raw_dcircles = bdata.get("circles")
            for bcircle in (raw_dcircles if isinstance(raw_dcircles, (list, tuple)) else []):
                if not isinstance(bcircle, dict):
                    continue
                report.total_entities_read += 1
                renderer.draw_circle(
                    center=bcircle.get("center", []),
                    radius=bcircle.get("radius", 0.0),
                    color=bcircle.get("color"),
                    layer=bcircle.get("layer", "dimension"),
                    line_width=bcircle.get("line_width"),
                )
            raw_dplines = bdata.get("polylines")
            for bpline in (raw_dplines if isinstance(raw_dplines, (list, tuple)) else []):
                if not isinstance(bpline, dict):
                    continue
                report.total_entities_read += 1
                renderer.draw_polyline(
                    points=bpline.get("points", []),
                    is_closed=bool(bpline.get("is_closed", False)),
                    color=bpline.get("color"),
                    layer=bpline.get("layer", "dimension"),
                    line_width=bpline.get("line_width"),
                )

        # B. Render dimension measurement text labels
        dims = ir_data.get("dimensions") or []
        if isinstance(dims, (list, tuple)):
            for dim in dims:
                if not isinstance(dim, dict):
                    continue
                if target_space and dim.get("space") and dim.get("space") != target_space:
                    continue
                report.total_entities_read += 1
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
                report.total_entities_read += 1
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

    report.conversion_time_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    if return_report:
        return out_file, report
    return out_file
