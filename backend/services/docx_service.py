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
    Skips w:ins elements (our tracked-change insertions) so the extracted
    text reflects the pre-redline original even when the doc already has
    tracked changes applied.
    """
    doc = Document(io.BytesIO(docx_bytes))
    paras = []
    for p in doc.paragraphs:
        text = _original_para_text(p._p).strip()
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
        # Extract text, skipping w:ins (our tracked insertions)
        text = _original_para_text(para._p).strip()
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
            if child.tag in (qn("w:r"), qn("w:hyperlink")):
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

        p_elem.append(_plain(f"[Jira Ticket: {ticket_id}]"))

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
    Write review suggestions as native Word tracked changes (w:del / w:ins).
    Compatible with both Word Desktop and Word Online.
    """
    doc = Document(io.BytesIO(docx_bytes))

    if ticket_id:
        fill_jira_placeholder(doc, ticket_id, jira_base_url)

    # Start revision IDs above the highest existing ID in the document
    rev_id = _max_revision_id(doc) + 1
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for suggestion in suggestions:
        original = suggestion.get("original_text", "").strip()
        new_text = suggestion.get("suggestion", "")
        if not original:
            continue
        para = _find_paragraph(doc, original)
        if para is None:
            continue
        applied = _apply_tracked_change(para, original, new_text, rev_id, author, now)
        if applied:
            rev_id += 2  # each change uses two IDs: one for del, one for ins

    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


# Keep the old name as an alias
write_comments = write_redlines


# ── Native tracked changes (w:del / w:ins) ────────────────────────────────────

def _max_revision_id(doc: Document) -> int:
    """Scan the full document XML for the highest w:id value to avoid conflicts."""
    max_id = 0
    for elem in doc.element.iter():
        val = elem.get(qn("w:id"))
        if val is not None:
            try:
                max_id = max(max_id, int(val))
            except ValueError:
                pass
    return max_id


def _apply_tracked_change(
    para, original_text: str, suggestion_text: str,
    rev_id: int, author: str, date: str
) -> bool:
    """
    Replace original_text with a tracked change in the paragraph:
      w:del  — marks original_text as deleted (Word shows red strikethrough)
      w:ins  — marks suggestion_text as inserted (Word shows underline)

    Uses w:delText inside w:del and w:t inside w:ins, as required by the OOXML spec.
    Both elements carry unique w:id, w:author, and w:date attributes.
    """
    full_text = _original_para_text(para._p)
    if original_text not in full_text:
        return False

    idx    = full_text.index(original_text)
    before = full_text[:idx]
    after  = full_text[idx + len(original_text):]

    p_elem = para._p

    # Remove runs and any existing tracked-change elements; keep structural nodes
    for child in list(p_elem):
        if child.tag in (
            qn("w:r"), qn("w:hyperlink"),
            qn("w:ins"), qn("w:del"),
            qn("w:commentRangeStart"), qn("w:commentRangeEnd"),
        ):
            p_elem.remove(child)

    def _plain_run(text: str) -> "OxmlElement":
        r = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.set(_XML_SPACE, "preserve")
        t.text = text
        r.append(t)
        return r

    if before:
        p_elem.append(_plain_run(before))

    # w:del — deleted (original) text
    del_elem = OxmlElement("w:del")
    del_elem.set(qn("w:id"),     str(rev_id))
    del_elem.set(qn("w:author"), author)
    del_elem.set(qn("w:date"),   date)
    del_r = OxmlElement("w:r")
    del_t = OxmlElement("w:delText")
    del_t.set(_XML_SPACE, "preserve")
    del_t.text = original_text
    del_r.append(del_t)
    del_elem.append(del_r)
    p_elem.append(del_elem)

    # w:ins — inserted (suggestion) text
    ins_elem = OxmlElement("w:ins")
    ins_elem.set(qn("w:id"),     str(rev_id + 1))
    ins_elem.set(qn("w:author"), author)
    ins_elem.set(qn("w:date"),   date)
    ins_r = OxmlElement("w:r")
    ins_t = OxmlElement("w:t")
    ins_t.set(_XML_SPACE, "preserve")
    ins_t.text = suggestion_text
    ins_r.append(ins_t)
    ins_elem.append(ins_r)
    p_elem.append(ins_elem)

    if after:
        p_elem.append(_plain_run(after))

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
    root = etree.fromstring(_get_comments_part(doc, create=True).blob)
    # Clear any existing comments so stale ones don't accumulate across approvals
    for existing in list(root):
        root.remove(existing)
    return root


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


def _original_para_text(p_elem) -> str:
    """
    Extract the original (pre-suggestion) text from a paragraph element.
    - Includes w:del text (w:delText) — that IS the original
    - Skips w:ins content — that is our inserted suggestion
    - Includes plain w:r runs
    """
    parts = []
    for child in p_elem:
        tag = child.tag
        if tag == qn("w:r"):
            # Plain run — include unless it is inside w:ins (handled below)
            for t in child.findall(qn("w:t")):
                parts.append(t.text or "")
            for t in child.findall(qn("w:delText")):
                parts.append(t.text or "")
        elif tag == qn("w:del"):
            # Deleted text = original — include it
            for t in child.iter(qn("w:delText")):
                parts.append(t.text or "")
        elif tag == qn("w:ins"):
            # Inserted text = our suggestion — skip entirely
            pass
        elif tag == qn("w:hyperlink"):
            for t in child.iter(qn("w:t")):
                parts.append(t.text or "")
    return "".join(parts)


def _find_paragraph(doc: Document, text: str):
    for para in doc.paragraphs:
        if text in _original_para_text(para._p):
            return para
    return None
