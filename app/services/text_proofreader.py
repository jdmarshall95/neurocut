from __future__ import annotations

import logging
import re

from google.genai import types
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.llm import GeminiClientError, create_gemini_client
from app.services.proofreader_silero import SileroProofreader, silero_te_is_available

logger = logging.getLogger(__name__)

# Punctuation that proofreading re-inserts; stripped from the input first so
# repeated runs stay idempotent (no compounding ".....", ",,", etc.).
_RESET_PUNCT = re.compile(r"[.,!?;:…]+")
_MULTISPACE = re.compile(r"\s+")


def _normalize_input(text: str) -> str:
    """Drop existing sentence punctuation so re-proofreading is stable."""
    cleaned = _RESET_PUNCT.sub(" ", text)
    return _MULTISPACE.sub(" ", cleaned).strip()


class ProofreadError(Exception):
    """Raised when the proofreading request fails."""


class ProofreadResult(BaseModel):
    lines: list[str]


_SYSTEM_INSTRUCTION = (
    "You are a subtitle proofreader. You receive a numbered list of subtitle lines.\n"
    "Task: fix ONLY spelling, punctuation, and capitalization.\n"
    "Strict rules:\n"
    "- Return EXACTLY the same number of lines you received, in the same order.\n"
    "- Do NOT merge, split, add, or remove lines.\n"
    "- Do NOT translate or change the language. Preserve meaning and wording.\n"
    "- Do not wrap text in quotes, dashes, or markdown.\n"
    "- If a line is already correct, return it unchanged.\n"
    'Return strict JSON {"lines": ["...", "..."]} with the same line count.'
)


class TextProofreader:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _build_prompt(self, texts: list[str], language: str | None) -> str:
        numbered = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(texts))
        lang = f"Text language: {language}.\n" if language else ""
        return (
            f"{lang}"
            f"Proofread the {len(texts)} subtitle line(s) below and return JSON with "
            f'a "lines" field of exactly {len(texts)} items in the same order:\n\n'
            f"{numbered}"
        )

    def _resolve_engine(self) -> str:
        pref = (self.settings.proofread_engine or "silero").lower()
        has_gemini = bool(self.settings.gemini_api_key)
        if pref == "none":
            raise ProofreadError(
                "Proofreading is disabled (PROOFREAD_ENGINE=none)."
            )
        if pref == "gemini":
            if not has_gemini:
                raise ProofreadError("GEMINI_API_KEY is not set for text proofreading.")
            return "gemini"
        # "silero" or "auto" (or unknown): prefer local, fall back to Gemini.
        if silero_te_is_available():
            return "silero"
        if has_gemini:
            logger.info("[proofread] torch unavailable, falling back to Gemini")
            return "gemini"
        raise ProofreadError(
            "Local proofreading requires the 'torch' package (Silero TE). "
            "Install it (requirements-silero.txt) or set GEMINI_API_KEY."
        )

    def proofread(self, texts: list[str], *, language: str | None = None) -> list[str]:
        if not texts:
            return []
        engine = self._resolve_engine()
        # Reset punctuation first so repeated checks don't pile up "..." / ",,".
        normalized = [_normalize_input(t) for t in texts]
        if engine == "silero":
            try:
                corrected = SileroProofreader(self.settings).proofread(
                    normalized, language=language
                )
            except ProofreadError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ProofreadError(
                    f"Local proofreading (Silero) failed: {exc}"
                ) from exc
        else:
            corrected = self._proofread_gemini(normalized, language)
        # Keep the original line if it was punctuation-only (normalized empty).
        return [
            out if norm else original
            for out, norm, original in zip(corrected, normalized, texts)
        ]

    def _proofread_gemini(self, texts: list[str], language: str | None) -> list[str]:
        try:
            client = create_gemini_client(self.settings)
        except GeminiClientError as exc:
            raise ProofreadError(str(exc)) from exc

        prompt = self._build_prompt(texts, language)
        models = self.settings.resolved_gemini_models
        errors: list[str] = []

        for model in models:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        system_instruction=_SYSTEM_INSTRUCTION,
                        response_mime_type="application/json",
                        response_schema=ProofreadResult,
                        temperature=0.1,
                    ),
                )
                result = self._parse(response)
                if len(result.lines) != len(texts):
                    raise ProofreadError(
                        "Model returned a different number of lines "
                        f"({len(result.lines)} instead of {len(texts)})."
                    )
                logger.info(
                    "[proofread] model=%s corrected %d lines", model, len(texts)
                )
                return [line.strip() for line in result.lines]
            except Exception as exc:  # noqa: BLE001 - try next model
                errors.append(f"{model}: {exc}")
                logger.warning("[proofread] model=%s failed: %s", model, exc)
                continue

        raise ProofreadError(
            "Proofreading failed. " + " | ".join(errors)
        )

    @staticmethod
    def _parse(response: types.GenerateContentResponse) -> ProofreadResult:
        if response.parsed is not None:
            if isinstance(response.parsed, ProofreadResult):
                return response.parsed
            return ProofreadResult.model_validate(response.parsed)
        raw = (response.text or "").strip()
        if not raw:
            raise ProofreadError("Empty model response.")
        return ProofreadResult.model_validate_json(raw)
