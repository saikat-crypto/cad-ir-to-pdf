"""
telemetry.py — Structured warning models and compilation reporting for cad-ir-to-pdf.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional


class HardeningCategory(str, Enum):
    COORDINATE_SINGULARITY = "coordinate_singularity"
    DEGENERATE_GEOMETRY = "degenerate_geometry"
    TRANSFORM_ABUSE = "transform_abuse"
    METADATA_MALFORMED = "metadata_malformed"
    FONT_FALLBACK = "font_fallback"
    COLOR_FALLBACK = "color_fallback"
    COLLECTION_DEFECT = "collection_defect"
    BLOCK_ABUSE = "block_abuse"


class ActionTaken(str, Enum):
    DROPPED = "dropped"
    CLAMPED = "clamped"
    FALLBACK_APPLIED = "fallback_applied"
    SANITIZED = "sanitized"


@dataclass
class HardeningWarning:
    category: HardeningCategory
    action: ActionTaken
    entity_type: str
    reason: str
    entity_index: Optional[int] = None
    layer: Optional[str] = None
    original_value: Any = None
    sanitized_value: Any = None


@dataclass
class CompilationReport:
    pdf_path: Path
    success: bool = True
    total_entities_read: int = 0
    total_entities_rendered: int = 0
    total_entities_dropped: int = 0
    total_entities_sanitized: int = 0
    warnings: List[HardeningWarning] = field(default_factory=list)
