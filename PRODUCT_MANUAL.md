# cad-ir-to-pdf: High-Fidelity Vector PDF Compiler & Printing Engine

> **Product**: `cad-ir-to-pdf`  
> **Package Version**: `0.1.0` (Production Hardened)  
> **Source Directory**: `products/cad-ir-to-pdf/`  
> **Role in Ecosystem**: Vector PDF Egress Compiler (`LAVINCI_CAD_IR_V3` $\to$ Vector PDF)  

---

## 1. Executive Summary & Core Purpose

The **`cad-ir-to-pdf`** compiler projects the canonical **`LAVINCI_CAD_IR_V3`** into publication-grade, mathematically exact vector PDF documents.

Unlike raster-based PDF generators that render CAD linework into low-resolution bitmap images embedded in PDF wrappers, `cad-ir-to-pdf` constructs native **PostScript vector draw paths** directly via the ReportLab PDF rendering engine:
* **Infinite Resolution**: Linework, text, and circular curves scale losslessly at any zoom level, maintaining hair-thin line precision suitable for professional plotting.
* **Affine Coordinate Mapping**: Maps arbitrary physical CAD coordinates (from millimeter-scale mechanical gears to kilometer-scale municipal civil surveys) into standardized paper spaces (A4 to ARCH E) with zero distortion.
* **Rotational Text Mathematics**: Implements native canvas matrix transformations (`saveState`, `translate`, `rotate`, `restoreState`) to faithfully render angled labels and vertical dimension strings.
* **Background-Aware Contrast Safety**: Dynamically analyzes Rec. 709 relative luminance to prevent white linework on white paper or black linework on dark blueprints.

```
 ┌──────────────────────────────┐
 │   LAVINCI_CAD_IR_V3 (JSON)   │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │   Preset & Options Ingestion │
 │   - Sheet Size & Orientation │
 │   - Scale Mode (Fit / Fixed) │
 │   - Palette & Color Mode     │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │     Extents & Outliers       │
 │   - Safe Text BBox Guard     │
 │   - Gap-based Clustered Crop │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │  Affine Viewport Calculation │
 │   - Aspect Ratio Lock        │
 │   - Margin Inset Buffer      │
 │   - Canvas Origin Shift      │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │   ReportLab Canvas Drawing   │
 │   - Cubic Bézier Arcs        │
 │   - Rotated Annotation Canvas│
 │   - Rec. 709 Contrast Guard  │
 │   - Line Weight Clamping     │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │     Vector PDF Document      │
 └──────────────────────────────┘
```

---

## 2. Mathematical Architecture: Affine Projection & Viewport Mapping

### 2.1 Affine Transformation Matrix (`AffineMatrix2D`)
CAD drawings use an arbitrary modelspace coordinate system with $+Y$ oriented upwards. A 2D affine transformation maps model coordinates $\vec{P}_{\text{cad}} = [x, y]^T$ to paper PostScript points $\vec{P}_{\text{pdf}} = [x', y']^T$:

$$\begin{bmatrix} x' \\ y' \\ 1 \end{bmatrix} = \begin{bmatrix} a & c & t_x \\ b & d & t_y \\ 0 & 0 & 1 \end{bmatrix} \begin{bmatrix} x \\ y \\ 1 \end{bmatrix}$$

Where:
* $a, d$: Uniform scaling factors along $X$ and $Y$.
* $b, c$: Shear / rotation components (default $0.0$).
* $t_x, t_y$: Translation offsets positioning the drawing within printable paper margins.

### 2.2 Uniform Aspect-Ratio Viewport Fitting
To prevent non-uniform stretching, the scale factor $S$ is calculated by taking the minimum of horizontal and vertical bounds:

$$W_{\text{avail}} = W_{\text{paper}} - 2 \cdot M_{\text{margin}}$$
$$H_{\text{avail}} = H_{\text{paper}} - 2 \cdot M_{\text{margin}}$$
$$S = \min\left( \frac{W_{\text{avail}}}{X_{\max} - X_{\min}}, \frac{H_{\text{avail}}}{Y_{\max} - Y_{\min}} \right)$$

