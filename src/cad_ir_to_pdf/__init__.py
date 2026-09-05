"""
cad_ir_to_pdf — High-fidelity vector CAD PDF compiler.
"""

from .config import DEFAULT_PRESET, PRESETS, PdfPreset
from .compiler import compile_ir_to_pdf

__version__ = "0.1.0"
__all__ = [
    "compile_ir_to_pdf",
    "PdfPreset",
    "DEFAULT_PRESET",
    "PRESETS",
]
