"""
docx_service.py — Extract text and write tracked-change redlines into Word docs.

Each suggestion produces:
  - A <w:del> element marking the original text as deleted (red strikethrough)
  - A <w:ins> element with the suggested replacement (underlined)
  - A <w:comment> anchored to the change containing the rationale

Run boundaries are split to align with the original_text span so tracked
changes are correctly scoped even when the text crosses multiple runs.
"""

import copy
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
    """Extract full text from a .docx file, preserving paragraph breaks."""
    doc = Document(io.BytesIO(docx_bytes))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


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


def write_redlines(
    docx_bytes: bytes,
    suggestions: list,
    author: str = "BlogReviewAgent",
) -> bytes:
    """
    Write review suggestions as tracked changes (redlines) with rationale comments.

    For each suggestion:
      - original_text is struck through as a <w:del> tracked deletion
      - suggestion text is inserted as a <w:ins> tracked insertion
      - rationale is written as a Word comment anchored to the change

    Each suggestion dict:
        {
            "original_text": str,   # exact phrase from the document
            "suggestion":    str,   # replacement wording
            "rationale":     str,   # reasoning for the change
        }
    """
    doc = Document(io.BytesIO(docx_bytes))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    comments_root = _ensure_comments_part(doc)
    comment_id  = _next_comment_id(comments_root)
    revision_id = _next_revision_id(doc)  # scan doc to avoid ID collisions

    for suggestion in suggestions:
        original      = suggestion.get("original_text", "").strip()
        new_text      = suggestion.get("suggestion", "")
        rationale     = suggestion.get("rationale", "")
        if not original:
            continue

        para = _find_paragraph(doc, original)
        if para is None:
            continue

        # Add comment containing only the rationale (the redline shows WHAT changed)
        _append_comment_element(comments_root, comment_id, author, now, rationale)

        # Insert tracked change anchored to the comment
        _insert_tracked_change(
            para, original, new_text,
            comment_id, revision_id, author, now,
        )

        comment_id  += 1
        revision_id += 2   # del takes one ID, ins takes the next

    _flush_comments_part(doc, comments_root)

    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


# Keep the old name as an alias so approve.py doesn't need an immediate update
write_comments = write_redlines


# ── Tracked-change insertion ──────────────────────────────────────────────────

def _insert_tracked_change(para, original_text, suggestion_text, cid, rev_id, author, date):
    """
    Replace original_text in para with:
      commentRangeStart → <w:del> → <w:ins> → commentRangeEnd → commentRef run
    """
    p_elem = para._p

    # Build full text from direct w:r children only
    full_text = _para_run_text(p_elem)
    if original_text not in full_text:
        return False

    find_start = full_text.index(original_text)
    find_end   = find_start + len(original_text)

    # Split runs at the two boundaries so target runs are cleanly bounded
    _split_runs_at_offset(p_elem, find_start)
    _split_runs_at_offset(p_elem, find_end)

    # Re-collect runs with updated offsets
    target_runs = _collect_runs_in_range(p_elem, find_start, find_end)
    if not target_runs:
        return False

    # Preserve rPr (character formatting) from the first target run
    rpr = target_runs[0].find(qn("w:rPr"))

    # Build <w:del> — contains clones of the original runs with w:delText
    del_elem = etree.Element(qn("w:del"))
    del_elem.set(qn("w:id"),     str(rev_id))
    del_elem.set(qn("w:author"), author)
    del_elem.set(qn("w:date"),   date)
    for r in target_runs:
        del_r = copy.deepcopy(r)
        t = del_r.find(qn("w:t"))
        if t is not None:
            t.tag = qn("w:delText")
            t.set(_XML_SPACE, "preserve")
        del_elem.append(del_r)

    # Build <w:ins> — single run with the suggestion text
    ins_elem = etree.Element(qn("w:ins"))
    ins_elem.set(qn("w:id"),     str(rev_id + 1))
    ins_elem.set(qn("w:author"), author)
    ins_elem.set(qn("w:date"),   date)
    ins_r = etree.SubElement(ins_elem, qn("w:r"))
    if rpr is not None:
        ins_r.append(copy.deepcopy(rpr))
    ins_t = etree.SubElement(ins_r, qn("w:t"))
    ins_t.set(_XML_SPACE, "preserve")
    ins_t.text = suggestion_text

    # Comment anchors
    cstart = etree.Element(qn("w:commentRangeStart"))
    cstart.set(qn("w:id"), str(cid))
    cend = etree.Element(qn("w:commentRangeEnd"))
    cend.set(qn("w:id"), str(cid))
    # Word Online requires rStyle="CommentReference" on the reference run
    cref_run = etree.Element(qn("w:r"))
    cref_rPr = etree.SubElement(cref_run, qn("w:rPr"))
    cref_rStyle = etree.SubElement(cref_rPr, qn("w:rStyle"))
    cref_rStyle.set(qn("w:val"), "CommentReference")
    cref = etree.SubElement(cref_run, qn("w:commentReference"))
    cref.set(qn("w:id"), str(cid))

    # Insert before the first target run
    first = target_runs[0]
    first.addprevious(cstart)

    # Remove target runs
    for r in target_runs:
        p_elem.remove(r)

    # Place del → ins → commentRangeEnd → commentRef after cstart
    cstart.addnext(cref_run)
    cstart.addnext(cend)
    cstart.addnext(ins_elem)
    cstart.addnext(del_elem)

    return True


