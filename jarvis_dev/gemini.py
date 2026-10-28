"""Small REST client for Google's official Gemini API."""
from __future__ import annotations

import os
import random
import re
import time

import httpx


API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "gemini-3.5-flash"
MAX_ATTEMPTS = 3
TRANSIENT_STATUSES = {500, 502, 503, 504}


class GeminiError(Exception):
    pass


def response_text(content: dict) -> str:
    return "\n".join(str(part["text"]) for part in content.get("parts", [])
                     if isinstance(part, dict) and part.get("text") and not part.get("thought")).strip()


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, *, transport=None):
        self.api_key = (api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        self.model = (model if model is not None else os.getenv("GEMINI_MODEL", MODEL)).strip() or MODEL
        self.transport = transport

    def _request(self, payload: dict) -> httpx.Response:
        # Only the inference request is retried; local project tools run outside this method.
        with httpx.Client(timeout=httpx.Timeout(90.0, connect=10.0), transport=self.transport) as client:
            for attempt in range(MAX_ATTEMPTS):
                response = client.post(f"{API_ROOT}/models/{self.model}:generateContent", json=payload,
                                       headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
                if response.status_code not in TRANSIENT_STATUSES or attempt == MAX_ATTEMPTS - 1:
                    return response
                time.sleep(2**attempt + random.uniform(0, 0.25))

    def generate(self, contents: list[dict], *, system: str = "", tools: list[dict] | None = None) -> dict:
        if not self.api_key or self.api_key == "cole_sua_chave_aqui":
            raise GeminiError("GEMINI_API_KEY ausente. Configure uma chave do Google AI Studio no arquivo .env.")
        if not re.fullmatch(r"gemini-[a-zA-Z0-9.-]+", self.model):
            raise GeminiError("GEMINI_MODEL inválido. Use um identificador como gemini-3.5-flash.")
        payload = {"contents": contents, "generationConfig": {"maxOutputTokens": 4096}}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            payload["tools"] = [{"functionDeclarations": tools}]
            payload["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        try:
            response = self._request(payload)
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates")
            if not candidates:
                raise GeminiError("O Gemini não retornou conteúdo. A solicitação pode ter sido bloqueada; reformule o pedido.")
            content = candidates[0].get("content")
            if not isinstance(content, dict) or not isinstance(content.get("parts"), list) or not content["parts"]:
                raise GeminiError("O Gemini não retornou uma resposta utilizável. Tente novamente.")
            return content
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise GeminiError("Chave do Gemini inválida ou sem permissão. Confira GEMINI_API_KEY no arquivo .env.") from exc
            if status == 400:
                # Invalid API keys are also reported as INVALID_ARGUMENT by Google.
                try:
                    details = exc.response.json().get("error", {}).get("details", [])
                except (ValueError, AttributeError):
                    details = []
                if any(isinstance(item, dict) and item.get("reason") == "API_KEY_INVALID" for item in details):
                    raise GeminiError("Chave do Gemini inválida. Confira GEMINI_API_KEY no arquivo .env.") from exc
                raise GeminiError("Gemini retornou HTTP 400. Verifique o modelo e o formato/tamanho dos anexos.") from exc
            if status == 404:
                raise GeminiError("Modelo Gemini não encontrado ou indisponível. Confira GEMINI_MODEL no arquivo .env.") from exc
            if status == 429:
                raise GeminiError("Limite de uso do Gemini atingido. Confira a cota da sua conta e tente novamente mais tarde.") from exc
            if status in TRANSIENT_STATUSES:
                raise GeminiError(f"Gemini temporariamente indisponível (HTTP {status}), mesmo após {MAX_ATTEMPTS} tentativas. Tente novamente em instantes.") from exc
            raise GeminiError(f"Gemini retornou HTTP {status}. Tente novamente mais tarde.") from exc
        except (httpx.RequestError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            # Keep request URLs, credentials and provider response bodies out of UI logs.
            raise GeminiError("Falha de conexão ou resposta inválida da API do Gemini. Tente novamente.") from exc
