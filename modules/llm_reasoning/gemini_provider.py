"""Gemini-backed LLM provider."""

from __future__ import annotations

from modules.llm_reasoning.base import LLMProvider


class GeminiProvider(LLMProvider):
    """Google Gemini provider implementation."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is missing")

        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("google-genai package is not installed") from exc

        self.client = genai.Client(api_key=api_key)
        self._model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        from google.genai import types

        # Ask for strict JSON output to match downstream validation parsing.
        composed_prompt = (
            f"System instructions:\n{system_prompt}\n\n"
            f"User input:\n{user_prompt}\n\n"
            "Return only a JSON object."
        )

        response = self.client.models.generate_content(
            model=self._model,
            contents=composed_prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
        )

        content = getattr(response, "text", None)
        if content:
            return content

        raise RuntimeError("Gemini returned an empty response")
