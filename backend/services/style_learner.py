import os
from pathlib import Path

import anthropic

STYLE_FILE = Path(__file__).parent.parent.parent / "review-style.md"


def learn_from_approval(original_suggestions: list[dict], ceo_final_suggestions: list[dict]):
    """
    Compare agent suggestions to CEO's final edits.
    If CEO made meaningful changes, update review-style.md with learned patterns.
    """
    deltas = _compute_deltas(original_suggestions, ceo_final_suggestions)
    if not deltas:
        return

    current_style = STYLE_FILE.read_text(encoding="utf-8") if STYLE_FILE.exists() else ""
    updated_style = _propose_style_update(current_style, deltas)
    if updated_style and updated_style != current_style:
        STYLE_FILE.write_text(updated_style, encoding="utf-8")
        print(f"[style_learner] Updated review-style.md with {len(deltas)} learned patterns")


def _compute_deltas(original: list[dict], final: list[dict]) -> list[dict]:
    """Find suggestions the CEO meaningfully changed."""
    original_map = {s["original_text"]: s for s in original}
    deltas = []
    for final_suggestion in final:
        orig = original_map.get(final_suggestion["original_text"])
        if orig and orig["suggestion"].strip() != final_suggestion["suggestion"].strip():
            deltas.append({
                "original_text": final_suggestion["original_text"],
                "agent_suggestion": orig["suggestion"],
                "ceo_final": final_suggestion["suggestion"],
            })
    return deltas


def _propose_style_update(current_style: str, deltas: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    delta_text = "\n".join(
        f"- Agent wrote: \"{d['agent_suggestion']}\"\n  CEO changed to: \"{d['ceo_final']}\""
        for d in deltas
    )

    message = client.messages.create(
        model=model,
        max_tokens=2048,
        system="You maintain a CEO's writing style guide in Markdown. Update the style guide based on observed editing patterns. Preserve all existing rules. Add new rules only if they are clearly supported by the examples. Return the complete updated Markdown file.",
        messages=[{
            "role": "user",
            "content": f"## Current Style Guide\n\n{current_style}\n\n## CEO Edits Observed This Session\n\n{delta_text}\n\nReturn the updated style guide."
        }],
    )
    return message.content[0].text.strip()
