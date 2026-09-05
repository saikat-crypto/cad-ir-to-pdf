"""
config.py — Preset and configuration architecture for CAD IR to PDF compiler.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# PostScript points per unit (1 inch = 72 pt, 1 mm = 72 / 25.4 pt = 2.83464567 pt)
PT_PER_MM = 72.0 / 25.4
PT_PER_INCH = 72.0

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
    default_line_width_pt: float = 0.35  # Base line weight in points (clean blueprint weight)
    background_color: Optional[str] = "#FFFFFF"  # White page background
    default_stroke_color: str = "#000000"        # Crisp architectural black
    color_mode: str = "monochrome"       # "monochrome" (pure black plot), "layer_color", or "true_color"
    draw_annotations: bool = True        # Render text annotations / room labels
    draw_components: bool = True         # Render block instances
    draw_dimensions: bool = True         # Render dimension blocks and measurement text
    prune_outliers: bool = True          # Automatically prune isolated scratch geometry voids
    custom_bbox: Optional[Tuple[float, float, float, float]] = None  # (min_x, min_y, max_x, max_y)
    font_name: str = "Helvetica"         # Standard PDF embedded sans-serif font

    def get_page_dimensions_pt(self) -> Tuple[float, float]:
        """Returns (width_pt, height_pt) taking orientation into account."""
        base_size = PAGE_SIZES_PORTRAIT.get(self.paper_size.upper())
        if not base_size:
            base_size = PAGE_SIZES_PORTRAIT["A3"]
        w, h = base_size
        if self.orientation.lower() == "landscape":
            return (max(w, h), min(w, h))
        return (min(w, h), max(w, h))

    @property
    def margin_pt(self) -> float:
        return self.margin_mm * PT_PER_MM

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
