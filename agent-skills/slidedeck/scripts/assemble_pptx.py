#!/usr/bin/env python3
"""
Generic PPTX Assembly Script — SlideDeck Skill

Assembles PNG slide images into a branded PPTX file with optional
template decorations (logo, gradient, copyright, page numbers) and
speaker notes injection.

Usage:
  1. Copy this script to your deck's output directory
  2. Update SLIDES list, TITLE_TEXT, SUBTITLE_TEXT, OUTPUT path
  3. Set TEMPLATE to your .pptx template path (or None for plain)
  4. Configure BRANDING dict (or set enabled=False for plain slides)
  5. Run: python3 assemble_pptx.py

Requirements:
  - Python 3.9+
  - No external dependencies (uses only stdlib: pathlib, shutil, zipfile, re)
"""

from pathlib import Path
import shutil
import zipfile
import re

# ─── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
TEMPLATE = None  # Path to .pptx template, or None for plain PPTX
OUTPUT = SCRIPT_DIR / "My-Presentation.pptx"
WORK_DIR = Path("/tmp/pptx_assembly")  # Override with <WORKSPACE>/tmp/pptx_assembly

# Slide PNGs — ordered list of content slide images
SLIDES = [
    "Slide_01_Example.png",
    # Add more slides here...
]

# Title slide content (page 0 — no PNG, no page number)
TITLE_TEXT = "Presentation Title"
SUBTITLE_TEXT = "Your Subtitle Here"

# Title & content layout XML filenames from the template
TITLE_LAYOUT = "slideLayout1.xml"
CONTENT_LAYOUT = "slideLayout1.xml"    # Use "Blank" layout; override for templates

# ─── Branding Configuration ───────────────────────────────────────────────────
BRANDING = {
    "enabled": False,                    # Set True to embed decorations
    "logo_image": "image17.png",         # Logo filename in template media/
    "logo_position": (196678, 4777740),  # EMU (x, y) — bottom-left
    "logo_size": (995378, 365760),       # EMU (cx, cy)
    "gradient_image": "image28.jpg",     # Background gradient filename
    "copyright_text": "",                # e.g., "© 2026 Company. All Rights Reserved."
    "page_numbers": True,                # Automatic slide numbers
    "page_number_start": 0,              # 0 = title is page 0, content starts at 1
    "notes_font_size": 1100,             # 1100 = 11pt in hundredths of a point
}


# ─── Speaker Notes Parser ────────────────────────────────────────────────────

def parse_speaker_notes(notes_path: Path) -> list[str]:
    """Parse Speaker-Notes.md into per-slide plain text notes."""
    content = notes_path.read_text(encoding="utf-8")

    # Split on "## Slide N:" headers
    sections = re.split(r'\n## Slide \d+:', content)

    notes = []
    for section in sections[1:]:  # skip preamble
        # Extract until next --- or ## Timing
        text = re.split(r'\n---|\n## Timing', section)[0]

        # Clean markdown formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # italic
        text = re.sub(r'> ', '', text)                    # blockquotes
        text = re.sub(r'```[a-z]*\n', '', text)          # code fence open
        text = re.sub(r'```\n?', '', text)               # code fence close
        text = re.sub(r'#{1,3} ', '', text)              # headers in notes
        text = re.sub(r'\n{3,}', '\n\n', text)           # excessive newlines
        text = text.strip()

        notes.append(text)

    # Pad if fewer notes than slides
    while len(notes) < len(SLIDES):
        notes.append("")

    return notes[:len(SLIDES)]


# ─── Slide XML Generators ────────────────────────────────────────────────────

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
NS_DECL = ' '.join(f'xmlns:{k}="{v}"' for k, v in NS.items())

EMU_W = 12192000   # 1920px at 96dpi
EMU_H = 6858000    # 1080px at 96dpi