The drawing is then perfectly centered on the page:
$$t_x = M_{\text{margin}} + \frac{W_{\text{avail}} - S(X_{\max} - X_{\min})}{2} - S \cdot X_{\min}$$
$$t_y = M_{\text{margin}} + \frac{H_{\text{avail}} - S(Y_{\max} - Y_{\min})}{2} - S \cdot Y_{\min}$$

---

## 3. Curve Decomposition: Cubic Bézier Arcs

PostScript and PDF specifications do not provide a native analytic circular arc drawing primitive; all curves must be drawn as cubic Bézier splines.

An analytic arc spanning $\Delta\theta \le 90^\circ$ centered at $(C_x, C_y)$ with radius $R$ is converted to a cubic Bézier spline with control points $P_0, P_1, P_2, P_3$:

$$\alpha = \frac{4}{3} \tan\left(\frac{\Delta\theta}{4}\right)$$
$$\vec{P}_0 = \begin{bmatrix} C_x + R\cos\theta_s \\ C_y + R\sin\theta_s \end{bmatrix}$$
$$\vec{P}_1 = \vec{P}_0 + \alpha R \begin{bmatrix} -\sin\theta_s \\ \cos\theta_s \end{bmatrix}$$
$$\vec{P}_3 = \begin{bmatrix} C_x + R\cos\theta_e \\ C_y + R\sin\theta_e \end{bmatrix}$$
$$\vec{P}_2 = \vec{P}_3 - \alpha R \begin{bmatrix} -\sin\theta_e \\ \cos\theta_e \end{bmatrix}$$

For arcs sweeping angles $\Delta\theta > 90^\circ$, `cad-ir-to-pdf` automatically subdivides the curve into multiple $\le 90^\circ$ spans, ensuring sub-micron mathematical fidelity with zero visual facetting.

---

## 4. Rotational Text Mathematics (The Bugatti Chiron Resolution)

In architectural and automotive drawings, dimensions and annotations are frequently rotated vertically or at arbitrary angles (e.g. alignment notes along angled walls).

### Canvas State Isolation Pattern
In ReportLab, attempting to draw rotated text using raw coordinates can cause catastrophic coordinate shifts across subsequent drawing operations. 

`cad-ir-to-pdf` isolates text drawing via canvas transformations:
```python
# 1. Transform insertion point to PDF canvas coordinates
pt_x, pt_y = matrix.transform_point(ann.position[0], ann.position[1])

# 2. Isolate transformation matrix state
c.saveState()

# 3. Translate canvas origin to text insertion point
c.translate(pt_x, pt_y)

# 4. Apply native counter-clockwise rotation angle
c.rotate(ann.rotation)

# 5. Draw text at localized origin (0, 0)
c.drawString(0, 0, ann.clean_text)

# 6. Restore global canvas matrix for subsequent geometry
c.restoreState()
```

---

## 5. Rec. 709 Relative Luminance & Contrast Safety

In AutoCAD, drafters frequently set linework colors to pure white (`#FFFFFF`) because they view drawings on a pitch-black modelspace background. When rendered onto white paper, white linework vanishes completely. Conversely, black linework vanishes on dark blueprint presets.

`cad-ir-to-pdf` implements the ITU-R Recommendation BT.709 relative luminance formula:

$$Y_{\text{lum}} = 0.2126 \cdot R_{\text{norm}} + 0.7152 \cdot G_{\text{norm}} + 0.0722 \cdot B_{\text{norm}}$$

### Contrast Rule Engine
1. **On Light Backgrounds ($Y_{\text{bg}} \ge 0.2$)**:
   - Any stroke with $Y_{\text{stroke}} > 0.95$ (pure white or pale yellow) is automatically remapped to the dark contrast fallback color (default `#000000`).
2. **On Dark Backgrounds ($Y_{\text{bg}} < 0.2$)**:
   - Any stroke with $Y_{\text{stroke}} \le 0.10$ (pure black or dark charcoal) is automatically inverted to pure white (`#FFFFFF`).