def _para_run_text(p_elem) -> str:
    """Concatenate text from direct w:r children of a paragraph element."""
    parts = []
    for r in p_elem.findall(qn("w:r")):
        t = r.find(qn("w:t"))
        parts.append((t.text or "") if t is not None else "")
    return "".join(parts)


def _split_runs_at_offset(p_elem, offset: int):
    """
    Split the run that straddles `offset` so that run boundaries align with it.
    If a run boundary already falls exactly at `offset`, this is a no-op.
    """
    pos = 0
    for r in list(p_elem.findall(qn("w:r"))):
        t = r.find(qn("w:t"))
        text = (t.text or "") if t is not None else ""
        r_end = pos + len(text)

        if pos < offset < r_end:
            split_at  = offset - pos
            left_text  = text[:split_at]
            right_text = text[split_at:]

            # Trim existing run to left portion
            if t is not None:
                t.text = left_text
                _set_xml_space(t, left_text)

            # Clone run for right portion
            right_r = copy.deepcopy(r)
            right_t = right_r.find(qn("w:t"))
            if right_t is not None:
                right_t.text = right_text
                _set_xml_space(right_t, right_text)

            r.addnext(right_r)
            return  # Only one run straddles any given offset

        pos = r_end
        if pos >= offset:
            return  # Boundary already aligned; nothing to split


def _collect_runs_in_range(p_elem, start: int, end: int) -> list:
    """Return w:r elements whose text span falls within [start, end)."""
    result = []
    pos = 0
    for r in p_elem.findall(qn("w:r")):
        t     = r.find(qn("w:t"))
        text  = (t.text or "") if t is not None else ""
        r_end = pos + len(text)
        if pos >= start and r_end <= end:
            result.append(r)
        pos = r_end
        if pos >= end:
            break
    return result


def _set_xml_space(t_elem, text: str):
    if text and (text[0] == " " or text[-1] == " "):
        t_elem.set(_XML_SPACE, "preserve")


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


def _next_revision_id(doc: Document) -> int:
    """Return a revision ID safely above any existing w:del/w:ins IDs in the document."""
    max_id = 0
    for elem in doc.element.body.iter():
        if elem.tag in (qn("w:del"), qn("w:ins")):
            try:
                max_id = max(max_id, int(elem.get(qn("w:id"), 0)))
            except (ValueError, TypeError):
                pass
    return max_id + 1


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


def _find_paragraph(doc: Document, text: str):
    for para in doc.paragraphs:
        if text in para.text:
            return para
    return None
