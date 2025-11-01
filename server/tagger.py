import json
import logging

import httpx

logger = logging.getLogger(__name__)


def _build_prompt(caption: str, creator: str, default_tags: list[str]) -> str:
    tag_list = ", ".join(default_tags) if default_tags else (
        "funny, recipe, travel, fitness, tech, music, fashion, motivation, education"
    )
    return (
        f"Categorize this Instagram reel into 2-5 tags.\n"
        f"Suggested tags: {tag_list}. You may create new relevant ones.\n"
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
        return json.loads(content)


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
        return json.loads(content)


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
            return await _call_anthropic(prompt, api_key)
        else:
            return await _call_openai(prompt, api_key)
    except Exception as e:
        logger.warning(f"Auto-tagging failed: {e}")
        return None
