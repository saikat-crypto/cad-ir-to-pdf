"""
geometry.py — Bounding box calculation, affine transformation, and coordinate projection.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


def is_valid_point(pt: Any) -> bool:
    """Validates that a point is a list/tuple of at least 2 finite numbers."""
    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
        return False
    return (
        isinstance(pt[0], (int, float))
        and not isinstance(pt[0], bool)
        and math.isfinite(pt[0])
        and isinstance(pt[1], (int, float))
        and not isinstance(pt[1], bool)
        and math.isfinite(pt[1])
    )


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
        if (
            isinstance(x, (int, float))
            and not isinstance(x, bool)
            and math.isfinite(x)
            and isinstance(y, (int, float))
            and not isinstance(y, bool)
            and math.isfinite(y)
        ):
            if x < self.min_x:
                self.min_x = float(x)
            if x > self.max_x:
                self.max_x = float(x)
            if y < self.min_y:
                self.min_y = float(y)
            if y > self.max_y:
                self.max_y = float(y)

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
        # Sanitize and ensure all parameters are finite numbers
        try:
            px = float(pos_x) if (isinstance(pos_x, (int, float)) and math.isfinite(pos_x)) else 0.0
            py = float(pos_y) if (isinstance(pos_y, (int, float)) and math.isfinite(pos_y)) else 0.0
            rot = float(rotation_deg) if (isinstance(rotation_deg, (int, float)) and math.isfinite(rotation_deg)) else 0.0
            sx = float(scale_x) if (isinstance(scale_x, (int, float)) and math.isfinite(scale_x)) else 1.0
            sy = float(scale_y) if (isinstance(scale_y, (int, float)) and math.isfinite(scale_y)) else 1.0
            bx = float(base_x) if (isinstance(base_x, (int, float)) and math.isfinite(base_x)) else 0.0
            by = float(base_y) if (isinstance(base_y, (int, float)) and math.isfinite(base_y)) else 0.0
        except Exception:
            return cls()

        rad = math.radians(rot)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)

        a = sx * cos_r
        b = sx * sin_r
        c = -sy * sin_r
        d = sy * cos_r

        tx = px - (a * bx + c * by)
        ty = py - (b * bx + d * by)

        if not (math.isfinite(a) and math.isfinite(b) and math.isfinite(c) and math.isfinite(d) and math.isfinite(tx) and math.isfinite(ty)):
            return cls()

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


def calculate_arc_bbox(
    cx: float, cy: float, r: float, sa_deg: float, ea_deg: float
) -> Tuple[float, float, float, float]:
    """Computes the exact bounding box of a circular arc spanning from sa_deg to ea_deg (CCW in degrees)."""
    if (
        not isinstance(cx, (int, float)) or isinstance(cx, bool) or not math.isfinite(cx)
        or not isinstance(cy, (int, float)) or isinstance(cy, bool) or not math.isfinite(cy)
        or not isinstance(r, (int, float)) or isinstance(r, bool) or not math.isfinite(r)
        or r <= 0
        or not isinstance(sa_deg, (int, float)) or isinstance(sa_deg, bool) or not math.isfinite(sa_deg)
        or not isinstance(ea_deg, (int, float)) or isinstance(ea_deg, bool) or not math.isfinite(ea_deg)
    ):
        fallback_x = cx if (isinstance(cx, (int, float)) and not isinstance(cx, bool) and math.isfinite(cx)) else 0.0
        fallback_y = cy if (isinstance(cy, (int, float)) and not isinstance(cy, bool) and math.isfinite(cy)) else 0.0
        return (fallback_x, fallback_y, fallback_x, fallback_y)

    if abs(sa_deg - ea_deg) < 1e-6:
        sa_rad = math.radians(sa_deg)
        pt_x = cx + r * math.cos(sa_rad)
        pt_y = cy + r * math.sin(sa_rad)
        return (pt_x, pt_y, pt_x, pt_y)

    sweep = ea_deg - sa_deg
    if abs(sweep) >= 360.0 or (sweep > 0 and abs(sweep % 360.0) < 1e-6):
        return (cx - r, cy - r, cx + r, cy + r)

    sa = sa_deg % 360.0
    ea = ea_deg % 360.0
    sa_rad = math.radians(sa_deg)
    ea_rad = math.radians(ea_deg)
    xs = [cx + r * math.cos(sa_rad), cx + r * math.cos(ea_rad)]
    ys = [cy + r * math.sin(sa_rad), cy + r * math.sin(ea_rad)]

    def in_arc(ang: float) -> bool:
        if sa <= ea:
            return sa <= ang <= ea
        else:
            return ang >= sa or ang <= ea

    for ang in [0.0, 90.0, 180.0, 270.0]:
        if in_arc(ang):
            rad = math.radians(ang)
            xs.append(cx + r * math.cos(rad))
            ys.append(cy + r * math.sin(rad))

    return (min(xs), min(ys), max(xs), max(ys))


def compute_primitive_bbox(primitives: Any, target_space: Optional[str] = None) -> BoundingBox:
    """Computes the 2D bounding box of a primitive collection, filtering by target space if specified."""
    bbox = BoundingBox()
    if not isinstance(primitives, dict):
        return bbox

    for line in (primitives.get("lines") or []):
        if not isinstance(line, dict):
            continue
        if target_space and line.get("space") and line.get("space") != target_space:
            continue
        start = line.get("start")
        end = line.get("end")
        if is_valid_point(start):
            bbox.expand(start[0], start[1])
        if is_valid_point(end):
            bbox.expand(end[0], end[1])

    for arc in (primitives.get("arcs") or []):
        if not isinstance(arc, dict):
            continue
        if target_space and arc.get("space") and arc.get("space") != target_space:
            continue
        center = arc.get("center")
        r = arc.get("radius", 0.0)
        sa = arc.get("start_angle", 0.0)
        ea = arc.get("end_angle", 360.0)
        if is_valid_point(center) and isinstance(r, (int, float)) and not isinstance(r, bool) and math.isfinite(r) and r > 0:
            sa_f = sa if (isinstance(sa, (int, float)) and not isinstance(sa, bool) and math.isfinite(sa)) else 0.0
            ea_f = ea if (isinstance(ea, (int, float)) and not isinstance(ea, bool) and math.isfinite(ea)) else 360.0
            min_x, min_y, max_x, max_y = calculate_arc_bbox(center[0], center[1], r, sa_f, ea_f)
            bbox.expand(min_x, min_y)
            bbox.expand(max_x, max_y)

    for circle in (primitives.get("circles") or []):
        if not isinstance(circle, dict):
            continue
        if target_space and circle.get("space") and circle.get("space") != target_space:
            continue
        center = circle.get("center")
        r = circle.get("radius", 0.0)
        if is_valid_point(center) and isinstance(r, (int, float)) and not isinstance(r, bool) and math.isfinite(r) and r > 0:
            bbox.expand(center[0] - r, center[1] - r)
            bbox.expand(center[0] + r, center[1] + r)

    for polyline in (primitives.get("polylines") or []):
        if not isinstance(polyline, dict):
            continue
        if target_space and polyline.get("space") and polyline.get("space") != target_space:
            continue
        points = polyline.get("points") or []
        if isinstance(points, (list, tuple)):
            for pt in points:
                if is_valid_point(pt):
                    bbox.expand(pt[0], pt[1])

    return bbox


def find_primary_cluster_1d(
    values: Sequence[float],
    min_gap_fraction: float = 0.10,
    max_outlier_ratio: float = 0.02,
) -> Tuple[float, float]:
    """
    Identifies the primary coordinate span by detecting large empty voids separating
    tiny isolated outlier clusters (< max_outlier_ratio) from the main drawing cluster.
    """
    if len(values) < 20:
        return (min(values), max(values)) if values else (0.0, 100.0)

    vals = sorted(values)
    n = len(vals)
    total_span = vals[-1] - vals[0]
    if total_span <= 1e-6:
        return (vals[0], vals[-1])

    start_idx = 0
    for i in range(n - 1):
        gap = vals[i + 1] - vals[i]
        pts_on_left = i + 1
        if gap >= min_gap_fraction * total_span and (pts_on_left / n) <= max_outlier_ratio:
            start_idx = i + 1
        elif (pts_on_left / n) > max_outlier_ratio:
            break

    end_idx = n - 1
    for i in range(n - 1, 0, -1):
        gap = vals[i] - vals[i - 1]
        pts_on_right = n - i
        if gap >= min_gap_fraction * total_span and (pts_on_right / n) <= max_outlier_ratio:
            end_idx = i - 1
        elif (pts_on_right / n) > max_outlier_ratio:
            break

    return (vals[start_idx], vals[end_idx])


def compute_ir_extents(
    ir_data: Dict[str, Any],
    target_space: Optional[str] = "Model",
    prune_outliers: bool = True,
    custom_bbox: Optional[Tuple[float, float, float, float]] = None,
) -> BoundingBox:
    """
    Calculates the true bounding box of the target space in the IR payload.
    When prune_outliers is True, filters out isolated scratch geometry clusters
    separated by large coordinate voids (>10% span, <2% entities).
    """
    if custom_bbox is not None and len(custom_bbox) == 4:
        c_min_x, c_min_y, c_max_x, c_max_y = custom_bbox
        if (
            isinstance(c_min_x, (int, float)) and math.isfinite(c_min_x)
            and isinstance(c_min_y, (int, float)) and math.isfinite(c_min_y)
            and isinstance(c_max_x, (int, float)) and math.isfinite(c_max_x)
            and isinstance(c_max_y, (int, float)) and math.isfinite(c_max_y)
        ):
            return BoundingBox(
                min_x=float(c_min_x),
                min_y=float(c_min_y),
                max_x=float(c_max_x),
                max_y=float(c_max_y),
            )

    all_xs: List[float] = []
    all_ys: List[float] = []

    if not isinstance(ir_data, dict):
        return BoundingBox(0.0, 0.0, 100.0, 100.0)

    # Helper to track point
    def add_point(x: float, y: float) -> None:
        if (
            isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
            and isinstance(y, (int, float)) and not isinstance(y, bool) and math.isfinite(y)
        ):
            all_xs.append(float(x))
            all_ys.append(float(y))

    # 1. Root geometry primitives
    geom_prims = ((ir_data.get("geometry_primitives") or {}).get("primitives") or {}) if isinstance(ir_data.get("geometry_primitives"), dict) else {}
    if isinstance(geom_prims, dict):
        for line in (geom_prims.get("lines") or []):
            if not isinstance(line, dict):
                continue
            if target_space and line.get("space") and line.get("space") != target_space:
                continue
            st = line.get("start")
            en = line.get("end")
            if is_valid_point(st):
                add_point(st[0], st[1])
            if is_valid_point(en):
                add_point(en[0], en[1])

        for arc in (geom_prims.get("arcs") or []):
            if not isinstance(arc, dict):
                continue
            if target_space and arc.get("space") and arc.get("space") != target_space:
                continue
            c = arc.get("center")
            r = arc.get("radius", 0.0)
            sa = arc.get("start_angle", 0.0)
            ea = arc.get("end_angle", 360.0)
            if is_valid_point(c) and isinstance(r, (int, float)) and not isinstance(r, bool) and math.isfinite(r) and r > 0:
                sa_f = sa if (isinstance(sa, (int, float)) and not isinstance(sa, bool) and math.isfinite(sa)) else 0.0
                ea_f = ea if (isinstance(ea, (int, float)) and not isinstance(ea, bool) and math.isfinite(ea)) else 360.0
                min_x, min_y, max_x, max_y = calculate_arc_bbox(c[0], c[1], r, sa_f, ea_f)
                add_point(min_x, min_y)
                add_point(max_x, max_y)

        for circle in (geom_prims.get("circles") or []):
            if not isinstance(circle, dict):
                continue
            if target_space and circle.get("space") and circle.get("space") != target_space:
                continue
            c = circle.get("center")
            r = circle.get("radius", 0.0)
            if is_valid_point(c) and isinstance(r, (int, float)) and not isinstance(r, bool) and math.isfinite(r) and r > 0:
                add_point(c[0] - r, c[1] - r)
                add_point(c[0] + r, c[1] + r)

        for pline in (geom_prims.get("polylines") or []):
            if not isinstance(pline, dict):
                continue
            if target_space and pline.get("space") and pline.get("space") != target_space:
                continue
            pts = pline.get("points") or []
            if isinstance(pts, (list, tuple)):
                for pt in pts:
                    if is_valid_point(pt):
                        add_point(pt[0], pt[1])

    # 2. Block definitions cache
    raw_block_defs = ir_data.get("block_definitions") or {}
    block_defs = raw_block_defs if isinstance(raw_block_defs, dict) else {}
    block_bboxes: Dict[str, BoundingBox] = {}
    for name, bdata in block_defs.items():
        if isinstance(bdata, dict):
            block_bboxes[name] = compute_primitive_bbox(bdata)

    # 3. Components (transformed into world coordinates)
    components = ir_data.get("components") or []
    if isinstance(components, (list, tuple)):
        for comp in components:
            if not isinstance(comp, dict):
                continue
            if target_space and comp.get("space") and comp.get("space") != target_space:
                continue
            bname = comp.get("block_name") or comp.get("resolved_name")
            pos = comp.get("position") or [0.0, 0.0, 0.0]
            rot = comp.get("rotation", 0.0)
            scale = comp.get("scale") or [1.0, 1.0, 1.0]
            b_bbox = block_bboxes.get(bname) if bname else None

            if b_bbox and b_bbox.is_valid:
                bdef = block_defs.get(bname) if isinstance(block_defs.get(bname), dict) else {}
                base_pt = bdef.get("base_point") or [0.0, 0.0, 0.0]
                mat = AffineMatrix2D.from_cad_insert(
                    pos_x=pos[0] if is_valid_point(pos) else 0.0,
                    pos_y=pos[1] if is_valid_point(pos) else 0.0,
                    rotation_deg=rot if (isinstance(rot, (int, float)) and math.isfinite(rot)) else 0.0,
                    scale_x=scale[0] if (isinstance(scale, (list, tuple)) and len(scale) > 0 and isinstance(scale[0], (int, float)) and math.isfinite(scale[0])) else 1.0,
                    scale_y=scale[1] if (isinstance(scale, (list, tuple)) and len(scale) > 1 and isinstance(scale[1], (int, float)) and math.isfinite(scale[1])) else 1.0,
                    base_x=base_pt[0] if is_valid_point(base_pt) else 0.0,
                    base_y=base_pt[1] if is_valid_point(base_pt) else 0.0,
                )
                corners = [
                    (b_bbox.min_x, b_bbox.min_y),
                    (b_bbox.max_x, b_bbox.min_y),
                    (b_bbox.max_x, b_bbox.max_y),
                    (b_bbox.min_x, b_bbox.max_y),
                ]
                for cx, cy in corners:
                    tx, ty = mat.transform_point(cx, cy)
                    add_point(tx, ty)
            else:
                if is_valid_point(pos):
                    add_point(pos[0], pos[1])

    # 4. Annotations
    annots = ir_data.get("annotations") or []
    if isinstance(annots, (list, tuple)):
        for annot in annots:
            if not isinstance(annot, dict):
                continue
            if target_space and annot.get("space") and annot.get("space") != target_space:
                continue
            pos = annot.get("position")
            if is_valid_point(pos):
                add_point(pos[0], pos[1])

    # 5. Dimensions
    dims = ir_data.get("dimensions") or []
    if isinstance(dims, (list, tuple)):
        for dim in dims:
            if not isinstance(dim, dict):
                continue
            if target_space and dim.get("space") and dim.get("space") != target_space:
                continue
            dp = dim.get("defpoint")
            dp2 = dim.get("defpoint2")
            if is_valid_point(dp):
                add_point(dp[0], dp[1])
            if is_valid_point(dp2):
                add_point(dp2[0], dp2[1])

    bbox = BoundingBox()
    if all_xs and all_ys:
        if prune_outliers and len(all_xs) >= 20:
            min_x, max_x = find_primary_cluster_1d(all_xs)
            min_y, max_y = find_primary_cluster_1d(all_ys)
            bbox.expand(min_x, min_y)
            bbox.expand(max_x, max_y)
        else:
            for x, y in zip(all_xs, all_ys):
                bbox.expand(x, y)

    # Fallback if drawing has declared extents or is empty
    if not bbox.is_valid:
        declared_ext = ir_data.get("extents") or {}
        if not isinstance(declared_ext, dict):
            declared_ext = {}
        min_p = declared_ext.get("min") or [0.0, 0.0]
        max_p = declared_ext.get("max") or [100.0, 100.0]
        min_x = min_p[0] if is_valid_point(min_p) else 0.0
        min_y = min_p[1] if is_valid_point(min_p) else 0.0
        max_x = max_p[0] if is_valid_point(max_p) else 100.0
        max_y = max_p[1] if is_valid_point(max_p) else 100.0
        bbox.expand(min_x, min_y)
        bbox.expand(max_x, max_y)
        if not bbox.is_valid:
            bbox.expand(0.0, 0.0)
            bbox.expand(100.0, 100.0)

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
