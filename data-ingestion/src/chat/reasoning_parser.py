"""Keyword heuristic parser that segments reasoning summary text into titled sections."""

import re

# Trigger patterns and their gerund-form prefixes
ACTION_TRIGGERS = [
    (r"^Let me\b", "Working on"),
    (r"^I need to\b", "Needing to"),
    (r"^Now I will\b", "Now"),
    (r"^First,?\b", "Starting with"),
    (r"^Next,?\b", "Moving to"),
    (r"^I should\b", "Working on"),
    (r"^Let's\b", "Working on"),
    (r"^I'll\b", "Working on"),
    (r"^Now I\b", "Now"),
    (r"^I want to\b", "Working on"),
]

REASONING_TRIGGERS = [
    (r"^This means\b", "Considering"),
    (r"^Because\b", "Reasoning about"),
    (r"^The reason is\b", "Reasoning about"),
    (r"^Considering\b", "Considering"),
    (r"^Since\b", "Considering"),
    (r"^Given that\b", "Evaluating"),
    (r"^This suggests\b", "Analyzing"),
    (r"^Therefore\b", "Concluding"),
    (r"^It appears\b", "Analyzing"),
    (r"^Based on\b", "Evaluating"),
]

ALL_TRIGGERS = ACTION_TRIGGERS + REASONING_TRIGGERS

_SENTENCE_SPLIT = re.compile(r"(?<=[.?!])\s+|\n+")


def _make_title(prefix: str, sentence: str) -> str:
    """Generate a short title from a trigger sentence."""
    # Remove the trigger phrase itself to get the rest
    for pattern, _ in ALL_TRIGGERS:
        cleaned = re.sub(pattern, "", sentence, count=1, flags=re.IGNORECASE).strip()
        if cleaned != sentence:
            sentence = cleaned
            break
    # Strip trailing punctuation
    sentence = sentence.rstrip(".!?")
    title = f"{prefix} {sentence}" if sentence else prefix
    # Truncate to ~60 chars
    if len(title) > 60:
        title = title[:57] + "..."
    return title


def _match_trigger(sentence: str) -> tuple[str, str] | None:
    stripped = sentence.strip()
    for pattern, prefix in ALL_TRIGGERS:
        if re.match(pattern, stripped, re.IGNORECASE):
            return prefix, stripped
    return None


def parse_reasoning(text: str) -> list[dict]:
    """Parse reasoning text into titled sections.

    Returns: [{"title": "Looking up spatial data", "content": "..."}]
    """
    if not text or not text.strip():
        return []

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]

    if not sentences:
        return [{"title": "Analyzing the request", "content": text.strip()}]

    blocks: list[dict] = []
    current_title = "Analyzing the request"
    current_content: list[str] = []

    for sentence in sentences:
        match = _match_trigger(sentence)
        if match:
            # Emit previous block
            if current_content:
                blocks.append({
                    "title": current_title,
                    "content": " ".join(current_content),
                })
            prefix, trigger_sentence = match
            current_title = _make_title(prefix, trigger_sentence)
            current_content = [sentence]
        else:
            current_content.append(sentence)

    # Flush final block
    if current_content:
        blocks.append({
            "title": current_title,
            "content": " ".join(current_content),
        })

    return blocks if blocks else [{"title": "Analyzing the request", "content": text.strip()}]
