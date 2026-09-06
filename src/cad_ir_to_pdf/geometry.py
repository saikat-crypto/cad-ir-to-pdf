"""
geometry.py — Bounding box calculation, affine transformation, and coordinate projection.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


MIN_WORLD_COORD: float = -1e9
MAX_WORLD_COORD: float = 1e9
MIN_SCALE: float = 1e-9
MAX_SCALE: float = 1e6
MIN_PDF_COORD: float = -100_000.0
MAX_PDF_COORD: float = 100_000.0


def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Safely converts val to a finite float.
    Rejects:
    - Non-numeric types (str, None, list, dict, etc.)
    - Booleans (isinstance(val, bool) is True)
    - Arbitrary-precision integers that raise OverflowError (e.g. 10**10000)
    - Non-finite floats (NaN, +inf, -inf)
    Returns:
        float if val is finite and numeric; otherwise default.
    """
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        return default
    try:
        f = float(val)
        return f if math.isfinite(f) else default
    except (OverflowError, TypeError, ValueError):
        return default


def _coerce_matrix_field(val: Any, default: float) -> float:
    """
    Safely coerces an affine matrix field to float.
    Rejects booleans and non-numeric types by returning the specified default float.
    Converts overflow/unrepresentable integers to float('nan') so that degenerate
    parameters remain valid floats but trigger singularity detection.
    Preserves IEEE non-finite floats (NaN, ±Inf) as floats so singularity checks can detect them.
    """
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return default
    try:
        return float(val)
    except (OverflowError, TypeError, ValueError):
        return float("nan")


def is_valid_point(pt: Any) -> bool:
    """
    Validates that a point is a list or tuple of at least 2 elements,
    and every coordinate is a finite numeric value (int or float, not bool).
    """
    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
        return False
    for coord in pt:
        if _safe_float(coord) is None:
            return False
    return True


@dataclass
class BoundingBox:
    """Represents an axis-aligned 2D bounding box."""
    min_x: float = float("inf")
    min_y: float = float("inf")
    max_x: float = float("-inf")
    max_y: float = float("-inf")

    @property
    def is_valid(self) -> bool:
        min_x = _safe_float(self.min_x)
        min_y = _safe_float(self.min_y)
        max_x = _safe_float(self.max_x)
        max_y = _safe_float(self.max_y)
        if min_x is None or min_y is None or max_x is None or max_y is None:
            return False
        return max_x >= min_x and max_y >= min_y

    @property
    def width(self) -> float:
        return self.max_x - self.min_x if self.is_valid else 0.0

    @property
    def height(self) -> float:
        return self.max_y - self.min_y if self.is_valid else 0.0

    @property
    def center(self) -> Tuple[float, float]:
        if not self.is_valid:
            return (0.0, 0.0)
        try:
            cx = (float(self.min_x) + float(self.max_x)) / 2.0
            cy = (float(self.min_y) + float(self.max_y)) / 2.0
            cx_safe = _safe_float(cx)
            cy_safe = _safe_float(cy)
            if cx_safe is None or cy_safe is None:
                return (0.0, 0.0)
            return (cx_safe, cy_safe)
        except (OverflowError, TypeError):
            return (0.0, 0.0)

    def expand(self, x: float, y: float) -> None:
        """Expand bbox to include the given (x, y) point."""
        fx = _safe_float(x)
        fy = _safe_float(y)
        if fx is not None and fy is not None:
            try:
                if fx < self.min_x:
                    self.min_x = fx
                if fx > self.max_x:
                    self.max_x = fx
                if fy < self.min_y:
                    self.min_y = fy
                if fy > self.max_y:
                    self.max_y = fy
            except (OverflowError, TypeError):
                pass

    def expand_bbox(self, other: BoundingBox) -> None:
        """Expand this bbox to include another bbox."""
        if other is not None and getattr(other, "is_valid", False):
            self.expand(other.min_x, other.min_y)
            self.expand(other.max_x, other.max_y)


