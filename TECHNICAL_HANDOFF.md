# TECHNICAL_HANDOFF.md — `cad-ir-to-pdf` Module Technical Specification & Handoff

> **Module**: `cad-ir-to-pdf` (La Vinci CAD Compiler — Product 3)  
> **Repository**: [`saikat-crypto/cad-ir-to-pdf`](https://github.com/saikat-crypto/cad-ir-to-pdf)  
> **Pipeline Role**: Downstream vector PDF synthesis engine (pure spoke).  
> **Specification Standard**: `LAVINCI_CAD_IR_V3`  
> **Target Audience**: Wrapper engineers, API developers, pipeline orchestrators, and UI/CLI integrators.

---

## 1. Executive Architecture Overview

`cad-ir-to-pdf` is a deterministic, non-lossy vector rendering compiler. It converts standard `LAVINCI_CAD_IR_V3` JSON payloads into publication-grade, resolution-independent vector PDF documents.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        UPSTREAM (CAD Extractor)                        │
│             DWG / DXF / DWT Files  ──►  cad-extractor-ir               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼ (Pure Hub-and-Spoke Contract)
                     LAVINCI_CAD_IR_V3 (JSON Payload)
                                    │
┌───────────────────────────────────┴────────────────────────────────────┐
│                    DOWNSTREAM: cad-ir-to-pdf (This Module)             │
│                                                                        │
│   Input: JSON File / Dict / Stream                                     │
│   Config: Ready-Made Preset ('monochrome-arch', etc.)                  │
│   Options: PdfOptions Overrides (watermark, layers, scale, paper)      │
│                                                                        │
│   [Affine Engine] ──► [Curvature Subdivider] ──► [Vector Renderer]     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
                     High-Fidelity Vector PDF Drawing
             (Infinite zoom clarity at 6400%, 0 bitmap raster)
```

---

## 2. What the Module Accepts

The primary compilation entrypoint is:
```python
def compile_ir_to_pdf(
    ir_source: Union[str, Path, Dict[str, Any]],
    output_path: Union[str, Path],
    preset: Optional[Union[str, PdfPreset]] = None,
    options: Optional[Union[PdfOptions, Dict[str, Any]]] = None,
    report: Optional[CompilationReport] = None,
    return_report: bool = False,
) -> Union[Path, Tuple[Path, CompilationReport]]:
```

### Accepted `ir_source` formats:
1. **`str` or `pathlib.Path`**: Filepath pointing to a valid `.json` file on disk.
2. **`dict`**: An in-memory Python dictionary conforming to `LAVINCI_CAD_IR_V3` schema.

---

## 3. Exact Input Schema (`LAVINCI_CAD_IR_V3`)

The input dictionary MUST contain the following structure:

```typescript
interface CADIntermediateRepresentation {
  format: "LAVINCI_CAD_IR_V3";             // Required schema version tag
  metadata: CADMetadata;                    // Drawing metadata
  extents: CADExtents;                      // World coordinate bounding box
  layouts?: CADLayout[];                    // Model / Paper space layouts
  layers: CADLayer[];                       // Layer table definitions
  block_definitions?: Record<string, CADBlockDefinition>; // Reusable block definitions
  components?: CADComponentInstance[];     // Inserted block instances
  annotations?: CADAnnotation[];            // Text & MText entities
  dimensions?: CADDimension[];              // Dimension blocks & measurements
  geometry_primitives: {
    primitives: {
      lines?: CADLine[];
      arcs?: CADArc[];
      circles?: CADCircle[];
      polylines?: CADPolyline[];
    };
    summary?: Record<string, number>;
  };
}
```

### Core Entity Definitions:

```typescript
interface CADLine {
  start: [number, number] | [number, number, number]; // [X, Y] world coords
  end: [number, number] | [number, number, number];
  layer: string;
  space?: "Model" | "Paper" | string;       // Default: "Model"
  color?: string | null;                     // Hex override or null (BYLAYER)
  line_width?: number | null;                // PostScript points override
}

interface CADArc {
  center: [number, number] | [number, number, number];
  radius: number;                            // Must be finite, non-negative
  start_angle: number;                       // In degrees [0, 360)
  end_angle: number;                         // In degrees [0, 360)
  layer: string;
  space?: "Model" | "Paper" | string;
  color?: string | null;
  line_width?: number | null;
}

interface CADCircle {
  center: [number, number] | [number, number, number];
  radius: number;                            // Must be finite, non-negative
  layer: string;
  space?: "Model" | "Paper" | string;
  color?: string | null;
  line_width?: number | null;
}

interface CADPolyline {
  points: Array<[number, number] | [number, number, number]>;
  is_closed: boolean;
  layer: string;
  space?: "Model" | "Paper" | string;
  color?: string | null;
  line_width?: number | null;
}

interface CADComponentInstance {
  block_name: string;                        // Matches key in block_definitions
  resolved_name?: string;
  layer: string;
  space?: "Model" | "Paper" | string;
  position: [number, number] | [number, number, number];
  rotation: number;                          // Counter-clockwise degrees
  scale: [number, number] | [number, number, number]; // [sx, sy, sz]
  attributes?: Record<string, string>;
}

interface CADDimension {
  type: string;                              // e.g. "aligned", "linear", "rotational"
  layer: string;
  space?: "Model" | "Paper" | string;
  measurement?: number | null;               // True numeric dimension value
  text?: string | null;                      // Explicit override text (if any)
  defpoint: [number, number];                // Primary dimension point
  defpoint2?: [number, number] | null;       // Secondary point
  text_midpoint?: [number, number] | null;   // Dimension text location
  text_height?: number | null;               // CAD text height
  text_rotation?: number | null;             // Rotation in degrees
}

interface CADAnnotation {
  type?: string;                             // "TEXT" or "MTEXT"
  layer: string;
  space?: "Model" | "Paper" | string;
  clean_text: string;                        // Stripped of AutoCAD escape codes
  raw_text?: string;
  position: [number, number];                // Insertion point
  height: number;                            // CAD text height in drawing units
  color?: string | null;
}
```

---

## 4. Exact Output Schema & Return Types

### Return Value
- By default (`return_report=False`): Returns `pathlib.Path` pointing to the generated vector `.pdf` file.
- With telemetry (`return_report=True`): Returns `Tuple[pathlib.Path, CompilationReport]`.

### Output PDF Technical Characteristics
- **Format**: Vector PDF 1.4 / 1.7 (ReportLab standard vector canvas).
- **Resolution**: Resolution-independent vector paths (equivalent to infinite vector DPI).
- **Embedded Fonts**: Standard Type 1 PostScript fonts (`Helvetica`, `Helvetica-Bold`, `Courier`, `Times-Roman`). No external `.ttf` dependencies required.
- **Layers**: Optional Content Groups (OCGs) supported; geometry grouped cleanly on white or dark canvas.

### The `CompilationReport` Telemetry Schema

```typescript
interface CompilationReport {
  pdf_path: string;                          // Destination path
  success: boolean;                          // True if PDF compiled cleanly
  total_entities_read: number;               // Raw primitives ingested
  total_entities_rendered: number;           // Vector elements drawn
  total_entities_dropped: number;            // Degenerate/invalid items discarded
  total_entities_sanitized: number;          // Elements clamped or corrected
  conversion_time_ms: number;                // Compilation latency in milliseconds
  cad_bbox_extents: {                        // Calculated model bounds
    min_x: number; min_y: number;
    max_x: number; max_y: number;
    width: number; height: number;
  };
  viewport_scale: number;                    // Fitted scale factor (pt per unit)
  page_dimensions_pt: {
    width: number;
    height: number;
  };
  warning_count: number;
  warnings: Array<{
    category: "coordinate_singularity" | "degenerate_geometry" | "transform_abuse" | 
              "metadata_malformed" | "font_fallback" | "color_fallback" | 
              "collection_defect" | "block_abuse";
    action: "dropped" | "clamped" | "fallback_applied" | "sanitized";
    entity_type: string;
    reason: string;
    layer?: string;
    original_value?: string;
    sanitized_value?: string;
  }>;
}
```

To serialize report for JSON or MCP transport:
```python
report_dict = report.to_dict()
```

---

## 5. Ready-Made Presets Catalog

The module ships with **8 production-engineered presets** matching industry CAD personas (AutoCAD `.pc3`, `.ctb`, and Bluebeam Revu standards):

| Preset ID | Industry Analogue | Paper Size | Color Mode | Line Weight | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`monochrome-arch`** *(Default)* | AutoCAD `monochrome.ctb` | A3 Landscape | `monochrome` (#000000 on #FFFFFF) | `0.35 pt` | Standard architectural blueprint plot for permits and reviews. |
| **`presentation-color`** | AutoCAD `acad.ctb` | A3 Landscape | `layer_color` (true CAD hues) | `0.50 pt` | Full CAD layer color preservation for client presentations. |
| **`permit-arch-d`** | US Municipal Plan Sets | ARCH D (24" × 36") | `monochrome` | `0.50 pt` (1.1x) | Full-size US Architectural D sheet with 1-inch (25.4mm) binding margins. |
| **`metric-construction-a1`** | ISO A1 Site Blueprint | ISO A1 (594 × 841 mm) | `monochrome` | `0.40 pt` | Metric job site drawing for European, UK, and Asian construction. |
| **`dark-blueprint`** | Digital Dark Mode CAD | A3 Landscape | Inverted Slate | `0.35 pt` | Crisp white linework on deep navy slate (`#0F172A`). |
| **`web-mobile-a4`** | AutoCAD (Web & Mobile) | A4 Landscape | `monochrome` | `0.28 pt` (0.85x)| Compact, lightweight drawing calibrated for screens and email attachments. |
| **`high-quality-print`** | AutoCAD (High Quality) | A2 Landscape | `layer_color` | `0.45 pt` (1.1x) | Maximum vector fidelity export for presentation boards and fine plotters. |
| **`review-screened`** | Half-Tone / Underlay | A3 Landscape | Screened Slate | `0.25 pt` (0.75x)| 50% screened slate linework engineered for redlining markup and QA. |

### Backward-Compatibility Aliases:
- `"monochrome-architectural"` $\to$ maps to `"monochrome-arch"`
- `"presentation-fit-vector"` $\to$ maps to `"presentation-color"`
- `"quick-preview-a4"` $\to$ maps to `"web-mobile-a4"`

---

## 6. Advanced Customization: `PdfOptions` Overrides

Callers can pass any preset name as a baseline, and selectively override specific parameters using `PdfOptions` (or a raw dictionary):

```python
@dataclass
class PdfOptions:
    paper_size: Optional[str] = None          # "A4", "A3", "A2", "A1", "A0", "LETTER", "LEGAL", "TABLOID", "ARCH_C", "ARCH_D", "ARCH_E"
    orientation: Optional[str] = None         # "landscape" or "portrait"
    target_space: Optional[str] = None        # "Model", "Paper", or "all"
    margin_mm: Optional[float] = None         # Boundary margin in mm (e.g. 10.0)
    scale_mode: Optional[str] = None          # "fit" (auto-fit) or "fixed"
    fixed_scale: Optional[float] = None       # e.g. 0.02 for 1:50, 0.01 for 1:100
    default_line_width_pt: Optional[float] = None # Base stroke weight in points
    line_weight_multiplier: Optional[float] = None # Global scaling factor for all pen widths (e.g. 1.2, 0.8)
    background_color: Optional[str] = None    # Hex color string (e.g. "#FFFFFF", "#0F172A")
    default_stroke_color: Optional[str] = None# Hex color string (e.g. "#000000", "#F8FAFC")
    color_mode: Optional[str] = None          # "monochrome" or "layer_color"
    draw_annotations: Optional[bool] = None   # Toggle text rendering
    draw_components: Optional[bool] = None    # Toggle block inserts rendering
    draw_dimensions: Optional[bool] = None    # Toggle dimension blocks & measurement text
    prune_outliers: Optional[bool] = None     # Discard isolated scratch objects far outside drawing bounds
    custom_bbox: Optional[Tuple[float, float, float, float]] = None # Zoom window crop: (min_x, min_y, max_x, max_y)
    font_name: Optional[str] = None           # PostScript font name (default: "Helvetica")
    visible_layers: Optional[List[str]] = None# Whitelist of layers to render
    hidden_layers: Optional[List[str]] = None # Blacklist of layers to suppress (e.g. ["DEFPOINTS", "TEMP_*"])
    watermark_text: Optional[str] = None      # Centered diagonal watermark text
    screening: Optional[float] = None         # Opacity screening multiplier (0.0 to 1.0)
```

---

## 7. Defaults & Validation Rules

### Line Widths:
- **Default Base**: `0.35 pt`
- **Bounds Clamping**: Clamped to `[0.05 pt, 50.0 pt]`. Any `NaN`, `±Inf`, negative, or zero width is safely sanitized to the preset default without throwing an exception.

### Typography & Fonts:
- **Default Font**: `"Helvetica"`
- **Font Size Clamping**: Clamped to `[1.0 pt, 144.0 pt]`.
- **Text Sanitization**: Strips AutoCAD MTEXT control formatting codes (`\f...;`, `\H...;`, `\W...;`, `\C...;`, `\P`, etc.) and decodes standard CAD symbols (`%%d` $\to$ `°`, `%%p` $\to$ `±`, `%%c` $\to$ `Ø`).
- **Dimension Text Baseline Clearance**: Dimension text baselines automatically snap `actual_line_py + clearance` above dimension lines to prevent the line from slicing through measurement numbers.

### Coordinates & Bounds:
- **Singularity Protection**: Coordinate inputs are strictly validated. Any point with `NaN`, `±Inf`, or non-numeric elements is dropped gracefully and logged to telemetry.
- **Outlier Pruning**: When `prune_outliers=True`, geometry isolated $> 5 \times$ standard interquartile spread from the median drawing extents is excluded from viewport calculations to avoid extreme zoom-outs caused by drafting scratchpad artifacts.

---

## 8. Error Conditions & Exception Hierarchy

`cad-ir-to-pdf` adheres to **graceful degradation**—it never crashes on corrupted entity geometry, but raises explicit standard exceptions when file I/O or input types are violated:

| Exception Raised | Cause / Trigger | Caller Mitigation |
| :--- | :--- | :--- |
| **`FileNotFoundError`** | `ir_source` was a string/path, but the file does not exist on disk. | Verify file path before invoking compiler. |
| **`TypeError`** | `ir_source` was neither a string, Path, nor dictionary (e.g., passed integer or list). | Ensure valid JSON path or dict is provided. |
| **`json.JSONDecodeError`** | `ir_source` file contains malformed/invalid JSON syntax. | Ensure upstream extractor completes writing JSON. |
| **`OSError` / `PermissionError`** | Cannot write to `output_path` (permission denied, disk full, invalid path). | Ensure target directory exists and is writable. |

**No exception is ever thrown for malformed geometry**: Malformed lines, zero-radius arcs, circular block hierarchies, or negative scales are dropped or sanitized cleanly and recorded in `CompilationReport.warnings`.

---

## 9. Supported vs. Unsupported Primitives & Edge Cases

### Fully Supported:
- **Lines (`LINE`)**: 2D/3D start and end coordinates. Zero-length lines are dropped cleanly.
- **Arcs (`ARC`)**: Analytic cubic Bézier curves. Sweeps spanning 0° to 360° across 0° boundary are mapped accurately.
- **Circles (`CIRCLE`)**: Approximated with 4 analytic cubic Bézier segments with sub-millimeter precision.
- **Polylines (`LWPOLYLINE` / `POLYLINE`)**: Multi-segment open and closed paths.
- **Block Instances (`INSERT`)**: Full 2D affine transformation matrices ($T \cdot R \cdot S$). Nested blocks supported up to recursion depth 16 with circular loop detection.
- **Anonymous Dimension Blocks (`*D...`)**: Rendered directly from block definitions alongside measurement text.
- **Dimension Entities (`DIMENSION`)**: Linear, aligned, and rotational dimension text labels with clearance offset logic.
- **Text & MText (`TEXT` / `MTEXT`)**: Multi-line strings, alignment, and escape sequence stripping.

### Unsupported / Out-of-Scope:
- **3D Solid ACIS Meshes (`3DSOLID`, `REGION`, `BODY`)**: Must be projected into 2D by the upstream extractor before reaching `cad-ir-to-pdf`.
- **TrueType Font Embedding (`.ttf` binaries)**: The compiler relies on PDF standard 14 PostScript typefaces (`Helvetica`, `Courier`, `Times`). Custom SHX architectural fonts are mapped to `Helvetica`.
- **Raster Bitmaps (`IMAGE`)**: CAD embedded aerial imagery is not rendered; only pure vector geometry is generated.

---

## 10. Performance Characteristics

Tested across real-world automotive, architectural, and electrical CAD drawings:

| Drawing Complexity | Primitives Extracted | Entities Rendered | Memory Usage | Compiler Latency | Output PDF Size |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Small Floor Plan** (Residential House) | ~800 | 1,129 | ~18 MB | **0.07 s** | ~20 KB |
| **Medium Layout** (Electrical Schematic) | ~350 | 659 | ~15 MB | **0.05 s** | ~16 KB |
| **Complex Assembly** (Automotive Chassis) | ~30 blocks | 17,661 | ~42 MB | **1.46 s** | ~508 KB |
| **Large Site Plan** (22,000+ lines) | ~30,000 | 29,611 | ~68 MB | **2.85 s** | ~738 KB |

- **Subprocess Calls**: **0**. `cad-ir-to-pdf` is 100% native in-process Python.
- **Temporary Files Created**: **0**. The canvas renders directly to the destination path or stream.
- **Concurrency**: Fully thread-safe. Multiple worker processes can compile separate PDFs simultaneously without shared state conflicts.

---

## 11. Code Examples

### Example 1: Basic Zero-Config Compilation
```python
from cad_ir_to_pdf import compile_ir_to_pdf

# Compiles with default 'monochrome-arch' preset
pdf_path = compile_ir_to_pdf(
    ir_source="experiments/e2e_demo/toyota_c_hr_2017_ir.json",
    output_path="outputs/toyota.pdf"
)
print(f"PDF created at: {pdf_path}")
```

### Example 2: Selecting a Ready-Made Preset
```python
from cad_ir_to_pdf import compile_ir_to_pdf

# Digital Dark Mode aesthetic
compile_ir_to_pdf(
    ir_source="drawing_ir.json",
    output_path="outputs/dark_blueprint.pdf",
    preset="dark-blueprint"
)

# Full presentation color
compile_ir_to_pdf(
    ir_source="drawing_ir.json",
    output_path="outputs/client_deck.pdf",
    preset="presentation-color"
)
```

### Example 3: Preset + Surgical `PdfOptions` Overrides
```python
from cad_ir_to_pdf import compile_ir_to_pdf, PdfOptions

compile_ir_to_pdf(
    ir_source="drawing_ir.json",
    output_path="outputs/permit_submission.pdf",
    preset="permit-arch-d",
    options=PdfOptions(
        watermark_text="PRELIMINARY - NOT FOR CONSTRUCTION",
        line_weight_multiplier=1.15,
        hidden_layers=["DEFPOINTS", "REVISION_CLOUDS"],
        margin_mm=20.0,
    )
)
```

### Example 4: Telemetry & Quality Assurance Auditing
```python
from cad_ir_to_pdf import compile_ir_to_pdf

out_path, report = compile_ir_to_pdf(
    ir_source="drawing_ir.json",
    output_path="outputs/verified.pdf",
    return_report=True
)

print(f"Rendered {report.total_entities_rendered} entities in {report.conversion_time_ms} ms")
if report.warning_count > 0:
    for warn in report.warnings:
        print(f"[{warn.category}] {warn.reason} on entity {warn.entity_type}")
```

### Example 5: Introspecting Available Presets for UI/REST API
```python
from cad_ir_to_pdf import list_presets

# Return catalog directly to frontend dropdown
presets_catalog = list_presets()
for p in presets_catalog:
    print(f"{p['id']}: {p['description']} (Paper: {p['paper_size']} {p['orientation']})")
```

---

## 12. Dependencies & Runtime Environment

### Runtime Dependencies:
- **Python**: `>= 3.9`
- **`reportlab >= 4.0.0`**: Core PostScript canvas and vector rendering engine.

### Development & Test Dependencies:
- **`pytest >= 7.0.0`**: Test runner.
- **`pymupdf >= 1.20.0`**: Vector PDF structural verification, page extents testing, and text extraction auditing.

### Subprocesses, Binaries & Temporary Files:
- **Subprocesses**: **None**. (Unlike `cad-extractor-ir` which wraps LibreDWG, `cad-ir-to-pdf` is 100% pure Python).
- **Native Binaries**: **None**.
- **Temporary Files**: **None**. Writes cleanly to the target `output_path`.

---

## 13. Critical Rules for Wrapper & Cloud Layers

1. **Do Not Pass Raw DWG/DXF**:
   `cad-ir-to-pdf` does NOT parse DWG or DXF files. It is strictly a spoke. Raw CAD files must first be converted to `LAVINCI_CAD_IR_V3` JSON by `cad-extractor-ir`.
2. **Preset Immutability**:
   Calling `preset.with_options(opts)` creates a brand new `PdfPreset` instance. Built-in presets (`MONOCHROME_ARCHITECTURAL_PRESET`, etc.) are immutable singletons.
3. **Safe JSON Ingestion**:
   When invoking over HTTP/REST APIs, parse user inputs into `PdfOptions(**request_data.get("options", {}))` or pass raw dictionaries directly to the `options` argument.
4. **Cloud Headless Readiness**:
   `cad-ir-to-pdf` does not require an X11 server, GUI display, or graphical framebuffer. It runs seamlessly in headless Docker containers, AWS Lambda, and Kubernetes workers.
