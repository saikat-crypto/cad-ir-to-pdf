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
    "LEGAL": (8.5 * PT_PER_INCH, 14.0 * PT_PER_INCH),  # 612.0 x 1008.0 pt
    "TABLOID": (11.0 * PT_PER_INCH, 17.0 * PT_PER_INCH), # 792.0 x 1224.0 pt (ANSI B)
    "ARCH_C": (18.0 * PT_PER_INCH, 24.0 * PT_PER_INCH),# 1296.0 x 1728.0 pt
    "ARCH_D": (24.0 * PT_PER_INCH, 36.0 * PT_PER_INCH),# 1728.0 x 2592.0 pt
    "ARCH_E": (36.0 * PT_PER_INCH, 48.0 * PT_PER_INCH),# 2592.0 x 3456.0 pt
}

@dataclass
class PdfOptions:
    """
    Advanced customization options to surgically override baseline PdfPreset properties.
    Any property set to None inherits directly from the active preset.
    """
    paper_size: Optional[str] = None
    orientation: Optional[str] = None
    target_space: Optional[str] = None
    margin_mm: Optional[float] = None
    scale_mode: Optional[str] = None
    fixed_scale: Optional[float] = None
    default_line_width_pt: Optional[float] = None
    line_weight_multiplier: Optional[float] = None
    background_color: Optional[str] = None
    default_stroke_color: Optional[str] = None
    color_mode: Optional[str] = None
    draw_annotations: Optional[bool] = None
    draw_components: Optional[bool] = None
    draw_dimensions: Optional[bool] = None
    prune_outliers: Optional[bool] = None
    custom_bbox: Optional[Tuple[float, float, float, float]] = None
    font_name: Optional[str] = None
    visible_layers: Optional[List[str]] = None
    hidden_layers: Optional[List[str]] = None
    watermark_text: Optional[str] = None
    screening: Optional[float] = None


@dataclass
class PdfPreset:
    """Configuration preset for rendering CAD IR to a PDF document."""
    name: str = "monochrome-arch"
    paper_size: str = "A3"
    orientation: str = "landscape"       # "landscape" or "portrait"
    target_space: str = "Model"          # "Model" (focus on building) or "all"
    margin_mm: float = 12.0              # Border margin
    scale_mode: str = "fit"              # "fit" (isotropic auto-fit) or "fixed"
    fixed_scale: Optional[float] = None  # e.g., 0.02 for 1:50
    default_line_width_pt: float = DEFAULT_LINE_WIDTH_PT  # Base line weight in points
    line_weight_multiplier: float = 1.0  # Scales all entity stroke weights
    background_color: Optional[str] = "#FFFFFF"  # White page background
    default_stroke_color: str = "#000000"        # Crisp architectural black
    color_mode: str = "monochrome"       # "monochrome", "layer_color", or "true_color"
    draw_annotations: bool = True        # Render text annotations / room labels
    draw_components: bool = True         # Render block instances
    draw_dimensions: bool = True         # Render dimension blocks and measurement text
    prune_outliers: bool = True          # Automatically prune isolated scratch geometry voids
    custom_bbox: Optional[Tuple[float, float, float, float]] = None  # (min_x, min_y, max_x, max_y)
    font_name: str = DEFAULT_FONT_NAME   # Standard PDF embedded sans-serif font
    visible_layers: Optional[List[str]] = None  # Whitelist of layers to draw (None = all)
    hidden_layers: Optional[List[str]] = None   # Blacklist of layers to suppress
    watermark_text: Optional[str] = None        # Semi-transparent diagonal watermark
    screening: float = 1.0                      # Stroke screening/opacity (0.0 to 1.0)
    description: str = ""                       # Human-readable preset purpose

    def __post_init__(self) -> None:
        """Sanitizes preset fields against malformed or whitespace inputs (Feature 14)."""
        if not isinstance(self.font_name, str) or not self.font_name.strip():
            self.font_name = DEFAULT_FONT_NAME
        else:
            self.font_name = self.font_name.strip()

    def with_options(self, options: Optional[Union[PdfOptions, Dict[str, Any]]]) -> PdfPreset:
        """
        Returns a new PdfPreset with surgical overrides applied from PdfOptions or dict.
        Guarantees non-mutating copy.
        """
        if options is None:
            return self

        # Extract dictionary of overrides
        if isinstance(options, PdfOptions):
            opts_dict = {k: v for k, v in options.__dict__.items() if v is not None}
        elif isinstance(options, dict):
            opts_dict = {k: v for k, v in options.items() if v is not None}
        else:
            return self

        kwargs = {
            "name": self.name,
            "paper_size": opts_dict.get("paper_size", self.paper_size),
            "orientation": opts_dict.get("orientation", self.orientation),
            "target_space": opts_dict.get("target_space", self.target_space),
            "margin_mm": opts_dict.get("margin_mm", self.margin_mm),
            "scale_mode": opts_dict.get("scale_mode", self.scale_mode),
            "fixed_scale": opts_dict.get("fixed_scale", self.fixed_scale),
            "default_line_width_pt": opts_dict.get("default_line_width_pt", self.default_line_width_pt),
            "line_weight_multiplier": opts_dict.get("line_weight_multiplier", self.line_weight_multiplier),
            "background_color": opts_dict.get("background_color", self.background_color),
            "default_stroke_color": opts_dict.get("default_stroke_color", self.default_stroke_color),
            "color_mode": opts_dict.get("color_mode", self.color_mode),
            "draw_annotations": opts_dict.get("draw_annotations", self.draw_annotations),
            "draw_components": opts_dict.get("draw_components", self.draw_components),
            "draw_dimensions": opts_dict.get("draw_dimensions", self.draw_dimensions),
            "prune_outliers": opts_dict.get("prune_outliers", self.prune_outliers),
            "custom_bbox": opts_dict.get("custom_bbox", self.custom_bbox),
            "font_name": opts_dict.get("font_name", self.font_name),
            "visible_layers": opts_dict.get("visible_layers", self.visible_layers),
            "hidden_layers": opts_dict.get("hidden_layers", self.hidden_layers),
            "watermark_text": opts_dict.get("watermark_text", self.watermark_text),
            "screening": opts_dict.get("screening", self.screening),
            "description": self.description,
        }
        return PdfPreset(**kwargs)

    def is_layer_visible(self, layer_name: Optional[str]) -> bool:
        """Determines if a given CAD layer should be rendered based on visibility filters."""
        if not layer_name:
            return True
        lyr = str(layer_name).strip()
        if self.hidden_layers:
            # Case-insensitive check
            hidden_norm = {h.lower().strip() for h in self.hidden_layers if isinstance(h, str)}
            if lyr.lower() in hidden_norm:
                return False
        if self.visible_layers:
            visible_norm = {v.lower().strip() for v in self.visible_layers if isinstance(v, str)}
            return lyr.lower() in visible_norm
        return True

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


