"""
renderer.py — High-fidelity ReportLab vector canvas renderer for CAD entities.
"""

from __future__ import annotations
import math
import re
from typing import Any, Dict, List, Optional, Tuple
from reportlab.pdfgen import canvas
from reportlab.lib import colors

import json
from .config import (
    DEFAULT_FONT_NAME,
    DEFAULT_LINE_WIDTH_PT,
    MAX_FONT_SIZE_PT,
    MAX_LINE_WIDTH_PT,
    MIN_FONT_SIZE_PT,
    MIN_LINE_WIDTH_PT,
    PdfPreset,
)
from .curves import arc_to_cubic_beziers, circle_to_cubic_beziers
from .geometry import AffineMatrix2D, ViewportMapping, is_valid_point

_HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _clean_hex(val: Any) -> Optional[str]:
    """Validates and normalizes hex strings into standard #RRGGBB format."""
    if not isinstance(val, str):
        return None
    s = val.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3 and re.fullmatch(r"[0-9a-fA-F]{3}", s):
        s = "".join(c * 2 for c in s)
    elif len(s) == 8 and re.fullmatch(r"[0-9a-fA-F]{8}", s):
        s = s[:6]
    if len(s) == 6 and re.fullmatch(r"[0-9a-fA-F]{6}", s):
        return "#" + s.upper()
    return None


def _hex_luminance(hex_str: Optional[str]) -> float:
    """Computes standard Rec. 709 relative luminance for a normalized #RRGGBB hex color."""
    if not hex_str or not hex_str.startswith("#") or len(hex_str) != 7:
        return 0.0
    try:
        r = int(hex_str[1:3], 16) / 255.0
        g = int(hex_str[3:5], 16) / 255.0
        b = int(hex_str[5:7], 16) / 255.0
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    except Exception:
        return 0.0


def hex_to_pdf_color(
    hex_str: Any,
    fallback: str = "#000000",
    background_hex: Optional[str] = "#FFFFFF",
    bg_color: Optional[str] = None,
) -> colors.Color:
    """
    Feature 12: Converts a hex string (#RRGGBB, #RGB, RRGGBB, RGB, #RRGGBBAA) to a ReportLab Color.

    Crash-proof guarantees:
    - Never raises an unhandled exception regardless of input type, malformed hex, or corrupted fallback.
    - If fallback is invalid, corrupted, or raises an error, safely falls back to reportlab.lib.colors.black.

    Contrast safety:
    - On light backgrounds (or default white #FFFFFF), pure white strokes (#FFFFFF, #FFF)
      are remapped to `fallback` (or dark contrast color) to ensure vector visibility.
    - On dark backgrounds, near-black strokes are remapped to #FFFFFF to ensure visibility.
    """
    fb_clean = _clean_hex(fallback) or "#000000"

    target_clean = _clean_hex(hex_str)
    if not target_clean:
        target_clean = fb_clean

    bg = bg_color if bg_color is not None else background_hex
    bg_clean = _clean_hex(bg)
    bg_lum = _hex_luminance(bg_clean) if bg_clean else 1.0

    target_lum = _hex_luminance(target_clean)

    # Background-aware contrast safety check:
    if bg_clean and bg_lum < 0.2:
        # Dark background: prevent invisible dark strokes on dark bg
        if target_lum <= 0.1 or target_clean in ("#000000", "#000"):
            target_clean = "#FFFFFF"
    else:
        # Light background (or default white): prevent invisible white strokes on white bg
        if (target_clean in ("#FFFFFF", "#FFF") or target_lum > 0.95) and fb_clean not in ("#FFFFFF", "#FFF"):
            target_clean = fb_clean
        elif (target_clean in ("#FFFFFF", "#FFF") or target_lum > 0.95) and bg_clean and bg_lum >= 0.8:
            target_clean = "#000000"

    try:
        return colors.HexColor(target_clean)
    except Exception:
        try:
            return colors.HexColor(fb_clean)
        except Exception:
            return colors.black


