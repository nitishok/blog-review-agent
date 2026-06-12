import io
from datetime import datetime

from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def extract_text(docx_bytes: bytes) -> str:
    """Extract full text from a .docx file, preserving paragraph breaks."""
    doc = Document(io.BytesIO(docx_bytes))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_comments(docx_bytes: bytes) -> list[dict]:
    """Extract existing Word comments from a .docx file."""
    doc = Document(io.BytesIO(docx_bytes))
    comments = []
    for comment in doc.element.findall('.//' + qn('w:comment')):
        text = "".join(r.text for r in comment.findall('.//' + qn('w:t')))
        comments.append({
            "author": comment.get(qn('w:author'), ""),
            "date": comment.get(qn('w:date'), ""),
            "text": text,
        })
    return comments


def write_comments(docx_bytes: bytes, suggestions: list[dict], author: str = "CEO Review Agent") -> bytes:
    """
    Write review suggestions as Word comments into a .docx.

    Each suggestion dict: {
        "original_text": str,   # text to anchor the comment to
        "suggestion": str,      # replacement text
        "rationale": str,       # why this change
    }
    """
    doc = Document(io.BytesIO(docx_bytes))
    suggestion_map = {s["original_text"]: s for s in suggestions}

    comment_id = 1
    for para in doc.paragraphs:
        for original_text, suggestion in suggestion_map.items():
            if original_text in para.text:
                _add_comment(
                    doc,
                    para,
                    original_text,
                    f"Suggestion: {suggestion['suggestion']}\n\nRationale: {suggestion['rationale']}",
                    author=author,
                    comment_id=comment_id,
                )
                comment_id += 1

    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


def _add_comment(doc: Document, para, anchor_text: str, comment_text: str, author: str, comment_id: int):
    """Add a Word comment anchored to a specific text run within a paragraph."""
    # Build comment element in comments part
    comments_part = _get_or_create_comments_part(doc)
    comment_elem = OxmlElement('w:comment')
    comment_elem.set(qn('w:id'), str(comment_id))
    comment_elem.set(qn('w:author'), author)
    comment_elem.set(qn('w:date'), datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))

    cp = OxmlElement('w:p')
    cr = OxmlElement('w:r')
    ct = OxmlElement('w:t')
    ct.text = comment_text
    ct.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    cr.append(ct)
    cp.append(cr)
    comment_elem.append(cp)
    comments_part.append(comment_elem)

    # Wrap the target run(s) in comment range marks
    for run in para.runs:
        if anchor_text in run.text:
            run_elem = run._r
            start = OxmlElement('w:commentRangeStart')
            start.set(qn('w:id'), str(comment_id))
            end = OxmlElement('w:commentRangeEnd')
            end.set(qn('w:id'), str(comment_id))
            ref = OxmlElement('w:r')
            ref_mark = OxmlElement('w:commentReference')
            ref_mark.set(qn('w:id'), str(comment_id))
            ref.append(ref_mark)

            run_elem.addprevious(start)
            run_elem.addnext(end)
            end.addnext(ref)
            break


def _get_or_create_comments_part(doc: Document):
    """Get or create the w:comments element in the document."""
    body = doc.element.body
    # Comments live in a separate part; for simplicity attach to body as extended element
    # In production use python-docx's part system for proper comments.xml
    comments = doc.element.find(qn('w:comments'))
    if comments is None:
        comments = OxmlElement('w:comments')
        doc.element.insert(0, comments)
    return comments
