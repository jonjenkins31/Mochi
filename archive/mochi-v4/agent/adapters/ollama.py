"""Thin wrapper around the Ollama HTTP API."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from .base import ChatTurn


@dataclass
class OllamaClient:
    base_url: str
    model: str
    timeout: float = 30.0
    logger: logging.Logger | None = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    def set_model(self, model: str) -> None:
        self.model = model

    def set_base_url(self, url: str) -> None:
        self.base_url = url.rstrip("/")

    # ------------------------------------------------------------------ API calls
    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        stream: bool = False,
    ) -> str | None:
        """
        Submit a chat completion request to the local Ollama server.

        Returns the assistant's reply as a string, or None on error.
        """
        payload = {
            "model": self.model,
            "stream": stream,
            "messages": [],
        }

        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        payload["messages"].append({"role": "user", "content": prompt})

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.URLError as exc:
            if self.logger:
                self.logger.error("Ollama connection failed: %s", exc)
            return None
        except Exception as exc:  # pragma: no cover - defensive
            if self.logger:
                self.logger.error("Unexpected error contacting Ollama: %s", exc, exc_info=True)
            return None

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:
            if self.logger:
                self.logger.error("Failed to decode Ollama response: %s", exc)
            return None

        message = payload.get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        response_text = payload.get("response")
        if isinstance(response_text, str) and response_text.strip():
            return response_text.strip()

        return None


@dataclass
class OllamaAdapter:
    base_url: str
    model: str
    timeout: float = 30.0
    logger: logging.Logger | None = None

    name: str = "ollama"

    def __post_init__(self) -> None:
        self.client = OllamaClient(
            base_url=self.base_url,
            model=self.model,
            timeout=self.timeout,
            logger=self.logger,
        )

    def complete(self, *, prompt: str, history: list[ChatTurn]) -> str | None:
        last = history[-1].text if history else ""
        return self.client.generate(last, system_prompt=prompt or None)

    def set_model(self, model: str) -> None:
        self.model = model
        self.client.set_model(model)
