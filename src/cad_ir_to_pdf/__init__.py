"""
cad_ir_to_pdf — High-fidelity vector CAD PDF compiler.
"""

from .config import (
    DEFAULT_PRESET,
    PRESETS,
    PdfOptions,
    PdfPreset,
    get_preset,
    list_presets,
    MONOCHROME_ARCHITECTURAL_PRESET,
    PERMIT_ARCH_D_PRESET,
    METRIC_CONSTRUCTION_A1_PRESET,
    PRESENTATION_COLOR_PRESET,
    DARK_BLUEPRINT_PRESET,
    WEB_MOBILE_A4_PRESET,
    HIGH_QUALITY_PRINT_PRESET,
    REVIEW_SCREENED_PRESET,
)
from .compiler import compile_ir_to_pdf
from .telemetry import ActionTaken, CompilationReport, HardeningCategory, HardeningWarning

__version__ = "0.2.0"
__all__ = [
    "compile_ir_to_pdf",
    "PdfOptions",
    "PdfPreset",
    "DEFAULT_PRESET",
    "PRESETS",
    "get_preset",
    "list_presets",
    "MONOCHROME_ARCHITECTURAL_PRESET",
    "PERMIT_ARCH_D_PRESET",
    "METRIC_CONSTRUCTION_A1_PRESET",
    "PRESENTATION_COLOR_PRESET",
    "DARK_BLUEPRINT_PRESET",
    "WEB_MOBILE_A4_PRESET",
    "HIGH_QUALITY_PRINT_PRESET",
    "REVIEW_SCREENED_PRESET",
    "ActionTaken",
    "CompilationReport",
    "HardeningCategory",
    "HardeningWarning",
]
