"""
telemetry.py — Structured warning models and compilation reporting for cad-ir-to-pdf.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


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

    def to_dict(self) -> Dict[str, Any]:
        """Serializes warning to a dictionary representation."""
        return {
            "category": self.category.value if isinstance(self.category, HardeningCategory) else str(self.category),
            "action": self.action.value if isinstance(self.action, ActionTaken) else str(self.action),
            "entity_type": self.entity_type,
            "reason": self.reason,
            "entity_index": self.entity_index,
            "layer": self.layer,
            "original_value": str(self.original_value) if self.original_value is not None else None,
            "sanitized_value": str(self.sanitized_value) if self.sanitized_value is not None else None,
        }


@dataclass
class CompilationReport:
    pdf_path: Path
    success: bool = True
    total_entities_read: int = 0
    total_entities_rendered: int = 0
    total_entities_dropped: int = 0
    total_entities_sanitized: int = 0
    warnings: List[HardeningWarning] = field(default_factory=list)
    conversion_time_ms: float = 0.0
    cad_bbox_extents: Optional[Dict[str, float]] = None
    viewport_scale: float = 1.0
    page_dimensions_pt: Optional[Dict[str, float]] = None

    def add_warning(
        self,
        category: HardeningCategory,
        action: ActionTaken,
        entity_type: str,
        reason: str,
        entity_index: Optional[int] = None,
        layer: Optional[str] = None,
        original_value: Any = None,
        sanitized_value: Any = None,
    ) -> HardeningWarning:
        """Helper to append a structured warning and adjust summary counters."""
        warn = HardeningWarning(
            category=category,
            action=action,
            entity_type=entity_type,
            reason=reason,
            entity_index=entity_index,
            layer=layer,
            original_value=original_value,
            sanitized_value=sanitized_value,
        )
        self.warnings.append(warn)
        if action == ActionTaken.DROPPED:
            self.total_entities_dropped += 1
        elif action in (ActionTaken.SANITIZED, ActionTaken.CLAMPED, ActionTaken.FALLBACK_APPLIED):
            self.total_entities_sanitized += 1
        return warn

    def to_dict(self) -> Dict[str, Any]:
        """Serializes compilation report to a dictionary representation for JSON/MCP transport."""
        return {
            "pdf_path": str(self.pdf_path),
            "success": self.success,
            "total_entities_read": self.total_entities_read,
            "total_entities_rendered": self.total_entities_rendered,
            "total_entities_dropped": self.total_entities_dropped,
            "total_entities_sanitized": self.total_entities_sanitized,
            "conversion_time_ms": self.conversion_time_ms,
            "cad_bbox_extents": self.cad_bbox_extents,
            "viewport_scale": self.viewport_scale,
            "page_dimensions_pt": self.page_dimensions_pt,
            "warning_count": len(self.warnings),
            "warnings": [w.to_dict() for w in self.warnings],
        }
