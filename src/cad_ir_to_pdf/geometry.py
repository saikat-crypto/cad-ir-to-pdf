"""
geometry.py — Bounding box calculation, affine transformation, and coordinate projection.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class BoundingBox:
    """Represents an axis-aligned 2D bounding box."""
    min_x: float = float("inf")
    min_y: float = float("inf")
    max_x: float = float("-inf")
    max_y: float = float("-inf")

    @property
    def is_valid(self) -> bool:
        return (
            self.min_x != float("inf")
            and self.min_y != float("inf")
            and self.max_x != float("-inf")
            and self.max_y != float("-inf")
            and self.max_x >= self.min_x
            and self.max_y >= self.min_y
        )

    @property
    def width(self) -> float:
        return self.max_x - self.min_x if self.is_valid else 0.0

    @property
    def height(self) -> float:
        return self.max_y - self.min_y if self.is_valid else 0.0

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    def expand(self, x: float, y: float) -> None:
        """Expand bbox to include the given (x, y) point."""
        if math.isfinite(x) and math.isfinite(y):
            if x < self.min_x:
                self.min_x = x
            if x > self.max_x:
                self.max_x = x
            if y < self.min_y:
                self.min_y = y
            if y > self.max_y:
                self.max_y = y

    def expand_bbox(self, other: BoundingBox) -> None:
        """Expand this bbox to include another bbox."""
        if other.is_valid:
            self.expand(other.min_x, other.min_y)
            self.expand(other.max_x, other.max_y)


@dataclass
class AffineMatrix2D:
    """
    2D Affine transformation matrix:
    [ x' ]   [ a  c  tx ] [ x ]
    [ y' ] = [ b  d  ty ] [ y ]
    [ 1  ]   [ 0  0   1 ] [ 1 ]
    """
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    tx: float = 0.0
    ty: float = 0.0

    def transform_point(self, x: float, y: float) -> Tuple[float, float]:
        x_prime = self.a * x + self.c * y + self.tx
        y_prime = self.b * x + self.d * y + self.ty
        return (x_prime, y_prime)

    @classmethod
    def from_cad_insert(
        cls,
        pos_x: float,
        pos_y: float,
        rotation_deg: float = 0.0,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        base_x: float = 0.0,
        base_y: float = 0.0,
    ) -> AffineMatrix2D:
        rad = math.radians(rotation_deg)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)

        a = scale_x * cos_r
        b = scale_x * sin_r
        c = -scale_y * sin_r
        d = scale_y * cos_r

        tx = pos_x - (a * base_x + c * base_y)
        ty = pos_y - (b * base_x + d * base_y)

        return cls(a=a, b=b, c=c, d=d, tx=tx, ty=ty)


@dataclass
class ViewportMapping:
    """
    Maps CAD world coordinates to PDF PostScript points:
    pdf_x = (cad_x - cad_bbox.center_x) * scale + pdf_center_x
    pdf_y = (cad_y - cad_bbox.center_y) * scale + pdf_center_y
    """
    scale: float
    cad_center_x: float
    cad_center_y: float
    pdf_center_x: float
    pdf_center_y: float

    def to_pdf(self, x: float, y: float) -> Tuple[float, float]:
        px = (x - self.cad_center_x) * self.scale + self.pdf_center_x
        py = (y - self.cad_center_y) * self.scale + self.pdf_center_y
        return (px, py)

    def to_pdf_length(self, length: float) -> float:
        return length * self.scale


def compute_primitive_bbox(primitives: Dict[str, Any], target_space: Optional[str] = None) -> BoundingBox:
    """Computes the 2D bounding box of a primitive collection, filtering by target space if specified."""
    bbox = BoundingBox()

    for line in primitives.get("lines", []):
        if target_space and line.get("space") and line.get("space") != target_space:
            continue
        start = line.get("start")
        end = line.get("end")
        if start and len(start) >= 2:
            bbox.expand(start[0], start[1])
        if end and len(end) >= 2:
            bbox.expand(end[0], end[1])

    for arc in primitives.get("arcs", []):
        if target_space and arc.get("space") and arc.get("space") != target_space:
            continue
        center = arc.get("center")
        r = arc.get("radius", 0.0)
        if center and len(center) >= 2 and r > 0:
            bbox.expand(center[0] - r, center[1] - r)
            bbox.expand(center[0] + r, center[1] + r)

    for circle in primitives.get("circles", []):
        if target_space and circle.get("space") and circle.get("space") != target_space:
            continue
        center = circle.get("center")
        r = circle.get("radius", 0.0)
        if center and len(center) >= 2 and r > 0:
            bbox.expand(center[0] - r, center[1] - r)
            bbox.expand(center[0] + r, center[1] + r)

    for polyline in primitives.get("polylines", []):
        if target_space and polyline.get("space") and polyline.get("space") != target_space:
            continue
        points = polyline.get("points", [])
        for pt in points:
            if len(pt) >= 2:
                bbox.expand(pt[0], pt[1])

    return bbox


def compute_ir_extents(ir_data: Dict[str, Any], target_space: Optional[str] = "Model") -> BoundingBox:
    """
    Calculates the true bounding box of the target space in the IR payload.
    """
    bbox = BoundingBox()

    # 1. Root geometry primitives
    geom_prims = ir_data.get("geometry_primitives", {}).get("primitives", {})
    root_bbox = compute_primitive_bbox(geom_prims, target_space=target_space)
    bbox.expand_bbox(root_bbox)

    # 2. Block definitions cache
    block_defs = ir_data.get("block_definitions", {})
    block_bboxes: Dict[str, BoundingBox] = {}
    for name, bdata in block_defs.items():
        block_bboxes[name] = compute_primitive_bbox(bdata)

    # 3. Components (filtered by target_space)
    components = ir_data.get("components", [])
    for comp in components:
        if target_space and comp.get("space") and comp.get("space") != target_space:
            continue
        bname = comp.get("block_name") or comp.get("resolved_name")
        pos = comp.get("position", [0.0, 0.0, 0.0])
        rot = comp.get("rotation", 0.0)
        scale = comp.get("scale", [1.0, 1.0, 1.0])
        b_bbox = block_bboxes.get(bname)

        if b_bbox and b_bbox.is_valid:
            base_pt = block_defs.get(bname, {}).get("base_point", [0.0, 0.0, 0.0])
            mat = AffineMatrix2D.from_cad_insert(
                pos_x=pos[0],
                pos_y=pos[1],
                rotation_deg=rot,
                scale_x=scale[0] if len(scale) > 0 else 1.0,
                scale_y=scale[1] if len(scale) > 1 else 1.0,
                base_x=base_pt[0],
                base_y=base_pt[1],
            )
            corners = [
                (b_bbox.min_x, b_bbox.min_y),
                (b_bbox.max_x, b_bbox.min_y),
                (b_bbox.max_x, b_bbox.max_y),
                (b_bbox.min_x, b_bbox.max_y),
            ]
            for cx, cy in corners:
                tx, ty = mat.transform_point(cx, cy)
                bbox.expand(tx, ty)
        else:
            if len(pos) >= 2:
                bbox.expand(pos[0], pos[1])

    # 4. Annotations (filtered by target_space)
    annotations = ir_data.get("annotations", [])
    for annot in annotations:
        if target_space and annot.get("space") and annot.get("space") != target_space:
            continue
        pos = annot.get("position", [0.0, 0.0])
        if len(pos) >= 2:
            bbox.expand(pos[0], pos[1])

    # Fallback if drawing has declared extents or is empty
    if not bbox.is_valid:
        declared_ext = ir_data.get("extents", {})
        min_p = declared_ext.get("min", [0.0, 0.0])
        max_p = declared_ext.get("max", [100.0, 100.0])
        bbox.expand(min_p[0], min_p[1])
        bbox.expand(max_p[0], max_p[1])

    return bbox


def calculate_viewport_mapping(
    cad_bbox: BoundingBox,
    page_width_pt: float,
    page_height_pt: float,
    margin_pt: float,
    scale_mode: str = "fit",
    fixed_scale: Optional[float] = None,
) -> ViewportMapping:
    avail_w = max(page_width_pt - 2.0 * margin_pt, 1.0)
    avail_h = max(page_height_pt - 2.0 * margin_pt, 1.0)

    cad_w = max(cad_bbox.width, 1e-6)
    cad_h = max(cad_bbox.height, 1e-6)

    if scale_mode == "fixed" and fixed_scale and fixed_scale > 0:
        scale = fixed_scale
    else:
        scale = min(avail_w / cad_w, avail_h / cad_h)

    cad_cx, cad_cy = cad_bbox.center
    pdf_cx = page_width_pt / 2.0
    pdf_cy = page_height_pt / 2.0

    return ViewportMapping(
        scale=scale,
        cad_center_x=cad_cx,
        cad_center_y=cad_cy,
        pdf_center_x=pdf_cx,
        pdf_center_y=pdf_cy,
    )
