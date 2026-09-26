# cad-ir-to-pdf: High-Precision Vector PDF Compiler & Blueprint Plotting Engine

<div align="center">

[![Python: 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Engine: ReportLab Vector](https://img.shields.io/badge/Engine-ReportLab%20PostScript-FF6B6B.svg?style=for-the-badge)](#)
[![Format: Vector PDF](https://img.shields.io/badge/Format-Infinite%20Resolution%20Vector-4ECDC4.svg?style=for-the-badge)](#)
[![Validation Suite](https://img.shields.io/badge/Test%20Suite-100%25%20Passing-2ED573.svg?style=for-the-badge)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

**A mathematical vector PDF compiler translating canonical `LAVINCI_CAD_IR_V3` JSON models into publication-grade engineering drawing sheets, featuring affine coordinate projections, cubic Bézier arc subdivision, and canvas rotation matrix stacks.**

*Part of the **La Vinci** engineering initiative by **Saikat Dutta Chowdhury** (Mechanical Engineering).*

</div>

---

## 💡 Engineering Scope & The Vector Precision Problem

In architectural, structural, and mechanical engineering, document review requires **pure vector fidelity**. 

Many automated CAD-to-PDF tools take the shortcut of rasterizing drawing models into bitmap pixels and embedding them in PDF wrappers. Under $800\%$ zoom, line intersections blur into fuzzy pixel grids, text labels become unreadable, and dimension measurements lose legal drafting precision.

**`cad-ir-to-pdf`** constructs native **ReportLab PostScript vector paths**:
* **Infinite Resolution**: Geometry scales losslessly at any magnification level on high-DPI plotters.
* **Affine Coordinate Mapping**: Projects unbounded real-world CAD coordinates into standardized ISO/ANSI drawing sheets with exact aspect-ratio preservation.
* **Rotated Annotation Matrices**: Renders vertical and angled dimensions with canvas state isolation stacks.
* **Luminance Contrast Safety**: Dynamically re-maps stroke colors to guarantee visibility across white paper and dark blueprint themes.

```
[ Input: LAVINCI_CAD_IR_V3 JSON ]
               │
               ▼
┌──────────────────────────────────────────────┐
│          cad-ir-to-pdf Pipeline              │
│                                              │
│  1. Extents & Outlier Isolation              │
│     • Gap clustering + safe text bbox guard  │
│                                              │
│  2. Affine Projection Matrix (2D)            │
│     • Aspect ratio lock & centering          │
│     • Margin padding (ISO A4 to ARCH E)      │
│                                              │
│  3. Curve Decomposition                      │
│     • Subdivides arcs into cubic Béziers     │
│       (Δθ ≤ 90° for sub-micron accuracy)     │
│                                              │
│  4. Rotated Annotation Canvas Isolation      │
│     • saveState() -> translate() -> rotate() │
│                                              │
│  5. Rec. 709 Luminance Contrast Guard        │
│     • Inverts white linework on white sheets │
│     • Inverts dark linework on dark themes   │
└──────────────────────────────────────────────┘
               │
               ▼
[ Output: publication_blueprint.pdf ]
```

---

## 🔬 Computational Geometry & Affine Mathematics

### 1. Affine Projection Matrix (`AffineMatrix2D`)
Transforms raw physical CAD coordinates $\vec{P}_{\text{cad}} = [x, y]^T$ into printable PostScript points $\vec{P}_{\text{pdf}} = [x', y']^T$:
$$\begin{bmatrix} x' \\ y' \\ 1 \end{bmatrix} = \begin{bmatrix} S & 0 & t_x \\ 0 & S & t_y \\ 0 & 0 & 1 \end{bmatrix} \begin{bmatrix} x \\ y \\ 1 \end{bmatrix}$$
Where the uniform scale factor $S$ prevents non-uniform distortion:
$$S = \min\left(\frac{W_{\text{paper}} - 2M}{X_{\max} - X_{\min}}, \; \frac{H_{\text{paper}} - 2M}{Y_{\max} - Y_{\min}}\right)$$

### 2. Cubic Bézier Arc Subdivision
Because the PDF specification lacks native analytic circular arc drawing commands, arcs are decomposed into cubic Bézier splines ($\vec{P}_0, \vec{P}_1, \vec{P}_2, \vec{P}_3$). For spans $\Delta\theta \le 90^\circ$:
$$\alpha = \frac{4}{3} \tan\left(\frac{\Delta\theta}{4}\right)$$
$$\vec{P}_1 = \vec{P}_0 + \alpha R \begin{bmatrix} -\sin\theta_s \\ \cos\theta_s \end{bmatrix}, \quad \vec{P}_2 = \vec{P}_3 - \alpha R \begin{bmatrix} -\sin\theta_e \\ \cos\theta_e \end{bmatrix}$$
Arcs spanning $> 90^\circ$ are automatically segmented into multiple Bézier curves, eliminating visual facetting.

### 3. Rotational Text State Isolation (The Bugatti Chiron Case)
To render dimensions and annotations rotated along mechanical surfaces without corrupting the global coordinate system:
```python
c.saveState()
c.translate(transformed_x, transformed_y)
c.rotate(annotation.rotation)
c.drawString(0, 0, annotation.clean_text)
c.restoreState()
```

### 4. Rec. 709 Relative Luminance
Calculates stroke luminance to guarantee legal document readability:
$$Y = 0.2126R + 0.7152G + 0.0722B$$
White lines on white paper ($Y > 0.95$) remap to pure black; black lines on dark blueprints remap to pure white.

---

## ⚡ Quick Start

### Installation
```bash
pip install -e products/cad-ir-to-pdf
```

### Python SDK
```python
from cad_ir_to_pdf import compile_ir_to_pdf
from cad_ir_to_pdf.config import PdfOptions

# 1. Compile standard permit blueprint (A1 Landscape)
compile_ir_to_pdf("chassis_ir.json", "chassis_blueprint.pdf", preset="monochrome-arch")

# 2. Compile presentation-grade dark blueprint (ARCH D 24x36)
compile_ir_to_pdf("chassis_ir.json", "chassis_retro.pdf", preset="dark-blueprint")

# 3. Surgical overrides (A3 Landscape with custom stroke scale)
options = PdfOptions(paper_size="A3", orientation="landscape", line_weight_multiplier=1.2)
compile_ir_to_pdf("chassis_ir.json", "custom.pdf", preset="presentation-color", options=options)
```

### Command Line Interface (CLI)
```bash
# Standard compilation
python -m cad_ir_to_pdf.cli drawing_ir.json -o blueprint.pdf

# Formal A1 construction sheet
python -m cad_ir_to_pdf.cli drawing_ir.json -o permit.pdf --preset monochrome-arch --paper-size A1
```

---

## 📄 License

Licensed under the [MIT License](LICENSE).
