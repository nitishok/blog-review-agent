"""
Smoke test for review_agent.py (Stage 3).

Uses the knowledge-base markdown as a stand-in for a real SharePoint .docx
(SharePoint permissions still pending). Tests the Claude call, JSON parsing,
prompt caching, and content-type inference.

Usage:
    python3 backend/scripts/test_review_agent.py
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

repo_root = Path(__file__).parent.parent.parent
backend_dir = repo_root / "backend"
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(backend_dir))

from services.review_agent import generate_review, _infer_content_type


def check(label, fn):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print("=" * 60)
    try:
        result = fn()
        print("✅ PASS")
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ FAIL: {e}")
        return None


# ── Load sample doc text from knowledge base ──────────────────────────────────

KB = Path(__file__).parent.parent.parent / "knowledge-base"

def load_kb_doc(filename: str) -> str:
    path = KB / filename
    text = path.read_text(encoding="utf-8")
    # Strip markdown metadata lines (---) at the top if present
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
        if end:
            lines = lines[end+1:]
    return "\n".join(lines).strip()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_content_type_inference():
    cases = [
        ("[Blog] How AI is Transforming...", "Blog"),
        ("[Content] - Blog - Drug Dev...", "Content"),
        ("[Email] Newsletter Q1", "Email"),
        ("No prefix here", "marketing content"),
    ]
    for summary, expected in cases:
        got = _infer_content_type(summary)
        assert got == expected, f"'{summary}' → expected '{expected}', got '{got}'"
        print(f"   '{summary[:40]}' → '{got}' ✓")


def test_generate_review_blog():
    doc_text = load_kb_doc("how-process-automation-and-ai-minimize-human-error-in-the-drug-development-lifecycle.md")
    print(f"   Doc length: {len(doc_text):,} chars")

    ticket_context = {
        "id": "MA2-587",
        "summary": "[Content] - Blog - How AI-Powered Process Automation is Compressing Regulatory Timelines",
    }

    suggestions = generate_review(doc_text, ticket_context)

    print(f"   Suggestions returned: {len(suggestions)}")
    assert isinstance(suggestions, list), "Should return a list"
    assert 1 <= len(suggestions) <= 10, f"Expected 1–10 suggestions, got {len(suggestions)}"

    for i, s in enumerate(suggestions, 1):
        assert "original_text" in s, f"Suggestion {i} missing 'original_text'"
        assert "suggestion" in s, f"Suggestion {i} missing 'suggestion'"
        assert "rationale" in s, f"Suggestion {i} missing 'rationale'"
        print(f"\n   [{i}] ORIGINAL:   {s['original_text'][:80]}")
        print(f"        SUGGESTION: {s['suggestion'][:80]}")
        print(f"        RATIONALE:  {s['rationale'][:80]}")

    return suggestions


def test_cache_hit(suggestions):
    """Call generate_review a second time — system prompt should be cache_read, not cache_write."""
    print("   Running second call to verify prompt cache hit...")
    doc_text = load_kb_doc("bpm-and-low-code-synergies-for-success.md")
    ticket_context = {
        "id": "MA2-109",
        "summary": "[Blog] BPM and Low-Code Synergies for Success",
    }
    suggestions2 = generate_review(doc_text, ticket_context)
    assert len(suggestions2) >= 1
    print(f"   Second call returned {len(suggestions2)} suggestions (check logs for cache_read tokens above)")


def test_json_structure(suggestions):
    """Verify the JSON is valid and has required keys."""
    raw = json.dumps(suggestions)
    parsed = json.loads(raw)
    for s in parsed:
        for key in ("original_text", "suggestion", "rationale"):
            assert key in s and isinstance(s[key], str) and len(s[key]) > 0, \
                f"Key '{key}' missing or empty in: {s}"
    print(f"   All {len(parsed)} suggestions have valid structure ✓")


if __name__ == "__main__":
    print("\nBlogReviewAgent — review_agent Smoke Test")

    check("1. Content-type inference", test_content_type_inference)
    suggestions = check("2. generate_review — live Claude call (MA2-587 topic)", test_generate_review_blog)
    if suggestions:
        check("3. Prompt cache hit — second call", lambda: test_cache_hit(suggestions))
        check("4. JSON structure validation", lambda: test_json_structure(suggestions))

    print(f"\n{'='*60}")
    print("Done.")
