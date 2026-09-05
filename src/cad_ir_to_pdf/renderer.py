"""
renderer.py — High-fidelity ReportLab vector canvas renderer for CAD entities.
"""

from __future__ import annotations
import math
import re
from typing import Any, Dict, List, Optional, Tuple
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from .config import PdfPreset
from .curves import arc_to_cubic_beziers, circle_to_cubic_beziers
from .geometry import AffineMatrix2D, ViewportMapping


def hex_to_pdf_color(hex_str: Optional[str], fallback: str = "#1E1E1E") -> colors.Color:
    """Converts a hex string (#RRGGBB) to a ReportLab Color with contrast safety."""
    target = hex_str or fallback
    target = target.strip()
    if not target.startswith("#"):
        target = "#" + target

    # Contrast safety check: if drawing on white background, don't draw pure white
    if target.lower() in ("#ffffff", "#fff"):
        return colors.HexColor(fallback)

    try:
        return colors.HexColor(target)
    except Exception:
        return colors.HexColor(fallback)


class PdfVectorRenderer:
    """Draws CAD primitives and annotations onto a ReportLab Canvas in PostScript point space."""

    def __init__(
        self,
        pdf_canvas: canvas.Canvas,
        viewport: ViewportMapping,
        preset: PdfPreset,
        layer_color_map: Optional[Dict[str, str]] = None,
    ):
        self.c = pdf_canvas
        self.vp = viewport
        self.preset = preset
        self.layer_colors = layer_color_map or {}
        self.default_line_width = preset.default_line_width_pt

    def resolve_color(self, entity_color: Optional[str], layer_name: Optional[str]) -> colors.Color:
        """Determines entity color via entity override -> layer color -> fallback."""
        if entity_color and entity_color.startswith("#"):
            return hex_to_pdf_color(entity_color, self.preset.default_stroke_color)
        if layer_name and layer_name in self.layer_colors:
            return hex_to_pdf_color(self.layer_colors[layer_name], self.preset.default_stroke_color)
        return hex_to_pdf_color(None, self.preset.default_stroke_color)

    def draw_line(
        self,
        start: Sequence[float],
        end: Sequence[float],
        color: Optional[str] = None,
        layer: Optional[str] = None,
        line_width: Optional[float] = None,
        transform: Optional[AffineMatrix2D] = None,
    ) -> None:
        """Renders a single vector line segment."""
        if len(start) < 2 or len(end) < 2:
            return

        x0, y0 = (start[0], start[1])
        x1, y1 = (end[0], end[1])

        if transform:
            x0, y0 = transform.transform_point(x0, y0)
            x1, y1 = transform.transform_point(x1, y1)

        px0, py0 = self.vp.to_pdf(x0, y0)
        px1, py1 = self.vp.to_pdf(x1, y1)

        col = self.resolve_color(color, layer)
        lw = line_width or self.default_line_width

        self.c.setStrokeColor(col)
        self.c.setLineWidth(lw)
        self.c.line(px0, py0, px1, py1)

    def draw_polyline(
        self,
        points: List[Sequence[float]],
        is_closed: bool = False,
        color: Optional[str] = None,
        layer: Optional[str] = None,
        line_width: Optional[float] = None,
        transform: Optional[AffineMatrix2D] = None,
    ) -> None:
        """Renders a polyline path with native vector lines."""
        if len(points) < 2:
            return

        transformed_pts: List[Tuple[float, float]] = []
        for pt in points:
            if len(pt) < 2:
                continue
            x, y = (pt[0], pt[1])
            if transform:
                x, y = transform.transform_point(x, y)
            transformed_pts.append(self.vp.to_pdf(x, y))

        if len(transformed_pts) < 2:
            return

        col = self.resolve_color(color, layer)
        lw = line_width or self.default_line_width

        self.c.setStrokeColor(col)
        self.c.setLineWidth(lw)

        path = self.c.beginPath()
        path.moveTo(transformed_pts[0][0], transformed_pts[0][1])
        for p in transformed_pts[1:]:
            path.lineTo(p[0], p[1])
        if is_closed:
            path.close()
        self.c.drawPath(path, stroke=1, fill=0)

    def draw_arc(
        self,
        center: Sequence[float],
        radius: float,
        start_angle_deg: float,
        end_angle_deg: float,
        color: Optional[str] = None,
        layer: Optional[str] = None,
        line_width: Optional[float] = None,
        transform: Optional[AffineMatrix2D] = None,
    ) -> None:
        """Renders an arc converted into cubic Bézier segments."""
        if len(center) < 2 or radius <= 0:
            return

        cx, cy = center[0], center[1]
        start_pt, segments = arc_to_cubic_beziers(cx, cy, radius, start_angle_deg, end_angle_deg)

        # Apply transforms to Bézier control points
        def tx_pt(x: float, y: float) -> Tuple[float, float]:
            if transform:
                x, y = transform.transform_point(x, y)
            return self.vp.to_pdf(x, y)

        p0_pdf = tx_pt(start_pt[0], start_pt[1])

        col = self.resolve_color(color, layer)
        lw = line_width or self.default_line_width

        self.c.setStrokeColor(col)
        self.c.setLineWidth(lw)

        path = self.c.beginPath()
        path.moveTo(p0_pdf[0], p0_pdf[1])

        for cp1x, cp1y, cp2x, cp2y, endx, endy in segments:
            cp1_pdf = tx_pt(cp1x, cp1y)
            cp2_pdf = tx_pt(cp2x, cp2y)
            end_pdf = tx_pt(endx, endy)
            path.curveTo(cp1_pdf[0], cp1_pdf[1], cp2_pdf[0], cp2_pdf[1], end_pdf[0], end_pdf[1])

        self.c.drawPath(path, stroke=1, fill=0)

    def draw_circle(
        self,
        center: Sequence[float],
        radius: float,
        color: Optional[str] = None,
        layer: Optional[str] = None,
        line_width: Optional[float] = None,
        transform: Optional[AffineMatrix2D] = None,
    ) -> None:
        """Renders a 360-degree circle."""
        self.draw_arc(
            center=center,
            radius=radius,
            start_angle_deg=0.0,
            end_angle_deg=360.0,
            color=color,
            layer=layer,
            line_width=line_width,
            transform=transform,
        )

    def draw_annotation(
        self,
        text: str,
        position: Sequence[float],
        height: float,
        color: Optional[str] = None,
        layer: Optional[str] = None,
    ) -> None:
        """Renders text labels (e.g., room names, dimensions)."""
        if not text or len(position) < 2:
            return

        # Sanitize AutoCAD MText codes like {\LLIVING ROOM\P\H0.6667x;\l...}
        clean = text.replace(r"\P", "\n").replace(r"\p", "\n")
        clean = re.sub(r"\\[A-Za-z0-9]+;?", "", clean)
        clean = clean.replace("{", "").replace("}", "").strip()

        if not clean:
            return

        px, py = self.vp.to_pdf(position[0], position[1])
        # Font size proportional to CAD height scaled to PDF points, clamped to readable size
        pdf_font_size = max(5.0, min(36.0, self.vp.to_pdf_length(height)))

        col = self.resolve_color(color, layer)
        self.c.setFillColor(col)
        self.c.setFont(self.preset.font_name, pdf_font_size)

        lines = clean.split("\n")
        line_spacing = pdf_font_size * 1.2
        for i, line_str in enumerate(lines):
            line_y = py - (i * line_spacing)
            self.c.drawString(px, line_y, line_str.strip())
