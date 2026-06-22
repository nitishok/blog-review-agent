"""
docx_service.py — Extract text from Word docs and write review suggestions as comments.

Word comments require a separate word/comments.xml part (not embedded in document.xml).
We handle this via python-docx's OPC part system so the output opens correctly in Word.
"""

import io
from datetime import datetime, timezone
from lxml import etree

from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.opc.part import Part
from docx.opc.packuri import PackURI
from docx.opc.constants import RELATIONSHIP_TYPE as RT


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text(docx_bytes: bytes) -> str:
    """Extract full text from a .docx file, preserving paragraph breaks."""
    doc = Document(io.BytesIO(docx_bytes))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_paragraphs(docx_bytes: bytes) -> list[dict]:
    """
    Extract paragraphs with their style info — useful for the review agent
    to understand structure (headings vs body vs bullets).
    """
    doc = Document(io.BytesIO(docx_bytes))
    result = []
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip():
            result.append({
                "index": i,
                "style": p.style.name,
                "text": p.text,
            })
    return result


def extract_existing_comments(docx_bytes: bytes) -> list[dict]:
    """Extract any existing Word comments (e.g. from training docs)."""
    doc = Document(io.BytesIO(docx_bytes))
    comments = []
    # Comments live in the comments part if it exists
    try:
        comments_part = _get_comments_part(doc, create=False)
        if comments_part is not None:
            root = etree.fromstring(comments_part.blob)
            for comment in root.findall(f'.//{qn("w:comment")}'):
                text = "".join(
                    t.text or ""
                    for t in comment.findall(f'.//{qn("w:t")}')
                )
                comments.append({
                    "author": comment.get(qn("w:author"), ""),
                    "date": comment.get(qn("w:date"), ""),
                    "text": text,
                })
    except Exception:
        pass
    return comments


def write_comments(
    docx_bytes: bytes,
    suggestions: list[dict],
    author: str = "BlogReviewAgent",
) -> bytes:
    """
    Write review suggestions as Word comments into a .docx.

    Each suggestion dict:
        {
            "original_text": str,   # paragraph text to anchor the comment to
            "suggestion":    str,   # replacement wording
            "rationale":     str,   # why this change
        }

    Returns the modified .docx as bytes.
    """
    doc = Document(io.BytesIO(docx_bytes))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build / retrieve the comments.xml part
    comments_root = _ensure_comments_part(doc)

    comment_id = _next_comment_id(comments_root)

    for suggestion in suggestions:
        original = suggestion.get("original_text", "")
        if not original:
            continue

        # Find the paragraph that contains this text
        para = _find_paragraph(doc, original)
        if para is None:
            continue

        body = f"Suggestion: {suggestion.get('suggestion', '')}\n\nRationale: {suggestion.get('rationale', '')}"

        # 1. Add the comment element to comments.xml
        _append_comment_element(comments_root, comment_id, author, now, body)

        # 2. Wrap the matching run in commentRangeStart / commentRangeEnd / commentReference
        _annotate_paragraph(para, original, comment_id)

        comment_id += 1

    # Serialise comments part back
    _flush_comments_part(doc, comments_root)

    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


# ── Internal helpers ──────────────────────────────────────────────────────────

_COMMENTS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
)
_COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_COMMENTS_TAG = f"{{{_W_NS}}}comments"


def _get_comments_part(doc: Document, create: bool = True):
    """Return the comments Part object, optionally creating it."""
    doc_part = doc.part
    for rel in doc_part.rels.values():
        if rel.reltype == _COMMENTS_REL_TYPE:
            return rel.target_part
    if not create:
        return None
    # Create a minimal comments.xml
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
    """Get or create the comments part and return its root element."""
    part = _get_comments_part(doc, create=True)
    return etree.fromstring(part.blob)


def _flush_comments_part(doc: Document, root: etree._Element):
    """Write the (modified) comments root back into the part blob."""
    part = _get_comments_part(doc, create=True)
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _next_comment_id(comments_root: etree._Element) -> int:
    existing = comments_root.findall(f"{{{_W_NS}}}comment")
    if not existing:
        return 1
    return max(int(c.get(f"{{{_W_NS}}}id", 0)) for c in existing) + 1


def _append_comment_element(root, cid: int, author: str, date: str, text: str):
    comment = etree.SubElement(root, f"{{{_W_NS}}}comment")
    comment.set(f"{{{_W_NS}}}id", str(cid))
    comment.set(f"{{{_W_NS}}}author", author)
    comment.set(f"{{{_W_NS}}}date", date)
    p = etree.SubElement(comment, f"{{{_W_NS}}}p")
    r = etree.SubElement(p, f"{{{_W_NS}}}r")
    t = etree.SubElement(r, f"{{{_W_NS}}}t")
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text


def _find_paragraph(doc: Document, text: str):
    """Return the first paragraph whose text contains `text`."""
    for para in doc.paragraphs:
        if text in para.text:
            return para
    return None


def _annotate_paragraph(para, anchor_text: str, comment_id: int):
    """
    Insert commentRangeStart before the matching run and
    commentRangeEnd + commentReference after it.
    """
    cid = str(comment_id)
    for run in para.runs:
        if anchor_text in run.text:
            run_elem = run._r

            start = OxmlElement("w:commentRangeStart")
            start.set(qn("w:id"), cid)

            end = OxmlElement("w:commentRangeEnd")
            end.set(qn("w:id"), cid)

            ref_run = OxmlElement("w:r")
            ref = OxmlElement("w:commentReference")
            ref.set(qn("w:id"), cid)
            ref_run.append(ref)

            run_elem.addprevious(start)
            run_elem.addnext(ref_run)
            run_elem.addnext(end)
            return