class SingularMatrixError(ValueError):
    """Raised when an operation requires an invertible matrix but the matrix is singular or non-finite."""
    pass


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

    def __post_init__(self) -> None:
        """
        Guarantees that all 6 fields (a, b, c, d, tx, ty) are valid Python floats.
        Sanitizes non-numeric types and booleans to defaults.
        Converts arbitrary-precision integers exceeding float capacity to float('nan')
        to eliminate OverflowError while correctly flagging the matrix as singular.
        """
        self.a = _coerce_matrix_field(self.a, default=1.0)
        self.b = _coerce_matrix_field(self.b, default=0.0)
        self.c = _coerce_matrix_field(self.c, default=0.0)
        self.d = _coerce_matrix_field(self.d, default=1.0)
        self.tx = _coerce_matrix_field(self.tx, default=0.0)
        self.ty = _coerce_matrix_field(self.ty, default=0.0)

    @property
    def determinant(self) -> float:
        """Returns the determinant of the linear 2x2 portion (a * d - b * c)."""
        try:
            return float(self.a) * float(self.d) - float(self.b) * float(self.c)
        except (OverflowError, TypeError, ValueError):
            return float("nan")

    @property
    def is_singular(self) -> bool:
        """Returns True if the matrix is non-invertible or numerically degenerate (|det| < 1e-12 or non-finite)."""
        try:
            if not (
                math.isfinite(self.a)
                and math.isfinite(self.b)
                and math.isfinite(self.c)
                and math.isfinite(self.d)
                and math.isfinite(self.tx)
                and math.isfinite(self.ty)
            ):
                return True
        except (OverflowError, TypeError):
            return True

        det = _safe_float(self.determinant)
        if det is None:
            return True
        return abs(det) < 1e-12

    def transform_point(self, x: float, y: float) -> Tuple[float, float]:
        """Transforms a 2D point (x, y) by this affine matrix."""
        fx = _safe_float(x, default=0.0)
        fy = _safe_float(y, default=0.0)
        fx = 0.0 if fx is None else fx
        fy = 0.0 if fy is None else fy
        try:
            x_prime = self.a * fx + self.c * fy + self.tx
            y_prime = self.b * fx + self.d * fy + self.ty
            safe_xp = _safe_float(x_prime)
            safe_yp = _safe_float(y_prime)
            if safe_xp is None or safe_yp is None:
                return (0.0, 0.0)
            return (safe_xp, safe_yp)
        except (OverflowError, TypeError):
            return (0.0, 0.0)

    def inverse(self, fallback: Optional[AffineMatrix2D] = None) -> AffineMatrix2D:
        """
        Computes and returns the multiplicative inverse of this affine matrix.
        Guarded against zero division, near-zero singularity (|det| < 1e-12), non-finite floats,
        and arithmetic overflow/type errors during coefficient computation.
        If singular or calculation fails and fallback is provided, returns fallback; otherwise raises SingularMatrixError.
        """
        if self.is_singular:
            if fallback is not None:
                return fallback
            raise SingularMatrixError(
                f"Cannot invert singular AffineMatrix2D (determinant={self.determinant})"
            )

        try:
            det = self.determinant
            inv_det = 1.0 / det

            inv_a = self.d * inv_det
            inv_b = -self.b * inv_det
            inv_c = -self.c * inv_det
            inv_d = self.a * inv_det
            inv_tx = (self.c * self.ty - self.d * self.tx) * inv_det
            inv_ty = (self.b * self.tx - self.a * self.ty) * inv_det

            if not (
                math.isfinite(inv_a)
                and math.isfinite(inv_b)
                and math.isfinite(inv_c)
                and math.isfinite(inv_d)
                and math.isfinite(inv_tx)
                and math.isfinite(inv_ty)
            ):
                if fallback is not None:
                    return fallback
                raise SingularMatrixError("Inversion produced non-finite coefficients.")

            return AffineMatrix2D(
                a=inv_a,
                b=inv_b,
                c=inv_c,
                d=inv_d,
                tx=inv_tx,
                ty=inv_ty,
            )
        except (OverflowError, TypeError, ValueError, ZeroDivisionError):
            if fallback is not None:
                return fallback
            raise SingularMatrixError("Inversion produced overflow or non-finite coefficients.")

    def compose(self, other: AffineMatrix2D) -> AffineMatrix2D:
        """
        Composes this matrix with another: returns self * other.
        Applies `other` first, then `self`:
            self.compose(other).transform_point(P) == self.transform_point(other.transform_point(P))
        """
        if not isinstance(other, AffineMatrix2D):
            raise TypeError(f"Expected AffineMatrix2D, got {type(other).__name__}")

        try:
            return AffineMatrix2D(
                a=self.a * other.a + self.c * other.b,
                b=self.b * other.a + self.d * other.b,
                c=self.a * other.c + self.c * other.d,
                d=self.b * other.c + self.d * other.d,
                tx=self.a * other.tx + self.c * other.ty + self.tx,
                ty=self.b * other.tx + self.d * other.ty + self.ty,
            )
        except (OverflowError, TypeError):
            return AffineMatrix2D(a=float("nan"), d=float("nan"))

    def __matmul__(self, other: AffineMatrix2D) -> AffineMatrix2D:
        """Syntactic sugar for matrix multiplication: M1 @ M2 == M1.compose(M2)."""
        if not isinstance(other, AffineMatrix2D):
            return NotImplemented
        try:
            return self.compose(other)
        except (OverflowError, TypeError):
            return AffineMatrix2D(a=float("nan"), d=float("nan"))

    def transform_angle(self, angle_deg: float) -> float:
        """
        Transforms a direction angle (in degrees) by the linear 2x2 portion of this matrix.
        Returns normalized angle in [0.0, 360.0).
        """
        safe_deg = _safe_float(angle_deg)
        if safe_deg is None:
            return 0.0
        try:
            rad = math.radians(safe_deg)
            ux = self.a * math.cos(rad) + self.c * math.sin(rad)
            uy = self.b * math.cos(rad) + self.d * math.sin(rad)
            safe_ux = _safe_float(ux)
            safe_uy = _safe_float(uy)
            if safe_ux is None or safe_uy is None:
                return 0.0
            if abs(safe_ux) < 1e-15 and abs(safe_uy) < 1e-15:
                return 0.0
            res = math.degrees(math.atan2(safe_uy, safe_ux)) % 360.0
            return res if math.isfinite(res) else 0.0
        except (OverflowError, TypeError):
            return 0.0

    def transform_arc_angles(self, start_angle_deg: float, end_angle_deg: float) -> Tuple[float, float]:
        """
        Transforms arc start and end angles (in degrees) under this transformation.
        If det(M) < 0 (reflection / parity flip), the CCW sweep direction is reversed to CW.
        To preserve CCW parameterization in PDF space, start and end angles are swapped.
        """
        try:
            sa = self.transform_angle(start_angle_deg)
            ea = self.transform_angle(end_angle_deg)
            det = _safe_float(self.determinant)
            if det is not None and det < 0.0:
                return (ea, sa)
            return (sa, ea)
        except (OverflowError, TypeError, ValueError):
            return (0.0, 0.0)

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
        px_val = _safe_float(pos_x, default=0.0)
        py_val = _safe_float(pos_y, default=0.0)
        rot_val = _safe_float(rotation_deg, default=0.0)
        sx_val = _safe_float(scale_x, default=1.0)
        sy_val = _safe_float(scale_y, default=1.0)
        bx_val = _safe_float(base_x, default=0.0)
        by_val = _safe_float(base_y, default=0.0)

        px = 0.0 if px_val is None else px_val
        py = 0.0 if py_val is None else py_val
        rot = 0.0 if rot_val is None else rot_val
        sx = 1.0 if sx_val is None else sx_val
        sy = 1.0 if sy_val is None else sy_val
        bx = 0.0 if bx_val is None else bx_val
        by = 0.0 if by_val is None else by_val

        try:
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
        except (OverflowError, TypeError):
            return cls()


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
        """
        Maps (x, y) CAD world coordinates to PDF PostScript points.
        Guarantees finite output clamped to [-10^5, +10^5] pt, never returning NaN or Inf.
        """
        safe_x = _safe_float(x, default=self.cad_center_x)
        safe_y = _safe_float(y, default=self.cad_center_y)
        val_x = self.cad_center_x if safe_x is None else safe_x
        val_y = self.cad_center_y if safe_y is None else safe_y

        try:
            px = (val_x - self.cad_center_x) * self.scale + self.pdf_center_x
            py = (val_y - self.cad_center_y) * self.scale + self.pdf_center_y

            if not math.isfinite(px):
                px = self.pdf_center_x
            else:
                px = max(MIN_PDF_COORD, min(px, MAX_PDF_COORD))

            if not math.isfinite(py):
                py = self.pdf_center_y
            else:
                py = max(MIN_PDF_COORD, min(py, MAX_PDF_COORD))

            return (px, py)
        except (OverflowError, TypeError):
            return (self.pdf_center_x, self.pdf_center_y)

    def to_pdf_length(self, length: float) -> float:
        """
        Converts CAD dimension length to PDF PostScript points length.
        Guarantees non-negative finite float clamped to [0, 10^5].
        """
        safe_len = _safe_float(length)
        if safe_len is None or safe_len <= 0.0:
            return 0.0
        try:
            val = safe_len * self.scale
            if not math.isfinite(val) or val <= 0.0:
                return 0.0
            return min(val, MAX_PDF_COORD)
        except (OverflowError, TypeError):
            return 0.0


