"""
json_utils.py — shared JSON extraction with truncation detection and recovery.
"""

import json
import re


def sanitize_json_text(text: str) -> str:
    """Replace smart quotes / unicode dashes that break json.loads."""
    return (
        text
        .replace('\u2018', "'").replace('\u2019', "'")   # smart single quotes
        .replace('\u201c', '"').replace('\u201d', '"')   # smart double quotes
        .replace('\u2011', '-').replace('\u2013', '-')   # non-breaking / en-dash
        .replace('\u2014', '-')                          # em-dash
    )


def detect_truncation(content: str, context: str = "") -> bool:
    """
    Check if the LLM response looks truncated (hit token limit).
    Returns True if truncation is likely.
    """
    if not content:
        return False

    stripped = content.rstrip()
    signs = [
        # Array/object never closed
        stripped.startswith('[') and not stripped.endswith(']'),
        stripped.startswith('{') and not stripped.endswith('}'),
        # Ends mid-string or mid-key
        stripped.endswith('"') and stripped.count('"') % 2 != 0,
        stripped.endswith(','),
        stripped.endswith(':'),
        # Truncated mid-word (last char is a letter after a quote)
    ]
    is_truncated = any(signs)

    if is_truncated:
        tail = stripped[-80:].replace('\n', ' ')
        print(f"[⚠ TRUNCATION DETECTED] {context}")
        print(f"    Response ends with: ...{tail}")
        print(f"    Total length: {len(content)} chars. "
              f"The LLM likely hit its max_tokens limit — "
              f"increase max_tokens or reduce the number of leads per call.")

    return is_truncated


def extract_json_list(text: str, context: str = "") -> list:
    """
    Robustly extract a JSON array from LLM output.
    Handles: markdown fences, smart quotes, truncated arrays.
    """
    if not text:
        return []

    # Strip markdown fences
    text = re.sub(r'```json|```', '', text).strip()

    # Sanitize unicode
    text = sanitize_json_text(text)

    # 1. Direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # 2. Regex for complete [...] block
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # 3. Truncation recovery — close the array at last complete object
    truncated = detect_truncation(text, context=context)

    if text.lstrip().startswith('['):
        last_brace = text.rfind('}')
        if last_brace > 0:
            attempt = text[:last_brace + 1].rstrip(', \t\n\r') + '\n]'
            attempt = sanitize_json_text(attempt)
            try:
                recovered = json.loads(attempt)
                if isinstance(recovered, list):
                    print(f"[JSON Recovery] {context}: salvaged {len(recovered)} "
                          f"items from truncated response")
                    return recovered
            except json.JSONDecodeError:
                pass

    if truncated:
        print(f"[JSON Recovery] {context}: could not recover any items")

    return []