"""
One-time script to ingest CEO sample docs from SharePoint and seed review-style.md.

Usage:
    cd backend
    python scripts/ingest_samples.py --folder-url "https://yourcompany.sharepoint.com/sites/marketing/Shared Documents/CEO Samples"
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from services.docx_service import extract_comments, extract_text
from services.sharepoint import fetch_docx, list_folder_docx

STYLE_FILE = Path(__file__).parent.parent.parent / "review-style.md"


def ingest(folder_url: str):
    print(f"Listing .docx files in {folder_url}")
    files = list_folder_docx(folder_url)
    print(f"Found {len(files)} files")

    all_samples = []
    for f in files:
        print(f"  Fetching {f['name']}...")
        try:
            docx_bytes = fetch_docx(f["url"])
            text = extract_text(docx_bytes)
            comments = extract_comments(docx_bytes)
            all_samples.append({
                "name": f["name"],
                "text": text,
                "comments": comments,
            })
        except Exception as e:
            print(f"  ERROR: {e}")

    print(f"\nExtracting CEO style patterns from {len(all_samples)} documents...")
    style = _extract_style(all_samples)
    STYLE_FILE.write_text(style, encoding="utf-8")
    print(f"Written to {STYLE_FILE}")


def _extract_style(samples: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    samples_text = "\n\n---\n\n".join(
        f"## {s['name']}\n\n{s['text']}"
        + (f"\n\n### Comments in this doc:\n" + "\n".join(c["text"] for c in s["comments"]) if s["comments"] else "")
        for s in samples
    )

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system="""You are analyzing marketing content written and approved by a CEO of an Appian IT services company.
Extract the CEO's writing style, preferences, and patterns.
Return a Markdown style guide with these sections:
- Voice & Tone
- Structural Preferences
- Appian Domain Rules
- Phrases to Avoid
- Phrases CEO Prefers
- Call-to-Action Style

Base your analysis entirely on the documents provided. Be specific and give examples.""",
        messages=[{"role": "user", "content": f"Analyze these {len(samples)} CEO-approved documents:\n\n{samples_text}"}],
    )

    return f"# CEO Review Style\n\n*Auto-generated from {len(samples)} sample documents. Edit as needed.*\n\n{message.content[0].text.strip()}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder-url", required=True, help="SharePoint folder URL containing CEO sample docs")
    args = parser.parse_args()
    ingest(args.folder_url)