def _arc_snapped_point(cx: float, cy: float, r: float, angle_deg: float) -> Tuple[float, float]:
    """Computes arc point with exact snapping at cardinal 90-degree quadrant boundaries."""
    ang = angle_deg % 360.0
    if abs(ang - 0.0) < 1e-6 or abs(ang - 360.0) < 1e-6:
        return (cx + r, cy)
    elif abs(ang - 90.0) < 1e-6:
        return (cx, cy + r)
    elif abs(ang - 180.0) < 1e-6:
        return (cx - r, cy)
    elif abs(ang - 270.0) < 1e-6:
        return (cx, cy - r)
    rad = math.radians(angle_deg)
    return (cx + r * math.cos(rad), cy + r * math.sin(rad))


def calculate_arc_bbox(
    cx: float, cy: float, r: float, sa_deg: float, ea_deg: float
) -> Tuple[float, float, float, float]:
    """Computes the exact bounding box of a circular arc spanning from sa_deg to ea_deg (CCW in degrees)."""
    safe_cx = _safe_float(cx)
    safe_cy = _safe_float(cy)
    safe_r = _safe_float(r)
    safe_sa = _safe_float(sa_deg)
    safe_ea = _safe_float(ea_deg)

    if (
        safe_cx is None
        or safe_cy is None
        or safe_r is None
        or safe_r <= 0.0
        or safe_sa is None
        or safe_ea is None
    ):
        fb_x = safe_cx if safe_cx is not None else 0.0
        fb_y = safe_cy if safe_cy is not None else 0.0
        return (fb_x, fb_y, fb_x, fb_y)

    cx_f = safe_cx
    cy_f = safe_cy
    r_f = safe_r
    sa_deg_f = safe_sa
    ea_deg_f = safe_ea

    try:
        if abs(sa_deg_f - ea_deg_f) < 1e-6:
            pt_x, pt_y = _arc_snapped_point(cx_f, cy_f, r_f, sa_deg_f)
            return (pt_x, pt_y, pt_x, pt_y)

        sweep = ea_deg_f - sa_deg_f
        if abs(sweep) >= 360.0 - 1e-6 or (sweep > 0 and abs(sweep % 360.0) < 1e-6):
            return (cx_f - r_f, cy_f - r_f, cx_f + r_f, cy_f + r_f)

        sa = sa_deg_f % 360.0
        ea = ea_deg_f % 360.0

        p1x, p1y = _arc_snapped_point(cx_f, cy_f, r_f, sa_deg_f)
        p2x, p2y = _arc_snapped_point(cx_f, cy_f, r_f, ea_deg_f)
        xs = [p1x, p2x]
        ys = [p1y, p2y]

        def in_arc(ang: float) -> bool:
            if sa <= ea:
                return sa <= ang <= ea
            else:
                return ang >= sa or ang <= ea

        quadrants = [
            (0.0, cx_f + r_f, cy_f),
            (90.0, cx_f, cy_f + r_f),
            (180.0, cx_f - r_f, cy_f),
            (270.0, cx_f, cy_f - r_f),
        ]
        for ang, qx, qy in quadrants:
            if in_arc(ang):
                xs.append(qx)
                ys.append(qy)

        min_x = min(xs)
        min_y = min(ys)
        max_x = max(xs)
        max_y = max(ys)
        if not (math.isfinite(min_x) and math.isfinite(min_y) and math.isfinite(max_x) and math.isfinite(max_y)):
            return (cx_f, cy_f, cx_f, cy_f)
        return (min_x, min_y, max_x, max_y)
    except (OverflowError, TypeError):
        return (cx_f, cy_f, cx_f, cy_f)


