"""
config.py — Preset and configuration architecture for CAD IR to PDF compiler.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# PostScript points per unit (1 inch = 72 pt, 1 mm = 72 / 25.4 pt = 2.83464567 pt)
PT_PER_MM = 72.0 / 25.4
PT_PER_INCH = 72.0

# Line weight clamping bounds in PostScript points (Feature 13 / INV-18)
MIN_LINE_WIDTH_PT: float = 0.05
MAX_LINE_WIDTH_PT: float = 50.0
DEFAULT_LINE_WIDTH_PT: float = 0.35

# Font size clamping bounds in PostScript points (Feature 14 / INV-19)
MIN_FONT_SIZE_PT: float = 1.0
MAX_FONT_SIZE_PT: float = 144.0
DEFAULT_FONT_NAME: str = "Helvetica"

# Standard Paper Sizes in Points (Width x Height, Portrait)
PAGE_SIZES_PORTRAIT: Dict[str, Tuple[float, float]] = {
    "A4": (210.0 * PT_PER_MM, 297.0 * PT_PER_MM),      # 595.28 x 841.89 pt
    "A3": (297.0 * PT_PER_MM, 420.0 * PT_PER_MM),      # 841.89 x 1190.55 pt
    "A2": (420.0 * PT_PER_MM, 594.0 * PT_PER_MM),      # 1190.55 x 1683.78 pt
    "A1": (594.0 * PT_PER_MM, 841.0 * PT_PER_MM),      # 1683.78 x 2383.94 pt
    "A0": (841.0 * PT_PER_MM, 1189.0 * PT_PER_MM),     # 2383.94 x 3370.39 pt
    "LETTER": (8.5 * PT_PER_INCH, 11.0 * PT_PER_INCH), # 612.0 x 792.0 pt
    "ARCH_D": (24.0 * PT_PER_INCH, 36.0 * PT_PER_INCH),# 1728.0 x 2592.0 pt
}

@dataclass
class PdfPreset:
    """Configuration preset for rendering CAD IR to a PDF document."""
    name: str = "monochrome-architectural"
    paper_size: str = "A3"
    orientation: str = "landscape"       # "landscape" or "portrait"
    target_space: str = "Model"          # "Model" (focus on building) or "all"
    margin_mm: float = 12.0              # Border margin
    scale_mode: str = "fit"              # "fit" (isotropic auto-fit) or "fixed"
    fixed_scale: Optional[float] = None  # e.g., 0.02 for 1:50
    default_line_width_pt: float = DEFAULT_LINE_WIDTH_PT  # Base line weight in points (clean blueprint weight)
    background_color: Optional[str] = "#FFFFFF"  # White page background
    default_stroke_color: str = "#000000"        # Crisp architectural black
    color_mode: str = "monochrome"       # "monochrome" (pure black plot), "layer_color", or "true_color"
    draw_annotations: bool = True        # Render text annotations / room labels
    draw_components: bool = True         # Render block instances
    draw_dimensions: bool = True         # Render dimension blocks and measurement text
    prune_outliers: bool = True          # Automatically prune isolated scratch geometry voids
    custom_bbox: Optional[Tuple[float, float, float, float]] = None  # (min_x, min_y, max_x, max_y)
    font_name: str = DEFAULT_FONT_NAME   # Standard PDF embedded sans-serif font

    def __post_init__(self) -> None:
        """Sanitizes preset fields against malformed or whitespace inputs (Feature 14)."""
        if not isinstance(self.font_name, str) or not self.font_name.strip():
            self.font_name = DEFAULT_FONT_NAME
        else:
            self.font_name = self.font_name.strip()

    def get_page_dimensions_pt(self) -> Tuple[float, float]:
        """Returns (width_pt, height_pt) taking orientation into account, safely handling non-string/None."""
        paper_key = "A3"
        if isinstance(self.paper_size, str) and self.paper_size.strip():
            paper_key = self.paper_size.strip().upper()
        base_size = PAGE_SIZES_PORTRAIT.get(paper_key, PAGE_SIZES_PORTRAIT["A3"])
        w, h = base_size
        orient = self.orientation.lower().strip() if isinstance(self.orientation, str) else "landscape"
        if orient == "landscape":
            return (max(w, h), min(w, h))
        return (min(w, h), max(w, h))

    @property
    def margin_pt(self) -> float:
        """Returns margin in points, guarded against non-finite, negative, or non-numeric margin_mm."""
        mm = self.margin_mm
        if not isinstance(mm, (int, float)) or isinstance(mm, bool):
            mm = 12.0
        try:
            f = float(mm)
            if not math.isfinite(f) or f < 0.0:
                f = 12.0
            return max(0.0, min(100.0, f)) * PT_PER_MM
        except (OverflowError, TypeError, ValueError):
            return 12.0 * PT_PER_MM

# Canonical Master Presets
ARCHITECTURAL_MONOCHROME_PRESET = PdfPreset(
    name="monochrome-architectural",
    paper_size="A3",
    orientation="landscape",
    target_space="Model",
    margin_mm=12.0,
    scale_mode="fit",
    default_line_width_pt=0.35,
    background_color="#FFFFFF",
    default_stroke_color="#000000",
    color_mode="monochrome",
    draw_annotations=True,
    draw_components=True,
    draw_dimensions=True,
    prune_outliers=True,
)

PRESENTATION_COLOR_PRESET = PdfPreset(
    name="presentation-fit-vector",
    paper_size="A3",
    orientation="landscape",
    target_space="Model",
    margin_mm=12.0,
    scale_mode="fit",
    default_line_width_pt=0.5,
    background_color="#FFFFFF",
    default_stroke_color="#1A1A1A",
    color_mode="layer_color",
    draw_annotations=True,
    draw_components=True,
    draw_dimensions=True,
    prune_outliers=True,
)

DEFAULT_PRESET = ARCHITECTURAL_MONOCHROME_PRESET

PRESETS: Dict[str, PdfPreset] = {
    "monochrome-architectural": ARCHITECTURAL_MONOCHROME_PRESET,
    "presentation-fit-vector": PRESENTATION_COLOR_PRESET,
    "quick-preview-a4": PdfPreset(
        name="quick-preview-a4",
        paper_size="A4",
        orientation="landscape",
        target_space="Model",
        margin_mm=8.0,
        default_line_width_pt=0.35,
        color_mode="monochrome",
        draw_dimensions=True,
        prune_outliers=True,
    ),
    "permit-arch-d": PdfPreset(
        name="permit-arch-d",
        paper_size="ARCH_D",
        orientation="landscape",
        target_space="Model",
        margin_mm=25.4,
        default_line_width_pt=0.5,
        color_mode="monochrome",
        draw_dimensions=True,
        prune_outliers=True,
    ),
}
