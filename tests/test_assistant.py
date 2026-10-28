import base64
from copy import deepcopy

import pytest

from jarvis_dev.ai import JarvisAssistant
from jarvis_dev.ai import AssistantError, MODEL
from jarvis_dev.data import DataStore
from jarvis_dev.projects import ProjectService


def test_tool_call_result_is_returned_to_model(tmp_path):
    assistant = JarvisAssistant(ProjectService(tmp_path), api_key="test-only")
    calls = []
    replies = [
        {"role": "model", "parts": [{"functionCall": {"id": "call_1", "name": "list_projects", "args": {}},
                                     "thoughtSignature": "opaque-google-signature"}]},
        {"role": "model", "parts": [{"text": "Não há projetos nesta pasta."}]},
    ]

    def fake_completion(messages):
        calls.append(deepcopy(messages))
        return replies.pop(0)

    assistant._completion = fake_completion
    result = assistant.respond("Liste os projetos", lambda _: None)
    assert result["actions"][0]["tool"] == "list_projects"
    assert result["answer"] == "Não há projetos nesta pasta."
    assert calls[1][-2]["parts"][0]["thoughtSignature"] == "opaque-google-signature"
    result_part = calls[1][-1]["parts"][0]["functionResponse"]
    assert result_part["id"] == "call_1"
    assert result_part["name"] == "list_projects"
    assert result_part["response"]["projects"] == []


def test_no_action_is_never_reported_as_completed(tmp_path):
    assistant = JarvisAssistant(ProjectService(tmp_path), api_key="test-only")
    assistant._completion = lambda messages: {"parts": [{"text": "Projeto criado com sucesso!"}]}
    result = assistant.respond("Crie um projeto chamado teste", lambda _: None)
    assert result["actions"] == []
    assert result["answer"].startswith("Nenhuma operação foi executada")


def test_gemini_receives_media_and_keeps_it_in_conversation_context(tmp_path):
    store = DataStore(tmp_path / "local")
    image = tmp_path / "photo.png"
    audio = tmp_path / "voice.wav"
    image.write_bytes(b"image bytes")
    audio.write_bytes(b"audio bytes")
    attachments = [store.add_media(image), store.add_media(audio)]
    assistant = JarvisAssistant(ProjectService(tmp_path), api_key="test-only", media_dir=store.media_dir)
    seen = []

    def complete(messages):
        seen.append(deepcopy(messages))
        return {"parts": [{"text": "Entendi os anexos."}]}

    assistant._completion = complete
    assert MODEL.startswith("gemini-")
    assistant.respond("Descreva", lambda _: None, attachments)
    parts = seen[0][-1]["parts"]
    assert parts[0]["text"] == "Descreva"
    assert parts[2]["inlineData"] == {"mimeType": "image/png", "data": base64.b64encode(b"image bytes").decode()}
    assert parts[4]["inlineData"] == {"mimeType": "audio/wav", "data": base64.b64encode(b"audio bytes").decode()}
    assistant.respond("E o áudio?", lambda _: None)
    assert seen[1][0]["parts"][2]["inlineData"]["mimeType"] == "image/png"


def test_media_context_rejects_files_outside_local_store(tmp_path):
    assistant = JarvisAssistant(ProjectService(tmp_path), api_key="test-only", media_dir=tmp_path / "media")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"private")
    with pytest.raises(AssistantError, match="fora do armazenamento"):
        assistant.respond("Olhe", lambda _: None, [{"name": "outside.png", "kind": "image", "path": str(outside)}])