# --- Canonical Ready-Made Output Presets ---

MONOCHROME_ARCHITECTURAL_PRESET = PdfPreset(
    name="monochrome-arch",
    paper_size="A3",
    orientation="landscape",
    target_space="Model",
    margin_mm=12.0,
    scale_mode="fit",
    default_line_width_pt=0.35,
    line_weight_multiplier=1.0,
    background_color="#FFFFFF",
    default_stroke_color="#000000",
    color_mode="monochrome",
    draw_annotations=True,
    draw_components=True,
    draw_dimensions=True,
    prune_outliers=True,
    description="Standard architectural blueprint. High-contrast crisp black linework on A3 white paper.",
)

PERMIT_ARCH_D_PRESET = PdfPreset(
    name="permit-arch-d",
    paper_size="ARCH_D",
    orientation="landscape",
    target_space="Model",
    margin_mm=25.4,
    default_line_width_pt=0.5,
    line_weight_multiplier=1.1,
    background_color="#FFFFFF",
    default_stroke_color="#000000",
    color_mode="monochrome",
    draw_annotations=True,
    draw_components=True,
    draw_dimensions=True,
    prune_outliers=True,
    description="Full-size US municipal permit plan set on 24x36 inch ARCH D sheet with 1-inch binding margins.",
)

METRIC_CONSTRUCTION_A1_PRESET = PdfPreset(
    name="metric-construction-a1",
    paper_size="A1",
    orientation="landscape",
    target_space="Model",
    margin_mm=15.0,
    default_line_width_pt=0.40,
    line_weight_multiplier=1.0,
    background_color="#FFFFFF",
    default_stroke_color="#000000",
    color_mode="monochrome",
    draw_annotations=True,
    draw_components=True,
    draw_dimensions=True,
    prune_outliers=True,
    description="Standard ISO A1 metric construction site drawing for Europe, Asia, and international projects.",
)

PRESENTATION_COLOR_PRESET = PdfPreset(
    name="presentation-color",
    paper_size="A3",
    orientation="landscape",
    target_space="Model",
    margin_mm=12.0,
    scale_mode="fit",
    default_line_width_pt=0.5,
    line_weight_multiplier=1.0,
    background_color="#FFFFFF",
    default_stroke_color="#1A1A1A",
    color_mode="layer_color",
    draw_annotations=True,
    draw_components=True,
    draw_dimensions=True,
    prune_outliers=True,
    description="High-fidelity client review deck preserving original CAD layer colors and rich visual hierarchy.",
)

