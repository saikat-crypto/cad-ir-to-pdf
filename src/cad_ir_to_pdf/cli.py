"""
cli.py — Command-Line Interface for cad-ir-to-pdf.
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

from .config import PRESETS, DEFAULT_PRESET
from .compiler import compile_ir_to_pdf


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cad-ir-to-pdf",
        description="High-fidelity vector CAD compiler converting La Vinci IR v3 into publication-grade vector PDF drawings.",
    )
    parser.add_argument("input", help="Path to input LAVINCI_CAD_IR_V3 JSON file.")
    parser.add_argument("-o", "--output", help="Path to output PDF file. (Default: <input_stem>.pdf)")
    parser.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        default="presentation-fit-vector",
        help="PDF styling and layout preset (default: presentation-fit-vector).",
    )
    parser.add_argument(
        "--paper-size",
        choices=["A4", "A3", "A2", "A1", "A0", "LETTER", "ARCH_D"],
        help="Override paper size.",
    )
    parser.add_argument(
        "--orientation",
        choices=["landscape", "portrait"],
        help="Override page orientation.",
    )

    args = parser.parse_args()
    input_p = Path(args.input)
    if not input_p.exists():
        print(f"Error: Input file does not exist: {input_p}", file=sys.stderr)
        return 1

    output_p = Path(args.output) if args.output else input_p.with_suffix(".pdf")

    # Load preset
    preset = PRESETS.get(args.preset, DEFAULT_PRESET)

    # Apply overrides if provided
    if args.paper_size or args.orientation:
        # Clone preset
        preset = type(preset)(
            name=f"{preset.name}-custom",
            paper_size=args.paper_size or preset.paper_size,
            orientation=args.orientation or preset.orientation,
            margin_mm=preset.margin_mm,
            scale_mode=preset.scale_mode,
            default_line_width_pt=preset.default_line_width_pt,
            background_color=preset.background_color,
            default_stroke_color=preset.default_stroke_color,
            draw_annotations=preset.draw_annotations,
            draw_components=preset.draw_components,
            font_name=preset.font_name,
        )

    print(f"Compiling CAD IR '{input_p.name}' -> '{output_p.name}' [Preset: {preset.name}, Paper: {preset.paper_size} {preset.orientation}]...")
    try:
        res = compile_ir_to_pdf(input_p, output_p, preset=preset)
        print(f"Success! Vector PDF compiled to: {res.resolve()} ({res.stat().st_size / 1024:.1f} KB)")
        return 0
    except Exception as ex:
        print(f"Compilation failed: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