def compute_primitive_bbox(primitives: Any, target_space: Optional[str] = None) -> BoundingBox:
    """Computes the 2D bounding box of a primitive collection, filtering by target space if specified."""
    bbox = BoundingBox()
    if not isinstance(primitives, dict):
        return bbox

    raw_lines = primitives.get("lines")
    for line in (raw_lines if isinstance(raw_lines, (list, tuple)) else []):
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

    raw_arcs = primitives.get("arcs")
    for arc in (raw_arcs if isinstance(raw_arcs, (list, tuple)) else []):
        if not isinstance(arc, dict):
            continue
        if target_space and arc.get("space") and arc.get("space") != target_space:
            continue
        center = arc.get("center")
        r_f = _safe_float(arc.get("radius"))
        if is_valid_point(center) and r_f is not None and r_f > 0:
            sa_f = _safe_float(arc.get("start_angle"), default=0.0)
            ea_f = _safe_float(arc.get("end_angle"), default=360.0)
            sa_val = 0.0 if sa_f is None else sa_f
            ea_val = 360.0 if ea_f is None else ea_f
            c0 = float(center[0])
            c1 = float(center[1])
            min_x, min_y, max_x, max_y = calculate_arc_bbox(c0, c1, r_f, sa_val, ea_val)
            bbox.expand(min_x, min_y)
            bbox.expand(max_x, max_y)

    raw_circles = primitives.get("circles")
    for circle in (raw_circles if isinstance(raw_circles, (list, tuple)) else []):
        if not isinstance(circle, dict):
            continue
        if target_space and circle.get("space") and circle.get("space") != target_space:
            continue
        center = circle.get("center")
        r_f = _safe_float(circle.get("radius"))
        if is_valid_point(center) and r_f is not None and r_f > 0:
            c0 = float(center[0])
            c1 = float(center[1])
            bbox.expand(c0 - r_f, c1 - r_f)
            bbox.expand(c0 + r_f, c1 + r_f)

    raw_polylines = primitives.get("polylines")
    for polyline in (raw_polylines if isinstance(raw_polylines, (list, tuple)) else []):
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
    valid_vals: List[float] = []
    for v in values:
        fv = _safe_float(v)
        if fv is not None and MIN_WORLD_COORD <= fv <= MAX_WORLD_COORD:
            valid_vals.append(fv)

    if not valid_vals:
        return (0.0, 100.0)

    vals = sorted(valid_vals)
    n = len(vals)
    if n < 4:
        return (vals[0], vals[-1])

    total_span = vals[-1] - vals[0]
    if total_span <= 1e-6:
        return (vals[0], vals[-1])

    # Small-payload outlier protection (4 <= n < 20):
    # Detect if a single outlier is separated by an extreme gap (>= 90% of total span)
    if n < 20:
        # Check right outlier
        if (vals[-1] - vals[-2]) >= 0.90 * total_span and (vals[-2] - vals[0]) < 0.10 * total_span:
            return (vals[0], vals[-2])
        # Check left outlier
        if (vals[1] - vals[0]) >= 0.90 * total_span and (vals[-1] - vals[1]) < 0.10 * total_span:
            return (vals[1], vals[-1])
        return (vals[0], vals[-1])

    # Cluster gap detector (n >= 20): allow at least 1 outlier to be pruned for 20 <= n < 50
    max_pts = max(1, math.floor(max_outlier_ratio * n))
    start_idx = 0
    for i in range(n - 1):
        gap = vals[i + 1] - vals[i]
        pts_on_left = i + 1
        if gap >= min_gap_fraction * total_span and pts_on_left <= max_pts:
            start_idx = i + 1
        elif pts_on_left > max_pts:
            break

    end_idx = n - 1
    for i in range(n - 1, 0, -1):
        gap = vals[i] - vals[i - 1]
        pts_on_right = n - i
        if gap >= min_gap_fraction * total_span and pts_on_right <= max_pts:
            end_idx = i - 1
        elif pts_on_right > max_pts:
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
        cb_x0 = _safe_float(custom_bbox[0])
        cb_y0 = _safe_float(custom_bbox[1])
        cb_x1 = _safe_float(custom_bbox[2])
        cb_y1 = _safe_float(custom_bbox[3])
        if cb_x0 is not None and cb_y0 is not None and cb_x1 is not None and cb_y1 is not None:
            fx0 = max(MIN_WORLD_COORD, min(cb_x0, MAX_WORLD_COORD))
            fy0 = max(MIN_WORLD_COORD, min(cb_y0, MAX_WORLD_COORD))
            fx1 = max(MIN_WORLD_COORD, min(cb_x1, MAX_WORLD_COORD))
            fy1 = max(MIN_WORLD_COORD, min(cb_y1, MAX_WORLD_COORD))
            if fx1 >= fx0 and fy1 >= fy0:
                return BoundingBox(min_x=fx0, min_y=fy0, max_x=fx1, max_y=fy1)

    all_xs: List[float] = []
    all_ys: List[float] = []

    if not isinstance(ir_data, dict):
        return BoundingBox(0.0, 0.0, 100.0, 100.0)

    # Helper to track point
    def add_point(x: float, y: float) -> None:
        fx = _safe_float(x)
        fy = _safe_float(y)
        if fx is not None and fy is not None:
            if MIN_WORLD_COORD <= fx <= MAX_WORLD_COORD and MIN_WORLD_COORD <= fy <= MAX_WORLD_COORD:
                all_xs.append(fx)
                all_ys.append(fy)

    # 1. Root geometry primitives
    geom_prims = ((ir_data.get("geometry_primitives") or {}).get("primitives") or {}) if isinstance(ir_data.get("geometry_primitives"), dict) else {}
    if isinstance(geom_prims, dict):
        raw_lines = geom_prims.get("lines")
        for line in (raw_lines if isinstance(raw_lines, (list, tuple)) else []):
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

        raw_arcs = geom_prims.get("arcs")
        for arc in (raw_arcs if isinstance(raw_arcs, (list, tuple)) else []):
            if not isinstance(arc, dict):
                continue
            if target_space and arc.get("space") and arc.get("space") != target_space:
                continue
            c = arc.get("center")
            r_f = _safe_float(arc.get("radius"))
            if is_valid_point(c) and r_f is not None and r_f > 0:
                sa_f = _safe_float(arc.get("start_angle"), default=0.0)
                ea_f = _safe_float(arc.get("end_angle"), default=360.0)
                sa_val = 0.0 if sa_f is None else sa_f
                ea_val = 360.0 if ea_f is None else ea_f
                min_x, min_y, max_x, max_y = calculate_arc_bbox(float(c[0]), float(c[1]), r_f, sa_val, ea_val)
                add_point(min_x, min_y)
                add_point(max_x, max_y)

        raw_circles = geom_prims.get("circles")
        for circle in (raw_circles if isinstance(raw_circles, (list, tuple)) else []):
            if not isinstance(circle, dict):
                continue
            if target_space and circle.get("space") and circle.get("space") != target_space:
                continue
            c = circle.get("center")
            r_f = _safe_float(circle.get("radius"))
            if is_valid_point(c) and r_f is not None and r_f > 0:
                c0 = float(c[0])
                c1 = float(c[1])
                add_point(c0 - r_f, c1 - r_f)
                add_point(c0 + r_f, c1 + r_f)

        raw_polylines = geom_prims.get("polylines")
        for polyline in (raw_polylines if isinstance(raw_polylines, (list, tuple)) else []):
            if not isinstance(polyline, dict):
                continue
            if target_space and polyline.get("space") and polyline.get("space") != target_space:
                continue
            points = polyline.get("points") or []
            if isinstance(points, (list, tuple)):
                for pt in points:
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
    raw_comp = ir_data.get("components")
    components = raw_comp if isinstance(raw_comp, (list, tuple)) else []
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
            scale_x_raw = scale[0] if (isinstance(scale, (list, tuple)) and len(scale) > 0) else 1.0
            scale_y_raw = scale[1] if (isinstance(scale, (list, tuple)) and len(scale) > 1) else 1.0
            rot_f = _safe_float(rot, default=0.0)
            sx_f = _safe_float(scale_x_raw, default=1.0)
            sy_f = _safe_float(scale_y_raw, default=1.0)
            mat = AffineMatrix2D.from_cad_insert(
                pos_x=pos[0] if is_valid_point(pos) else 0.0,
                pos_y=pos[1] if is_valid_point(pos) else 0.0,
                rotation_deg=0.0 if rot_f is None else rot_f,
                scale_x=1.0 if sx_f is None else sx_f,
                scale_y=1.0 if sy_f is None else sy_f,
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
    raw_annots = ir_data.get("annotations")
    annots = raw_annots if isinstance(raw_annots, (list, tuple)) else []
    for annot in annots:
        if not isinstance(annot, dict):
            continue
        if target_space and annot.get("space") and annot.get("space") != target_space:
            continue
        pos = annot.get("position")
        if is_valid_point(pos):
            add_point(pos[0], pos[1])

    # 5. Dimensions
    raw_dims = ir_data.get("dimensions")
    dims = raw_dims if isinstance(raw_dims, (list, tuple)) else []
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
        if prune_outliers:
            min_x, max_x = find_primary_cluster_1d(all_xs)
            min_y, max_y = find_primary_cluster_1d(all_ys)
            bbox.expand(min_x, min_y)
            bbox.expand(max_x, max_y)
        else:
            for x, y in zip(all_xs, all_ys):
                bbox.expand(x, y)

    # Fallback if drawing has declared extents or is empty
    if not bbox.is_valid or (bbox.width < 1e-6 and bbox.height < 1e-6):
        declared_ext = ir_data.get("extents")
        fallback_used = True
        if isinstance(declared_ext, dict):
            min_p = declared_ext.get("min")
            max_p = declared_ext.get("max")
            if is_valid_point(min_p) and is_valid_point(max_p):
                d_x0 = _safe_float(min_p[0])
                d_y0 = _safe_float(min_p[1])
                d_x1 = _safe_float(max_p[0])
                d_y1 = _safe_float(max_p[1])
                if d_x0 is not None and d_y0 is not None and d_x1 is not None and d_y1 is not None:
                    d_min_x = max(MIN_WORLD_COORD, min(d_x0, MAX_WORLD_COORD))
                    d_min_y = max(MIN_WORLD_COORD, min(d_y0, MAX_WORLD_COORD))
                    d_max_x = max(MIN_WORLD_COORD, min(d_x1, MAX_WORLD_COORD))
                    d_max_y = max(MIN_WORLD_COORD, min(d_y1, MAX_WORLD_COORD))
                    if d_max_x - d_min_x >= 1e-6 or d_max_y - d_min_y >= 1e-6:
                        bbox = BoundingBox(min_x=d_min_x, min_y=d_min_y, max_x=d_max_x, max_y=d_max_y)
                        fallback_used = False

        if fallback_used:
            bbox = BoundingBox(0.0, 0.0, 100.0, 100.0)

    return bbox


def calculate_viewport_mapping(
    cad_bbox: BoundingBox,
    page_width_pt: float,
    page_height_pt: float,
    margin_pt: float,
    scale_mode: str = "fit",
    fixed_scale: Optional[float] = None,
) -> ViewportMapping:
    """
    Calculates isotropic 2D viewport mapping from CAD bounding box to PDF canvas.
    Enforces scale clamping within [1e-9, 1e6] and guards against non-finite inputs.
    """
    pw_val = _safe_float(page_width_pt)
    pw = pw_val if (pw_val is not None and pw_val > 0) else 595.275

    ph_val = _safe_float(page_height_pt)
    ph = ph_val if (ph_val is not None and ph_val > 0) else 841.890

    m_val = _safe_float(margin_pt)
    m = m_val if (m_val is not None and m_val >= 0) else 28.346

    avail_w = max(pw - 2.0 * m, 1.0)
    avail_h = max(ph - 2.0 * m, 1.0)

    if not isinstance(cad_bbox, BoundingBox) or not cad_bbox.is_valid:
        cad_bbox = BoundingBox(0.0, 0.0, 100.0, 100.0)

    cad_w = max(cad_bbox.width, 1e-6)
    cad_h = max(cad_bbox.height, 1e-6)

    fs_val = _safe_float(fixed_scale)
    if scale_mode == "fixed" and fs_val is not None and fs_val > 0:
        raw_scale = fs_val
    else:
        raw_scale = min(avail_w / cad_w, avail_h / cad_h)

    if not math.isfinite(raw_scale) or raw_scale <= 0.0:
        scale = 1.0
    else:
        scale = max(MIN_SCALE, min(raw_scale, MAX_SCALE))

    cad_cx, cad_cy = cad_bbox.center
    if not (math.isfinite(cad_cx) and math.isfinite(cad_cy)):
        cad_cx, cad_cy = 0.0, 0.0

    pdf_cx = pw / 2.0
    pdf_cy = ph / 2.0

    return ViewportMapping(
        scale=scale,
        cad_center_x=cad_cx,
        cad_center_y=cad_cy,
        pdf_center_x=pdf_cx,
        pdf_center_y=pdf_cy,
    )
