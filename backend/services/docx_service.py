"""
docx_service.py — Extract text and write tracked-change redlines into Word docs.

Each suggestion produces:
  - A <w:del> element marking the original text as deleted (red strikethrough)
  - A <w:ins> element with the suggested replacement (underlined)
  - A <w:comment> anchored to the change containing the rationale

Run boundaries are split to align with the original_text span so tracked
changes are correctly scoped even when the text crosses multiple runs.
"""

import base64
import io
from datetime import datetime, timezone
from lxml import etree

from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.opc.part import Part
from docx.opc.packuri import PackURI


# ── Namespaces ────────────────────────────────────────────────────────────────

_W_NS   = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_HYPERLINK_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"

_COMMENTS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
)
_COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text(docx_bytes: bytes) -> str:
    """
    Extract original text from a .docx, preserving paragraph breaks.
    Skips runs coloured 00B050 (green) — those are our inserted suggestions
    so the extracted text reflects the pre-redline content even when the
    SharePoint document already has our visual redlines applied.
    """
    doc = Document(io.BytesIO(docx_bytes))
    paras = []
    for p in doc.paragraphs:
        parts = []
        for run in p.runs:
            rPr = run._r.find(qn("w:rPr"))
            if rPr is not None:
                color_el = rPr.find(qn("w:color"))
                if color_el is not None and color_el.get(qn("w:val"), "").upper() == "00B050":
                    continue  # skip our inserted suggestion text
            parts.append(run.text)
        text = "".join(parts).strip()
        if text:
            paras.append(text)
    return "\n\n".join(paras)


_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def extract_blocks(docx_bytes: bytes) -> list:
    """
    Extract document content as an ordered list of blocks:
      {"type": "paragraph", "text": "..."}
      {"type": "image", "src": "data:<mime>;base64,...", "alt": ""}

    Green-coloured runs (our inserted suggestions) are excluded from paragraph
    text so blocks always reflect the clean original content.
    """
    doc = Document(io.BytesIO(docx_bytes))

    # Build a map of paragraph element id → image data URL
    image_map: dict = {}
    for shape in doc.inline_shapes:
        blip = shape._inline.find(f'.//{{{_A_NS}}}blip')
        if blip is None:
            continue
        rId = blip.get(f'{{{_R_NS}}}embed')
        if not rId:
            continue
        img_part = doc.part.related_parts.get(rId)
        if img_part is None:
            continue
        b64 = base64.b64encode(img_part.blob).decode()
        src = f"data:{img_part.content_type};base64,{b64}"
        # Walk up from the inline element to the parent w:p
        elem = shape._inline
        while elem is not None and elem.tag != qn("w:p"):
            elem = elem.getparent()
        if elem is not None:
            image_map[id(elem)] = src

    blocks = []
    for para in doc.paragraphs:
        p_id = id(para._p)
        if p_id in image_map:
            blocks.append({"type": "image", "src": image_map[p_id], "alt": ""})
            continue
        # Extract text, skipping green insertion runs
        parts = []
        for run in para.runs:
            rPr = run._r.find(qn("w:rPr"))
            if rPr is not None:
                color_el = rPr.find(qn("w:color"))
                if color_el is not None and color_el.get(qn("w:val"), "").upper() == "00B050":
                    continue
            parts.append(run.text)
        text = "".join(parts).strip()
        if text:
            blocks.append({"type": "paragraph", "text": text})

    return blocks


def extract_paragraphs(docx_bytes: bytes) -> list:
    """Extract paragraphs with style info for structure-aware review."""
    doc = Document(io.BytesIO(docx_bytes))
    result = []
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip():
            result.append({"index": i, "style": p.style.name, "text": p.text})
    return result


def extract_existing_comments(docx_bytes: bytes) -> list:
    """Extract any existing Word comments (e.g. from training docs)."""
    doc = Document(io.BytesIO(docx_bytes))
    comments = []
    try:
        part = _get_comments_part(doc, create=False)
        if part is not None:
            root = etree.fromstring(part.blob)
            for comment in root.findall(f'.//{qn("w:comment")}'):
                text = "".join(
                    t.text or "" for t in comment.findall(f'.//{qn("w:t")}')
                )
                comments.append({
                    "author": comment.get(qn("w:author"), ""),
                    "date":   comment.get(qn("w:date"), ""),
                    "text":   text,
                })
    except Exception:
        pass
    return comments