def sanitize_metadata_string(val: Any, default: str = "") -> str:
    """
    Feature 11: Safely converts arbitrary metadata values to clean, printable strings.
    Prevents ReportLab PDFString crashes on non-string/None/dict/list/int inputs.
    Strips null bytes and C0 control characters, capping length to 1024 chars.
    """
    if val is None:
        return default
    if isinstance(val, float) and not math.isfinite(val):
        return default
    if not isinstance(val, str):
        if isinstance(val, bytes):
            try:
                val = val.decode("utf-8", errors="replace")
            except Exception:
                return default
        elif isinstance(val, (dict, list, tuple)):
            try:
                val = json.dumps(val, ensure_ascii=False)
            except Exception:
                try:
                    val = str(val)
                except Exception:
                    return default
        else:
            try:
                val = str(val)
            except Exception:
                return default

    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", val).strip()
    return cleaned[:1024] if cleaned else default


coerce_metadata_str = sanitize_metadata_string


def sanitize_line_width(
    line_width: Any,
    default: float = DEFAULT_LINE_WIDTH_PT,
    min_width: float = MIN_LINE_WIDTH_PT,
    max_width: float = MAX_LINE_WIDTH_PT,
) -> float:
    """
    Feature 13: Sanitizes and clamps stroke line widths in PostScript points to [0.05, 50.0] pt.
    Falls back to safe default if non-numeric, boolean, non-finite, or <= 0.
    """
    if (
        default is None
        or not isinstance(default, (int, float))
        or isinstance(default, bool)
        or not math.isfinite(default)
        or default <= 0
    ):
        safe_default = DEFAULT_LINE_WIDTH_PT
    else:
        safe_default = max(min_width, min(max_width, float(default)))

    if (
        line_width is None
        or not isinstance(line_width, (int, float))
        or isinstance(line_width, bool)
        or not math.isfinite(line_width)
        or line_width <= 0
    ):
        return safe_default

    return max(min_width, min(max_width, float(line_width)))


