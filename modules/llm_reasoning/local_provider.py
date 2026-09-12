"""Local LLM provider via Ollama-compatible HTTP API."""

from __future__ import annotations

import json
from urllib import request

from modules.llm_reasoning.base import LLMProvider


class LocalProvider(LLMProvider):
    """Call local model endpoints (e.g., Ollama /api/generate)."""

    def __init__(self, base_url: str, model: str) -> None:
        self._url = f"{base_url.rstrip('/')}/api/generate"
        self._model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self._model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        body = json.dumps(payload).encode("utf-8")

        req = request.Request(
            self._url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            response_text = data.get("response")
            if not response_text:
                raise RuntimeError("Local LLM returned an empty response")
            return response_text
