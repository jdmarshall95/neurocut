from __future__ import annotations

import logging

import requests

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class DeepSeekClientError(Exception):
    """Raised when DeepSeek API call fails."""


def chat_completion_json(
    *,
    system: str,
    user: str,
    settings: Settings | None = None,
    model: str | None = None,
    temperature: float | None = None,
    timeout_sec: float = 180.0,
) -> str:
    """Call DeepSeek chat completions API (OpenAI-compatible) and return JSON text."""
    app_settings = settings or get_settings()
    api_key = app_settings.deepseek_api_key.strip()
    if not api_key:
        raise DeepSeekClientError(
            "DEEPSEEK_API_KEY is not configured. Add it to your .env file."
        )

    url = f"{app_settings.deepseek_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model or app_settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": (
            app_settings.deepseek_temperature
            if temperature is None
            else temperature
        ),
    }

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout_sec,
        )
    except requests.RequestException as exc:
        raise DeepSeekClientError(f"DeepSeek request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()[:500]
        raise DeepSeekClientError(
            f"DeepSeek API error {response.status_code}: {detail or response.reason}"
        )

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise DeepSeekClientError(
            f"Unexpected DeepSeek response format: {response.text[:500]}"
        ) from exc

    text = (content or "").strip()
    if not text:
        raise DeepSeekClientError("DeepSeek returned an empty response.")
    return text
