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
from .geometry import AffineMatrix2D, ViewportMapping, is_valid_point


def hex_to_pdf_color(hex_str: Optional[str], fallback: str = "#1E1E1E") -> colors.Color:
    """Converts a hex string (#RRGGBB) to a ReportLab Color with contrast safety."""
    if not isinstance(hex_str, str) or not hex_str.strip():
        target = fallback
    else:
        target = hex_str.strip()

    if not target.startswith("#"):
        target = "#" + target

    # Contrast safety check: if drawing on white background, don't draw pure white
    if target.lower() in ("#ffffff", "#fff"):
        return colors.HexColor(fallback)

    try:
        return colors.HexColor(target)
    except Exception:
        return colors.HexColor(fallback)


def sanitize_cad_text(text: str) -> str:
    """
    Cleans raw AutoCAD TEXT and MTEXT strings:
    - Removes formatting codes like \\f..., \\W..., \\H..., \\C..., \\Q...
    - Decodes AutoCAD inline escapes: %%u/%%U (underline), %%d/%%D (°), %%p/%%P (±), %%c/%%C (Ø), %%% (%)
    - Decodes CP1252/ISO-8859 superscript replacement characters (\\ufffd or \\u00b2) -> ²
    - Handles line breaks (\\P, \\p -> \\n)
    """
    if not text:
        return ""

    # Line break escapes
    txt = text.replace(r"\P", "\n").replace(r"\p", "\n")

    # AutoCAD inline special escapes
    txt = re.sub(r"%%[uU]", "", txt)  # Underline toggle
    txt = re.sub(r"%%[oO]", "", txt)  # Overline toggle
    txt = re.sub(r"%%[dD]", "\u00b0", txt)  # Degree symbol °
    txt = re.sub(r"%%[pP]", "\u00b1", txt)  # Plus-minus symbol ±
    txt = re.sub(r"%%[cC]", "\u00d8", txt)  # Diameter symbol Ø
    txt = txt.replace("%%%", "%")

    # MTEXT formatting codes: \f...;, \H...;, \W...;, \C...;, \Q...;, \T...;, \A...;
    txt = re.sub(r"\\[a-zA-Z][^;]*;", "", txt)
    txt = re.sub(r"\\[a-zA-Z~]", "", txt)

    # Braces grouping
    txt = txt.replace("{", "").replace("}", "").strip()

    # Unicode replacement character for superscript 2 (e.g. Area, m²)
    txt = txt.replace("\ufffd", "\u00b2")

    return txt


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
        """Determines entity color via preset mode (monochrome) -> entity override -> layer color -> fallback."""
        if self.preset.color_mode == "monochrome":
            return hex_to_pdf_color(self.preset.default_stroke_color, "#000000")
        if entity_color and entity_color.startswith("#"):
            return hex_to_pdf_color(entity_color, self.preset.default_stroke_color)
        if layer_name and layer_name in self.layer_colors:
            return hex_to_pdf_color(self.layer_colors[layer_name], self.preset.default_stroke_color)
        return hex_to_pdf_color(None, self.preset.default_stroke_color)

    def _set_font_safe(self, font_name: Optional[str], font_size: float) -> None:
        """Safely sets canvas font, falling back to Helvetica if font_name is invalid or unregistered."""
        target_font = font_name if (isinstance(font_name, str) and font_name.strip()) else "Helvetica"
        try:
            self.c.setFont(target_font, font_size)
        except Exception:
            try:
                self.c.setFont("Helvetica", font_size)
            except Exception:
                pass

    def draw_line(
        self,
        start: Any,
        end: Any,
        color: Optional[str] = None,
        layer: Optional[str] = None,
        line_width: Optional[float] = None,
        transform: Optional[AffineMatrix2D] = None,
    ) -> None:
        """Renders a single vector line segment."""
        if not is_valid_point(start) or not is_valid_point(end):
            return

        x0, y0 = float(start[0]), float(start[1])
        x1, y1 = float(end[0]), float(end[1])

        if transform:
            x0, y0 = transform.transform_point(x0, y0)
            x1, y1 = transform.transform_point(x1, y1)

        px0, py0 = self.vp.to_pdf(x0, y0)
        px1, py1 = self.vp.to_pdf(x1, y1)

        if not (math.isfinite(px0) and math.isfinite(py0) and math.isfinite(px1) and math.isfinite(py1)):
            return

        col = self.resolve_color(color, layer)
        lw = line_width if (isinstance(line_width, (int, float)) and not isinstance(line_width, bool) and math.isfinite(line_width) and line_width > 0) else self.default_line_width

        self.c.setStrokeColor(col)
        self.c.setLineWidth(lw)
        self.c.line(px0, py0, px1, py1)

    def draw_polyline(
        self,
        points: Any,
        is_closed: bool = False,
        color: Optional[str] = None,
        layer: Optional[str] = None,
        line_width: Optional[float] = None,
        transform: Optional[AffineMatrix2D] = None,
    ) -> None:
        """Renders a polyline path with native vector lines."""
        if not isinstance(points, (list, tuple)) or len(points) < 2:
            return

        transformed_pts: List[Tuple[float, float]] = []
        for pt in points:
            if not is_valid_point(pt):
                continue
            x, y = float(pt[0]), float(pt[1])
            if transform:
                x, y = transform.transform_point(x, y)
            px, py = self.vp.to_pdf(x, y)
            if math.isfinite(px) and math.isfinite(py):
                transformed_pts.append((px, py))

        if len(transformed_pts) < 2:
            return

        col = self.resolve_color(color, layer)
        lw = line_width if (isinstance(line_width, (int, float)) and not isinstance(line_width, bool) and math.isfinite(line_width) and line_width > 0) else self.default_line_width

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
        center: Any,
        radius: float,
        start_angle_deg: float,
        end_angle_deg: float,
        color: Optional[str] = None,
        layer: Optional[str] = None,
        line_width: Optional[float] = None,
        transform: Optional[AffineMatrix2D] = None,
    ) -> None:
        """Renders an arc converted into cubic Bézier segments."""
        if not is_valid_point(center):
            return
        if not isinstance(radius, (int, float)) or isinstance(radius, bool) or not math.isfinite(radius) or radius <= 0:
            return
        if not isinstance(start_angle_deg, (int, float)) or isinstance(start_angle_deg, bool) or not math.isfinite(start_angle_deg):
            return
        if not isinstance(end_angle_deg, (int, float)) or isinstance(end_angle_deg, bool) or not math.isfinite(end_angle_deg):
            return

        cx, cy = float(center[0]), float(center[1])
        start_pt, segments = arc_to_cubic_beziers(cx, cy, float(radius), float(start_angle_deg), float(end_angle_deg))
        if not segments:
            return

        # Apply transforms to Bézier control points
        def tx_pt(x: float, y: float) -> Tuple[float, float]:
            if transform:
                x, y = transform.transform_point(x, y)
            return self.vp.to_pdf(x, y)

        p0_pdf = tx_pt(start_pt[0], start_pt[1])
        if not (math.isfinite(p0_pdf[0]) and math.isfinite(p0_pdf[1])):
            return

        col = self.resolve_color(color, layer)
        lw = line_width if (isinstance(line_width, (int, float)) and not isinstance(line_width, bool) and math.isfinite(line_width) and line_width > 0) else self.default_line_width

        self.c.setStrokeColor(col)
        self.c.setLineWidth(lw)

        path = self.c.beginPath()
        path.moveTo(p0_pdf[0], p0_pdf[1])

        for cp1x, cp1y, cp2x, cp2y, endx, endy in segments:
            cp1_pdf = tx_pt(cp1x, cp1y)
            cp2_pdf = tx_pt(cp2x, cp2y)
            end_pdf = tx_pt(endx, endy)
            if all(math.isfinite(v) for v in (cp1_pdf[0], cp1_pdf[1], cp2_pdf[0], cp2_pdf[1], end_pdf[0], end_pdf[1])):
                path.curveTo(cp1_pdf[0], cp1_pdf[1], cp2_pdf[0], cp2_pdf[1], end_pdf[0], end_pdf[1])

        self.c.drawPath(path, stroke=1, fill=0)

    def draw_circle(
        self,
        center: Any,
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
        text: Any,
        position: Any,
        height: float,
        color: Optional[str] = None,
        layer: Optional[str] = None,
    ) -> None:
        """Renders text labels (e.g., room names, room numbers, elevation markers)."""
        if not text or not isinstance(text, str) or not is_valid_point(position):
            return

        clean = sanitize_cad_text(text)
        if not clean:
            return

        h = float(height) if (isinstance(height, (int, float)) and not isinstance(height, bool) and math.isfinite(height) and height > 0) else 250.0

        px, py = self.vp.to_pdf(float(position[0]), float(position[1]))
        if not (math.isfinite(px) and math.isfinite(py)):
            return

        # Font size proportional to CAD height scaled to PDF points, clamped to readable limits
        pdf_font_size = max(1.0, min(36.0, self.vp.to_pdf_length(h)))
        if not math.isfinite(pdf_font_size):
            pdf_font_size = 12.0

        col = self.resolve_color(color, layer)
        self.c.setFillColor(col)
        self._set_font_safe(getattr(self.preset, "font_name", "Helvetica"), pdf_font_size)

        # In AutoCAD MTEXT, the insertion point is Top-Left; shift downward to font baseline
        baseline_y = py - (pdf_font_size * 0.75)

        lines = clean.split("\n")
        line_spacing = pdf_font_size * 1.2
        for i, line_str in enumerate(lines):
            line_y = baseline_y - (i * line_spacing)
            if math.isfinite(line_y):
                self.c.drawString(px, line_y, line_str.strip())

    def draw_dimension_text(
        self,
        measurement: Any,
        defpoint: Any,
        defpoint2: Any,
        override_text: Optional[str] = None,
        color: Optional[str] = None,
        layer: Optional[str] = None,
    ) -> None:
        """Renders linear dimension measurement text centered along the dimension line."""
        if (
            measurement is None
            or not isinstance(measurement, (int, float))
            or isinstance(measurement, bool)
            or not math.isfinite(measurement)
            or measurement <= 0
            or not is_valid_point(defpoint)
            or not is_valid_point(defpoint2)
        ):
            return

        txt = sanitize_cad_text(override_text) if (override_text and isinstance(override_text, str)) else f"{round(float(measurement))}"
        if not txt:
            return

        dp0 = float(defpoint[0])
        dp1 = float(defpoint[1])
        dp20 = float(defpoint2[0])
        dp21 = float(defpoint2[1])

        dx = abs(dp0 - dp20)
        dy = abs(dp1 - dp21)

        # Dimension text scaled proportionally
        font_sz = max(1.0, min(14.0, self.vp.to_pdf_length(250.0)))
        if not math.isfinite(font_sz):
            font_sz = 10.0

        col = self.resolve_color(color, layer)
        self.c.setFillColor(col)
        self._set_font_safe(getattr(self.preset, "font_name", "Helvetica"), font_sz)

        if dx >= dy:
            # Horizontal dimension line: center above line
            mid_x = (dp0 + dp20) / 2.0
            mid_y = dp1 + 100.0
            px, py = self.vp.to_pdf(mid_x, mid_y)
            if math.isfinite(px) and math.isfinite(py):
                self.c.drawCentredString(px, py, txt)
        else:
            # Vertical dimension line: center and rotate 90 degrees
            mid_x = dp0 - 100.0
            mid_y = (dp1 + dp21) / 2.0
            px, py = self.vp.to_pdf(mid_x, mid_y)
            if math.isfinite(px) and math.isfinite(py):
                self.c.saveState()
                self.c.translate(px, py)
                self.c.rotate(90)
                self.c.drawCentredString(0, 0, txt)
                self.c.restoreState()

