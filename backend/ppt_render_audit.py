"""Real PDF/page evidence for the frozen teaching scene, after OOXML audit."""
from collections import Counter
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from pypdf import PdfReader

from ppt_layout_execution import file_digest


def _glyphs(text):
    # The two vertical middle pieces have the same rendered outline. PDF font
    # subsetting can give their shared glyph just one ToUnicode entry. Their
    # left/right positions and original Unicode remain audited in OOXML.
    return Counter(c for c in text.replace("⎥", "⎢") if not c.isspace())


def audit_pdf_scenes(pdf, scenes):
    pages = PdfReader(pdf).pages
    if len(pages) != len(scenes):
        raise ValueError("teaching_pdf_page_count_mismatch")
    reports = []
    for page, scene in zip(pages, scenes, strict=True):
        if abs(float(page.mediabox.width) - scene.width) > 1 or abs(float(page.mediabox.height) - scene.height) > 1:
            raise ValueError("teaching_pdf_geometry_mismatch")
        objects = [o for o in scene.objects if o.kind == "text"] + [e.label_object for e in scene.edges if e.label_object]
        observed = {o.object_id: Counter() for o in objects}

        def visit(text, cm, tm, _font, _size):
            if not text.strip():
                return
            # PDF affine text-to-page transform, without private pypdf APIs.
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = scene.height - (tm[4] * cm[1] + tm[5] * cm[3] + cm[5])
            owners = [o for o in objects if o.x - 1 <= x <= o.x + o.width + 1 and o.y - 1 <= y <= o.y + o.height + 1]
            if len(owners) == 1:
                observed[owners[0].object_id].update(_glyphs(text))

        page.extract_text(visitor_text=visit)
        for obj in objects:
            # PDF extraction orders fallback font runs differently. Verify
            # glyph counts inside each object; OOXML verifies exact text/order.
            if observed[obj.object_id] != _glyphs(obj.text):
                raise ValueError(f"teaching_pdf_object_text_mismatch:{scene.logical_page_id}:{obj.object_id}")
        reports.append({"page_id": scene.logical_page_id, "state_id": scene.state_id,
                        "objects_verified": len(objects), "passed": True})
    return reports


def render_evidence(path, scenes, *, output=None):
    path = Path(path)
    output = Path(output) if output else path.parent
    output.mkdir(parents=True, exist_ok=True)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    pdftoppm = shutil.which("pdftoppm")
    if not soffice or not pdftoppm:
        raise ValueError("teaching_render_tools_unavailable")
    with tempfile.TemporaryDirectory(prefix="ppt-scene-lo-") as profile:
        from slide_deck_renderer import _write_libreoffice_fontconfig
        fontconfig = _write_libreoffice_fontconfig(Path(profile))
        env = {**os.environ, "FONTCONFIG_FILE": str(fontconfig), "FONTCONFIG_PATH": str(fontconfig.parent),
               "XDG_CACHE_HOME": str(Path(profile) / "cache")}
        subprocess.run([soffice, f"-env:UserInstallation={Path(profile).as_uri()}", "--headless", "--convert-to", "pdf", "--outdir", str(output), str(path)],
                       check=True, capture_output=True, timeout=180, env=env)
    pdf = output / path.with_suffix(".pdf").name
    if not pdf.is_file():
        raise ValueError("teaching_pdf_render_missing")
    text_reports = audit_pdf_scenes(pdf, scenes)
    subprocess.run([pdftoppm, "-scale-to", "1200", "-png", str(pdf), str(output / path.stem)],
                   check=True, capture_output=True, timeout=180)
    images = sorted(output.glob(f"{path.stem}-*.png"))
    if len(images) != len(scenes):
        raise ValueError("teaching_render_page_count_mismatch")
    return {"pptx_sha256": file_digest(path), "pdf_sha256": file_digest(pdf),
            "render_page_sha256": [file_digest(p) for p in images], "pdf_object_reports": text_reports,
            "render_engine": subprocess.run([soffice, "--version"], capture_output=True, text=True, check=True, timeout=20).stdout.strip()}
