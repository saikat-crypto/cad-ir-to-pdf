# cad-ir-to-pdf

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://python.org)
[![Output: Vector%20PDF](https://img.shields.io/badge/Output-Vector%20PDF-red.svg)](#)
[![Ecosystem](https://img.shields.io/badge/Project-La%20Vinci-purple.svg)](#)

**High-Fidelity Vector CAD to PDF Compiler.**  
Converts a [`LAVINCI_CAD_IR_V3`](https://github.com/saikat-crypto/cad-extractor-ir) JSON payload into publication-grade vector PDF drawings with pure native vector geometry and zero pixelation at any zoom level.

*Engineered by **Saikat Dutta Chowdhury** as part of the **La Vinci** engineering initiative.*

</div>

---

## 💡 Pipeline Position

This package is a core downstream spoke of the La Vinci Hub-and-Spoke CAD architecture:

```
DWG / DXF ──► cad-extractor-ir ──► LAVINCI_CAD_IR_V3 ──► cad-ir-to-pdf ──► Vector PDF
```

---

## ✨ Features

- **100% Native PDF Vector Streams**: Lines, polylines, arcs, circles, and annotations are rendered into native PostScript vector streams (`pdfgen.canvas`). Infinite clarity at 6400% zoom.
- **Analytic Arc-to-Bézier Subdivision**: Implements cubic Bézier arc subdivision maintaining sub-millimeter geometric accuracy across all zoom levels.
- **Hierarchical Block & Component Flattening**: Evaluates 2D affine transformation matrices (`T · R · S`) on nested CAD blocks (`INSERT`), accurately scaling, rotating, and projecting doors, windows, and fixtures.
- **Isotropic Auto-Fit Viewport**: Automatically computes full-extent bounding boxes and centers drawings on target paper sizes with clean margins, preserving 1:1 aspect ratios.
- **Text & MText Sanitization**: Strips raw AutoCAD formatting tags (e.g. `\P`, font overrides) while preserving multi-line room labels, scales, and dimensional text.
- **Modular Presets Architecture**: Ready for one-to-many PDF output configurations (A4, A3, Arch D, landscape/portrait, Model/Paper space).

---

## 📐 Active Default Preset: `presentation-fit-vector`

| Parameter | Value | Description |
| :--- | :--- | :--- |
| **Paper Size** | **`A3`** | Universal architectural presentation format (420 x 297 mm / 1190.55 x 841.89 pt). |
| **Orientation** | **`Landscape`** | Standard widescreen blueprint layout. |
| **Target Space** | **`Model`** | Automatically targets Model space geometry to ensure true building extents are centered and scaled. |
| **Viewport Scale** | **`Fit`** | Isotropic auto-fit with 12mm boundary margins. |
| **Line Width** | **`0.6 pt`** | Crisp, balanced stroke weight for floor plans. |
| **Background** | **`#FFFFFF`** | Pure white presentation canvas. |
| **Default Color** | **`#1A1A1A`** | High-contrast charcoal/slate with layer color preservation. |

---

## 🚀 Installation

```bash
git clone https://github.com/saikat-crypto/cad-ir-to-pdf.git
cd cad-ir-to-pdf
pip install -e .
```

---

## 💻 CLI Usage

### Basic Compilation
```bash
cad-ir-to-pdf floor_plan.json -o floor_plan.pdf
```

### Overriding Paper Size and Orientation
```bash
cad-ir-to-pdf floor_plan.json -o permit_sheet.pdf --paper-size ARCH_D --orientation landscape
cad-ir-to-pdf floor_plan.json -o quick_sheet.pdf --preset quick-preview-a4
```

### Options
```text
usage: cad-ir-to-pdf [-h] [-o OUTPUT]
                     [--preset {presentation-fit-vector,quick-preview-a4,permit-arch-d}]
                     [--paper-size {A4,A3,A2,A1,A0,LETTER,ARCH_D}]
                     [--orientation {landscape,portrait}]
                     input

positional arguments:
  input                 Path to input LAVINCI_CAD_IR_V3 JSON file.

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Path to output PDF file. (Default: <input_stem>.pdf)
  --preset {presentation-fit-vector,quick-preview-a4,permit-arch-d}
                        PDF styling and layout preset (default: presentation-fit-vector).
  --paper-size {A4,A3,A2,A1,A0,LETTER,ARCH_D}
                        Override paper size.
  --orientation {landscape,portrait}
                        Override page orientation.
```

---

## 🐍 Python API

```python
from cad_ir_to_pdf import compile_ir_to_pdf, PRESETS

# Compile with default presentation preset
pdf_path = compile_ir_to_pdf("floor_plan.json", "output.pdf")

# Or compile using a specific preset
arch_d_preset = PRESETS["permit-arch-d"]
compile_ir_to_pdf("floor_plan.json", "output_arch_d.pdf", preset=arch_d_preset)
```

---

## 📄 License

MIT License. Copyright (c) 2026 La Vinci.
