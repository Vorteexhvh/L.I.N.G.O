import base64
import json

import httpx
import pytest

from jarvis_dev.gemini import GeminiClient, GeminiError, response_text
from jarvis_dev import speech
from jarvis_dev import gemini


def test_uses_official_google_endpoint_auth_and_native_payload():
    def handle(request):
        assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
        assert request.headers["x-goog-api-key"] == "google-test-key"
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body["contents"] == [{"role": "user", "parts": [{"text": "Oi"}]}]
        assert body["systemInstruction"]["parts"] == [{"text": "Responda em português"}]
        assert body["tools"][0]["functionDeclarations"][0]["name"] == "list_projects"
        assert "messages" not in body and "model" not in body
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": "Olá!"}]}}]})

    client = GeminiClient("google-test-key", "gemini-3.8-flash", transport=httpx.MockTransport(handle))
    result = client.generate([{"role": "user", "parts": [{"text": "Oi"}]}],
                             system="Responda em português", tools=[{"name": "list_projects"}])
    assert response_text(result) == "Olá!"


def test_openrouter_key_is_not_used_as_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "unrelated-key")
    with pytest.raises(GeminiError, match="GEMINI_API_KEY ausente"):
        GeminiClient().generate([{"role": "user", "parts": [{"text": "Oi"}]}])


@pytest.mark.parametrize("status,details,expected", [
    (400, [{"reason": "API_KEY_INVALID"}], "Chave do Gemini inválida"),
    (403, [], "sem permissão"),
    (429, [], "Limite de uso"),
])
def test_provider_errors_have_actionable_messages_without_credentials(status, details, expected):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"details": details}})
    transport = httpx.MockTransport(handle)
    client = GeminiClient("private-test-key", transport=transport)
    with pytest.raises(GeminiError, match=expected) as error:
        client.generate([{"role": "user", "parts": [{"text": "Oi"}]}])
    assert "private-test-key" not in str(error.value)
    assert len(requests) == 1


def test_transient_503_recovers_without_changing_model_or_replaying_tools(monkeypatch):
    attempts = []
    delays = []
    monkeypatch.setattr(gemini.time, "sleep", delays.append)
    def handle(request):
        attempts.append(request)
        if len(attempts) < 3:
            return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Olá!"}]}}]})
    client = GeminiClient("test-key", "gemini-3.8-flash", transport=httpx.MockTransport(handle))
    result = client.generate([{"role": "user", "parts": [{"text": "Oi"}]}])
    assert response_text(result) == "Olá!"
    assert len(attempts) == 3
    assert len({str(request.url) for request in attempts}) == 1
    assert len({request.content for request in attempts}) == 1
    assert 1 <= delays[0] <= 1.25 and 2 <= delays[1] <= 2.25


def test_transient_failure_stops_after_three_attempts(monkeypatch):
    requests = []
    monkeypatch.setattr(gemini.time, "sleep", lambda seconds: None)
    def handle(request):
        requests.append(request)
        return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})
    client = GeminiClient("test-key", transport=httpx.MockTransport(handle))
    with pytest.raises(GeminiError, match="após 3 tentativas"):
        client.generate([{"role": "user", "parts": [{"text": "Oi"}]}])
    assert len(requests) == 3


def test_microphone_transcription_uses_gemini_native_audio(monkeypatch):
    def handle(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        body = json.loads(request.content)
        assert body["contents"][0]["parts"][1]["inlineData"] == {
            "mimeType": "audio/wav", "data": base64.b64encode(b"wav-bytes").decode()}
        assert "tools" not in body
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Bom dia"}]}}]})

    client = GeminiClient("google-test-key", transport=httpx.MockTransport(handle))
    monkeypatch.setattr(speech, "GeminiClient", lambda **kwargs: client)
    assert speech.transcribe_wav(b"wav-bytes", "google-test-key") == "Bom dia"
