from functools import lru_cache

from google import genai

from app.core.config import Settings, get_settings


class GeminiClientError(Exception):
    """Raised when Gemini client cannot be initialized."""


@lru_cache
def get_gemini_client(api_key: str) -> genai.Client:
    if not api_key:
        raise GeminiClientError(
            "GEMINI_API_KEY is not configured. Add it to your .env file."
        )
    return genai.Client(api_key=api_key)


def create_gemini_client(settings: Settings | None = None) -> genai.Client:
    app_settings = settings or get_settings()
    return get_gemini_client(app_settings.gemini_api_key)
