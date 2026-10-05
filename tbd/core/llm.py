"""Anbindung an die lokale Ollama-API.

Es wird ``/api/chat`` mit "Structured Outputs" genutzt: Ollama bekommt ein
JSON-Schema und garantiert, dass die Antwort diesem Schema entspricht.
"""

from __future__ import annotations

import json
import logging

import requests

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, url: str, model: str, temperature: float = 0.0, num_ctx: int = 16384,
                 timeout: int = 600, think: bool | None = None):
        self.url = url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.think = think

    @classmethod
    def from_config(cls, config) -> "OllamaClient":
        return cls(config.ollama_url, config.model, config.temperature, config.num_ctx,
                   config.timeout, config.think)

    def check(self) -> None:
        """Prüft vorab, ob Ollama erreichbar und das Modell installiert ist."""
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=10)
            response.raise_for_status()
        except requests.RequestException as err:
            raise LLMError(f"Ollama ist unter {self.url} nicht erreichbar ({err}).\n"
                           f"Läuft 'ollama serve'? Andere Adresse mit --ollama-url angeben.") from err
        installed = {m.get("name", "") for m in response.json().get("models", [])}
        wanted = {self.model, f"{self.model}:latest"}
        if not installed & wanted:
            raise LLMError(f"Modell '{self.model}' ist nicht installiert. Abhilfe: ollama pull {self.model}")

    def chat_json(self, system: str, user: str, schema: dict) -> dict:
        """Schickt eine Anfrage und gibt die Antwort als dict zurück (passend zum Schema)."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": False,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        if self.think is not None:
            payload["think"] = self.think
        try:
            response = requests.post(f"{self.url}/api/chat", json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as err:
            raise LLMError(f"Anfrage an Ollama fehlgeschlagen: {err}") from err
        content = response.json().get("message", {}).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as err:
            raise LLMError(f"Antwort ist kein gültiges JSON: {content[:200]!r}") from err