def make_title_slide_xml() -> str:
    """Generate XML for the title slide (page 0, text only).

    Uses absolute-positioned text boxes instead of placeholder types.
    Placeholders (ctrTitle/subTitle) require the slide layout to define
    their position and size. Our minimal Blank layout has no such
    definitions, so PowerPoint renders them at (0,0) causing overlap.
    """
    # Escape XML special chars in title/subtitle
    title_esc = TITLE_TEXT.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    subtitle_esc = SUBTITLE_TEXT.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Title: centered, at ~1/3 height (y=2286000 EMU = ~2.5")
    # Size: 10" wide × 1.5" tall, centered horizontally
    title_x = 1143000    # (12192000 - 9906000) / 2
    title_y = 2286000    # ~1/3 down
    title_cx = 9906000   # ~10.3"
    title_cy = 1371600   # ~1.4"

    # Subtitle: centered, below title
    sub_y = 3886200      # ~4.0" down
    sub_cy = 914400      # ~0.95"

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld {NS_DECL}>
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
        <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm>
      </p:grpSpPr>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="2" name="Title"/>
          <p:cNvSpPr txBox="1"/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{title_x}" y="{title_y}"/><a:ext cx="{title_cx}" cy="{title_cy}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr anchor="ctr"/>
          <a:lstStyle/>
          <a:p>
            <a:pPr algn="ctr"/>
            <a:r>
              <a:rPr lang="en-US" sz="4400" b="1" dirty="0">
                <a:solidFill><a:srgbClr val="333333"/></a:solidFill>
                <a:latin typeface="Calibri Light"/>
              </a:rPr>
              <a:t>{title_esc}</a:t>
            </a:r>
          </a:p>
        </p:txBody>
      </p:sp>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="3" name="Subtitle"/>
          <p:cNvSpPr txBox="1"/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{title_x}" y="{sub_y}"/><a:ext cx="{title_cx}" cy="{sub_cy}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr anchor="t"/>
          <a:lstStyle/>
          <a:p>
            <a:pPr algn="ctr"/>
            <a:r>
              <a:rPr lang="en-US" sz="2400" dirty="0">
                <a:solidFill><a:srgbClr val="666666"/></a:solidFill>
                <a:latin typeface="Calibri"/>
              </a:rPr>
              <a:t>{subtitle_esc}</a:t>
            </a:r>
          </a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>'''


def make_content_slide_xml(branding: dict) -> str:
    """Generate XML for a content slide with optional decorations."""
    bg_xml = ""
    decorations = ""

    if branding["enabled"]:
        # Gradient background fill
        if branding.get("gradient_image"):
            bg_xml = f'''  <p:bg>
    <p:bgPr>
      <a:blipFill dpi="0" rotWithShape="1">
        <a:blip r:embed="rId5"/>
        <a:stretch><a:fillRect/></a:stretch>
      </a:blipFill>
      <a:effectLst/>
    </p:bgPr>
  </p:bg>'''

        # Logo
        if branding.get("logo_image"):
            lx, ly = branding["logo_position"]
            lcx, lcy = branding["logo_size"]
            decorations += f'''
      <p:pic>
        <p:nvPicPr>
          <p:cNvPr id="10" name="Logo"/>
          <p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>
          <p:nvPr/>
        </p:nvPicPr>
        <p:blipFill>
          <a:blip r:embed="rId4"/>
          <a:stretch><a:fillRect/></a:stretch>
        </p:blipFill>
        <p:spPr>
          <a:xfrm><a:off x="{lx}" y="{ly}"/><a:ext cx="{lcx}" cy="{lcy}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
      </p:pic>'''

        # Copyright text
        if branding.get("copyright_text"):
            decorations += f'''
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="11" name="Copyright"/>
          <p:cNvSpPr txBox="1"/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="1371600" y="6553200"/><a:ext cx="9601200" cy="228600"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr wrap="square" rtlCol="0"/>
          <a:lstStyle/>
          <a:p>
            <a:pPr algn="l"/>
            <a:r>
              <a:rPr lang="en-US" sz="600" i="1" dirty="0">
                <a:solidFill><a:srgbClr val="A6A6A6"/></a:solidFill>
              </a:rPr>
              <a:t>{branding["copyright_text"]}</a:t>
            </a:r>
          </a:p>
        </p:txBody>
      </p:sp>'''

    # Page numbers work independently of branding
    if branding.get("page_numbers"):
        decorations += '''
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="12" name="Slide Number"/>
          <p:cNvSpPr txBox="1"/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="11277600" y="6553200"/><a:ext cx="609600" cy="228600"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
        <p:txBody>
          <a:bodyPr wrap="square" rtlCol="0"/>
          <a:lstStyle/>
          <a:p>
            <a:pPr algn="r"/>
            <a:fld id="{B6F15528-F159-4107-2D15-F9CC29DEADBE}" type="slidenum">
              <a:rPr lang="en-US" sz="1100" dirty="0">
                <a:solidFill><a:srgbClr val="A6A6A6"/></a:solidFill>
              </a:rPr>
              <a:t>&lt;#&gt;</a:t>
            </a:fld>
          </a:p>
        </p:txBody>
      </p:sp>'''

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld {NS_DECL}>
  <p:cSld>
{bg_xml}
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
        <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm>
      </p:grpSpPr>
      <p:pic>
        <p:nvPicPr>
          <p:cNvPr id="4" name="Slide Image"/>
          <p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>
          <p:nvPr/>
        </p:nvPicPr>
        <p:blipFill>
          <a:blip r:embed="rId2"/>
          <a:stretch><a:fillRect/></a:stretch>
        </p:blipFill>
        <p:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="{EMU_W}" cy="{EMU_H}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
      </p:pic>{decorations}
    </p:spTree>
  </p:cSld>
</p:sld>'''


# ─── Relationship & Content Type Helpers ──────────────────────────────────────

def make_title_slide_rels(layout: str, has_layouts: bool = True) -> str:
    if has_layouts:
        return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/{layout}"/>
</Relationships>'''
    else:
        return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>'''


def make_content_slide_rels(layout: str, image_file: str, branding: dict, has_layouts: bool = True) -> str:
    rels = []
    if has_layouts:
        rels.append(f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/{layout}"/>')
    rels.append(f'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{image_file}"/>')
    if branding["enabled"]:
        if branding.get("logo_image"):
            rels.append(f'<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{branding["logo_image"]}"/>')
        if branding.get("gradient_image"):
            rels.append(f'<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{branding["gradient_image"]}"/>')

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {chr(10).join("  " + r for r in rels)}
</Relationships>'''


# ─── Speaker Notes Injection ─────────────────────────────────────────────────

def insert_speaker_notes(notes: list[str]):
    """Insert speaker notes into notesSlide XML for each slide."""
    slides_dir = WORK_DIR / "ppt" / "slides"
    notes_dir = WORK_DIR / "ppt" / "notesSlides"
    notes_rels_dir = notes_dir / "_rels"
    notes_dir.mkdir(exist_ok=True)
    notes_rels_dir.mkdir(exist_ok=True)

    ct_path = WORK_DIR / "[Content_Types].xml"
    ct_content = ct_path.read_text(encoding="utf-8")

    notes_layouts = list((WORK_DIR / "ppt" / "notesMasters").glob("notesMaster*.xml")) if (WORK_DIR / "ppt" / "notesMasters").exists() else []
    notes_master_rel = "../notesMasters/notesMaster1.xml" if notes_layouts else ""

    font_size = BRANDING.get("notes_font_size", 1100)

    for i, note_text in enumerate(notes):
        if not note_text:
            continue

        slide_num = 101 + i  # offset for title page
        slide_file = f"slide{slide_num}.xml"
        notes_file = f"notesSlide{slide_num}.xml"

        # Escape XML special chars
        note_text_escaped = (note_text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

        # Split into paragraphs
        paragraphs = note_text_escaped.split("\n")
        para_xml = []
        for para in paragraphs:
            para_xml.append(f'''            <a:p>
              <a:r>
                <a:rPr lang="en-US" sz="{font_size}" dirty="0"/>
                <a:t>{para}</a:t>
              </a:r>
            </a:p>''')
        paras_joined = "\n".join(para_xml)

        notes_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notes {NS_DECL}>
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
        <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm>
      </p:grpSpPr>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="2" name="Slide Image Placeholder 1"/>
          <p:cNvSpPr><a:spLocks noGrp="1" noRot="1" noChangeAspect="1"/></p:cNvSpPr>
          <p:nvPr><p:ph type="sldImg"/></p:nvPr>
        </p:nvSpPr>
        <p:spPr/>
      </p:sp>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="3" name="Notes Placeholder 2"/>
          <p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>
          <p:nvPr><p:ph type="body" idx="1"/></p:nvPr>
        </p:nvSpPr>
        <p:spPr/>
        <p:txBody>
          <a:bodyPr/>
          <a:lstStyle/>
{paras_joined}
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:notes>'''

        (notes_dir / notes_file).write_text(notes_xml, encoding="utf-8")

        # Notes rels
        rels_entries = [f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="../slides/{slide_file}"/>']
        if notes_master_rel:
            rels_entries.append(f'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster" Target="{notes_master_rel}"/>')

        notes_rels_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {chr(10).join("  " + r for r in rels_entries)}
</Relationships>'''
        (notes_rels_dir / f"{notes_file}.rels").write_text(notes_rels_xml, encoding="utf-8")

        # Add notesSlide relationship to slide rels
        slide_rels_path = slides_dir / "_rels" / f"{slide_file}.rels"
        slide_rels = slide_rels_path.read_text(encoding="utf-8")
        notes_rel = f'<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/{notes_file}"/>'
        slide_rels = slide_rels.replace("</Relationships>", f"  {notes_rel}\n</Relationships>")
        slide_rels_path.write_text(slide_rels, encoding="utf-8")

        # Update Content_Types
        override = f'<Override PartName="/ppt/notesSlides/{notes_file}" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>'
        if f"/ppt/notesSlides/{notes_file}" not in ct_content:
            ct_content = ct_content.replace("</Types>", f"  {override}\n</Types>")

    ct_path.write_text(ct_content, encoding="utf-8")
    print(f"Inserted speaker notes for {sum(1 for n in notes if n)} slides")


# ─── Main Assembly ────────────────────────────────────────────────────────────

def assemble():
    print("=" * 60)
    print("PPTX Assembly")
    print("=" * 60)

    # 1. Clean and unpack template
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True)

    if TEMPLATE and TEMPLATE.exists():
        print(f"Unpacking template: {TEMPLATE.name}")
        with zipfile.ZipFile(TEMPLATE, 'r') as z:
            z.extractall(WORK_DIR)
    else:
        print("No template — creating minimal PPTX structure")
        _create_minimal_pptx_structure()

    slides_dir = WORK_DIR / "ppt" / "slides"
    slides_rels_dir = slides_dir / "_rels"
    media_dir = WORK_DIR / "ppt" / "media"
    slides_dir.mkdir(parents=True, exist_ok=True)
    slides_rels_dir.mkdir(exist_ok=True)
    media_dir.mkdir(exist_ok=True)

    # Detect if template has slide layouts (no-template mode won't)
    has_layouts = (WORK_DIR / "ppt" / "slideLayouts").exists()

    # 2. Remove existing slides from template
    for f in slides_dir.glob("slide*.xml"):
        f.unlink()
    for f in slides_rels_dir.glob("slide*.xml.rels"):
        f.unlink()

    # 3. Create title slide (slide100)
    print(f"Creating title slide: {TITLE_TEXT}")
    (slides_dir / "slide100.xml").write_text(make_title_slide_xml(), encoding="utf-8")
    (slides_rels_dir / "slide100.xml.rels").write_text(
        make_title_slide_rels(TITLE_LAYOUT, has_layouts), encoding="utf-8")

    # 4. Create content slides (slide101, slide102, ...)
    actual_slide_count = 0
    for i, slide_png in enumerate(SLIDES):
        slide_num = 101 + i
        src = SCRIPT_DIR / slide_png
        if not src.exists():
            print(f"  WARN: {slide_png} not found — skipping")
            continue

        img_name = f"slideImage{slide_num}.png"
        shutil.copy2(src, media_dir / img_name)

        (slides_dir / f"slide{slide_num}.xml").write_text(
            make_content_slide_xml(BRANDING), encoding="utf-8")
        (slides_rels_dir / f"slide{slide_num}.xml.rels").write_text(
            make_content_slide_rels(CONTENT_LAYOUT, img_name, BRANDING, has_layouts), encoding="utf-8")

        actual_slide_count += 1
        print(f"  Slide {i+1}: {slide_png}")

    # 5. Update presentation.xml
    _update_presentation_xml()

    # 6. Update [Content_Types].xml
    _update_content_types()

    # 7. Speaker notes
    notes_path = SCRIPT_DIR / "Speaker-Notes.md"
    if notes_path.exists():
        print("Inserting speaker notes...")
        notes = parse_speaker_notes(notes_path)
        insert_speaker_notes(notes)
    else:
        print("No Speaker-Notes.md found — skipping notes")

    # 8. Clean unreferenced template slides
    _clean_unreferenced()

    # 9. Pack into PPTX
    print(f"Packing PPTX...")
    with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(WORK_DIR.rglob("*")):
            if fp.is_file():
                zf.write(fp, fp.relative_to(WORK_DIR))

    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"\n✓ Output: {OUTPUT}")
    print(f"  Size: {size_mb:.1f} MB")


def _update_presentation_xml():
    """Update presentation.xml with our slide list and page numbering."""
    pres_path = WORK_DIR / "ppt" / "presentation.xml"
    if not pres_path.exists():
        return

    pres = pres_path.read_text(encoding="utf-8")

    # Remove existing sldIdLst (both self-closing and open/close forms)
    pres = re.sub(r'<p:sldIdLst/>', '', pres)
    pres = re.sub(r'<p:sldIdLst>.*?</p:sldIdLst>', '', pres, flags=re.DOTALL)

    # Build new slide ID list
    slide_ids = []
    base_id = 256
    # Title slide
    slide_ids.append(f'<p:sldId id="{base_id}" r:id="rId100"/>')

    # Content slides
    for i in range(len(SLIDES)):
        slide_ids.append(f'<p:sldId id="{base_id + 1 + i}" r:id="rId{101 + i}"/>')

    sld_list = f'<p:sldIdLst>\n    {chr(10).join("    " + s for s in slide_ids)}\n  </p:sldIdLst>'

    # Insert before sldSz
    pres = pres.replace('<p:sldSz', f'{sld_list}\n  <p:sldSz')

    # Set firstSlideNum for page numbering
    start_num = BRANDING.get("page_number_start", 0)
    if 'firstSlideNum' in pres:
        pres = re.sub(r'firstSlideNum="\d+"', f'firstSlideNum="{start_num}"', pres)
    else:
        pres = pres.replace('<p:sldSz', f'firstSlideNum="{start_num}" <p:sldSz')

    pres_path.write_text(pres, encoding="utf-8")

    # Update presentation.xml.rels
    pres_rels_path = WORK_DIR / "ppt" / "_rels" / "presentation.xml.rels"
    if pres_rels_path.exists():
        pres_rels = pres_rels_path.read_text(encoding="utf-8")

        # Remove old slide rels
        pres_rels = re.sub(r'<Relationship[^>]*Type="[^"]*relationships/slide"[^>]*/>', '', pres_rels)

        # Add our slide rels
        new_rels = [f'<Relationship Id="rId100" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide100.xml"/>']
        for i in range(len(SLIDES)):
            new_rels.append(f'<Relationship Id="rId{101+i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{101+i}.xml"/>')

        pres_rels = pres_rels.replace("</Relationships>", "\n".join("  " + r for r in new_rels) + "\n</Relationships>")
        pres_rels_path.write_text(pres_rels, encoding="utf-8")


def _update_content_types():
    """Update [Content_Types].xml with our slide entries."""
    ct_path = WORK_DIR / "[Content_Types].xml"
    if not ct_path.exists():
        return

    ct = ct_path.read_text(encoding="utf-8")

    # Remove old slide overrides
    ct = re.sub(r'<Override PartName="/ppt/slides/slide\d+\.xml"[^/]*/>', '', ct)

    # Add our slide overrides
    overrides = [f'<Override PartName="/ppt/slides/slide100.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>']
    for i in range(len(SLIDES)):
        overrides.append(f'<Override PartName="/ppt/slides/slide{101+i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>')

    # Add PNG extension if missing (check exact attribute, not substring)
    if 'Extension="png"' not in ct:
        overrides.append('<Default Extension="png" ContentType="image/png"/>')

    ct = ct.replace("</Types>", "\n".join("  " + o for o in overrides) + "\n</Types>")
    ct_path.write_text(ct, encoding="utf-8")


def _clean_unreferenced():
    """Remove slides from template that we don't use."""
    slides_dir = WORK_DIR / "ppt" / "slides"
    our_slides = {f"slide{100 + i}.xml" for i in range(len(SLIDES) + 1)}

    for f in slides_dir.glob("slide*.xml"):
        if f.name not in our_slides:
            f.unlink()
            rels = slides_dir / "_rels" / f"{f.name}.rels"
            if rels.exists():
                rels.unlink()


def _create_minimal_pptx_structure():
    """Create a valid PPTX structure with slide master, layout, and theme.

    PowerPoint requires at minimum: presentation.xml, a slideMaster,
    a slideLayout, and a theme. Without these, PowerPoint shows a repair
    dialog or refuses to open the file.
    """
    # ── [Content_Types].xml ──────────────────────────────────────────────
    ct = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="jpg" ContentType="image/jpeg"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>
</Types>'''
    (WORK_DIR / "[Content_Types].xml").write_text(ct, encoding="utf-8")

    # ── _rels/.rels ──────────────────────────────────────────────────────
    rels_dir = WORK_DIR / "_rels"
    rels_dir.mkdir()
    (rels_dir / ".rels").write_text('''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>''', encoding="utf-8")

    # ── ppt/presentation.xml ─────────────────────────────────────────────
    ppt_dir = WORK_DIR / "ppt"
    ppt_dir.mkdir()
    (ppt_dir / "presentation.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation {NS_DECL}
  xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"
  saveSubsetFonts="1" firstSlideNum="0">
  <p:sldMasterIdLst>
    <p:sldMasterId id="2147483648" r:id="rId1"/>
  </p:sldMasterIdLst>
  <p:sldIdLst/>
  <p:sldSz cx="{EMU_W}" cy="{EMU_H}"/>
  <p:notesSz cx="{EMU_H}" cy="{EMU_W}"/>
</p:presentation>''', encoding="utf-8")

    # ── ppt/_rels/presentation.xml.rels ──────────────────────────────────
    ppt_rels_dir = ppt_dir / "_rels"
    ppt_rels_dir.mkdir()
    (ppt_rels_dir / "presentation.xml.rels").write_text('''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster" Target="notesMasters/notesMaster1.xml"/>
</Relationships>''', encoding="utf-8")

    # ── ppt/slideMasters/slideMaster1.xml ────────────────────────────────
    masters_dir = ppt_dir / "slideMasters"
    masters_dir.mkdir()
    (masters_dir / "slideMaster1.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster {NS_DECL}>
  <p:cSld>
    <p:bg>
      <p:bgRef idx="1001">
        <a:schemeClr val="bg1"/>
      </p:bgRef>
    </p:bg>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
        <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm>
      </p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1"
    accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5"
    accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst>
    <p:sldLayoutId id="2147483649" r:id="rId1"/>
  </p:sldLayoutIdLst>
</p:sldMaster>''', encoding="utf-8")

    # slideMaster1 rels
    masters_rels = masters_dir / "_rels"
    masters_rels.mkdir()
    (masters_rels / "slideMaster1.xml.rels").write_text('''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>''', encoding="utf-8")

    # ── ppt/slideLayouts/slideLayout1.xml (Blank) ────────────────────────
    layouts_dir = ppt_dir / "slideLayouts"
    layouts_dir.mkdir()
    (layouts_dir / "slideLayout1.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout {NS_DECL} type="blank" preserve="1">
  <p:cSld name="Blank">
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
        <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm>
      </p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>''', encoding="utf-8")

    # slideLayout1 rels
    layouts_rels = layouts_dir / "_rels"
    layouts_rels.mkdir()
    (layouts_rels / "slideLayout1.xml.rels").write_text('''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>''', encoding="utf-8")

    # ── ppt/theme/theme1.xml (minimal Office theme) ──────────────────────
    theme_dir = ppt_dir / "theme"
    theme_dir.mkdir()
    (theme_dir / "theme1.xml").write_text('''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Minimal">
  <a:themeElements>
    <a:clrScheme name="Office">
      <a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
      <a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="44546A"/></a:dk2>
      <a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>
      <a:accent1><a:srgbClr val="4472C4"/></a:accent1>
      <a:accent2><a:srgbClr val="ED7D31"/></a:accent2>
      <a:accent3><a:srgbClr val="A5A5A5"/></a:accent3>
      <a:accent4><a:srgbClr val="FFC000"/></a:accent4>
      <a:accent5><a:srgbClr val="5B9BD5"/></a:accent5>
      <a:accent6><a:srgbClr val="70AD47"/></a:accent6>
      <a:hlink><a:srgbClr val="0563C1"/></a:hlink>
      <a:folHlink><a:srgbClr val="954F72"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Office">
      <a:majorFont>
        <a:latin typeface="Calibri Light"/>
        <a:ea typeface=""/>
        <a:cs typeface=""/>
      </a:majorFont>
      <a:minorFont>
        <a:latin typeface="Calibri"/>
        <a:ea typeface=""/>
        <a:cs typeface=""/>
      </a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Office">
      <a:fillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:fillStyleLst>
      <a:lnStyleLst>
        <a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
      </a:lnStyleLst>
      <a:effectStyleLst>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
      </a:effectStyleLst>
      <a:bgFillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
  <a:objectDefaults/>
  <a:extraClrSchemeLst/>
</a:theme>''', encoding="utf-8")

    # ── ppt/notesMasters/notesMaster1.xml ──────────────────────────────
    # Required when notesSlides exist — defines placeholder positions
    masters_notes_dir = ppt_dir / "notesMasters"
    masters_notes_dir.mkdir()
    (masters_notes_dir / "notesMaster1.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notesMaster {NS_DECL}>
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
        <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm>
      </p:grpSpPr>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="2" name="Slide Image Placeholder 1"/>
          <p:cNvSpPr><a:spLocks noGrp="1" noRot="1" noChangeAspect="1"/></p:cNvSpPr>
          <p:nvPr><p:ph type="sldImg"/></p:nvPr>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="381000" y="685800"/><a:ext cx="6096000" cy="3429000"/></a:xfrm>
        </p:spPr>
      </p:sp>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="3" name="Notes Placeholder 2"/>
          <p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>
          <p:nvPr><p:ph type="body" idx="1"/></p:nvPr>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="381000" y="4343400"/><a:ext cx="6096000" cy="4114800"/></a:xfrm>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/>
          <a:lstStyle/>
          <a:p><a:endParaRPr lang="en-US"/></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1"
    accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5"
    accent6="accent6" hlink="hlink" folHlink="folHlink"/>
</p:notesMaster>''', encoding="utf-8")

    # notesMaster1 rels
    masters_notes_rels = masters_notes_dir / "_rels"
    masters_notes_rels.mkdir()
    (masters_notes_rels / "notesMaster1.xml.rels").write_text('''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>''', encoding="utf-8")

    # ── Create remaining directories ─────────────────────────────────────
    (ppt_dir / "slides" / "_rels").mkdir(parents=True)
    (ppt_dir / "media").mkdir()


if __name__ == "__main__":
    assemble()