DARK_BLUEPRINT_PRESET = PdfPreset(
    name="dark-blueprint",
    paper_size="A3",
    orientation="landscape",
    target_space="Model",
    margin_mm=12.0,
    scale_mode="fit",
    default_line_width_pt=0.35,
    line_weight_multiplier=1.0,
    background_color="#0F172A",      # Deep slate blueprint navy
    default_stroke_color="#F8FAFC",  # Crisp blueprint white
    color_mode="monochrome",
    draw_annotations=True,
    draw_components=True,
    draw_dimensions=True,
    prune_outliers=True,
    description="Classic blueprint / dark-mode engineering aesthetic with white vector linework on deep navy slate.",
)

WEB_MOBILE_A4_PRESET = PdfPreset(
    name="web-mobile-a4",
    paper_size="A4",
    orientation="landscape",
    target_space="Model",
    margin_mm=8.0,
    scale_mode="fit",
    default_line_width_pt=0.28,
    line_weight_multiplier=0.85,
    background_color="#FFFFFF",
    default_stroke_color="#000000",
    color_mode="monochrome",
    draw_annotations=True,
    draw_components=True,
    draw_dimensions=True,
    prune_outliers=True,
    description="Compact, lightweight A4 drawing optimized for mobile screens, email attachments, and office printing.",
)

HIGH_QUALITY_PRINT_PRESET = PdfPreset(
    name="high-quality-print",
    paper_size="A2",
    orientation="landscape",
    target_space="Model",
    margin_mm=15.0,
    scale_mode="fit",
    default_line_width_pt=0.45,
    line_weight_multiplier=1.1,
    background_color="#FFFFFF",
    default_stroke_color="#000000",
    color_mode="layer_color",
    draw_annotations=True,
    draw_components=True,
    draw_dimensions=True,
    prune_outliers=True,
    description="Maximum fidelity vector export for publication boards and fine-art plotters on large A2 format.",
)

REVIEW_SCREENED_PRESET = PdfPreset(
    name="review-screened",
    paper_size="A3",
    orientation="landscape",
    target_space="Model",
    margin_mm=12.0,
    scale_mode="fit",
    default_line_width_pt=0.25,
    line_weight_multiplier=0.75,
    background_color="#FFFFFF",
    default_stroke_color="#64748B",  # Medium slate gray for low contrast underlay
    color_mode="monochrome",
    screening=0.5,
    draw_annotations=True,
    draw_components=True,
    draw_dimensions=True,
    prune_outliers=True,
    description="Screened half-tone underlay drawing engineered for markup redlining and QA coordination.",
)

DEFAULT_PRESET = MONOCHROME_ARCHITECTURAL_PRESET

# Canonical Presets Dictionary (including backward-compatibility aliases)
PRESETS: Dict[str, PdfPreset] = {
    "monochrome-arch": MONOCHROME_ARCHITECTURAL_PRESET,
    "monochrome-architectural": MONOCHROME_ARCHITECTURAL_PRESET,  # Alias
    "presentation-color": PRESENTATION_COLOR_PRESET,
    "presentation-fit-vector": PRESENTATION_COLOR_PRESET,          # Alias
    "permit-arch-d": PERMIT_ARCH_D_PRESET,
    "metric-construction-a1": METRIC_CONSTRUCTION_A1_PRESET,
    "dark-blueprint": DARK_BLUEPRINT_PRESET,
    "web-mobile-a4": WEB_MOBILE_A4_PRESET,
    "quick-preview-a4": WEB_MOBILE_A4_PRESET,                     # Alias
    "high-quality-print": HIGH_QUALITY_PRINT_PRESET,
    "review-screened": REVIEW_SCREENED_PRESET,
}

def get_preset(name_or_preset: Optional[Union[str, PdfPreset]] = None) -> PdfPreset:
    """Resolves a preset from name string or returns the preset directly, falling back to DEFAULT_PRESET."""
    if name_or_preset is None:
        return DEFAULT_PRESET
    if isinstance(name_or_preset, PdfPreset):
        return name_or_preset
    if isinstance(name_or_preset, str):
        key = name_or_preset.strip().lower()
        if key in PRESETS:
            return PRESETS[key]
    return DEFAULT_PRESET

def list_presets() -> List[Dict[str, Any]]:
    """Returns metadata catalog of all distinct ready-made presets for UI/API discovery."""
    distinct = [
        MONOCHROME_ARCHITECTURAL_PRESET,
        PRESENTATION_COLOR_PRESET,
        PERMIT_ARCH_D_PRESET,
        METRIC_CONSTRUCTION_A1_PRESET,
        DARK_BLUEPRINT_PRESET,
        WEB_MOBILE_A4_PRESET,
        HIGH_QUALITY_PRINT_PRESET,
        REVIEW_SCREENED_PRESET,
    ]
    return [
        {
            "id": p.name,
            "description": p.description,
            "paper_size": p.paper_size,
            "orientation": p.orientation,
            "color_mode": p.color_mode,
            "background_color": p.background_color,
            "default_stroke_color": p.default_stroke_color,
            "margin_mm": p.margin_mm,
        }
        for p in distinct
    ]

