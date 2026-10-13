from __future__ import annotations

import importlib.util
import logging
from functools import lru_cache

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

SILERO_MODELS_REPO = "snakers4/silero-models"

# Languages supported by the Silero text-enhancement (te) model.
SILERO_TE_LANGUAGES = frozenset({"ru", "en", "de", "es"})


def silero_te_is_available() -> bool:
    """True when torch is importable (Silero TE is pulled via torch.hub)."""
    return importlib.util.find_spec("torch") is not None


@lru_cache
def _load_silero_te():
    import torch

    logger.info("Loading Silero text-enhancement (te) model")
    model, example_texts, languages, punct, apply_te = torch.hub.load(
        repo_or_dir=SILERO_MODELS_REPO,
        model="silero_te",
        trust_repo=True,
    )
    return apply_te, set(languages)


class SileroProofreader:
    """Local punctuation + capitalization restoration via Silero TE.

    Silero TE fixes punctuation and casing (the parts STT output lacks); it is
    not a spell corrector. It runs offline on CPU with no API cost.
    """

    engine_name = "silero"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _resolve_language(self, language: str | None) -> str:
        candidate = (language or self.settings.proofread_language or "en").lower()
        if candidate not in SILERO_TE_LANGUAGES:
            return "ru" if "ru" in SILERO_TE_LANGUAGES else "en"
        return candidate

    def proofread(self, texts: list[str], *, language: str | None = None) -> list[str]:
        if not texts:
            return []

        apply_te, supported = _load_silero_te()
        lang = self._resolve_language(language)
        if lang not in supported:
            lang = "ru" if "ru" in supported else next(iter(supported))

        result: list[str] = []
        for text in texts:
            stripped = text.strip()
            if not stripped:
                result.append(text)
                continue
            try:
                enhanced = apply_te(stripped.lower(), lan=lang)
            except Exception as exc:  # noqa: BLE001 - keep original on failure
                logger.warning("[proofread] silero te failed on a line: %s", exc)
                enhanced = stripped
            result.append(enhanced.strip() or stripped)

        logger.info("[proofread] silero te processed %d lines (lang=%s)", len(texts), lang)
        return result
