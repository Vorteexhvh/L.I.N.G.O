from datetime import date
from pathlib import Path

import pytest

from jarvis_dev.data import DataStore


def test_streak_is_consecutive_and_does_not_double_count(tmp_path):
    store = DataStore(tmp_path)
    assert store.record_daily_use(date(2026, 10, 28))["current"] == 1
    assert store.record_daily_use(date(2026, 10, 28))["days_used"] == 1
    assert store.record_daily_use(date(2026, 10, 29))["current"] == 2
    assert store.record_daily_use(date(2026, 11, 1))["current"] == 1
    assert store.record_daily_use(date(2026, 11, 1))["best"] == 2
    again = DataStore(tmp_path)
    assert again.data["activity"]["best"] == 2
    assert again.data["activity"]["days_used"] == 3


def test_history_persists_and_is_separated_by_conversation(tmp_path):
    store = DataStore(tmp_path)
    first = store.new_chat()
    second = store.new_chat()
    store.add_message(first["id"], "user", "Olá! Vamos praticar inglês?")
    store.add_message(first["id"], "assistant", "Claro!")
    store.add_message(second["id"], "user", "Como digo bom dia?")
    restored = DataStore(tmp_path)
    assert restored.get(first["id"])["title"] == "Olá! Vamos praticar inglês?"
    assert len(restored.get(first["id"])["messages"]) == 2
    assert len(restored.get(second["id"])["messages"]) == 1


def test_media_is_copied_into_local_storage_and_removed_with_chat(tmp_path):
    source = tmp_path / "sample.png"
    source.write_bytes(b"fake png data")
    store = DataStore(tmp_path / "local")
    item = store.add_media(source)
    copy = Path(item["path"])
    assert copy.exists() and copy.read_bytes() == source.read_bytes()
    assert item["kind"] == "image"
    chat = store.new_chat()
    store.add_message(chat["id"], "user", "", [item])
    assert DataStore(tmp_path / "local").get(chat["id"])["messages"][0]["attachments"][0]["name"] == "sample.png"
    store.remove_chat(chat["id"])
    assert source.exists() and not copy.exists()


def test_media_import_rejects_unsupported_formats_and_empty_files(tmp_path):
    store = DataStore(tmp_path / "local")
    script = tmp_path / "malware.exe"
    script.write_bytes(b"hello")
    with pytest.raises(ValueError, match="Formato não suportado"):
        store.add_media(script)
    empty_audio = tmp_path / "empty.mp3"
    empty_audio.touch()
    with pytest.raises(ValueError, match="vazio"):
        store.add_media(empty_audio)


def test_delete_media_never_deletes_an_external_file(tmp_path):
    store = DataStore(tmp_path / "local")
    external = tmp_path / "keep.mp4"
    external.write_bytes(b"x")
    store.remove_media(str(external))
    assert external.exists()


def test_export_conversation_includes_messages_and_attachment_names(tmp_path):
    store = DataStore(tmp_path / "local")
    chat = store.new_chat()
    store.add_message(chat["id"], "user", "Olá", [{"name": "foto.png", "kind": "image"}])
    store.add_message(chat["id"], "assistant", "Oi!")
    target = tmp_path / "conversa.txt"
    assert store.export_chat_text(chat["id"], target) == target
    exported = target.read_text(encoding="utf-8")
    assert "Você\nOlá\nAnexo (image): foto.png" in exported
    assert "L.I.N.G.O.\nOi!" in exported