def sanitize_cad_text(text: Any) -> str:
    """
    Cleans raw AutoCAD TEXT and MTEXT strings:
    - Removes formatting codes like \\f..., \\W..., \\H..., \\C..., \\Q...
    - Decodes AutoCAD inline escapes: %%u/%%U (underline), %%d/%%D (°), %%p/%%P (±), %%c/%%C (Ø), %%% (%)
    - Decodes CP1252/ISO-8859 superscript replacement characters (\\ufffd or \\u00b2) -> ²
    - Handles line breaks (\\P, \\p -> \\n)
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return ""
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

    # Strip null bytes and C0 control characters except \n (newline) and \t (tab)
    txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", txt)

    return txt


class PdfVectorRenderer:
    """Draws CAD primitives and annotations onto a ReportLab Canvas in PostScript point space."""

    def __init__(
        self,
        pdf_canvas: canvas.Canvas,
        viewport: ViewportMapping,
        preset: PdfPreset,
        layer_color_map: Optional[Dict[str, str]] = None,
        warning_collector: Optional[List[Any]] = None,
    ):
        self.c = pdf_canvas
        self.vp = viewport
        self.preset = preset
        self.layer_colors = layer_color_map or {}
        self.warning_collector = warning_collector
        raw_lw = getattr(preset, "default_line_width_pt", DEFAULT_LINE_WIDTH_PT)
        self.default_line_width = sanitize_line_width(raw_lw, default=DEFAULT_LINE_WIDTH_PT)

    def sanitize_line_width(self, line_width: Any, default: Optional[float] = None) -> float:
        """Sanitizes and clamps line width to [MIN_LINE_WIDTH_PT, MAX_LINE_WIDTH_PT] pt (Feature 13)."""
        def_lw = self.default_line_width if default is None else default
        return sanitize_line_width(line_width, default=def_lw)

    def sanitize_font_size(self, size: Any, default: float = 12.0) -> float:
        """Sanitizes and clamps font size to [MIN_FONT_SIZE_PT, MAX_FONT_SIZE_PT] pt (Feature 14)."""
        if size is None or isinstance(size, bool):
            return default
        try:
            val = float(size)
            if not math.isfinite(val) or val <= 0.0:
                return default
            return max(MIN_FONT_SIZE_PT, min(MAX_FONT_SIZE_PT, val))
        except (OverflowError, TypeError, ValueError):
            return default

    def set_document_metadata(
        self,
        title: Any = None,
        author: Any = None,
        subject: Any = None,
        creator: Optional[str] = "cad-ir-to-pdf (La Vinci CAD Compiler)",
    ) -> None:
        """Safely sets PDF document metadata properties on the underlying ReportLab canvas (Feature 11)."""
        safe_title = sanitize_metadata_string(title, default="La Vinci CAD Drawing")
        safe_author = sanitize_metadata_string(author, default="La Vinci Engine")
        safe_creator = sanitize_metadata_string(creator, default="cad-ir-to-pdf (La Vinci CAD Compiler)")

        try:
            self.c.setTitle(safe_title)
        except Exception:
            try:
                self.c.setTitle("La Vinci CAD Drawing")
            except Exception:
                pass

        try:
            self.c.setAuthor(safe_author)
        except Exception:
            try:
                self.c.setAuthor("La Vinci Engine")
            except Exception:
                pass

        try:
            self.c.setCreator(safe_creator)
        except Exception:
            pass

        if subject is not None:
            safe_subj = sanitize_metadata_string(subject, default="")
            if safe_subj:
                try:
                    self.c.setSubject(safe_subj)
                except Exception:
                    pass

    def resolve_color(self, entity_color: Optional[str], layer_name: Optional[str]) -> colors.Color:
        """Determines entity color via preset mode (monochrome) -> entity override -> layer color -> fallback (Feature 12)."""
        bg = getattr(self.preset, "background_color", "#FFFFFF")
        default_stroke = getattr(self.preset, "default_stroke_color", "#000000")

        if getattr(self.preset, "color_mode", "monochrome") == "monochrome":
            return hex_to_pdf_color(default_stroke, fallback="#000000", background_hex=bg)

        # Check entity override with type check
        if isinstance(entity_color, str) and entity_color.strip() and entity_color.strip().upper() not in ("BYLAYER", "BYBLOCK"):
            clean_ent = _clean_hex(entity_color)
            if clean_ent:
                return hex_to_pdf_color(clean_ent, fallback=default_stroke, background_hex=bg)

        # Check layer color with type check
        if isinstance(layer_name, str) and layer_name in self.layer_colors:
            raw_layer_color = self.layer_colors[layer_name]
            clean_layer = _clean_hex(raw_layer_color)
            if clean_layer:
                return hex_to_pdf_color(clean_layer, fallback=default_stroke, background_hex=bg)

        return hex_to_pdf_color(None, fallback=default_stroke, background_hex=bg)

    def _set_font_safe(self, font_name: Optional[str], font_size: Any) -> float:
        """
        Safely sets canvas font, falling back to Helvetica if font_name is invalid or unregistered.
        Sanitizes and clamps font size to [1.0, 144.0] pt (Feature 14 / INV-19). Returns safe_size.
        """
        safe_size = self.sanitize_font_size(font_size, default=12.0)
        target_font = font_name.strip() if (isinstance(font_name, str) and font_name.strip()) else DEFAULT_FONT_NAME
        try:
            self.c.setFont(target_font, safe_size)
        except Exception:
            try:
                self.c.setFont(DEFAULT_FONT_NAME, safe_size)
            except Exception:
                pass
        return safe_size

    def draw_line(
        self,
        start: Any,
        end: Any,
        color: Optional[str] = None,
        layer: Optional[str] = None,
        line_width: Optional[float] = None,
        transform: Optional[AffineMatrix2D] = None,
    ) -> None:
        """Renders a single vector line segment. Drops zero-length lines (Feature 15 / INV-06)."""
        if not is_valid_point(start) or not is_valid_point(end):
            return

        x0, y0 = float(start[0]), float(start[1])
        x1, y1 = float(end[0]), float(end[1])

        # Feature 15 (INV-06): Drop zero-length line in CAD coordinate space
        try:
            if math.hypot(x1 - x0, y1 - y0) < 1e-6:
                return
        except OverflowError:
            pass

        if transform:
            x0, y0 = transform.transform_point(x0, y0)
            x1, y1 = transform.transform_point(x1, y1)

            # Re-check in transformed world space
            try:
                if math.hypot(x1 - x0, y1 - y0) < 1e-6:
                    return
            except OverflowError:
                pass

        px0, py0 = self.vp.to_pdf(x0, y0)
        px1, py1 = self.vp.to_pdf(x1, y1)

        if not (math.isfinite(px0) and math.isfinite(py0) and math.isfinite(px1) and math.isfinite(py1)):
            return

        # Feature 15 (INV-06): Drop zero-length line in PDF point space to emit zero redundant operators
        try:
            if math.hypot(px1 - px0, py1 - py0) < 1e-6:
                return
        except OverflowError:
            pass

        col = self.resolve_color(color, layer)
        lw = self.sanitize_line_width(line_width)

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
        """Renders a polyline path with native vector lines. Filters coincident vertices (Feature 15)."""
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

        # Filter consecutive coincident points (< 1e-6 pt) to avoid redundant zero-length lineTo operators
        filtered_pts: List[Tuple[float, float]] = []
        for p in transformed_pts:
            if not filtered_pts or math.hypot(p[0] - filtered_pts[-1][0], p[1] - filtered_pts[-1][1]) >= 1e-6:
                filtered_pts.append(p)

        if len(filtered_pts) > 2 and is_closed and math.hypot(filtered_pts[-1][0] - filtered_pts[0][0], filtered_pts[-1][1] - filtered_pts[0][1]) < 1e-6:
            filtered_pts.pop()

        if len(filtered_pts) < 2:
            return

        col = self.resolve_color(color, layer)
        lw = self.sanitize_line_width(line_width)

        self.c.setStrokeColor(col)
        self.c.setLineWidth(lw)

        path = self.c.beginPath()
        path.moveTo(filtered_pts[0][0], filtered_pts[0][1])
        for p in filtered_pts[1:]:
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
        """Renders an arc converted into cubic Bézier segments. Drops zero/negative radius & zero sweeps (Feature 16)."""
        if not is_valid_point(center):
            return
        # Feature 16: Zero/Negative/Non-finite radius dropping
        if not isinstance(radius, (int, float)) or isinstance(radius, bool) or not math.isfinite(radius) or radius <= 0:
            return
        if not isinstance(start_angle_deg, (int, float)) or isinstance(start_angle_deg, bool) or not math.isfinite(start_angle_deg):
            return
        if not isinstance(end_angle_deg, (int, float)) or isinstance(end_angle_deg, bool) or not math.isfinite(end_angle_deg):
            return

        # Zero-sweep arc check (INV-08)
        if abs(float(end_angle_deg) - float(start_angle_deg)) < 1e-6:
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

        # Validate all segment points and verify non-degenerate extent on PDF canvas
        transformed_segments: List[Tuple[float, float, float, float, float, float]] = []
        is_degenerate = True
        for cp1x, cp1y, cp2x, cp2y, endx, endy in segments:
            cp1_pdf = tx_pt(cp1x, cp1y)
            cp2_pdf = tx_pt(cp2x, cp2y)
            end_pdf = tx_pt(endx, endy)
            if not all(math.isfinite(v) for v in (cp1_pdf[0], cp1_pdf[1], cp2_pdf[0], cp2_pdf[1], end_pdf[0], end_pdf[1])):
                return
            if (
                math.hypot(cp1_pdf[0] - p0_pdf[0], cp1_pdf[1] - p0_pdf[1]) >= 1e-6
                or math.hypot(cp2_pdf[0] - p0_pdf[0], cp2_pdf[1] - p0_pdf[1]) >= 1e-6
                or math.hypot(end_pdf[0] - p0_pdf[0], end_pdf[1] - p0_pdf[1]) >= 1e-6
            ):
                is_degenerate = False
            transformed_segments.append((cp1_pdf[0], cp1_pdf[1], cp2_pdf[0], cp2_pdf[1], end_pdf[0], end_pdf[1]))

        if is_degenerate or not transformed_segments:
            return

        col = self.resolve_color(color, layer)
        lw = self.sanitize_line_width(line_width)

        self.c.setStrokeColor(col)
        self.c.setLineWidth(lw)

        path = self.c.beginPath()
        path.moveTo(p0_pdf[0], p0_pdf[1])

        for cp1_pdf_x, cp1_pdf_y, cp2_pdf_x, cp2_pdf_y, end_pdf_x, end_pdf_y in transformed_segments:
            path.curveTo(cp1_pdf_x, cp1_pdf_y, cp2_pdf_x, cp2_pdf_y, end_pdf_x, end_pdf_y)

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
        """Renders a 360-degree circle. Drops zero, negative, or non-finite radius (Feature 16)."""
        if not is_valid_point(center):
            return
        if not isinstance(radius, (int, float)) or isinstance(radius, bool) or not math.isfinite(radius) or radius <= 0:
            return
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
        """Renders text labels. Clamps font size to [1.0, 144.0] pt (Feature 14 / INV-19)."""
        if text is None or not is_valid_point(position):
            return

        clean = sanitize_cad_text(text)
        if not clean or not clean.strip():
            return

        h = float(height) if (isinstance(height, (int, float)) and not isinstance(height, bool) and math.isfinite(height) and height > 0) else 250.0

        px, py = self.vp.to_pdf(float(position[0]), float(position[1]))
        if not (math.isfinite(px) and math.isfinite(py)):
            return

        # Font size proportional to CAD height scaled to PDF points, clamped to [1.0, 144.0] pt
        raw_sz = self.vp.to_pdf_length(h) if (isinstance(h, (int, float)) and not isinstance(h, bool) and math.isfinite(h) and h > 0) else 12.0
        pdf_font_size = self.sanitize_font_size(raw_sz, default=12.0)

        col = self.resolve_color(color, layer)
        self.c.setFillColor(col)
        actual_font_size = self._set_font_safe(getattr(self.preset, "font_name", DEFAULT_FONT_NAME), pdf_font_size)

        # In AutoCAD MTEXT, the insertion point is Top-Left; shift downward to font baseline
        baseline_y = py - (actual_font_size * 0.75)

        lines = clean.split("\n")
        line_spacing = actual_font_size * 1.2
        for i, line_str in enumerate(lines):
            stripped = line_str.strip()
            if not stripped:
                continue
            line_y = baseline_y - (i * line_spacing)
            if math.isfinite(line_y):
                self.c.drawString(px, line_y, stripped)

    def draw_dimension_text(
        self,
        measurement: Any,
        defpoint: Any,
        defpoint2: Any,
        override_text: Optional[str] = None,
        color: Optional[str] = None,
        layer: Optional[str] = None,
    ) -> None:
        """Renders linear dimension measurement text centered along the dimension line (Feature 14)."""
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
        if not txt or not txt.strip():
            return

        dp0 = float(defpoint[0])
        dp1 = float(defpoint[1])
        dp20 = float(defpoint2[0])
        dp21 = float(defpoint2[1])

        dx = abs(dp0 - dp20)
        dy = abs(dp1 - dp21)

        # Dimension text scaled proportionally, clamped to [1.0, 144.0] pt
        raw_size = self.vp.to_pdf_length(250.0)
        font_sz = self.sanitize_font_size(raw_size, default=10.0)

        col = self.resolve_color(color, layer)
        self.c.setFillColor(col)
        self._set_font_safe(getattr(self.preset, "font_name", DEFAULT_FONT_NAME), font_sz)

        if dx >= dy:
            # Horizontal dimension line: center above line
            mid_x = (dp0 + dp20) / 2.0
            mid_y = dp1 + 100.0
            px, py = self.vp.to_pdf(mid_x, mid_y)
            if math.isfinite(px) and math.isfinite(py):
                self.c.drawCentredString(px, py, txt.strip())
        else:
            # Vertical dimension line: center and rotate 90 degrees
            mid_x = dp0 - 100.0
            mid_y = (dp1 + dp21) / 2.0
            px, py = self.vp.to_pdf(mid_x, mid_y)
            if math.isfinite(px) and math.isfinite(py):
                self.c.saveState()
                self.c.translate(px, py)
                self.c.rotate(90)
                self.c.drawCentredString(0, 0, txt.strip())
                self.c.restoreState()