---

## 6. Presets & Options Configuration Schema

### 6.1 Production Preset Catalog

| Preset Name | Paper Size | Orientation | Background | Stroke Strategy | Primary Application |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`monochrome-arch`** *(Default)* | A4 | Portrait | `#FFFFFF` | Monochromatic Black | Architectural permit submissions, technical drafting. |
| **`presentation-color`** | A4 | Landscape | `#FFFFFF` | TrueColor ACI | Client presentation layouts, colored floorplans. |
| **`dark-blueprint`** | Arch D | Landscape | `#002040` | Cyan / White | Classic engineering blueprints, retro schematic views. |
| **`permit-arch-d`** | Arch D | Landscape | `#FFFFFF` | High-Contrast Black | Large-format 24" × 36" plotting sheets. |
| **`web-mobile-a4`** | A4 | Portrait | `#FFFFFF` | Optimized 0.25pt | Mobile tablet viewers, fast PDF previews. |
| **`metric-construction-a1`** | A1 | Landscape | `#FFFFFF` | Construction Weight | ISO standard civil & structural engineering sets. |

---

### 6.2 Granular Customization Schema (`PdfOptions`)

```python
@dataclass
class PdfOptions:
    paper_size: Optional[str] = None          # 'A4', 'A3', 'A1', 'ARCH_D', 'LETTER', 'TABLOID'
    orientation: Optional[str] = None         # 'portrait' or 'landscape'
    margin_mm: Optional[float] = None         # Boundary margin in millimeters (default 10.0)
    scale_mode: Optional[str] = None          # 'fit' (auto-fit) or 'fixed'
    fixed_scale: Optional[float] = None       # Scale ratio (e.g. 0.01 for 1:100)
    default_line_width_pt: Optional[float] = None # Base stroke weight (clamped [0.05, 50.0])
    line_weight_multiplier: Optional[float] = None # Scale factor applied to all line weights
    background_color: Optional[str] = None    # Hex color string (e.g. '#002040')
    default_stroke_color: Optional[str] = None# Fallback stroke hex
    color_mode: Optional[str] = None          # 'layer', 'monochrome', or 'entity'
    draw_annotations: Optional[bool] = None   # Toggle text labels
    draw_dimensions: Optional[bool] = None    # Toggle dimension strings & leader arrows
    draw_components: Optional[bool] = None    # Toggle block instances
    prune_outliers: Optional[bool] = None     # Enable/disable outlier pruning
```

---

## 7. Public API & Usage Reference

### 7.1 Python SDK

```python
from cad_ir_to_pdf import compile_ir_to_pdf
from cad_ir_to_pdf.config import PdfOptions

# 1. Compile with standard preset
pdf_path = compile_ir_to_pdf(
    ir_source="ir_data.json",
    output_path="drawing_sheet.pdf",
    preset="monochrome-arch"
)

# 2. Compile with custom overrides (A3 Landscape Blueprint)
custom_options = PdfOptions(
    paper_size="A3",
    orientation="landscape",
    background_color="#002040",
    default_stroke_color="#FFFFFF",
    draw_dimensions=False
)

pdf_path_blueprint = compile_ir_to_pdf(
    ir_source=ir_dict,
    output_path="blueprint_a3.pdf",
    preset="presentation-color",
    options=custom_options
)
```

---

### 7.2 Command Line Interface (CLI)

```bash
# Standard compilation
python -m cad_ir_to_pdf.cli input_ir.json -o output.pdf

# Large-format ARCH D blueprint
python -m cad_ir_to_pdf.cli input_ir.json -o blueprint.pdf --preset dark-blueprint --paper-size ARCH_D

# Monochrome A3 Landscape with 1.5x line thickness
python -m cad_ir_to_pdf.cli input_ir.json -o sheet.pdf \
       --preset monochrome-arch \
       --paper-size A3 \
       --orientation landscape \
       --line-weight-multiplier 1.5
```