def fill_jira_placeholder(doc: Document, ticket_id: str, jira_base_url: str) -> None:
    """Find '[Jira Ticket: ]' in the document and replace it with a hyperlink."""
    placeholder = "[Jira Ticket: ]"
    url = f"{jira_base_url.rstrip('/')}/browse/{ticket_id}"

    for para in doc.paragraphs:
        if placeholder not in para.text:
            continue

        # Rebuild the paragraph replacing the placeholder with hyperlink + surrounding text
        full_text = para.text
        idx = full_text.index(placeholder)
        before = full_text[:idx]
        after = full_text[idx + len(placeholder):]

        p_elem = para._p
        for child in list(p_elem):
            if child.tag != qn("w:pPr"):
                p_elem.remove(child)

        def _plain(text):
            r = OxmlElement("w:r")
            t = OxmlElement("w:t")
            t.set(_XML_SPACE, "preserve")
            t.text = text
            r.append(t)
            return r

        if before:
            p_elem.append(_plain(before))

        # Add hyperlink element
        r_id = para.part.relate_to(url, _HYPERLINK_REL, is_external=True)
        hl = OxmlElement("w:hyperlink")
        hl.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", r_id)
        hl_r = OxmlElement("w:r")
        hl_rPr = OxmlElement("w:rPr")
        hl_rStyle = OxmlElement("w:rStyle")
        hl_rStyle.set(qn("w:val"), "Hyperlink")
        hl_rPr.append(hl_rStyle)
        hl_r.append(hl_rPr)
        hl_t = OxmlElement("w:t")
        hl_t.set(_XML_SPACE, "preserve")
        hl_t.text = f"[Jira Ticket: {ticket_id}]"
        hl_r.append(hl_t)
        hl.append(hl_r)
        p_elem.append(hl)

        if after:
            p_elem.append(_plain(after))
        break


def write_redlines(
    docx_bytes: bytes,
    suggestions: list,
    author: str = "BlogReviewAgent",
    ticket_id: str = None,
    jira_base_url: str = "https://princetonblue.atlassian.net",
) -> bytes:
    """
    Write review suggestions as visual redlines with rationale comments.

    For each suggestion:
      - original_text rendered in red with strikethrough
      - suggestion text rendered in green with underline
      - rationale written as a Word comment anchored to the change

    Uses standard run character formatting (w:color, w:strike, w:u) rather than
    tracked-change XML (w:del/w:ins) for full Word Online compatibility.
    """
    doc = Document(io.BytesIO(docx_bytes))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if ticket_id:
        fill_jira_placeholder(doc, ticket_id, jira_base_url)

    comments_root = _ensure_comments_part(doc)
    comment_id = _next_comment_id(comments_root)

    for suggestion in suggestions:
        original  = suggestion.get("original_text", "").strip()
        new_text  = suggestion.get("suggestion", "")
        rationale = suggestion.get("rationale", "")
        if not original:
            continue

        para = _find_paragraph(doc, original)
        if para is None:
            continue

        _append_comment_element(comments_root, comment_id, author, now, rationale)
        _apply_visual_redline(para, original, new_text, comment_id)
        comment_id += 1

    _flush_comments_part(doc, comments_root)
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


# Keep the old name as an alias
write_comments = write_redlines


# ── Visual redline (color formatting — Word Online safe) ──────────────────────

def _apply_visual_redline(para, original_text: str, suggestion_text: str, cid: int):
    """
    Rewrite the paragraph in place:
      [before] [red strikethrough: original] [space] [green underline: suggestion] [after]
    with a comment range wrapping the changed portion.

    Avoids w:del/w:ins tracked-change XML entirely; uses only standard w:rPr
    properties (w:color, w:strike, w:u) which Word Online handles correctly.
    """
    full_text = _clean_para_text(para)
    if original_text not in full_text:
        return False

    idx   = full_text.index(original_text)
    before = full_text[:idx]
    after  = full_text[idx + len(original_text):]

    p_elem = para._p

    # Clear all content children; preserve paragraph properties (w:pPr)
    for child in list(p_elem):
        if child.tag != qn("w:pPr"):
            p_elem.remove(child)

    def _run(text: str, color: str = None, strike: bool = False, underline: bool = False):
        r = OxmlElement("w:r")
        if color or strike or underline:
            rPr = OxmlElement("w:rPr")
            if color:
                c = OxmlElement("w:color")
                c.set(qn("w:val"), color)
                rPr.append(c)
            if strike:
                rPr.append(OxmlElement("w:strike"))
            if underline:
                u = OxmlElement("w:u")
                u.set(qn("w:val"), "single")
                rPr.append(u)
            r.append(rPr)
        t = OxmlElement("w:t")
        t.set(_XML_SPACE, "preserve")
        t.text = text
        r.append(t)
        return r

    if before:
        p_elem.append(_run(before))

    # Comment range start
    cstart = OxmlElement("w:commentRangeStart")
    cstart.set(qn("w:id"), str(cid))
    p_elem.append(cstart)

    # Original text: red + strikethrough
    p_elem.append(_run(original_text, color="FF0000", strike=True))

    # Separator
    p_elem.append(_run("  "))

    # Suggestion: green + underline
    p_elem.append(_run(suggestion_text, color="00B050", underline=True))

    # Comment range end
    cend = OxmlElement("w:commentRangeEnd")
    cend.set(qn("w:id"), str(cid))
    p_elem.append(cend)

    # Comment reference run (rStyle required by Word Online)
    cref_run = OxmlElement("w:r")
    cref_rPr = OxmlElement("w:rPr")
    cref_rStyle = OxmlElement("w:rStyle")
    cref_rStyle.set(qn("w:val"), "CommentReference")
    cref_rPr.append(cref_rStyle)
    cref_run.append(cref_rPr)
    cref = OxmlElement("w:commentReference")
    cref.set(qn("w:id"), str(cid))
    cref_run.append(cref)
    p_elem.append(cref_run)

    if after:
        p_elem.append(_run(after))

    return True



