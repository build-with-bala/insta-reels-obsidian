import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

MAX_TAGS = 5

_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*|\s*```$", re.MULTILINE)
_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


def _parse_tags(content: str) -> list[str]:
    """Extract a list of tag strings from an LLM completion.

    Tolerates markdown code fences, surrounding prose, and a
    {"tags": [...]} object instead of a bare array. Raises ValueError if no
    list of strings can be recovered (callers treat that as a soft failure).
    """
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty LLM response")

    text = _CODE_FENCE_RE.sub("", content).strip()

    candidates = []
    try:
        candidates.append(json.loads(text))
    except (json.JSONDecodeError, ValueError):
        pass

    if not candidates:
        # Fall back to the first JSON array embedded in prose.
        for match in _JSON_ARRAY_RE.finditer(text):
            try:
                candidates.append(json.loads(match.group(0)))
                break
            except (json.JSONDecodeError, ValueError):
                continue

    if not candidates:
        raise ValueError(f"no JSON array found in LLM response: {content[:200]!r}")

    parsed = candidates[0]
    if isinstance(parsed, dict):
        parsed = parsed.get("tags")
    if not isinstance(parsed, list):
        raise ValueError(f"LLM response is not a list of tags: {content[:200]!r}")

    tags = [t for t in parsed if isinstance(t, str) and t.strip()]
    if not tags:
        raise ValueError(f"LLM response contained no usable tags: {content[:200]!r}")
    return tags[:MAX_TAGS]


def _build_prompt(caption: str, creator: str, default_tags: list[str]) -> str:
    tag_list = ", ".join(default_tags) if default_tags else (
        "funny, recipe, travel, fitness, tech, music, fashion, motivation, education"
    )
    return (
        f"Categorize this Instagram reel into 2-5 tags.\n"
        f"Preferred tags: {tag_list}. Reuse these when they fit.\n"
        f"Only create a new tag if none of the above apply.\n"
        f"Keep tags short (1-2 words), lowercase, no spaces (use hyphens).\n\n"
        f"Creator: @{creator}\n"
        f"Caption: {caption}\n\n"
        f"Return ONLY a JSON array of lowercase strings, e.g. [\"recipe\", \"italian\"]."
    )


async def _call_openai(prompt: str, api_key: str) -> list[str]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _parse_tags(content)


async def _call_anthropic(prompt: str, api_key: str) -> list[str]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
        return _parse_tags(content)


async def auto_tag_reel(
    caption: str,
    creator: str,
    provider: str,
    api_key: str,
    default_tags: list[str],
) -> list[str] | None:
    prompt = _build_prompt(caption or "", creator or "unknown", default_tags)

    try:
        if provider == "anthropic":
            tags = await _call_anthropic(prompt, api_key)
        else:
            tags = await _call_openai(prompt, api_key)

        # Normalize: lowercase, strip whitespace, replace spaces with hyphens
        return [t.lower().strip().replace(" ", "-") for t in tags if t.strip()]
    except Exception as e:
        logger.warning(f"Auto-tagging failed: {e}")
        return None
