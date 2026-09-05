import pytest
from pathlib import Path
from cad_ir_to_pdf.compiler import compile_ir_to_pdf
import pymupdf


def test_live_ir_to_pdf_roundtrip(tmp_path):
    fixture_path = Path(__file__).parent / "fixtures" / "live_extracted.json"
    fallback_path = Path(__file__).resolve().parent.parent.parent.parent / "experiments" / "e2e_demo" / "live_extracted.json"
    ir_path = fixture_path if fixture_path.exists() else fallback_path
    assert ir_path.exists(), "live_extracted.json should exist"

    out_pdf = tmp_path / "live_test_output.pdf"
    res = compile_ir_to_pdf(ir_path, out_pdf)

    assert res.exists()
    assert res.stat().st_size > 10000

    # Verify PDF structure using pymupdf
    doc = pymupdf.open(str(res))
    assert len(doc) == 1
    page = doc[0]
    rect = page.rect
    # Check A3 Landscape dimensions (~1190.55 x 841.89 pt)
    assert abs(rect.width - 1190.55) < 1.0
    assert abs(rect.height - 841.89) < 1.0

    drawings = page.get_drawings()
    assert len(drawings) > 1000, f"Expected >1000 vector drawing paths, got {len(drawings)}"

    text = page.get_text()
    assert "LIVING ROOM" in text
    assert "KITCHEN" in text
    assert "BEDROOM" in text
    doc.close()