# ── Comments part helpers ─────────────────────────────────────────────────────

def _get_comments_part(doc: Document, create: bool = True):
    doc_part = doc.part
    for rel in doc_part.rels.values():
        if rel.reltype == _COMMENTS_REL_TYPE:
            return rel.target_part
    if not create:
        return None
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:comments xmlns:w="{_W_NS}"/>'
    ).encode("utf-8")
    part = Part(
        PackURI("/word/comments.xml"),
        _COMMENTS_CONTENT_TYPE,
        xml,
        doc_part.package,
    )
    doc_part.relate_to(part, _COMMENTS_REL_TYPE)
    return part


def _ensure_comments_part(doc: Document):
    return etree.fromstring(_get_comments_part(doc, create=True).blob)


def _flush_comments_part(doc: Document, root):
    part = _get_comments_part(doc, create=True)
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)



def _next_comment_id(comments_root) -> int:
    existing = comments_root.findall(f"{{{_W_NS}}}comment")
    if not existing:
        return 1
    return max(int(c.get(f"{{{_W_NS}}}id", 0)) for c in existing) + 1


def _append_comment_element(root, cid: int, author: str, date: str, text: str):
    """
    Build a comment element compatible with Word Online.
    Requires: w:pStyle="CommentText", w:annotationRef run,
              w:rStyle="CommentReference" on the annotation run,
              and w:initials on the comment element.
    """
    W = _W_NS
    comment = etree.SubElement(root, f"{{{W}}}comment")
    comment.set(f"{{{W}}}id",       str(cid))
    comment.set(f"{{{W}}}author",   author)
    comment.set(f"{{{W}}}date",     date)
    comment.set(f"{{{W}}}initials", "BRA")

    p = etree.SubElement(comment, f"{{{W}}}p")

    # Paragraph style required by Word Online
    pPr = etree.SubElement(p, f"{{{W}}}pPr")
    pStyle = etree.SubElement(pPr, f"{{{W}}}pStyle")
    pStyle.set(f"{{{W}}}val", "CommentText")

    # Annotation reference run (required marker before comment body)
    ann_r = etree.SubElement(p, f"{{{W}}}r")
    ann_rPr = etree.SubElement(ann_r, f"{{{W}}}rPr")
    ann_rStyle = etree.SubElement(ann_rPr, f"{{{W}}}rStyle")
    ann_rStyle.set(f"{{{W}}}val", "CommentReference")
    etree.SubElement(ann_r, f"{{{W}}}annotationRef")

    # Comment body text
    text_r = etree.SubElement(p, f"{{{W}}}r")
    t = etree.SubElement(text_r, f"{{{W}}}t")
    t.set(_XML_SPACE, "preserve")
    t.text = text


def _clean_para_text(para) -> str:
    """Return paragraph text excluding our redline-coloured runs (FF0000 / 00B050).
    Use this instead of para.text when the doc may already have redlines applied."""
    parts = []
    for run in para.runs:
        rPr = run._r.find(qn("w:rPr"))
        if rPr is not None:
            color_el = rPr.find(qn("w:color"))
            if color_el is not None:
                val = color_el.get(qn("w:val"), "").upper()
                if val in ("FF0000", "00B050"):
                    continue
        parts.append(run.text)
    return "".join(parts)


def _find_paragraph(doc: Document, text: str):
    for para in doc.paragraphs:
        if text in _clean_para_text(para):
            return para
    return None
